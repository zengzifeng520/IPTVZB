#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 cqshushu 接口采集到的中转服务器数据转成 udpxy.py 可消费的 m3u。

输入（存在哪个读哪个）：
  data/shushu_relays.json  站点列表里的第三方服务器（经解析接口验证可用）
  data/shushu_ours.json    用解析接口枚举的「我方已验证服务器」完整频道清单

输出：data/proxy_shushu.m3u

格式与 proxy_source.m3u 一致：
    #EXTINF:-1,频道名
    http://<中转IP>:<端口>/rtp/239.x.x.x:port
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SOURCES = [DATA / "shushu_relays.json", DATA / "shushu_ours.json"]
OUT = DATA / "proxy_shushu.m3u"


def main() -> int:
    relays = []
    for p in SOURCES:
        if not p.exists():
            continue
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  跳过损坏文件 {p.name}: {e}")
            continue
        relays.extend(items)
        print(f"  读入 {p.name}: {len(items)} 台")

    if not relays:
        print("  没有可导入的数据（先跑 shushu_crawl.py）")
        return 1

    lines = ["#EXTM3U"]
    n_stream = 0
    n_host = 0
    seen_url = set()
    for r in relays:
        chans = r.get("channels") or []
        if not chans:
            continue
        n_host += 1
        for c in chans:
            url = (c.get("url") or "").strip()
            name = (c.get("name") or "").strip()
            if not url or not name:
                continue
            if "/rtp/" not in url and "/udp/" not in url:
                continue
            if url in seen_url:
                continue
            seen_url.add(url)
            lines.append(f"#EXTINF:-1,{name}")
            lines.append(url)
            n_stream += 1

    if not n_stream:
        print("  没有可用的中转地址，保持原文件不变")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  导入 {n_host} 台服务器 / {n_stream} 条地址 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
