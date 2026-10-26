#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集主流程：抓源 -> 归一化 -> 并发探测 -> 入库 -> 编译前端数据。

用法：
    python run.py                  # 全量抓取 + 探测 + 生成站点数据
    python run.py --fetch-only     # 只抓源看清单
    python run.py --limit 300      # 只探测前 300 条（快速验证）
    python run.py --recheck        # 忽略历史结果，全量重测
    python run.py --build-only     # 只用现有数据库重新生成站点数据
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import normalize
import probe as probe_mod
import sources
import store


def collect_candidates(use_cache: bool = False) -> tuple[list[dict], dict]:
    """抓取并归一到频道维度。"""
    print("[1/4] 抓取公开源 ...")
    raw = sources.fetch_all(use_cache=use_cache)
    print(f"      原始条目 {len(raw)} 条")

    matcher = normalize.load_matcher(config.CATEGORIES_PATH)
    print("[2/4] 频道名归一化 ...")
    seen: dict[str, dict] = {}
    unmatched = 0
    scheme_drop = 0
    private_drop = 0
    for e in raw:
        scheme = e.url.split("://", 1)[0].lower() if "://" in e.url else ""
        if scheme not in config.ALLOWED_SCHEMES:
            scheme_drop += 1
            continue
        host = probe_mod.host_of(e.url)
        if config.PROBE_SKIP_LOCAL and probe_mod.is_private_host(host):
            private_drop += 1
            continue
        key = matcher.match(e.name)
        if not key:
            placed = matcher.match_or_local(e.name)
            if not placed:
                unmatched += 1
                continue
            key, _is_local = placed
        h = e.url_hash
        cand = {
            "channel": key,
            "url": e.url.strip(),
            "url_hash": h,
            "host": host,
            "source_id": e.source_id,
            "weight": e.weight,
        }
        old = seen.get(h)
        if old is None or cand["weight"] > old["weight"]:
            seen[h] = cand

    print(
        f"      命中频道 {len(seen)} 条源 | 未识别频道 {unmatched} | "
        f"非 HTTP 协议 {scheme_drop} | 内网/组播 {private_drop}"
    )
    stats = {
        "raw": len(raw),
        "matched": len(seen),
        "unmatched": unmatched,
        "scheme_drop": scheme_drop,
        "private_drop": private_drop,
    }
    return list(seen.values()), stats


def probe_all(candidates: list[dict], workers: int = config.PROBE_WORKERS,
              recheck: bool = False) -> list[dict]:
    """并发探测，返回可写入数据库的行。"""
    known = store.known_hashes()
    todo: list[dict] = []
    reused: list[dict] = []
    for c in candidates:
        old = known.get(c["url_hash"])
        if old and not recheck:
            # 6 小时内测过的直接复用结果
            if old["checked_at"] and _hours_since(old["checked_at"]) < 6:
                row = {**c,
                       "ok": old["ok"], "width": old["width"], "height": old["height"],
                       "fps": old["fps"], "speed": old["speed"], "cors": old["cors"],
                       "error": "", "checked_at": old["checked_at"]}
                reused.append(row)
                continue
        todo.append(c)

    print(f"[3/4] 探测 {len(todo)} 条源（复用近期结果 {len(reused)} 条，并发 {workers}）...")
    results: list[dict] = list(reused)
    t0 = time.time()
    done = 0
    online = 0

    def task(c: dict) -> dict:
        r = probe_mod.probe(
            c["url"],
            connect_timeout=config.PROBE_CONNECT_TIMEOUT,
            read_timeout=config.PROBE_READ_TIMEOUT,
            sample_bytes=config.PROBE_SAMPLE_BYTES,
        )
        return {**c,
                "ok": 1 if r.ok else 0,
                "width": r.width, "height": r.height, "fps": r.fps,
                "speed": r.speed_kbps, "cors": 1 if r.cors else 0,
                "error": r.error, "checked_at": r.checked_at}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, c): c for c in todo}
        for fut in as_completed(futures):
            done += 1
            try:
                row = fut.result()
            except Exception as e:  # noqa: BLE001
                c = futures[fut]
                row = {**c, "ok": 0, "width": 0, "height": 0, "fps": 0,
                       "speed": 0, "cors": 0, "error": str(e)[:60],
                       "checked_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            results.append(row)
            if row["ok"]:
                online += 1
            if done % 50 == 0 or done == len(todo):
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed else 0
                eta = (len(todo) - done) / rate if rate else 0
                print(f"      {done}/{len(todo)}  在线 {online}  "
                      f"({rate:.1f}/s, 剩余约 {eta/60:.1f} 分钟)")
    return results


def _hours_since(ts: str) -> float:
    try:
        t = time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))
        return (time.time() - t) / 3600
    except (ValueError, TypeError):
        return 1e9


def main() -> int:
    ap = argparse.ArgumentParser(description="IPTV 源采集与检测")
    ap.add_argument("--fetch-only", action="store_true", help="只抓取源，不探测")
    ap.add_argument("--build-only", action="store_true", help="只用已有数据库生成站点数据")
    ap.add_argument("--limit", type=int, default=0, help="限制探测条数")
    ap.add_argument("--workers", type=int, default=config.PROBE_WORKERS, help="并发线程数")
    ap.add_argument("--recheck", action="store_true", help="忽略历史结果全量重测")
    ap.add_argument("--cache", action="store_true", help="优先使用本地源文件缓存")
    args = ap.parse_args()

    store.init_db()

    if args.build_only:
        import build

        build.main()
        return 0

    started = time.strftime("%Y-%m-%d %H:%M:%S")
    candidates, cstats = collect_candidates(use_cache=args.cache)

    if args.fetch_only:
        print(f"\n候选清单（{len(candidates)} 条）示例：")
        for c in candidates[:15]:
            print(f"  {c['channel']:<14} {c['url'][:78]}")
        return 0

    if args.limit:
        # 按频道轮流取，保证覆盖度而不是全挤在某几个台
        by_ch: dict[str, list[dict]] = {}
        for c in candidates:
            by_ch.setdefault(c["channel"], []).append(c)
        picked: list[dict] = []
        idx = 0
        while len(picked) < args.limit and any(by_ch.values()):
            for ch in list(by_ch.keys()):
                if by_ch[ch]:
                    picked.append(by_ch[ch].pop(0))
                    if len(picked) >= args.limit:
                        break
            idx += 1
            if idx > 10000:
                break
        candidates = picked
        print(f"      抽样探测 {len(candidates)} 条（跨频道均衡）")

    rows = probe_all(candidates, workers=args.workers, recheck=args.recheck)
    n = store.upsert_streams(rows)
    print(f"      入库 {n} 条")

    pruned = store.prune_stale(days=7)
    if pruned:
        print(f"      清理过期失效源 {pruned} 条")

    print("[4/4] 生成站点数据 ...")
    import build

    payload = build.main()

    store.log_run({
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "candidates": cstats["matched"],
        "probed": len(rows),
        "online": sum(1 for r in rows if r["ok"]),
        "channels": payload["stats"]["channels"],
        "note": f"raw={cstats['raw']} unmatched={cstats['unmatched']}",
    })

    s = store.stats()
    print(f"\n[完成] 源库总计 {s['total']} 条，在线 {s['online']} 条，"
          f"覆盖 {s['channels']} 个频道，其中 1080P+ {s['hd']} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
