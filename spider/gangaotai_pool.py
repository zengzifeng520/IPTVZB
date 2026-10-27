# -*- coding: utf-8 -*-
"""港澳台直播源采集：大陆可直连的台湾/香港/凤凰/澳门频道。

为什么单独一条线
----------------
港澳台没有组播中转（之前全网调研确认），但有几个大陆可直连的 HLS 源：
  1. 中国移动酒店 IPTV（111.59.139.85:11888，tsfile / key=txiptv）
     有一组「测试频道」，实际是台湾台 + 凤凰 + 澳门莲花
  2. 香港 myTV 服务器（103.172.187.30:12000）——翡翠台/黄金翡翠台/亚洲剧台/美亚电影/创世电视
  3. 台湾各台直连源（TVBS亚洲、原住民、美好生活、华视）
台标通过 ffmpeg 截图逐一识别（见记忆 2026-10-27），频道名硬编码在这里。

数据流
------
  逐条 GET 验活（跟随 master->chunklist 拿 ts 分片即活）
    -> data/proxy_gangaotai.json（与 proxy_hotel.json 同构，subs.py 复用）

用法
----
  python gangaotai_pool.py            # 全量验活（约 20 秒）
  python gangaotai_pool.py --no-probe # 跳过验活，直接生成
"""
from __future__ import annotations

import argparse
import json
import ssl
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import config

OUT_JSON = config.WEB_DATA_DIR / "proxy_gangaotai.json"

# 深度体检报告（tools/deep_verify.py -> tools/merge_verify_report.py）。
# A/B 直接放行，C/D 直接拒绝；超过 7 天视为过期，回退到实时探测。
REPORT_JSON = Path(__file__).parent / "data" / "verify_report.json"
REPORT_MAX_AGE_DAYS = 7
_REPORT: dict | None = None
_REPORT_AT: str = ""

# 频道表：key, display, url, host, region
# 台标已通过 ffmpeg 截图识别（2026-10-27）
CHANNELS: list[tuple[str, str, str, str, str]] = [
    # ---- 移动 tsfile 源（台湾台 + 凤凰 + 澳门莲花）----
    ("TVBS", "TVBS", "http://111.59.139.85:11888/tsfile/live/1201_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("FenghuangWS", "凤凰卫视", "http://111.59.139.85:11888/tsfile/live/1202_1.m3u8?key=txiptv", "111.59.139.85:11888", "凤凰"),
    ("ANIMAX", "ANIMAX", "http://111.59.139.85:11888/tsfile/live/1203_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("DaAi", "大爱", "http://111.59.139.85:11888/tsfile/live/1204_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("FeifanNews", "非凡新闻", "http://111.59.139.85:11888/tsfile/live/1205_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("MacauLotus", "澳门莲花", "http://111.59.139.85:11888/tsfile/live/1206_1.m3u8?key=txiptv", "111.59.139.85:11888", "澳门"),
    ("FTV", "民视", "http://111.59.139.85:11888/tsfile/live/1207_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("VLJapan", "纬来日本台", "http://111.59.139.85:11888/tsfile/live/1208_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("TTV", "台视", "http://111.59.139.85:11888/tsfile/live/1214_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("EBCWest", "东森洋片台", "http://111.59.139.85:11888/tsfile/live/1217_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("FenghuangMovie", "凤凰电影", "http://111.59.139.85:11888/tsfile/live/1218_1.m3u8?key=txiptv", "111.59.139.85:11888", "凤凰"),
    ("SJTV", "信吉卫视", "http://111.59.139.85:11888/tsfile/live/1220_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("CTiNews", "中天新闻", "http://111.59.139.85:11888/tsfile/live/1221_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("PTS3", "公视3台", "http://111.59.139.85:11888/tsfile/live/1222_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    ("PTS", "公视", "http://111.59.139.85:11888/tsfile/live/1223_1.m3u8?key=txiptv", "111.59.139.85:11888", "台湾"),
    # ---- 香港 myTV 服务器（103.172.187.30:12000）----
    # 2026-10-27 枚举 null-1..60（正确格式是 null-{n}/master.m3u8），
    # 9 个能播，逐个 ffmpeg 抓帧 + 截图识别台标，结果如下：
    #   null-1 翡翠台 / null-2,9,10 美亚电影台（三路同源）
    #   null-3 中国电影频道 / null-4 创世电视 / null-8 黄金华剧台
    #   null-11 myTV SUPER(剧集) / null-12 myTV SUPER(综艺)
    # 注意：null-11 / null-12 以前被标成「亚洲剧台」「黄金翡翠台」是错的，
    # 画面右上角台标就是 myTV SUPER，按实测改名。
    ("TVBJade", "翡翠台", "http://103.172.187.30:12000/stream/mytv/null-1/master.m3u8", "103.172.187.30:12000", "香港"),
    ("MyTVSuperDrama", "myTV SUPER剧集", "http://103.172.187.30:12000/stream/mytv/null-11/master.m3u8", "103.172.187.30:12000", "香港"),
    ("MyTVSuperShow", "myTV SUPER综艺", "http://103.172.187.30:12000/stream/mytv/null-12/master.m3u8", "103.172.187.30:12000", "香港"),
    # 美亚电影台：null-2 / null-9 / null-10 是同一频道的三个入口，做多线路
    ("MeiAhMovie", "美亚电影台", "http://103.172.187.30:12000/stream/mytv/null-9/master.m3u8", "103.172.187.30:12000", "香港"),
    ("MeiAhMovie", "美亚电影台", "http://103.172.187.30:12000/stream/mytv/null-2/master.m3u8", "103.172.187.30:12000", "香港"),
    ("MeiAhMovie", "美亚电影台", "http://103.172.187.30:12000/stream/mytv/null-10/master.m3u8", "103.172.187.30:12000", "香港"),
    ("CreationTV", "创世电视", "http://103.172.187.30:12000/stream/mytv/null-4/master.m3u8", "103.172.187.30:12000", "香港"),
    # 新增（截图识别确认）
    ("ChinaMovie", "中国电影频道", "http://103.172.187.30:12000/stream/mytv/null-3/master.m3u8", "103.172.187.30:12000", "香港"),
    ("GoldenDrama", "黄金华剧台", "http://103.172.187.30:12000/stream/mytv/null-8/master.m3u8", "103.172.187.30:12000", "香港"),
    # ---- 台湾各台直连源（iptv-org 收录）----
    ("TVBSAsia", "TVBS亚洲", "http://38.64.72.148/hls/modn/list/4005/chunklist1.m3u8", "38.64.72.148", "台湾"),
    ("TVBSAsia", "TVBS亚洲", "http://38.64.72.148/hls/modn/list/4005/playlist.m3u8", "38.64.72.148", "台湾"),
    ("TITV", "原住民电视台", "https://streamipcfapp.akamaized.net/live/_definst_/live_720/key_b1500.m3u8", "streamipcfapp.akamaized.net", "台湾"),
    ("BLTV", "美好生活电视", "https://5ddce30eb4b55.streamlock.net/bltvhd/bltv1/playlist.m3u8", "5ddce30eb4b55.streamlock.net", "台湾"),
    ("WXTV", "华视", "https://mobile.ccdntech.com/transcoder/_definst_/vod164_Live/live/chunklist_w1177047531.m3u8", "mobile.ccdntech.com", "台湾"),

    # ================= 2026-10-27 全网扩挖 =================
    # 台湾 IPTV 播控系统（61.221.215.25）——不挑运营商，全国可通
    # 频道号经 ffmpeg 3 秒真解码验证 + 画面截图识别台标
    # 中天娱乐HD(hls/47)：2026-10-27 起分片只有 188B（无信号），已移除，
    # 恢复后再加回来
    ("TVBSNews", "TVBS新闻台", "http://61.221.215.25:8800/hls/9/index.m3u8", "61.221.215.25:8800", "台湾"),
    ("SETDrama", "三立戏剧", "http://61.221.215.25:8800/hls/41/index.m3u8", "61.221.215.25:8800", "台湾"),
    ("VLJingcai", "纬来精采", "http://61.221.215.25:8800/hls/48/index.m3u8", "61.221.215.25:8800", "台湾"),
    ("AnimalPlanet", "动物星球", "http://61.221.215.25:8800/hls/57/index.m3u8", "61.221.215.25:8800", "台湾"),
    ("MusicEnjoy", "音乐欣赏", "http://61.221.215.25:8800/hls/49/index.m3u8", "61.221.215.25:8800", "台湾"),
    # 台湾 modn 系统（38.64.72.148）——同样全国可通
    ("EBCSuper", "东森超视", "http://38.64.72.148/hls/modn/list/2013/chunklist1.m3u8", "38.64.72.148", "台湾"),
    ("EBCSuper", "东森超视", "http://38.64.72.148/hls/modn/list/2013/playlist.m3u8", "38.64.72.148", "台湾"),
    ("TTVNews", "台视新闻", "http://38.64.72.148/hls/modn/list/4013/chunklist1.m3u8", "38.64.72.148", "台湾"),
    # 台湾/香港单源直连
    ("WorldTV", "环球电视", "http://utv1.hqtvzb.com:9999/hls/world.m3u8", "utv1.hqtvzb.com:9999", "台湾"),
    ("MeiAhCPlus", "美亚C+", "http://ottproxy2.ist.ooo/livehls/MOB-U1-NO/03.m3u8", "ottproxy2.ist.ooo", "香港"),
    ("BLTV2", "人间卫视", "http://61.216.67.119:1935/bltvhd/bltv1/chunklist_w1266569526.m3u8", "61.216.67.119", "台湾"),
    ("HKSTV", "香港卫视", "http://webcast.hkstv.tv/livestream/mutfysrq/playlist.m3u8", "webcast.hkstv.tv", "香港"),
    ("BrightSmart", "耀才财经", "https://v3.mediacast.hk/webcast/bshdlive-pc/chunklist_w99771165.m3u8", "v3.mediacast.hk", "香港"),
    ("PhoenixHK", "凤凰香港", "https://epg.pw/stream/5f16dc7fc8aaaed3205516c63e4a8c24bca9dbba1181684244729cf574505b0e.m3u8", "epg.pw", "凤凰"),
    # 纬来体育：三条线路（epg.pw 同一频道多 CDN 节点），播放器里会显示三条同名
    ("VL体育", "纬来体育", "https://epg.pw/stream/8855a9936e37e608a0ec8a014cce1673dee9c5d68d560da376cc92e5edef2b25.m3u8", "epg.pw", "台湾"),
    ("VL体育", "纬来体育", "https://epg.pw/stream/ab6df63b64d0cc44a1f4f029ed847a26fa54a7aebd455578fb05a63f02c22f4b.m3u8", "epg.pw", "台湾"),
    ("VL体育", "纬来体育", "https://epg.pw/stream/4f18dfe0593db5c686eb64ae8edaf2a9202d4d46bdc9bbde2cee27708e12ea01.m3u8", "epg.pw", "台湾"),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


_REPORT_LOCK = threading.Lock()


def _load_report() -> dict:
    """读体检报告 {url: {grade, at, ...}}，过期条目当没有。

    注意并发：多个 probe 线程会同时进来。这里必须用锁 + **一次性赋值**，
    绝不能先 `_REPORT = {}` 再慢慢填 —— 那样别的线程会看到「非 None 但空」
    直接返回空报告，退回实时探测，移动专线在这种并发下会被误判失效。
    """
    global _REPORT, _REPORT_AT
    if _REPORT is not None:
        return _REPORT
    with _REPORT_LOCK:
        if _REPORT is not None:
            return _REPORT
        data: dict = {}
        at_text = ""
        if REPORT_JSON.exists():
            try:
                raw = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
                at_text = raw.get("generated_at") or ""
                today = date.today()
                for u, r in (raw.get("urls") or {}).items():
                    at = r.get("at") or ""
                    try:
                        fresh = (today - datetime.strptime(at, "%Y-%m-%d").date()).days <= REPORT_MAX_AGE_DAYS
                    except Exception:  # noqa: BLE001
                        fresh = False
                    if fresh:
                        data[u] = r
            except Exception:  # noqa: BLE001
                pass
        _REPORT_AT = at_text
        _REPORT = data
        return _REPORT


def _fetch(url: str, nbytes: int = 4000, timeout: int = 8) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read(nbytes).decode("utf-8", "ignore")


def _playlist_ts(url: str, body: str) -> str | None:
    """从播放列表里挑第一个 ts 分片地址（转成绝对地址）"""
    import re
    m = re.search(r'(?m)^(?!#)(\S+\.ts(?:\?\S*)?)\s*$', body)
    if not m:
        m = re.search(r'(\S+\.ts(?:\?[^\s"\']*)?)', body)
    if not m:
        return None
    ts = m.group(1)
    return ts if ts.startswith("http") else urljoin(url, ts)


def probe(item: tuple) -> bool:
    """验活：跟随播放列表到 ts 分片，并真的下载一段数据。

    只判断「播放列表里有 .ts」是不够的——很多过期点播列表的标题还在，
    分片却已经 404 或只有几百字节（频道停播）。必须实际拉到数据才算活。

    兼容两种特殊结构：
      - master -> chunklist -> ts（myTV / modn 系统）
      - 自引用 playlist（香港卫视：返回自己 + ?hls_ctx=xxx，要带参数再跟一层）
    """
    key, display, url, host, region = item
    # 有深度体检结论就直接采信：C/D 是「播放器里看不了」的主因，必须拦掉
    rep = _load_report().get(url)
    if rep:
        return rep.get("grade") in ("A", "B")
    cur = url
    seen: set[str] = set()
    for _ in range(4):
        if not cur or cur in seen:
            return False
        seen.add(cur)
        try:
            body = _fetch(cur, 6000)
        except Exception:  # noqa: BLE001
            return False
        if "#EXTM3U" not in body:
            return False
        ts = _playlist_ts(cur, body)
        if ts:
            try:
                req = urllib.request.Request(ts, headers=UA)
                with urllib.request.urlopen(req, timeout=10, context=_CTX) as r:
                    got = 0
                    while got < 16384:
                        chunk = r.read(8192)
                        if not chunk:
                            break
                        got += len(chunk)
                    return got >= 8000
            except Exception:  # noqa: BLE001
                return False
        # 找下一层 m3u8
        import re
        m = re.search(r'(\S+\.m3u8(?:\?[^\s"\']*)?)', body)
        if not m:
            return False
        nxt = m.group(1)
        # 必须用 urljoin：以 / 开头的是相对域名根，不是相对当前目录
        cur = nxt if nxt.startswith("http") else urljoin(cur, nxt)
    return False


# 只在中国移动宽带内可达的源（广西移动 IPTV 播控系统）。
# 其它源跑在台湾/香港/国际 CDN 上，任何运营商都能连。
MOBILE_ONLY_HOSTS = {"111.59.139.85:11888"}


def _line_of(streams: list[dict]) -> str:
    """线路类型：全部源都是移动专线才算「移动专线」，否则「全国通用」。"""
    hosts = {s["h"] for s in streams}
    return "移动专线" if hosts and hosts <= MOBILE_ONLY_HOSTS else "全国通用"


def build(alive: list[tuple]) -> dict:
    # 按 host 聚合（统计每个源服务器承载多少频道）
    host_map: dict[str, dict] = {}
    for key, display, url, host, region in alive:
        if host not in host_map:
            host_map[host] = {"h": host, "rn": region, "isp": "HLS", "ch": 0}
        host_map[host]["ch"] += 1

    # 按 key 聚合：同一个 key 出现多行 = 同一频道多条线路
    # （播放器里会看到多条同名条目，某条不通就换下一条）
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for key, display, url, host, region in alive:
        if key not in by_key:
            by_key[key] = {
                "key": key,
                "display": display,
                "type": "港澳台",
                "region": region,
                "streams": [],
            }
            order.append(key)
        by_key[key]["streams"].append({"h": host, "u": url})

    channels = [by_key[k] for k in order]
    for c in channels:
        c["line"] = _line_of(c["streams"])
        # 全国通用的线路排在前面（用户优先要能播的）
        c["streams"].sort(key=lambda s: (s["h"] in MOBILE_ONLY_HOSTS, s["u"]))
    channels.sort(key=lambda c: (c["display"], c["key"]))
    hosts = sorted(host_map.values(), key=lambda x: -x["ch"])
    total = sum(len(c["streams"]) for c in channels)
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts_alive": len(hosts),
            "hosts_total": len(hosts),
            "channels": len(channels),
            "streams": total,
        },
        "hosts": hosts,
        "channels": channels,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="采集港澳台 HLS 频道")
    ap.add_argument("--no-probe", action="store_true", help="跳过验活")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    alive: list[tuple] = []
    if args.no_probe:
        # 不实时探测（Actions 跑在美国，移动专线必然不通会被误杀），
        # 改为按深度体检报告筛：报告 A/B 放行、C/D 拒绝、没报告的先保留
        rep = _load_report()
        alive = []
        for c in CHANNELS:
            r = rep.get(c[2])
            if r and r.get("grade") not in ("A", "B"):
                continue
            alive.append(c)
        print("  [gangaotai] 跳过实时验活，按体检报告保留 %d/%d 条"
              % (len(alive), len(CHANNELS)))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(probe, c) for c in CHANNELS]
            for c, f in zip(CHANNELS, futs):
                if f.result():
                    alive.append(c)
        dead = [c[1] for c in CHANNELS if c not in alive]
        rep = _load_report()
        n_rep = sum(1 for c in CHANNELS if c[2] in rep)
        print("  [gangaotai] 验活 %d/%d 个频道%s"
              % (len(alive), len(CHANNELS),
                 ("，失效：%s" % "、".join(dead)) if dead else ""))
        if n_rep:
            print("  [gangaotai] 其中 %d 条采信深度体检报告（%s）"
                  % (n_rep, _REPORT_AT or "本地体检"))

    if not alive:
        print("  [gangaotai] 无可用频道，跳过输出")
        return

    payload = build(alive)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("  [gangaotai] %d 台 / %d 频道 / %d 条 -> %s"
          % (len(payload["hosts"]), len(payload["channels"]),
             payload["stats"]["streams"], OUT_JSON))


if __name__ == "__main__":
    main()
