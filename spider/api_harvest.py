# -*- coding: utf-8 -*-
"""组播中转服务器统一采集器（所有可用 API 集中在这里）。

三个数据源：

  1. api.809899.xyz/extract_multicast   主源。GET 带 X-App-Auth 头，
     返回 [{ip, region, channel_count, channels:[{name,url}]}]，
     单次最多 100 条；用「电信/联通/移动/广电 + 各省」多关键词并集可翻出更多。
     来源：IPTV搜索神器源码 iptv_core.py 的 DEFAULT_SETTINGS。

  2. api.809899.xyz/extract_hotel       酒店源。多为 http://ip:port/hls/...，
     只有少数是 /udp/ 中转，默认只收 udp/rtp 的（本池子是中转服务器池）。

  3. foodieguide.com/iptvsearch/getall.php?ip=<host:port>   逐台校验并取频道。
     302 返回正文，必须禁止跟随跳转；无效 IP 会随机返回 8 个推荐 IP 用于滚雪球。

输出：
  spider/data/api_hosts.json   {host: {region, isp, src, channels: [[name,url], ...]}}
  spider/data/proxy_api.m3u    给 udpxy.py 合并的标准 m3u

用法：
  python api_harvest.py                 # 主源全关键词 + 滚雪球
  python api_harvest.py --no-foodie     # 只跑 809899
  python api_harvest.py --hotel         # 额外收酒店源里的 udp 中转
  python api_harvest.py --fresh         # 忽略缓存强制重抓
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config

DATA_DIR = config.DATA_DIR
HOSTS_JSON = DATA_DIR / "api_hosts.json"
CACHE_JSON = DATA_DIR / "api_cache.json"
M3U_OUT = DATA_DIR / "proxy_api.m3u"

# ---- 809899 接口（来自 IPTV搜索神器源码 DEFAULT_SETTINGS）----
API_BASE = "https://api.809899.xyz"
API_AUTH = "iptv-tools-official-v1"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 关键词组合：运营商 + 省份，逐个拉再求并集（接口每次硬上限 100 条）
KEYWORDS = [
    "",
    "电信",
    "联通",
    "移动",
    "广电",
    "北京", "上海", "天津", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "广西", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "宁夏", "新疆", "内蒙古",
]

PROXY_RE = re.compile(
    r"^(https?)://([A-Za-z0-9._\-]+):(\d+)/(?:rtp|udp)/(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$"
)

CACHE_TTL = 6 * 3600  # 6 小时内不重复请求同一接口

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return fallback


def api_get(path: str, timeout: int = 90):
    """调 809899 接口，返回 (json|None, err)。"""
    url = API_BASE + path
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "X-App-Auth": API_AUTH,
            "Connection": "close",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            raw = r.read().decode("utf-8", "replace")
        if not raw.strip().startswith(("{", "[")):
            return None, "非 JSON 响应: " + raw[:120]
        return json.loads(raw), None
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, exc)


def split_region(text: str) -> tuple[str, str]:
    """'湖南省 湖南电信' -> ('湖南', '电信')"""
    text = (text or "").strip()
    isp = ""
    for key in ("电信", "联通", "移动", "广电"):
        if key in text:
            isp = key
            break
    prov = text.split()[0] if text.split() else ""
    for suf in ("特别行政区", "自治区", "省", "市"):
        if prov.endswith(suf) and len(prov) > len(suf):
            prov = prov[: -len(suf)]
    prov = prov.replace("壮族", "").replace("回族", "").replace("维吾尔", "")
    return prov or "未知", isp or "其他"


def harvest_809899(keywords: list[str], only_proxy: bool = True) -> tuple[dict, dict]:
    """多关键词拉组播源，返回 (hosts, stats)。"""
    hosts: dict[str, dict] = {}
    stats = {"requests": 0, "errors": 0, "records": 0, "dupes": 0}

    seen_urls: set[str] = set()
    for i, kw in enumerate(keywords):
        data, err = api_get("/extract_multicast?keyword=" + urllib.parse.quote(kw))
        stats["requests"] += 1
        if err or not data:
            stats["errors"] += 1
            print("  [api] %-6s 失败: %s" % (kw or "全部", err))
            time.sleep(1.0)
            continue

        results = data.get("results") or []
        new_hosts = 0
        for it in results:
            if not isinstance(it, dict):
                continue
            ip = str(it.get("ip") or "").strip()
            chans = it.get("channels") or []
            if not ip or not chans:
                continue
            prov, isp = split_region(str(it.get("region") or ""))

            is_new = ip not in hosts
            bucket = hosts.setdefault(
                ip, {"region": prov, "isp": isp, "src": "809899", "channels": []}
            )
            if is_new:
                new_hosts += 1
            added = 0
            for c in chans:
                name = str(c.get("name") or "").strip()
                url = str(c.get("url") or "").strip()
                if not name or not url:
                    continue
                if only_proxy and not PROXY_RE.match(url):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                bucket["channels"].append([name, url])
                added += 1
            stats["records"] += 1
            if added == 0:
                stats["dupes"] += 1

        print(
            "  [api] %-6s %3d 条记录（新增主机 %2d）"
            % (kw or "全部", len(results), new_hosts)
        )
        if i + 1 < len(keywords):
            time.sleep(0.35)

    return hosts, stats


def harvest_foodie(rounds: int, max_probe: int, timeout: int = 15) -> dict:
    """foodieguide 滚雪球：无效 IP 推荐新 IP，逐台取回频道名+地址。"""
    try:
        import foodie_scan
    except Exception as exc:  # noqa: BLE001
        print("  [api] foodie 模块不可用: %s" % exc)
        return {}

    cands = foodie_scan.mine_recs(rounds, timeout)
    out: dict[str, dict] = {}
    if not cands:
        return out

    done = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(foodie_scan.probe, h, timeout): h for h in cands[:max_probe]}
        for fut in as_completed(futs):
            h = futs[fut]
            done += 1
            try:
                r = fut.result()
            except Exception:  # noqa: BLE001
                continue
            if not r.get("ok"):
                continue
            prov, isp = split_region(r.get("operator") or "")
            out[h] = {
                "region": prov,
                "isp": isp,
                "src": "foodie",
                "channels": [[c["name"], c["url"]] for c in r["channels"]],
            }
            print("  [api] + %-22s %-8s %3d 频道" % (h, r.get("operator") or "?", len(r["channels"])))
    print("  [api] foodie 探测 %d 个候选，命中 %d 台" % (done, len(out)))
    return out


def harvest_hotel() -> dict:
    """酒店源里只取 /udp/ 或 /rtp/ 的中转（hls 直连不属本池子）。"""
    data, err = api_get("/extract_hotel?keyword=")
    out: dict[str, dict] = {}
    if err or not data:
        print("  [api] 酒店源失败: %s" % err)
        return out
    for it in data.get("results") or []:
        if not isinstance(it, dict):
            continue
        ip = str(it.get("ip") or "").strip()
        prov, isp = split_region(str(it.get("region") or ""))
        for c in it.get("channels") or []:
            url = str(c.get("url") or "")
            name = str(c.get("name") or "").strip()
            if not PROXY_RE.match(url) or not name:
                continue
            b = out.setdefault(ip, {"region": prov, "isp": isp, "src": "hotel", "channels": []})
            b["channels"].append([name, url])
    out = {k: v for k, v in out.items() if v["channels"]}
    print("  [api] 酒店源命中 %d 台带中转的主机" % len(out))
    return out


def build_m3u(hosts: dict) -> tuple[int, int]:
    lines = ["#EXTM3U"]
    n = 0
    for host, info in sorted(hosts.items(), key=lambda kv: -len(kv[1].get("channels") or [])):
        group = info.get("region") or "组播"
        if info.get("isp") and info["isp"] != "其他":
            group = "%s%s" % (group, info["isp"])
        for name, url in info.get("channels") or []:
            if not name or not PROXY_RE.match(url):
                continue
            lines.append('#EXTINF:-1 group-title="%s",%s' % (group, name))
            lines.append(url)
            n += 1
    M3U_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(hosts), n


def main() -> None:
    ap = argparse.ArgumentParser(description="组播中转 API 统一采集")
    ap.add_argument("--keywords", default="", help="逗号分隔，覆盖默认关键词组")
    ap.add_argument("--no-foodie", action="store_true", help="跳过 foodieguide")
    ap.add_argument("--foodie-rounds", type=int, default=24, help="滚雪球轮数")
    ap.add_argument("--foodie-probe", type=int, default=60, help="foodie 最多探测多少候选")
    ap.add_argument("--hotel", action="store_true", help="额外收酒店源里的 udp 中转")
    ap.add_argument("--allow-hls", action="store_true", help="保留 hls 直连地址（一般不用）")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    cache = {} if args.fresh else load_json(CACHE_JSON, {})
    now = time.time()

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else KEYWORDS

    print("[api] 开始采集（%d 个关键词）..." % len(keywords))
    hosts, stats = harvest_809899(keywords, only_proxy=not args.allow_hls)

    if not args.no_foodie:
        print("[api] foodieguide 滚雪球 ...")
        for h, info in harvest_foodie(args.foodie_rounds, args.foodie_probe).items():
            cur = hosts.get(h)
            if cur:
                have = {u for _n, u in cur["channels"]}
                cur["channels"].extend([c for c in info["channels"] if c[1] not in have])
            else:
                hosts[h] = info

    if args.hotel:
        for h, info in harvest_hotel().items():
            cur = hosts.get(h)
            if cur:
                have = {u for _n, u in cur["channels"]}
                cur["channels"].extend([c for c in info["channels"] if c[1] not in have])
            else:
                hosts[h] = info

    # 丢掉没有任何可用地址的主机
    hosts = {k: v for k, v in hosts.items() if v.get("channels")}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HOSTS_JSON.write_text(json.dumps(hosts, ensure_ascii=False, indent=1), encoding="utf-8")
    cache["last_run"] = now
    CACHE_JSON.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    n_hosts, n_urls = build_m3u(hosts)
    print(
        "  [api] 请求 %d 次（失败 %d）→ %d 台主机 / %d 条地址，耗时 %.0fs"
        % (stats["requests"], stats["errors"], n_hosts, n_urls, time.time() - t0)
    )
    print("  [api] -> %s" % M3U_OUT.name)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    main()
