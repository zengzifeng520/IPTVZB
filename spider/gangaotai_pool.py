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
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import config

OUT_JSON = config.WEB_DATA_DIR / "proxy_gangaotai.json"

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
    # ---- 香港 myTV 服务器（iptv-org 收录）----
    ("TVBJade", "翡翠台", "http://103.172.187.30:12000/stream/mytv/null-1/master.m3u8", "103.172.187.30:12000", "香港"),
    ("GoldenJade", "黄金翡翠台", "http://103.172.187.30:12000/stream/mytv/null-12/master.m3u8", "103.172.187.30:12000", "香港"),
    ("AsianDrama", "亚洲剧台", "http://103.172.187.30:12000/stream/mytv/null-11/master.m3u8", "103.172.187.30:12000", "香港"),
    ("MeiAhMovie", "美亚电影台", "http://103.172.187.30:12000/stream/mytv/null-9/master.m3u8", "103.172.187.30:12000", "香港"),
    ("CreationTV", "创世电视", "http://103.172.187.30:12000/stream/mytv/null-4/master.m3u8", "103.172.187.30:12000", "香港"),
    # ---- 台湾各台直连源（iptv-org 收录）----
    ("TVBSAsia", "TVBS亚洲", "http://38.64.72.148/hls/modn/list/4005/playlist.m3u8", "38.64.72.148", "台湾"),
    ("TITV", "原住民电视台", "https://streamipcfapp.akamaized.net/live/_definst_/live_720/key_b1500.m3u8", "streamipcfapp.akamaized.net", "台湾"),
    ("BLTV", "美好生活电视", "https://5ddce30eb4b55.streamlock.net/bltvhd/bltv1/playlist.m3u8", "5ddce30eb4b55.streamlock.net", "台湾"),
    ("WXTV", "华视", "https://mobile.ccdntech.com/transcoder/_definst_/vod164_Live/live/chunklist_w1177047531.m3u8", "mobile.ccdntech.com", "台湾"),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def probe(item: tuple) -> bool:
    """验活：跟随 master->chunklist，能拿到 ts 分片即活。"""
    key, display, url, host, region = item
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=8, context=_CTX) as r:
            body = r.read(4000).decode("utf-8", "ignore")
        # 直接有 ts 分片，或嵌套 m3u8 再跟一层
        if ".ts" in body:
            return True
        if ".m3u8" in body:
            import re
            m = re.search(r'([^\s"\']+\.m3u8[^\s"\']*)', body)
            if m:
                nxt = m.group(1) if m.group(1).startswith("http") else url.rsplit("/", 1)[0] + "/" + m.group(1).lstrip("/")
                req2 = urllib.request.Request(nxt, headers=UA)
                with urllib.request.urlopen(req2, timeout=8, context=_CTX) as r2:
                    b2 = r2.read(4000).decode("utf-8", "ignore")
                return ".ts" in b2
    except Exception:  # noqa: BLE001
        pass
    return False


def build(alive: list[tuple]) -> dict:
    # 按 host 聚合
    host_map: dict[str, dict] = {}
    for key, display, url, host, region in alive:
        if host not in host_map:
            host_map[host] = {"h": host, "rn": region, "isp": "HLS", "ch": 0}
        host_map[host]["ch"] += 1

    channels = []
    for key, display, url, host, region in alive:
        channels.append(
            {
                "key": key,
                "display": display,
                "type": "港澳台",
                "streams": [{"h": host, "u": url}],
            }
        )
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
        alive = list(CHANNELS)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(probe, c) for c in CHANNELS]
            for c, f in zip(CHANNELS, futs):
                if f.result():
                    alive.append(c)
        dead = [c[1] for c in CHANNELS if c not in alive]
        print("  [gangaotai] 验活 %d/%d 个频道%s"
              % (len(alive), len(CHANNELS),
                 ("，失效：%s" % "、".join(dead)) if dead else ""))

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
