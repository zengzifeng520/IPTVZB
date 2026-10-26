#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 IPTV神器Pro（iptv.cqshushu.com）采集中转服务器与频道地址。

全程走接口，不在本地逐 IP 扫端口：
  1. 列表接口  → IP + 加密ID + 类型 + 频道数 + 状态（分页）
  2. 详情接口  → IP:端口
  3. 解析接口  → 该服务器完整频道列表（含 rtp/udp 中转地址）

产出：
  data/shushu_relays.json   原始采集结果（含频道）
  data/proxy_shushu.m3u     供 udpxy.py 合并的中转源

用法：
  python shushu_crawl.py            # 全流程，断点续抓
  python shushu_crawl.py list       # 只抓列表
  python shushu_crawl.py detail     # 只抓端口
  python shushu_crawl.py parse      # 只抓频道
  python shushu_crawl.py import     # 只把 relays 转成 m3u
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import config
from shushu_api import ShushuSession, parse_list, parse_detail_port

TYPES = ["multicast", "hotel", "migu", "other"]
LIMIT = 10
DATA = config.DATA_DIR
LIST_FILE = DATA / "shushu_list.json"
DETAIL_FILE = DATA / "shushu_detail.json"
RELAY_FILE = DATA / "shushu_relays.json"
M3U_FILE = DATA / "proxy_shushu.m3u"

# 每阶段最多保留多少条历史（避免文件无限增长）
KEEP_DAYS = 3


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def stage_list(sess: ShushuSession) -> list[dict]:
    raw = load(LIST_FILE, [])
    data = {x["ip"]: x for x in raw} if isinstance(raw, list) else {}
    log(f"[list] 已有 {len(data)} 条，续抓")

    for t in TYPES:
        empty = 0
        for page in range(1, 80):
            r = sess.list_page(t, page, LIMIT)
            if r.status_code != 200:
                log(f"[list] {t} p{page} HTTP {r.status_code}，结束该类型")
                break
            rows = parse_list(r.text)
            if not rows:
                empty += 1
                if empty >= 2:
                    break
                continue
            empty = 0
            new = sum(1 for x in rows if x["ip"] not in data)
            for x in rows:
                data[x["ip"]] = x
            save(LIST_FILE, list(data.values()))
            log(f"[list] {t} p{page}: {len(rows)} 行（新 {new}），累计 {len(data)}")
            time.sleep(2.5)
    log(f"[list] 完成 {len(data)} 个 IP")
    return list(data.values())


def stage_detail(sess: ShushuSession, items: list[dict]) -> list[dict]:
    done = load(DETAIL_FILE, {})
    if not isinstance(done, dict):
        done = {}
    todo = [x for x in items if x["ip"] not in done and x.get("p")]
    log(f"[detail] 待抓 {len(todo)} 个（已有 {len(done)}）")

    for i, item in enumerate(todo, 1):
        r = sess.detail(item["p"], item.get("t") or "multicast")
        if r.status_code != 200:
            log(f"[detail] [{i}/{len(todo)}] {item['ip']} HTTP {r.status_code}")
            continue
        port = parse_detail_port(r.text, item["ip"])
        if port:
            done[item["ip"]] = {
                "ip": item["ip"], "port": port, "type": item["type"],
                "channels": item["channels"], "status": item["status"],
            }
            log(f"[detail] [{i}/{len(todo)}] {item['ip']}:{port} {item['type']}")
        else:
            log(f"[detail] [{i}/{len(todo)}] {item['ip']} 未取到端口")
        save(DETAIL_FILE, done)
        time.sleep(2.0)
    log(f"[detail] 完成 {len(done)} 个端口")
    return list(done.values())


def stage_parse(sess: ShushuSession, relays: list[dict], only_fresh: bool = False) -> list[dict]:
    raw = load(RELAY_FILE, [])
    done = {x["ip"]: x for x in raw} if isinstance(raw, list) else {}

    todo = [r for r in relays if r["ip"] not in done]
    if only_fresh:
        todo = [r for r in todo if r["status"] == "新上线" or str(r["status"]).startswith("存活")]

    # 优先解析本机可达的（大部分中转服务器有 ISP 白名单）
    todo.sort(key=lambda r: (r.get("status") != "新上线", -r.get("channels", 0)))
    log(f"[parse] 待解析 {len(todo)} 台（已有 {len(done)}）")

    ok = 0
    for i, relay in enumerate(todo, 1):
        ip_port = f"{relay['ip']}:{relay['port']}"
        try:
            data = sess.parse(ip_port)
        except Exception as e:
            log(f"[parse] [{i}/{len(todo)}] {ip_port} 异常 {type(e).__name__}")
            continue
        if data.get("success"):
            chans = data.get("channels") or []
            done[relay["ip"]] = {
                "ip": relay["ip"], "port": relay["port"],
                "type": data.get("type") or relay["type"],
                "location": data.get("location"), "isp": data.get("isp"),
                "channel_count": data.get("channel_count"),
                "channels": chans,
            }
            ok += 1
            log(f"[parse] [{i}/{len(todo)}] {ip_port} ✓ {len(chans)} 频道 / {data.get('location')}")
        else:
            log(f"[parse] [{i}/{len(todo)}] {ip_port} ✗ 不可用")
        save(RELAY_FILE, list(done.values()))
        time.sleep(1.2)
    log(f"[parse] 成功 {ok} 台，累计 {len(done)} 台")
    return list(done.values())


def stage_import() -> int:
    relays = load(RELAY_FILE, [])
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
            if not url or not name:
                continue
            if "/rtp/" not in url and "/udp/" not in url:
                continue
            lines.append(f"#EXTINF:-1,{name}")
            lines.append(url)
            n_stream += 1

    if n_stream:
        M3U_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log(f"[import] {n_host} 台 / {n_stream} 条 -> {M3U_FILE}")
    else:
        log("[import] 无可用数据，跳过写入（保留旧文件）")
    return n_stream


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"

    if stage == "import":
        stage_import()
        return

    sess = ShushuSession()
    sess.boot()

    items = stage_list(sess) if stage in ("all", "list") else load(LIST_FILE, [])
    log(f"列表 {len(items)} 个 IP")

    relays = stage_detail(sess, items) if stage in ("all", "detail") else list(load(DETAIL_FILE, {}).values())
    log(f"端口 {len(relays)} 台")

    if stage in ("all", "parse"):
        stage_parse(sess, relays)

    stage_import()

    rl = load(RELAY_FILE, [])
    total = sum(len(x.get("channels") or []) for x in rl)
    log(f"汇总: {len(rl)} 台服务器 / {total} 条地址")


if __name__ == "__main__":
    main()
