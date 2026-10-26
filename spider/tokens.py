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
    """轮询把中转服务器分配给各 token，尽量分散压力。"""
    hosts = [h["h"] for h in all_hosts]
    if not hosts:
        return {t["token"]: [] for t in tokens}
    result: dict[str, list[str]] = {}
    cursor = 0
    for t in tokens:
        n = max(1, min(t["servers"], len(hosts)))
        picked = [hosts[(cursor + i) % len(hosts)] for i in range(n)]
        cursor = (cursor + n) % len(hosts)
        result[t["token"]] = sorted(set(picked))
    return result


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

    SUB_DIR.mkdir(parents=True, exist_ok=True)
    index: dict[str, dict] = {}

    for t in tokens:
        host_set = set(assigned[t["token"]])
        want = set(t["channels"]) if t["channels"] else None

        lines = ['#EXTM3U x-tvg-url=""']
        n_stream = 0
        n_chan = 0
        for ch in channels:
            if want is not None and ch["key"] not in want:
                continue
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

        safe = SAFE_NAME.sub("_", t["token"])
        sub_name = f"{safe}.m3u"
        (SUB_DIR / sub_name).write_text("\n".join(lines) + "\n", encoding="utf-8")

        index[t["token"]] = {
            "n": t["name"],
            "e": t["expire"],
            "note": t["note"],
            "sub": f"data/sub/{sub_name}",
            "hosts": sorted(host_set),
            "channels": n_chan,
            "streams": n_stream,
        }
        print(f"  [token] {t['token']:<20} {t['name']:<8} {len(host_set)} 台 / {n_chan} 频道 / {n_stream} 条")

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tokens": index,
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  [token] 生成 {len(index)} 个 token -> {OUT_JSON}")
    return payload


if __name__ == "__main__":
    build()
