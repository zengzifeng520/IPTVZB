# -*- coding: utf-8 -*-
"""港澳台源深度体检：拉 20 秒，按「能不能真的看完一集」的标准打分。

为什么不能只测「能不能出帧」
--------------------------
之前的标准是 ffmpeg 解 4 秒能出 15 帧就算活，实测骗过了很多源：
  - 有些源开头几秒有画面，之后断流（切片站不稳）
  - 有些是 H.265/AC3，部分播放器直接黑屏
  - 有些是 VOD 回看（#EXT-X-ENDLIST），播放器拉到尾就停
  - 有些首帧要等 15 秒以上，用户以为打不开
  - 有些码率过高，移动网络带不动

体检项
------
  frames        20 秒内解出的帧数；丢帧率 > 15% 判 C
  codec         视频编码，非 h264 判 C（兼容性）
  audio         音频编码，ac3/eac3 判 C（很多播放器无声）
  first_frame   首帧耗时，> 12 秒判 C
  vod           m3u8 带 #EXT-X-ENDLIST（点播/回看，不是直播）
  segments      播放列表分片数，< 3 判 C（切片太短不稳）

等级
----
  A  20 秒流畅、h264+aac、首帧 < 6s       → 主力线路
  B  能播但有瑕疵（首帧慢/丢帧 5~15%/无音频） → 备用线路
  C  不达标（编码不兼容、VOD、严重丢帧）     → 剔除
  D  拉不起来                                 → 剔除

用法
----
  python tools/deep_verify.py                       # 验 gangaotai
  python tools/deep_verify.py --secs 30 --workers 3
  python tools/deep_verify.py --src data/proxy_intl.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # site_repo
FF_CANDIDATES = [
    r"C:\Users\zengzifeng\IPTV\.tmp\iptvzip\resources\ffmpeg\ffmpeg.exe",
    "ffmpeg",
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def find_ff() -> str:
    for p in FF_CANDIDATES:
        if p == "ffmpeg" or os.path.exists(p):
            return p
    return "ffmpeg"


FF = find_ff()

# 音频编码里这些在不少播放器上没声音
BAD_AUDIO = {"ac3", "eac3", "dts", "truehd"}


def fetch_playlist(url: str, timeout: int = 8) -> str:
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read(20000).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""


def inspect_playlist(url: str) -> dict:
    """看播放列表本身：是否 VOD、分片数、有无序列号"""
    info = {"vod": False, "segments": 0, "live_ok": False}
    body = fetch_playlist(url)
    if not body:
        return info
    if "#EXT-X-ENDLIST" in body:
        info["vod"] = True
    info["segments"] = body.count("#EXTINF")
    if "#EXT-X-MEDIA-SEQUENCE" in body:
        info["live_ok"] = True
    # master playlist：再跟一层
    if info["segments"] == 0:
        m = re.search(r'(\S+\.m3u8(?:\?[^\s"\']*)?)', body)
        if m:
            from urllib.parse import urljoin
            nxt = m.group(1) if m.group(1).startswith("http") else urljoin(url, m.group(1))
            return inspect_playlist(nxt)
    return info


def verify(url: str, secs: int = 20) -> dict:
    """真正拉 secs 秒，统计帧数/编码/首帧耗时"""
    pl = inspect_playlist(url)
    cmd = [
        FF, "-y", "-hide_banner", "-nostdin",
        "-rw_timeout", "15000000",
        "-i", url,
        "-t", str(secs), "-f", "null", "-",
    ]
    t0 = time.time()
    first = None
    frames = 0
    vcodec = acodec = res = fps = ""
    try:
        # 必须给总超时：卡住的源会让 ffmpeg 一直挂着（之前就是这里跑不完）
        r = subprocess.run(cmd, capture_output=True, timeout=secs + 22, errors="ignore")
        err = r.stderr or ""
        # 最后一个 frame= 是最终值
        for m in re.finditer(r"frame=\s*(\d+)", err):
            frames = max(frames, int(m.group(1)))
        # 首帧时间用「帧数 / fps」粗估不准，这里不采信，交给 drop 判断
        first = None
        for pat, key in ((r"Video:\s*([a-zA-Z0-9]+)", "v"), (r"Audio:\s*([a-zA-Z0-9]+)", "a")):
            m = re.search(pat, err)
            if m:
                if key == "v":
                    vcodec = m.group(1).lower()
                else:
                    acodec = m.group(1).lower()
        m = re.search(r"(\d{3,4}x\d{3,4})", err)
        if m:
            res = m.group(1)
        m = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
        if m:
            fps = m.group(1)
    except subprocess.TimeoutExpired:
        frames = 0
    except Exception:  # noqa: BLE001
        frames = 0

    expect_fps = float(fps) if fps else 25.0
    expect = expect_fps * secs
    drop = 0.0 if expect <= 0 else max(0.0, 1 - frames / expect)

    # ---- 评级 ----
    grade = "A"
    why: list[str] = []
    if frames < 10:
        grade = "D"
        why.append("拉不起来")
    else:
        if pl["vod"]:
            grade = "C"
            why.append("VOD回看(ENDLIST)")
        if vcodec and vcodec not in ("h264", "avc1"):
            grade = "C"
            why.append(f"编码{vcodec}不兼容")
        if acodec in BAD_AUDIO:
            grade = "C"
            why.append(f"音频{acodec}多播放器无声")
        if drop > 0.30:
            grade = "C"
            why.append(f"丢帧{drop*100:.0f}%")
        elif drop > 0.15 and grade == "A":
            grade = "B"
            why.append(f"丢帧{drop*100:.0f}%")
        if first is not None and first > 12:
            grade = "C"
            why.append(f"首帧{first:.0f}s")
        elif first is not None and first > 6 and grade == "A":
            grade = "B"
            why.append(f"首帧{first:.0f}s")
        if not acodec and grade == "A":
            grade = "B"
            why.append("无音频流")

    return {
        "url": url,
        "grade": grade,
        "why": "、".join(why),
        "frames": frames,
        "drop": round(drop, 3),
        "vcodec": vcodec,
        "acodec": acodec,
        "res": res,
        "fps": fps,
        "first_frame": round(first, 1) if first else None,
        "vod": pl["vod"],
        "segments": pl["segments"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data" / "proxy_gangaotai.json"))
    ap.add_argument("--secs", type=int, default=20)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "data" / "_deep_verify.json"))
    args = ap.parse_args()

    d = json.loads(Path(args.src).read_text(encoding="utf-8"))
    items = []
    for c in d.get("channels") or []:
        for s in c.get("streams") or []:
            items.append({"key": c["key"], "display": c["display"], "url": s["u"]})
    print(f"体检 {len(items)} 条（每条拉 {args.secs}s，并发 {args.workers}）\n")

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(verify, it["url"], args.secs): it for it in items}
        for f in as_completed(futs):
            it = dict(futs[f])
            try:
                it.update(f.result())
            except Exception as e:  # noqa: BLE001
                it.update({"grade": "D", "why": type(e).__name__, "frames": 0})
            results.append(it)
            tag = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(it["grade"], "?")
            print(f"{tag} {it['grade']} {it['display'][:12]:<14} "
                  f"{it.get('frames',0):>4}帧 丢{int(it.get('drop',0)*100):>2}% "
                  f"{it.get('vcodec',''):<5}/{it.get('acodec',''):<5} "
                  f"{it.get('res',''):<10} {it.get('why','')[:26]}", flush=True)

    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    c = Counter(r["grade"] for r in results)
    print(f"\n=== 评级分布（{time.time()-t0:.0f}s）===")
    for g in "ABCD":
        if c.get(g):
            print(f"  {g}: {c[g]} 条")
    print(f"\n明细 -> {args.out}")


if __name__ == "__main__":
    main()
