#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直播源探测：可用性 / 分辨率 / 帧率 / 码率 / 速度 / CORS 支持。

原项目依赖 ffprobe + ffmpeg 命令行，未安装即完全不可用。这里改成纯 Python 实现：
  1. 优先读 m3u8 主播放列表里的 RESOLUTION 属性；
  2. 否则抓取首个 TS 分片，解析 H.264 SPS 里的 pic_width/pic_height（含裁剪修正）；
  3. 同时用一个采样窗口算实际下载速度，并记录是否放行 CORS，供网页播放器判断。
"""
from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse

import requests
import urllib3

urllib3.disable_warnings()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ------------------------------------------------------------------ H.264 SPS


class _Bits:
    """按位读取器（含 Exp-Golomb）。"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0  # 比特位置

    def u(self, n: int) -> int:
        v = 0
        for _ in range(n):
            byte = self.pos >> 3
            if byte >= len(self.data):
                raise EOFError
            bit = (self.data[byte] >> (7 - (self.pos & 7))) & 1
            v = (v << 1) | bit
            self.pos += 1
        return v

    def skip(self, n: int) -> None:
        self.pos += n

    def ue(self) -> int:
        zeros = 0
        while self.u(1) == 0:
            zeros += 1
            if zeros > 32:
                raise EOFError
        return (1 << zeros) - 1 + (self.u(zeros) if zeros else 0)

    def se(self) -> int:
        v = self.ue()
        return -(v // 2) if v % 2 == 0 else (v + 1) // 2


def _unescape(data: bytes) -> bytes:
    """去掉 H.264 的防竞争字节 00 00 03 -> 00 00。"""
    out = bytearray()
    zeros = 0
    for b in data:
        if zeros >= 2 and b == 3:
            zeros = 0
            continue
        out.append(b)
        zeros = zeros + 1 if b == 0 else 0
    return bytes(out)


def parse_h264_sps(nal: bytes) -> tuple[int, int] | None:
    """输入以 0x67 开头的 SPS NAL（含头字节），返回 (宽, 高)。"""
    if not nal or (nal[0] & 0x1F) != 7:
        return None
    r = _Bits(_unescape(nal[1:]))
    try:
        profile_idc = r.u(8)
        r.u(8)  # constraint flags
        r.u(8)  # level_idc
        r.ue()  # sps_id

        chroma_format_idc = 1
        if profile_idc in (100, 110, 122, 244, 44, 83, 86, 118, 128, 138, 139, 134, 135):
            chroma_format_idc = r.ue()
            if chroma_format_idc == 3:
                r.u(1)  # separate_colour_plane_flag
            r.ue()  # bit_depth_luma_minus8
            r.ue()  # bit_depth_chroma_minus8
            r.u(1)  # qpprime_y_zero_transform_bypass_flag
            if r.u(1):  # seq_scaling_matrix_present_flag
                count = 8 + (2 if chroma_format_idc == 3 else 0)
                for i in range(count):
                    if r.u(1):  # seq_scaling_list_present_flag
                        size = 16 if i < 6 else 64
                        last, nxt = 8, 8
                        for _ in range(size):
                            if nxt != 0:
                                delta = r.se()
                                nxt = (last + delta + 256) % 256
                            last = nxt if nxt != 0 else last

        r.ue()  # log2_max_frame_num_minus4
        poc_type = r.ue()
        if poc_type == 0:
            r.ue()
        elif poc_type == 1:
            r.u(1)
            r.se()
            r.se()
            for _ in range(r.ue()):
                r.se()

        r.ue()  # max_num_ref_frames
        r.u(1)  # gaps_in_frame_num_value_allowed_flag
        width_mbs = r.ue() + 1
        height_map_units = r.ue() + 1
        frame_mbs_only = r.u(1)
        if not frame_mbs_only:
            r.u(1)  # mb_adaptive_frame_field_flag
        r.u(1)  # direct_8x8_inference_flag

        width = width_mbs * 16
        height = (2 - frame_mbs_only) * height_map_units * 16

        if r.u(1):  # frame_cropping_flag
            left, right, top, bottom = r.ue(), r.ue(), r.ue(), r.ue()
            sub_w = 2 if chroma_format_idc in (1, 2) else 1
            sub_h = 2 if chroma_format_idc == 1 else 1
            width -= (left + right) * sub_w
            height -= (top + bottom) * sub_h * (2 - frame_mbs_only)

        if 0 < width <= 8192 and 0 < height <= 8192:
            return width, height
    except (EOFError, IndexError, ValueError):
        return None
    return None


SPS_PATTERNS = (b"\x00\x00\x00\x01\x67", b"\x00\x00\x01\x67")
PPS_PATTERN = b"\x00\x00\x00\x01\x68"


def sniff_ts_resolution(blob: bytes) -> tuple[int, int] | None:
    """在 TS/ES 码流里找 SPS 并解析分辨率。"""
    best = None
    for pat in SPS_PATTERNS:
        start = 0
        while True:
            idx = blob.find(pat, start)
            if idx < 0:
                break
            nal = blob[idx + len(pat) - 1: idx + len(pat) - 1 + 96]
            # 截断到下一个 NAL 起始码，避免读到脏数据
            nxt = nal.find(b"\x00\x00\x00\x01", 1)
            if nxt > 0:
                nal = nal[:nxt]
            res = parse_h264_sps(nal)
            if res:
                # 同一码流可能有多个 SPS（不同码率），取面积最大的
                if best is None or res[0] * res[1] > best[0] * best[1]:
                    best = res
            start = idx + 4
    return best


# ------------------------------------------------------------------ 结构定义


@dataclass
class ProbeResult:
    url: str
    ok: bool = False
    width: int = 0
    height: int = 0
    fps: float = 0.0
    speed_kbps: int = 0
    latency_ms: int = 0
    cors: bool = False
    content_type: str = ""
    error: str = ""
    checked_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


RESOLUTION_RE = re.compile(r"RESOLUTION=(\d{2,5})x(\d{2,5})")
FRAME_RATE_RE = re.compile(r"FRAME-RATE=([\d.]+)")
BANDWIDTH_RE = re.compile(r"BANDWIDTH=(\d+)")


def _cors_ok(resp: requests.Response) -> bool:
    acao = resp.headers.get("Access-Control-Allow-Origin", "")
    return acao == "*" or acao.strip() != ""


def _absolute(base: str, uri: str) -> str:
    if uri.startswith("http"):
        return uri
    return urljoin(base, uri)


def _fetch_text(url: str, headers: dict, connect_timeout: float, read_timeout: float,
                limit: int = 256 * 1024) -> str | None:
    try:
        r = requests.get(url, headers=headers, timeout=(connect_timeout, read_timeout),
                         verify=False, allow_redirects=True)
        if r.status_code not in (200, 206):
            return None
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text[:limit]
    except requests.RequestException:
        return None


def _resolve_segment(url: str, text: str, headers: dict, connect_timeout: float,
                     read_timeout: float, depth: int = 0) -> str | None:
    """从播放列表文本里解析出一个可下载的分片地址。

    主播放列表（含 EXT-X-STREAM-INF）会先下钻到变体列表，最多两层，避免递归过深。
    """
    if depth > 2:
        return None
    if "#EXT-X-STREAM-INF" in text:
        lines = [ln.strip() for ln in text.splitlines()]
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    variant = _absolute(url, nxt)
                    sub = _fetch_text(variant, headers, connect_timeout, read_timeout)
                    if sub:
                        seg = _resolve_segment(variant, sub, headers,
                                               connect_timeout, read_timeout, depth + 1)
                        if seg:
                            return seg
                    break
            break
        return None

    # 媒体列表：第一个非注释行即分片
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return _absolute(url, line)
    return None


def _measure_segment(seg_url: str, headers: dict, connect_timeout: float,
                     read_timeout: float, sample_bytes: int) -> tuple[int, bytes, float]:
    """下载一个分片的头部样本，返回 (字节数, 数据, 耗时秒)。"""
    t0 = time.time()
    buf = bytearray()
    r = requests.get(seg_url, headers=headers, timeout=(connect_timeout, read_timeout),
                     stream=True, verify=False, allow_redirects=True)
    try:
        if r.status_code not in (200, 206):
            return 0, b"", 0.0
        for chunk in r.iter_content(48 * 1024):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) >= sample_bytes:
                break
    finally:
        r.close()
    elapsed = max(time.time() - t0, 0.01)
    return len(buf), bytes(buf), elapsed


def probe(url: str, connect_timeout: float = 6.0, read_timeout: float = 8.0,
          sample_bytes: int = 480 * 1024) -> ProbeResult:
    """探测单个直播源。"""
    res = ProbeResult(url=url, checked_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    t0 = time.time()
    headers = {"User-Agent": UA, "Accept": "*/*"}
    try:
        r = requests.get(
            url,
            headers=headers,
            timeout=(connect_timeout, read_timeout),
            stream=True,
            verify=False,
            allow_redirects=True,
        )
        res.latency_ms = int((time.time() - t0) * 1000)
        if r.status_code not in (200, 206):
            res.error = f"HTTP {r.status_code}"
            r.close()
            return res
        res.cors = _cors_ok(r)
        res.content_type = (r.headers.get("Content-Type") or "").split(";")[0].strip()

        # 读回样本，边读边限长
        buf = bytearray()
        for chunk in r.iter_content(64 * 1024):
            if not chunk:
                continue
            buf.extend(chunk)
            if len(buf) >= sample_bytes:
                break
        r.close()

        body = bytes(buf)
        if not body:
            res.error = "空响应"
            return res

        head = body[:2048].lstrip()
        is_playlist = head.startswith(b"#EXTM3U") or b"#EXTINF" in head[:4096]

        if is_playlist:
            text = body.decode("utf-8", "ignore")
            # 有些站点的播放列表极短但仍是有效的，只要含 EXTM3U 就算可用
            res.ok = True
            m = RESOLUTION_RE.search(text)
            if m:
                res.width, res.height = int(m.group(1)), int(m.group(2))
            mf = FRAME_RATE_RE.search(text)
            if mf:
                res.fps = round(float(mf.group(1)), 2)

            # 抓一个分片，用于测速 + 解析真实分辨率
            seg = _resolve_segment(url, text, headers, connect_timeout, read_timeout)
            if seg:
                try:
                    size, blob, elapsed = _measure_segment(
                        seg, headers, connect_timeout, read_timeout, sample_bytes
                    )
                    if size > 0:
                        res.speed_kbps = int(size / 1024 / elapsed)
                        if not res.width:
                            dim = sniff_ts_resolution(blob)
                            if dim:
                                res.width, res.height = dim
                except requests.RequestException as e:
                    if not res.width:
                        res.error = f"分片读取失败:{type(e).__name__}"
            if res.speed_kbps == 0:
                mb = BANDWIDTH_RE.search(text)
                if mb:
                    res.speed_kbps = int(int(mb.group(1)) / 8 / 1024)
        else:
            # 直连 TS/MP4 等裸流
            res.speed_kbps = int(len(body) / 1024 / max(time.time() - t0, 0.01))
            dim = sniff_ts_resolution(body)
            if dim:
                res.width, res.height = dim
                res.ok = True
            elif res.content_type in ("video/mp2t", "video/mp4", "application/octet-stream"):
                res.ok = True
            else:
                res.error = f"非流媒体内容({res.content_type[:24]})"
        if res.ok and res.fps == 0.0:
            res.fps = 25.0
        return res
    except requests.Timeout:
        res.error = "超时"
    except requests.ConnectionError:
        res.error = "连接失败"
    except requests.RequestException as e:
        res.error = type(e).__name__
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {e}"[:80]
    return res


def host_of(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except ValueError:
        return ""


def is_private_host(host: str) -> bool:
    """判断是否为内网/保留地址（个人网络无法访问）。"""
    if not host:
        return True
    if host in ("localhost", "0.0.0.0"):
        return True
    m = re.fullmatch(r"(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})", host)
    if not m:
        return False
    a, b, c, d = (int(x) for x in m.groups())
    if a == 10:
        return True
    if a == 127:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    if a == 100 and 64 <= b <= 127:  # 运营商 CGNAT
        return True
    if a == 169 and b == 254:
        return True
    if a >= 224:  # 组播/保留
        return True
    return False


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
    out = probe(target)
    print(json.dumps(out.to_dict(), ensure_ascii=False, indent=2))
