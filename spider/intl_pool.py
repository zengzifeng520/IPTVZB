# -*- coding: utf-8 -*-
"""国外（境外）直播源采集：全球 FAST / 公共广播 / 新闻频道。

为什么单独一条线
----------------
国外频道没有组播中转，也不走国内 IPTV 播控，只能靠「境外公开 HLS 源」。
绝大多数境外官方源（RTHK / TDM / HOY TV 等）对大陆 IP 做了地域封锁（实测 403/超时），
真正大陆能通的是跑在 Cloudflare / Fastly / Akamai 全球 CDN 上的 FAST 频道：
Samsung TV Plus、Pluto TV、Rakuten TV、Plex 这类免费频道的公开流。

数据来源
--------
  iptv-org 全量 API（streams.json + channels.json，约 1.8 万条流 / 180 个国家）
    -> 按国家采样 3536 条
    -> 在中国大陆网络实测快筛 2198 条通过
    -> 深验（跟随 master->chunklist 拿 ts 真数据）1294 条真流
    -> 去重 + 剔垃圾 + 按国限额 -> 867 个频道 / 50 个国家
  种子清单落在 spider/data/intl_seed.json（2026-10-27 大陆网络实测生成）。

重要：验活口径
--------------
种子是在**中国大陆网络**验活的。GitHub Actions 跑在美国，地域结论完全不同，
所以在 CI 里必须用 --no-probe（否则会把大陆能通的源误判为死源删掉）。
需要重新摸底时，在本地跑 `python intl_pool.py`（会真验活）。

数据流
------
  intl_seed.json -> data/proxy_intl.json（与 proxy_hotel / proxy_gangaotai 同构）
    -> subs.py 生成 intl.m3u + public/intl.json

用法
----
  python intl_pool.py                 # 本地全量验活（大陆网络，约 6 分钟）
  python intl_pool.py --no-probe      # 跳过验活，直接用种子（CI 用）
  python intl_pool.py --workers 40    # 调并发
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config

SEED_JSON = Path(__file__).parent / "data" / "intl_seed.json"
OUT_JSON = config.WEB_DATA_DIR / "proxy_intl.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

MIN_TS = 10000  # 拿到 10KB 以上 ts 数据才算真流


def _open(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read(8000).decode("utf-8", "ignore")


def probe(item: dict) -> bool:
    """验活：跟随 master -> chunklist，能拿到 ts 分片即活。"""
    url = item["url"]
    try:
        body = _open(url)
        if "#EXTM3U" not in body:
            return False
        # 直接有 ts 分片
        m = re.search(r'(?m)^(?!#)(\S+\.ts(?:\?\S*)?)\s*$', body)
        if not m:
            m2 = re.search(r'(\S+\.ts(?:\?[^\s"\']*)?)', body)
            m = m2
        if m:
            ts = m.group(1)
            if not ts.startswith("http"):
                ts = url.rsplit("/", 1)[0] + "/" + ts.lstrip("/")
            try:
                req = urllib.request.Request(ts, headers=UA)
                with urllib.request.urlopen(req, timeout=10, context=_CTX) as r:
                    got = 0
                    while got < 40000:
                        chunk = r.read(16384)
                        if not chunk:
                            break
                        got += len(chunk)
                    return got >= MIN_TS
            except Exception:  # noqa: BLE001
                return False
        # 嵌套 m3u8
        m = re.search(r'(\S+\.m3u8(?:\?[^\s"\']*)?)', body)
        if m:
            nxt = m.group(1)
            if not nxt.startswith("http"):
                nxt = url.rsplit("/", 1)[0] + "/" + nxt.lstrip("/")
            body2 = _open(nxt)
            return ".ts" in body2
    except Exception:  # noqa: BLE001
        pass
    return False


def build(alive: list[dict]) -> dict:
    host_map: dict[str, dict] = {}
    for it in alive:
        h = it["host"]
        if h not in host_map:
            host_map[h] = {"h": h, "rn": "国际", "isp": "HLS", "ch": 0}
        host_map[h]["ch"] += 1

    channels = []
    for it in alive:
        channels.append(
            {
                "key": it["key"],
                "display": it["display"],
                "type": "国外",
                "region": it.get("region") or "其他",
                "streams": [{"h": it["host"], "u": it["url"]}],
            }
        )
    # 按国家（保持种子里的国家顺序）+ 名称排序
    order: dict[str, int] = {}
    for it in alive:
        r = it.get("region") or "其他"
        if r not in order:
            order[r] = len(order)
    channels.sort(key=lambda c: (order.get(c["region"], 999), c["display"].lower()))

    hosts = sorted(host_map.values(), key=lambda x: -x["ch"])
    total = sum(len(c["streams"]) for c in channels)
    regions = Counter(c["region"] for c in channels)
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts_alive": len(hosts),
            "hosts_total": len(hosts),
            "channels": len(channels),
            "streams": total,
            "countries": len(regions),
        },
        "regions": [{"name": k, "channels": v} for k, v in regions.most_common()],
        "hosts": hosts,
        "channels": channels,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="采集国外 HLS 频道")
    ap.add_argument("--no-probe", action="store_true",
                    help="跳过验活（CI 用：种子已在大陆网络验活过）")
    ap.add_argument("--workers", type=int, default=40)
    args = ap.parse_args()

    if not SEED_JSON.exists():
        print(f"  [intl] 种子不存在：{SEED_JSON}")
        return
    seed: list[dict] = json.loads(SEED_JSON.read_text(encoding="utf-8"))
    print(f"  [intl] 种子 {len(seed)} 条 / {len({x['region'] for x in seed})} 个国家")

    if args.no_probe:
        alive = seed
        print("  [intl] 跳过验活（使用种子清单）")
    else:
        alive = []
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(probe, it): it for it in seed}
            for i, f in enumerate(as_completed(futs), 1):
                if f.result():
                    alive.append(futs[f])
                if i % 200 == 0:
                    print(f"  [intl] 验活 {i}/{len(seed)} 通过 {len(alive)} "
                          f"({time.time() - t0:.0f}s)")
        print(f"  [intl] 验活 {len(alive)}/{len(seed)} 可用，用时 {time.time() - t0:.0f}s")

    if not alive:
        print("  [intl] 无可用频道，保留旧数据不改写")
        return

    payload = build(alive)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("  [intl] %d 台 / %d 频道 / %d 条 / %d 国 -> %s"
          % (len(payload["hosts"]), payload["stats"]["channels"],
             payload["stats"]["streams"], payload["stats"]["countries"], OUT_JSON))


if __name__ == "__main__":
    main()
