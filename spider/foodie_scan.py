# -*- coding: utf-8 -*-
"""从 foodieguide 组播 API 发现并验证中转服务器（udpxy）。

接口：
    GET http://www.foodieguide.com/iptvsearch/getall.php?ip=<host:port>&p=1

要点（踩过的坑）：
  * 该接口用 302 返回数据体，**必须禁止跟随跳转**，否则拿到的是跳转后的首页
  * 有效 IP 返回「来自<b>运营商</b>的组播源(host)共有<b>N</b>个频道」，
    每行 copyto('http://host:port/rtp/组播:端口')，**频道名在它前面最近的
    data-title="Play with PC">频道名</div> 里**（实测 327/327 都能取到）
  * p 参数不分页，一页就把全部频道给全
  * 无效 IP 会返回一批「推荐 IP」，每次随机 8 个 —— 用它滚雪球挖新中转

用法：
    python foodie_scan.py                    # 默认 240 个候选、6 并发
    python foodie_scan.py --max 400 --mine 40
    python foodie_scan.py --fresh            # 忽略缓存重测

输出：
    spider/data/foodie_hosts.json    host -> {operator, declared, channels:[{name,url}]}
    spider/data/proxy_foodie.m3u     喂给 udpxy.py 的 m3u（带真实频道名）
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config

DATA_DIR = config.DATA_DIR
HOSTS_JSON = DATA_DIR / "foodie_hosts.json"
CACHE_JSON = DATA_DIR / "foodie_cache.json"
M3U_OUT = DATA_DIR / "proxy_foodie.m3u"

BASE = "http://www.foodieguide.com/iptvsearch/getall.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

HDR_RE = re.compile(
    r"来自<b>([^<]*)</b>的(组播源|酒店源|代理源|秒播源)\(([^)]+)\)共有<b>(\d+)</b>个频道"
)
COPY_RE = re.compile(r"copyto\('([^']+)'\)")
NAME_RE = re.compile(r'data-title="Play with PC">\s*([^<]+?)\s*</div>')
REC_RE = re.compile(r'href="\?ip=([^"&]+)"')
URL_RE = re.compile(
    r"^https?://([A-Za-z0-9._\-]+:\d+)/(?:rtp|udp)/(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})$"
)

CACHE_TTL = 12 * 3600  # 12 小时内验证过的 host 不再重复请求


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """接口用 302 返回数据体，禁止自动跟随。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # 302 的正文就是数据
        try:
            return exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""
    except Exception:  # noqa: BLE001
        return ""


def probe(host: str, timeout: int = 15) -> dict:
    """查一个 host，返回 {host, ok, operator, kind, declared, channels, recs}。"""
    url = "%s?ip=%s&p=1" % (BASE, urllib.parse.quote(host, safe=""))
    html = fetch(url, timeout)
    out = {
        "host": host,
        "ok": False,
        "operator": "",
        "kind": "",
        "declared": 0,
        "channels": [],
        "recs": [],
    }
    if not html:
        return out

    out["recs"] = [h for h in REC_RE.findall(html) if h != host]
    m = HDR_RE.search(html)
    if not m:
        return out

    out["operator"] = m.group(1).strip()
    out["kind"] = m.group(2)
    out["declared"] = int(m.group(4))
    if out["kind"] != "组播源":
        return out

    # 每个 copyto 往前找最近的频道名
    channels: list[dict] = []
    seen: set[str] = set()
    for cm in COPY_RE.finditer(html):
        u = cm.group(1).strip()
        if u in seen or not URL_RE.match(u):
            continue
        names = NAME_RE.findall(html[: cm.start()])
        name = names[-1] if names else ""
        if not name:
            continue
        seen.add(u)
        channels.append({"name": name, "url": u})

    out["channels"] = channels
    out["ok"] = bool(channels)
    return out


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return fallback


def seed_hosts() -> list[str]:
    """候选种子：现有池子 + 已抓到的中转 m3u + 历史命中。"""
    hosts: list[str] = []

    proxy = load_json(config.WEB_DATA_DIR / "proxy.json", {})
    for h in proxy.get("hosts") or []:
        v = h.get("h") if isinstance(h, dict) else h
        if v:
            hosts.append(str(v))

    for name in ("proxy_source.m3u", "proxy_shushu.m3u", "proxy_foodie.m3u"):
        src = DATA_DIR / name
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"https?://([A-Za-z0-9._\-]+:\d+)/(?:rtp|udp)/", text):
            hosts.append(m.group(1))

    known = load_json(HOSTS_JSON, {})
    hosts.extend(list(known.keys()))

    extra = DATA_DIR / "hosts_extra.txt"
    if extra.exists():
        for line in extra.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                hosts.append(line)

    seen, out = set(), []
    for h in hosts:
        h = h.strip()
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def mine_recs(rounds: int, timeout: int) -> list[str]:
    """用一组公网 IP 反复请求，每次能拿到 8 个随机推荐中转。"""
    bases = ["1.1.1.%d" % i for i in range(1, 90)] + [
        "8.8.8.8",
        "114.114.114.114",
        "223.5.5.5",
        "9.9.9.9",
    ]
    random.shuffle(bases)
    found: list[str] = []
    seen: set[str] = set()
    for i in range(min(rounds, len(bases))):
        r = probe(bases[i], timeout)
        for h in r["recs"]:
            if h not in seen:
                seen.add(h)
                found.append(h)
        time.sleep(0.3)
    print("  [scan] 挖到推荐候选 %d 个" % len(found))
    return found


def build_m3u(hosts: dict) -> tuple[int, int]:
    """写 m3u，返回 (主机数, 地址数)。频道名用 API 给的真实名称。"""
    lines = ["#EXTM3U"]
    n = 0
    for host, info in sorted(
        hosts.items(), key=lambda kv: -len(kv[1].get("channels") or [])
    ):
        op = info.get("operator") or "组播"
        for ch in info.get("channels") or []:
            name = (ch.get("name") or "").strip()
            url = (ch.get("url") or "").strip()
            if not name or not URL_RE.match(url):
                continue
            lines.append('#EXTINF:-1 group-title="%s",%s' % (op, name))
            lines.append(url)
            n += 1
    M3U_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(hosts), n


def main() -> None:
    ap = argparse.ArgumentParser(description="foodieguide 组播 API 中转发现")
    ap.add_argument("--max", type=int, default=240, help="最多探测多少个候选 host")
    ap.add_argument("--workers", type=int, default=6, help="并发数（别太高，会被限流）")
    ap.add_argument("--mine", type=int, default=30, help="先用无效 IP 挖多少批推荐")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--budget", type=int, default=900, help="最长运行秒数，超时收尾")
    ap.add_argument("--fresh", action="store_true", help="忽略缓存")
    args = ap.parse_args()

    cache = {} if args.fresh else load_json(CACHE_JSON, {})
    now = time.time()
    hosts: dict = load_json(HOSTS_JSON, {})

    queue: deque[str] = deque(seed_hosts())
    seen: set[str] = set()

    if args.mine:
        for h in mine_recs(args.mine, args.timeout):
            if h not in seen:
                queue.append(h)

    # 缓存命中的有效 host 直接保留，不重复请求
    reused = 0
    for h in list(queue):
        c = cache.get(h) or {}
        if c.get("ok") and now - c.get("ts", 0) < CACHE_TTL and h in hosts:
            reused += 1
            seen.add(h)

    print("  [scan] 初始候选 %d 个（缓存复用 %d），上限 %d" % (len(queue), reused, args.max))

    done = fresh_hits = 0
    t0 = time.time()

    while queue and done < args.max:
        if time.time() - t0 > args.budget:
            print("  [scan] 达到时间预算 %ds，提前收尾" % args.budget)
            break

        batch: list[str] = []
        while queue and len(batch) < args.workers and done + len(batch) < args.max:
            h = queue.popleft()
            if h in seen:
                continue
            seen.add(h)
            batch.append(h)
        if not batch:
            continue

        with ThreadPoolExecutor(max_workers=len(batch)) as ex:
            futs = {ex.submit(probe, h, args.timeout): h for h in batch}
            for fut in as_completed(futs):
                h = futs[fut]
                try:
                    r = fut.result()
                except Exception:  # noqa: BLE001
                    continue
                done += 1
                cache[h] = {
                    "ts": now,
                    "ok": r["ok"],
                    "op": r["operator"],
                    "n": len(r["channels"]),
                }

                if r["ok"]:
                    hosts[h] = {
                        "operator": r["operator"],
                        "declared": r["declared"],
                        "channels": r["channels"],
                    }
                    fresh_hits += 1
                    print(
                        "  [scan] + %-24s %-10s %3d 频道"
                        % (h, r["operator"] or "?", len(r["channels"]))
                    )
                for rec in r["recs"]:
                    if rec not in seen and rec not in cache:
                        queue.append(rec)

    # 清理缓存里太老的记录
    cache = {k: v for k, v in cache.items() if now - v.get("ts", 0) < 7 * 86400}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_JSON.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    HOSTS_JSON.write_text(json.dumps(hosts, ensure_ascii=False, indent=1), encoding="utf-8")

    n_hosts, n_urls = build_m3u(hosts)
    print(
        "  [scan] 本轮探测 %d 个 / 新命中 %d 台；累计 %d 台 %d 条地址，耗时 %.0fs"
        % (done, fresh_hits, n_hosts, n_urls, time.time() - t0)
    )
    print("  [scan] -> %s" % M3U_OUT.name)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    main()
