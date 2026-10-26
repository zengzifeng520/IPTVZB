#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 IPTV神器Pro 采集到的中转服务器数据转成 udpxy.py 可消费的 m3u。

输入：shushu_relays.json（由 shushu_crawl.py 生成）
输出：spider/data/proxy_shushu.m3u

格式与 proxy_source.m3u 一致：
    #EXTINF:-1,频道名
    http://<中转IP>:<端口>/rtp/239.x.x.x:port
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "shushu_relays.json"
OUT = ROOT / "data" / "proxy_shushu.m3u"


def main() -> int:
    if not SRC.exists():
        print(f"  缺少 {SRC}，请先运行 shushu_crawl.py")
        return 1
    relays = json.loads(SRC.read_text(encoding="utf-8"))
    lines = ["#EXTM3U"]
    n_stream = 0
    n_host = 0
    for r in relays:
        chans = r.get("channels") or []
        if not chans:
            continue
        n_host += 1
        for c in chans:
            url = (c.get("url") or "").strip()
            name = (c.get("name") or "").strip()
            if not url or not name or "/rtp/" not in url and "/udp/" not in url:
                continue
            lines.append(f"#EXTINF:-1,{name}")
            lines.append(url)
            n_stream += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  导入 {n_host} 台服务器 / {n_stream} 条地址 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
