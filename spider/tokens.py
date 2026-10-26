#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Token 分发：为每个 token 分配一组中转服务器，生成专属订阅文件。

- 输入：spider/data/tokens.json（token 配置）+ data/proxy.json（中转地址池）
- 输出：data/tokens.json（前端查询用）+ data/sub/<token>.m3u（专属订阅）

安全说明：这是纯静态站点，token 只能做「分发凭证」，无法做真正的访问控制。
拿到 token 的人能看到对应订阅文件，因此不要把它当密码使用。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import config

TOKEN_CFG = config.DATA_DIR / "tokens.json"
PROXY_JSON = config.WEB_DATA_DIR / "proxy.json"
OUT_JSON = config.WEB_DATA_DIR / "tokens.json"
SUB_DIR = config.WEB_DATA_DIR / "sub"

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def load_config() -> list[dict]:
    if not TOKEN_CFG.exists():
        return []
    raw = json.loads(TOKEN_CFG.read_text(encoding="utf-8"))
    items = raw.get("tokens", raw if isinstance(raw, list) else [])
    out = []
    for i, t in enumerate(items):
        token = str(t.get("token", "")).strip()
        if not token:
            continue
        out.append(
            {
                "token": token,
                "name": t.get("name") or f"套餐 {i+1}",
                "servers": int(t.get("servers", 3)),
                "expire": t.get("expire", ""),
                "note": t.get("note", ""),
                "channels": t.get("channels") or [],  # 空 = 全部频道
            }
        )
    return out


def assign_hosts(tokens: list[dict], all_hosts: list[dict]) -> dict[str, list[str]]:
    """把中转服务器按「地区」整块分配给各 token。

    为什么按地区分配：同一个 token 内的服务器应该属于同一地区，这样它的地区订阅
    才是完整可用的；同时保证每个地区都落到某个 token 上，不会出现「有地区没订阅」。

    没有地区信息（regions.py 未跑）时退化为原来的轮询分配。
    """
    hosts = [h["h"] for h in all_hosts]
    if not hosts:
        return {t["token"]: [] for t in tokens}

    if not any(h.get("r") for h in all_hosts):
        result: dict[str, list[str]] = {}
        cursor = 0
        for t in tokens:
            n = max(1, min(t["servers"], len(hosts)))
            picked = [hosts[(cursor + i) % len(hosts)] for i in range(n)]
            cursor = (cursor + n) % len(hosts)
            result[t["token"]] = sorted(set(picked))
        return result

    # 地区 → 服务器列表
    buckets: dict[str, list[str]] = {}
    for h in all_hosts:
        buckets.setdefault(h.get("r") or "XX", []).append(h["h"])
    # 地区按服务器数降序，大套餐先挑
    regions = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    # 按 servers 权重算每个 token 能分到几个地区（至少 1 个）
    total_w = sum(max(1, t["servers"]) for t in tokens) or 1
    n_region = len(regions)
    quotas = {}
    for t in tokens:
        quotas[t["token"]] = max(1, round(n_region * max(1, t["servers"]) / total_w))
    # 配额之和与实际地区数对齐（加减到配额最大的 token 上）
    diff = n_region - sum(quotas.values())
    order = sorted(tokens, key=lambda t: -t["servers"])
    idx = 0
    while diff != 0 and order:
        key = order[idx % len(order)]["token"]
        if diff > 0:
            quotas[key] += 1
            diff -= 1
        elif quotas[key] > 1:
            quotas[key] -= 1
            diff += 1
        idx += 1

    result = {t["token"]: [] for t in tokens}
    cursor = 0
    for t in order:
        take = quotas[t["token"]]
        for _code, hs in regions[cursor : cursor + take]:
            result[t["token"]].extend(hs)
        cursor += take
    return {k: sorted(set(v)) for k, v in result.items()}


def _write_m3u(path: Path, channels: list[dict], host_set: set[str]) -> tuple[int, int]:
    """写订阅文件，返回 (频道数, 地址数)。"""
    lines = ['#EXTM3U x-tvg-url=""']
    n_stream = 0
    n_chan = 0
    for ch in channels:
        picked = [s for s in ch["streams"] if s["h"] in host_set]
        if not picked:
            continue
        n_chan += 1
        for s in picked:
            lines.append(
                f'#EXTINF:-1 tvg-name="{ch["display"]}" group-title="{ch["type"]}",{ch["display"]}'
            )
            lines.append(s["u"])
            n_stream += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n_chan, n_stream


def build() -> dict:
    if not PROXY_JSON.exists():
        print("  [token] 缺少 data/proxy.json，请先运行 udpxy.py")
        return {}
    proxy = json.loads(PROXY_JSON.read_text(encoding="utf-8"))
    channels = proxy.get("channels", [])
    host_stats = proxy.get("hosts", [])

    tokens = load_config()
    if not tokens:
        print("  [token] 未配置 token（spider/data/tokens.json）")
        return {}

    assigned = assign_hosts(tokens, host_stats)

    # host → 地区（由 regions.py 写入 hosts[].r / .rn）
    host_region = {h["h"]: (h.get("r") or "XX", h.get("rn") or "未知") for h in host_stats}
    isp_of = {h["h"]: (h.get("isp") or "") for h in host_stats}

    SUB_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}

    for t in tokens:
        host_set = set(assigned[t["token"]])
        want = set(t["channels"]) if t["channels"] else None
        picked_channels = [c for c in channels if want is None or c["key"] in want]

        safe = SAFE_NAME.sub("_", t["token"])

        # 全量订阅
        n_chan, n_stream = _write_m3u(SUB_DIR / f"{safe}.m3u", picked_channels, host_set)

        # 按地区拆订阅
        by_region: dict[str, list[str]] = {}
        for h in host_set:
            by_region.setdefault(host_region.get(h, ("XX", "未知"))[0], []).append(h)

        regions = []
        for code, hs in by_region.items():
            r_hosts = set(hs)
            fname = f"{safe}__{SAFE_NAME.sub('_', code)}.m3u"
            rc, rs = _write_m3u(SUB_DIR / fname, picked_channels, r_hosts)
            if not rs:
                continue
            regions.append(
                {
                    "k": code,
                    "n": host_region.get(hs[0], ("XX", "未知"))[1],
                    "isp": "/".join(sorted({isp_of.get(h, "") for h in hs} - {""})),
                    "sub": f"data/sub/{fname}",
                    "hosts": sorted(r_hosts),
                    "channels": rc,
                    "streams": rs,
                }
            )
        regions.sort(key=lambda r: (-r["streams"], r["n"]))

        index[t["token"]] = {
            "n": t["name"],
            "e": t["expire"],
            "note": t["note"],
            "sub": f"data/sub/{safe}.m3u",
            "hosts": sorted(host_set),
            "channels": n_chan,
            "streams": n_stream,
            "regions": regions,
        }
        detail = "、".join(f"{r['n']}{r['channels']}" for r in regions[:4])
        more = f" 等 {len(regions)} 个地区" if len(regions) > 4 else ""
        print(
            f"  [token] {t['token']:<20} {t['name']:<8} {len(host_set)} 台 / "
            f"{n_chan} 频道 / {n_stream} 条 | 地区: {detail}{more}"
        )

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tokens": index,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  [token] 生成 {len(index)} 个 token -> {OUT_JSON}")
    return payload


if __name__ == "__main__":
    build()
