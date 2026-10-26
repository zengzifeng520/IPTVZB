#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""udpxy 中转服务器采集与汇聚。

数据来源：spider/data/proxy_source.m3u —— 由 360 Quake 测绘接口（quake.360.net）
搜到的公网 udpxy 服务器 + 各地组播地址，格式形如：

    http://<中转IP>:<端口>/udp/239.x.x.x:端口

本模块负责：
  1. 解析出「中转服务器」与「频道 → 地址」的对应关系；
  2. 探测每台中转服务器的 /status 是否存活；
  3. 频道名归一化后输出 data/proxy.json，供站点按 token 分发。
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from pathlib import Path

import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor

import config
import normalize

urllib3.disable_warnings()

SOURCE_FILE = config.DATA_DIR / "proxy_source.m3u"
SOURCE_SHUSHU = config.DATA_DIR / "proxy_shushu.m3u"
PROBE_CACHE = config.DATA_DIR / "hosts_probe.json"
OUT_FILE = config.WEB_DATA_DIR / "proxy.json"

# http://1.2.3.4:8080/udp/239.1.1.1:8000
PROXY_RE = re.compile(r"^(https?)://(\d+\.\d+\.\d+\.\d+):(\d+)/(?:udp|rtp)/([\d.]+):(\d+)", re.I)
EXTINF_NAME_RE = re.compile(r",([^,]*)$")


def parse_source(path: Path | list[Path] = None) -> list[dict]:
    """解析原始 m3u（支持多个文件），返回 [{name, url, host, mcast}]。"""
    paths = path if isinstance(path, list) else [path or SOURCE_FILE]
    entries: list[dict] = []
    for p in paths:
        if not p or not Path(p).exists():
            print(f"  [proxy] 源文件不存在: {p}")
            continue
        entries.extend(_parse_one(Path(p)))
    return entries


def _parse_one(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    entries: list[dict] = []
    pending = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            m = EXTINF_NAME_RE.search(line)
            pending = (m.group(1).strip() if m else "")
            # 从 tvg-name 里兜底
            if not pending:
                m2 = re.search(r'tvg-name="([^"]*)"', line)
                pending = m2.group(1) if m2 else ""
            continue
        if line.startswith("#"):
            continue
        if not pending:
            continue
        m = PROXY_RE.match(line)
        if m:
            scheme, ip, port, mcast_ip, mcast_port = m.groups()
            entries.append(
                {
                    "name": pending,
                    "url": line,
                    "host": f"{ip}:{port}",
                    "scheme": scheme,
                    "multicast": f"{mcast_ip}:{mcast_port}",
                }
            )
        pending = None
    return entries


def probe_host(host: str, timeout: tuple[float, float] = (4.0, 7.0)) -> dict:
    """探测一台 udpxy 是否存活，返回 {host, alive, kind, code, ms}。"""
    t0 = time.time()
    for path in ("/status", "/"):
        try:
            r = requests.get(f"http://{host}{path}", timeout=timeout, verify=False, stream=True)
            body = b""
            for chunk in r.iter_content(4096):
                body += chunk
                if len(body) > 4096:
                    break
            r.close()
            ms = int((time.time() - t0) * 1000)
            if r.status_code in (200, 206):
                low = body.decode("utf-8", "ignore").lower()
                kind = "udpxy" if "udpxy" in low else "http"
                return {"host": host, "alive": True, "kind": kind,
                        "code": r.status_code, "ms": ms}
        except requests.RequestException:
            continue
    return {"host": host, "alive": False, "kind": "", "code": 0,
            "ms": int((time.time() - t0) * 1000)}


def probe_all(hosts: list[str], workers: int = 24) -> dict[str, dict]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(probe_host, hosts))
    return {r["host"]: r for r in results}


def save_probe_cache(status: dict[str, dict]) -> None:
    """把探测结果落盘，供后续步骤（如解析接口枚举）复用，避免重复探测。"""
    payload = {"ts": time.time(), "hosts": status}
    PROBE_CACHE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_probe_cache(max_age: float = 3 * 3600) -> dict[str, dict] | None:
    """读取 3 小时内的探测缓存，过期返回 None。"""
    if not PROBE_CACHE.exists():
        return None
    try:
        payload = json.loads(PROBE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if time.time() - payload.get("ts", 0) > max_age:
        return None
    return payload.get("hosts") or None


def probe_or_cache(hosts: list[str], workers: int = 24) -> dict[str, dict]:
    """优先复用缓存，缺失的主机补测。

    保护：若一次探测出现「全灭」（多为本机网络/沙箱临时拦截），
    用更低并发重测一轮；仍全灭则不写缓存，避免把好数据覆盖成空。
    """
    cached = load_probe_cache() or {}
    missing = [h for h in hosts if h not in cached]
    if missing:
        print(f"  [proxy] 探测 {len(missing)} 台（复用缓存 {len(hosts) - len(missing)} 台）")
        fresh = probe_all(missing, workers)
        alive_n = sum(1 for v in fresh.values() if v["alive"])
        if alive_n == 0 and len(missing) >= 5:
            print("  [proxy] 本轮全部不可达，疑似网络拦截，降并发重测 ...")
            fresh = probe_all(missing, max(4, workers // 4))
            alive_n = sum(1 for v in fresh.values() if v["alive"])
        if alive_n == 0 and len(missing) >= 5:
            print("  [proxy] 重测仍全灭，不更新探测缓存")
            return {h: cached[h] for h in hosts if h in cached}
        cached.update(fresh)
        save_probe_cache(cached)
    else:
        print(f"  [proxy] 全部命中探测缓存（{len(hosts)} 台）")
    return {h: cached[h] for h in hosts if h in cached}


def build(probe_hosts: bool = True) -> dict:
    matcher = normalize.load_matcher(config.CATEGORIES_PATH)
    sources = [p for p in (SOURCE_FILE, SOURCE_SHUSHU) if p.exists()]
    entries = parse_source(sources)
    if not entries:
        return {"error": "无源数据"}
    print(f"  [proxy] 解析 {len(entries)} 条中转地址（{len(sources)} 个源文件）")

    hosts = sorted({e["host"] for e in entries})
    print(f"  [proxy] 待探测中转服务器 {len(hosts)} 台")

    if probe_hosts:
        status = probe_or_cache(hosts)
        alive = {h for h, s in status.items() if s["alive"]}
    else:
        status = {h: {"host": h, "alive": True, "kind": "udpxy", "code": 200, "ms": 0} for h in hosts}
        alive = set(hosts)
    print(f"  [proxy] 存活 {len(alive)} / {len(hosts)} 台")

    # 全灭保护：不覆盖线上已有数据（多为网络临时中断导致）
    if probe_hosts and not alive and len(hosts) >= 5:
        return {"error": f"探测结果全灭（0/{len(hosts)}），疑似网络中断，保留原有数据"}

    # 频道 → 地址（仅保留存活服务器的线路）
    by_channel: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    dropped = 0
    for e in entries:
        if e["host"] not in alive:
            dropped += 1
            continue
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        placed = matcher.match_or_local(e["name"])
        if not placed:
            dropped += 1
            continue
        key, _is_local = placed
        meta = matcher.get(key)
        by_channel[key].append(
            {
                "h": e["host"],
                "u": e["url"],
                "m": e["multicast"],
                "t": (meta or {}).get("type", "地方频道"),
            }
        )

    # 排序：分类顺序 → 频道序号
    order = [
        "央视频道", "卫视频道", "体育频道", "影视频道", "电影频道", "电视剧频道",
        "少儿频道", "纪实频道", "港台频道", "港澳频道", "国教频道", "明星频道",
        "主题频道", "数字频道", "地方频道", "其他",
    ]
    rank = {t: i for i, t in enumerate(order)}

    channels = []
    for key, streams in by_channel.items():
        meta = matcher.get(key) or {}
        ch_type = meta.get("type") or (streams[0]["t"] if streams else "其他")
        streams.sort(key=lambda s: s["h"])
        hosts_of_ch = sorted({s["h"] for s in streams})
        channels.append(
            {
                "key": key,
                "name": key,
                "display": normalize.display_name(key),
                "type": ch_type,
                "hosts": hosts_of_ch,
                "streams": [{"h": s["h"], "u": s["u"], "m": s["m"]} for s in streams],
            }
        )
    channels.sort(key=lambda c: (rank.get(c["type"], 99), _sort_key(c["key"])))

    # 服务器信息
    host_list = []
    for h in sorted(alive):
        n = sum(1 for c in channels for s in c["streams"] if s["h"] == h)
        host_list.append({"h": h, "n": n, "ms": status[h]["ms"]})

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts_alive": len(alive),
            "hosts_total": len(hosts),
            "channels": len(channels),
            "streams": sum(len(c["streams"]) for c in channels),
            "dropped": dropped,
        },
        "hosts": host_list,
        "channels": channels,
    }
    return payload


def _sort_key(key: str) -> tuple:
    m = re.fullmatch(r"CCTV(\d+)(\+?)", key)
    if m:
        return (0, int(m.group(1)), m.group(2))
    m = re.fullmatch(r"CCTV(4|8)K", key)
    if m:
        return (0, int(m.group(1)) + 0.5, "K")
    return (1, key, "")


def write(payload: dict) -> Path:
    config.WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return OUT_FILE


def main(probe: bool = True) -> dict:
    print("[proxy] 开始汇聚 udpxy 中转源 ...")
    payload = build(probe_hosts=probe)
    if "error" in payload:
        print("  [proxy]", payload["error"])
        return payload
    path = write(payload)
    s = payload["stats"]
    print(
        f"  [proxy] 中转服务器 {s['hosts_alive']}/{s['hosts_total']} 台存活，"
        f"{s['channels']} 个频道，{s['streams']} 条地址"
    )
    print(f"          -> {path} ({path.stat().st_size/1024:.1f} KB)")
    return payload


if __name__ == "__main__":
    main()
