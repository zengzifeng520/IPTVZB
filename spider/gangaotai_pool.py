# -*- coding: utf-8 -*-
"""港澳台直播源采集：111.59.139.85 移动 tsfile 系统的台湾/凤凰/澳门频道。

为什么单独一条线
----------------
港澳台没有组播中转（之前全网调研确认），但中国移动的酒店 IPTV 系统
（111.59.139.85:11888，tsfile / key=txiptv）里有一组「测试频道」，
实际内容是台湾台 + 凤凰系列 + 澳门莲花，大陆可直连。
台标通过 ffmpeg 截图逐一识别（见记忆 2026-10-27），频道名硬编码在这里。

数据流
------
  枚举 111.59.139.85:11888/tsfile/live/{chid}_1.m3u8?key=txiptv
    -> 验活（GET 能拿到 ts 分片即活）
    -> data/proxy_gangaotai.json（与 proxy_hotel.json 同构，subs.py 复用）

用法
----
  python gangaotai_pool.py            # 全量枚举+验活（约 10 秒）
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

HOST = "111.59.139.85:11888"
BASE = f"http://{HOST}"

# 港澳台频道表：chid -> (key, display)
# 台标已通过 ffmpeg 截图识别（2026-10-27），仅保留台湾/凤凰/澳门，过滤大陆与无关频道
CHANNELS = {
    1201: ("TVBS", "TVBS"),
    1202: ("FenghuangWS", "凤凰卫视"),
    1203: ("ANIMAX", "ANIMAX"),
    1204: ("DaAi", "大爱"),
    1205: ("FeifanNews", "非凡新闻"),
    1206: ("MacauLotus", "澳门莲花"),
    1207: ("FTV", "民视"),
    1208: ("VLJapan", "纬来日本台"),
    1214: ("TTV", "台视"),
    1217: ("EBCWest", "东森洋片台"),
    1218: ("FenghuangMovie", "凤凰电影"),
    1220: ("SJTV", "信吉卫视"),
    1221: ("CTiNews", "中天新闻"),
    1222: ("PTS3", "公视3台"),
    1223: ("PTS", "公视"),
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def url_of(chid: int) -> str:
    return f"{BASE}/tsfile/live/{chid:04d}_1.m3u8?key=txiptv"


def probe(chid: int) -> tuple[int, str] | None:
    """验活：GET m3u8 能拿到 ts 分片即活，返回 (chid, url)。"""
    u = url_of(chid)
    try:
        req = urllib.request.Request(u, headers=UA)
        with urllib.request.urlopen(req, timeout=8, context=_CTX) as r:
            body = r.read(2000).decode("utf-8", "ignore")
        if ".ts" in body or "#EXTINF" in body:
            return chid, u
    except Exception:  # noqa: BLE001
        pass
    return None


def build(alive: list[tuple[int, str]]) -> dict:
    hosts = [{"h": HOST, "rn": "港澳台", "isp": "移动", "ch": len(alive)}]
    channels = []
    for chid, u in alive:
        key, display = CHANNELS[chid]
        channels.append(
            {
                "key": key,
                "display": display,
                "type": "港澳台",
                "streams": [{"h": HOST, "u": u}],
            }
        )
    channels.sort(key=lambda c: (c["display"], c["key"]))
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
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    chids = sorted(CHANNELS)
    alive: list[tuple[int, str]] = []
    if args.no_probe:
        alive = [(c, url_of(c)) for c in chids]
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(probe, c) for c in chids]
            for f in as_completed(futs):
                r = f.result()
                if r:
                    alive.append(r)
        alive.sort(key=lambda x: x[0])
        dead = [c for c in chids if c not in {a[0] for a in alive}]
        print("  [gangaotai] 验活 %d/%d 个频道%s"
              % (len(alive), len(chids),
                 ("，失效 %d 个" % len(dead)) if dead else ""))

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
