#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用自己的探测结果喂 cqshushu 的解析接口，扩充每台服务器的频道清单。

为什么这么做：
  我们手上的 m3u 是「按 URL 抓到的碎片」，每台服务器只覆盖部分频道；
  解析接口让服务器自己报全量，实测单台频道数是 m3u 的 2~3 倍。

流程：
  1. 解析现有源文件 → 得到全部中转服务器 host
  2. 本地探测 /status（与 udpxy.py 共用缓存，不重复探测）
  3. 只把存活主机喂给解析接口 → data/shushu_ours.json
  4. shushu_import.py 会把它转成 proxy_shushu.m3u 供 udpxy.py 合并

用法：
  python shushu_enrich.py            # 全量（默认只解析未解析过的）
  python shushu_enrich.py --force    # 忽略已有结果，全部重解析
  python shushu_enrich.py --limit 5  # 只解析前 5 台（调试用）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import config
import udpxy
from shushu_api import ShushuSession

OUT = config.DATA_DIR / "shushu_ours.json"
SLEEP = 1.5


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load_done() -> dict:
    if not OUT.exists():
        return {}
    try:
        items = json.loads(OUT.read_text(encoding="utf-8"))
        return {x["ip"]: x for x in items}
    except Exception:
        return {}


def save(done: dict):
    OUT.write_text(json.dumps(list(done.values()), ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            pass

    sources = [p for p in (udpxy.SOURCE_FILE, udpxy.SOURCE_SHUSHU) if p.exists()]
    entries = udpxy.parse_source(sources)
    if not entries:
        log("[enrich] 没有可用的源文件")
        return

    hosts = sorted({e["host"] for e in entries})
    log(f"[enrich] 候选服务器 {len(hosts)} 台，先本地探测")

    status = udpxy.probe_or_cache(hosts)
    alive = [h for h in hosts if status.get(h, {}).get("alive")]
    log(f"[enrich] 本机可达 {len(alive)} / {len(hosts)} 台")

    done = {} if force else load_done()
    if done:
        log(f"[enrich] 已有 {len(done)} 台解析结果，增量更新")

    todo = [h for h in alive if h.split(":")[0] not in done]
    if limit:
        todo = todo[:limit]
    log(f"[enrich] 待喂解析接口 {len(todo)} 台")

    if not todo:
        log("[enrich] 没有需要解析的服务器")
        _report(done)
        return

    sess = ShushuSession()
    sess.boot()

    ok = 0
    for i, h in enumerate(todo, 1):
        ip, port = h.rsplit(":", 1)
        try:
            d = sess.parse(h)
        except Exception as e:
            log(f"[enrich] [{i}/{len(todo)}] {h} 异常 {type(e).__name__}")
            continue
        if d.get("success"):
            chans = d.get("channels") or []
            done[ip] = {
                "ip": ip,
                "port": int(port),
                "type": d.get("type") or "multicast",
                "location": d.get("location"),
                "isp": d.get("isp"),
                "channel_count": d.get("channel_count"),
                "channels": chans,
            }
            ok += 1
            log(f"[enrich] [{i}/{len(todo)}] {h} ✓ {len(chans)} 频道 / {d.get('location')}")
        else:
            log(f"[enrich] [{i}/{len(todo)}] {h} ✗ 接口侧不可达")
        save(done)
        time.sleep(SLEEP)

    log(f"[enrich] 成功 {ok} 台")
    _report(done)


def _report(done: dict):
    total = sum(len(x.get("channels") or []) for x in done.values())
    log(f"[enrich] 累计 {len(done)} 台 / {total} 条地址 -> {OUT}")


if __name__ == "__main__":
    main()
