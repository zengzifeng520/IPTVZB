# -*- coding: utf-8 -*-
"""酒店源采集：从 809899 的 extract_hotel 拉全量 HLS 频道，验证后并入池子。

为什么单独一条线
----------------
组播中转（/rtp/239.x.x.x）和酒店源（/hls/xxx/index.m3u8）是两种东西：
  组播：强地区限制（必须同省同运营商），但走运营商专网、稳
  酒店：无地区限制（任何网络都能访问），但依赖酒店带宽、峰值可能卡
所以站上单独归为「酒店源」分类，用户自己按需选。

数据流
------
  api.809899.xyz/extract_hotel?keyword=<空/电信/联通/移动/广电>
    -> 100 台主机 / 6000+ 条 m3u8（单次上限 100 条，多关键词求并集）
    -> 逐条 GET 验活（能拿到 #EXTM3U 或 .ts 就算活）
    -> 频道名归一化 -> 按频道聚合
    -> data/proxy_hotel.json（与 proxy.json 同构，subs.py 直接复用）

用法
----
  python hotel_pool.py              # 全量拉取+验证（约 6-8 分钟）
  python hotel_pool.py --no-probe   # 跳过验证，只拉清单（快，但含死链）
  python hotel_pool.py --reuse      # 复用 data/hotel_ok.json（已验证过的）
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config
import normalize

DATA_DIR = config.DATA_DIR
OUT_JSON = config.WEB_DATA_DIR / "proxy_hotel.json"
OK_JSON = DATA_DIR / "hotel_ok.json"

API_BASE = "https://api.809899.xyz"
API_AUTH = "iptv-tools-official-v1"
UA_JSON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "X-App-Auth": API_AUTH,
    "Connection": "close",
}
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

KEYWORDS = ["", "电信", "联通", "移动", "广电"]

# 每个频道最多留几条（酒店源同频道重复很多，控体积）
MAX_PER_CHANNEL = 12


def split_region(text: str) -> tuple[str, str]:
    """'广西壮族自治区 联通' -> ('广西', '联通')"""
    t = (text or "").strip()
    isp = ""
    for k in ("电信", "联通", "移动", "广电"):
        if k in t:
            isp = k
            break
    prov = t
    for suffix in ("壮族自治区", "回族自治区", "维吾尔自治区", "自治区", "特别行政区", "省", "市"):
        prov = prov.replace(suffix, "")
    if isp:
        prov = prov.replace(isp, "")
    return prov.strip() or "未知", isp


def fetch_api(kw: str) -> list[dict]:
    url = API_BASE + "/extract_hotel?keyword=" + urllib.parse.quote(kw)
    try:
        req = urllib.request.Request(url, headers=UA_JSON)
        with urllib.request.urlopen(req, timeout=90, context=_CTX) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("results") or []
    except Exception as exc:  # noqa: BLE001
        print("  [hotel] 关键词 %-4s 失败: %s" % (kw or "全部", exc))
        return []


def collect() -> dict[str, dict]:
    """多关键词拉全量，返回 {url: {name, region, isp, host}}。"""
    items: dict[str, dict] = {}
    for kw in KEYWORDS:
        res = fetch_api(kw)
        n0 = len(items)
        for it in res:
            if not isinstance(it, dict):
                continue
            host = str(it.get("ip") or "").strip()
            if not host:
                continue
            prov, isp = split_region(str(it.get("region") or ""))
            for c in it.get("channels") or []:
                u = str(c.get("url") or "").strip()
                nm = str(c.get("name") or "").strip()
                if ".m3u8" not in u or not nm:
                    continue
                if u.startswith("/"):
                    u = "http://" + host + u
                u = u.replace("&amp;", "&")
                if u not in items:
                    items[u] = {"name": nm, "region": prov, "isp": isp, "host": host}
        print("  [hotel] 关键词 %-4s 返回 %3d 台，新增地址 %d（累计 %d）"
              % (kw or "全部", len(res), len(items) - n0, len(items)))
        time.sleep(0.4)
    return items


def check(item: tuple[str, dict]) -> tuple[str, dict] | None:
    u, info = item
    try:
        req = urllib.request.Request(u, headers=UA)
        with urllib.request.urlopen(req, timeout=6, context=_CTX) as r:
            body = r.read(2000).decode("utf-8", "ignore")
        if "#EXTM3U" in body or "#EXTINF" in body or ".ts" in body:
            return u, info
    except Exception:  # noqa: BLE001
        pass
    return None


def probe(items: dict[str, dict], workers: int = 50) -> dict[str, dict]:
    ok: dict[str, dict] = {}
    total = len(items)
    print("  [hotel] 验证 %d 条（%d 并发）..." % (total, workers))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(check, kv) for kv in items.items()]
        done = 0
        for f in as_completed(futs):
            done += 1
            r = f.result()
            if r:
                ok[r[0]] = r[1]
            if done % 800 == 0:
                print("    进度 %d/%d，可用 %d" % (done, total, len(ok)))
    print("  [hotel] 验证完成：可用 %d / %d（%d%%）"
          % (len(ok), total, len(ok) * 100 // max(1, total)))
    return ok


def build_pool(ok: dict[str, dict]) -> dict:
    """按频道聚合，输出与 proxy.json 同构的结构。"""
    matcher = normalize.load_matcher(config.CATEGORIES_PATH)

    hosts: dict[str, dict] = {}
    chan_map: dict[str, dict] = {}
    n_skip = 0

    for url, info in ok.items():
        name = info["name"]
        placed = matcher.match_or_local(name)
        if not placed:
            n_skip += 1
            continue
        key = placed[0]
        if not key or len(key) < 2:
            n_skip += 1
            continue
        host = info["host"]
        prov = info["region"]
        isp = info["isp"]

        h = hosts.setdefault(host, {"h": host, "rn": prov, "isp": isp, "ch": 0})
        h["ch"] = h.get("ch", 0) + 1

        ch = chan_map.setdefault(key, {
            "key": key,
            "display": normalize.display_name(key),
            "type": "",
            "streams": [],
        })
        if len(ch["streams"]) < MAX_PER_CHANNEL:
            ch["streams"].append({"h": host, "u": url})

    channels = [c for c in chan_map.values() if c["streams"]]
    channels.sort(key=lambda c: (-len(c["streams"]), c["key"]))
    host_list = sorted(hosts.values(), key=lambda x: -x.get("ch", 0))

    total_streams = sum(len(c["streams"]) for c in channels)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts_alive": len(host_list),
            "hosts_total": len(host_list),
            "channels": len(channels),
            "streams": total_streams,
        },
        "hosts": host_list,
        "channels": channels,
    }
    print("  [hotel] 聚合：%d 台 / %d 频道 / %d 条（跳过无名 %d）"
          % (len(host_list), len(channels), total_streams, n_skip))
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description="采集酒店源 HLS 频道")
    ap.add_argument("--no-probe", action="store_true", help="跳过验活")
    ap.add_argument("--reuse", action="store_true", help="复用已验证的 hotel_ok.json")
    ap.add_argument("--workers", type=int, default=50)
    args = ap.parse_args()

    ok: dict[str, dict] = {}
    if args.reuse and OK_JSON.exists():
        raw = json.loads(OK_JSON.read_text(encoding="utf-8"))
        for x in raw:
            prov, isp = split_region(x.get("region") or "")
            ok[x["url"]] = {
                "name": x["name"], "region": prov,
                "isp": isp, "host": x["host"],
            }
        print("  [hotel] 复用 %d 条已验证地址" % len(ok))
    else:
        print("[hotel] 拉取酒店源清单 ...")
        items = collect()
        if not items:
            print("  [hotel] 没拉到数据，跳过")
            return
        if args.no_probe:
            ok = items
        else:
            ok = probe(items, args.workers)
            OK_JSON.parent.mkdir(parents=True, exist_ok=True)
            OK_JSON.write_text(
                json.dumps(
                    [{"name": v["name"], "url": u, "region": v["region"], "host": v["host"]}
                     for u, v in ok.items()],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    if not ok:
        print("  [hotel] 无可用地址，跳过输出")
        return

    payload = build_pool(ok)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print("  [hotel] -> %s（%.1f MB）"
          % (OUT_JSON, OUT_JSON.stat().st_size / 1048576))


if __name__ == "__main__":
    main()
