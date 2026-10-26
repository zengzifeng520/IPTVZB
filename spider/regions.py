#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「中转服务器所在地区」给频道分组。

为什么按服务器地区分：每个 udpxy 中转服务器只能转它本地运营商网内的组播，
北京联通的用户只能用北京联通的服务器。混在一起列，大部分地址对用户是死的。

产出：
  data/regions.json   [{key, name, hosts, isp, channels, streams}]
  并在 proxy.json 的 hosts 里补上 r/rn/isp 字段

归属地来自 ip-api.com（免费，批量 100 个/次，限 15 次/分钟），本地缓存 30 天。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

import config

PROXY_JSON = config.WEB_DATA_DIR / "proxy.json"
OUT_JSON = config.WEB_DATA_DIR / "regions.json"
GEO_CACHE = config.DATA_DIR / "hosts_geo.json"

GEO_URL = "http://ip-api.com/batch?lang=zh-CN&fields=status,query,country,region,regionName,city,isp"
GEO_TTL = 30 * 86400

# 省份尾缀，用于把「山西省」变成「山西」
SUFFIXES = ("特别行政区", "自治区", "省", "市")

ISP_RULES = [
    ("电信", ("chinanet", "china telecom", "telecom")),
    ("联通", ("unicom", "cnc", "china169", "netcom")),
    ("移动", ("china mobile", "cmnet", "mobile")),
    ("广电", ("radio and tv", "cbn", "broadcast")),
]


def norm_region(name: str, code: str) -> str:
    if not name:
        return "未知"
    for s in SUFFIXES:
        if name.endswith(s) and len(name) > len(s):
            name = name[: -len(s)]
    # 内蒙古自治区 / 广西壮族自治区 / 宁夏回族自治区 / 新疆维吾尔自治区
    name = name.replace("壮族", "").replace("回族", "").replace("维吾尔", "")
    return name or "未知"


def norm_isp(isp: str) -> str:
    low = (isp or "").lower()
    for label, keys in ISP_RULES:
        if any(k in low for k in keys):
            return label
    return "其他"


def load_cache() -> tuple[dict, float]:
    if not GEO_CACHE.exists():
        return {}, 0.0
    try:
        payload = json.loads(GEO_CACHE.read_text(encoding="utf-8"))
        return payload.get("items", {}), payload.get("ts", 0)
    except Exception:
        return {}, 0.0


def save_cache(items: dict):
    GEO_CACHE.write_text(
        json.dumps({"ts": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8"
    )


def lookup(ips: list[str]) -> dict:
    """批量查归属地，命中缓存的不再请求。"""
    items, _ts = load_cache()
    missing = [ip for ip in ips if ip not in items]
    if missing:
        for i in range(0, len(missing), 100):
            batch = missing[i : i + 100]
            try:
                r = requests.post(GEO_URL, json=batch, timeout=25)
                for row in r.json():
                    ip = row.get("query")
                    if not ip:
                        continue
                    if row.get("status") == "success":
                        items[ip] = {
                            "code": row.get("region") or "",
                            "name": norm_region(row.get("regionName") or "", row.get("region") or ""),
                            "city": (row.get("city") or "").replace("市", ""),
                            "isp": norm_isp(row.get("isp") or ""),
                        }
                    else:
                        items[ip] = {"code": "", "name": "未知", "city": "", "isp": "其他"}
            except Exception as e:
                print(f"  [region] 归属地查询失败: {type(e).__name__}")
            if len(missing) > 100:
                time.sleep(4.5)  # 免费接口限 15 次/分钟
        save_cache(items)
    return items


def build() -> dict:
    payload = json.loads(PROXY_JSON.read_text(encoding="utf-8"))
    hosts = payload.get("hosts", [])
    channels = payload.get("channels", [])

    ips = sorted({h["h"].rsplit(":", 1)[0] for h in hosts})
    print(f"  [region] 查询 {len(ips)} 台服务器归属地")
    geo = lookup(ips)

    # host → 地区
    host_region: dict[str, str] = {}
    region_meta: dict[str, dict] = {}
    for h in hosts:
        ip = h["h"].rsplit(":", 1)[0]
        g = geo.get(ip) or {"code": "", "name": "未知", "isp": "其他"}
        code = g["code"] or "XX"
        h["r"] = code
        h["rn"] = g["name"]
        h["isp"] = g["isp"]
        host_region[h["h"]] = code
        m = region_meta.setdefault(code, {"key": code, "name": g["name"], "isps": set(), "hosts": []})
        m["isps"].add(g["isp"])
        m["hosts"].append(h["h"])

    # 统计每个地区的频道/地址数
    for code, m in region_meta.items():
        ch_keys = {c["key"] for c in channels if any(s["h"] in m["hosts"] for s in c["streams"])}
        streams = sum(
            1 for c in channels for s in c["streams"] if s["h"] in m["hosts"]
        )
        m["channels"] = len(ch_keys)
        m["streams"] = streams

    regions = []
    for code, m in region_meta.items():
        isps = sorted(m["isps"], key=lambda x: (x == "其他", x))
        regions.append(
            {
                "key": code,
                "name": m["name"],
                "isp": "/".join(isps),
                "hosts": sorted(m["hosts"]),
                "channels": m["channels"],
                "streams": m["streams"],
            }
        )
    regions.sort(key=lambda r: (-r["streams"], r["name"]))

    PROXY_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    OUT_JSON.write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "regions": regions},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  [region] {len(regions)} 个地区: " + "、".join(f"{r['name']}({r['channels']})" for r in regions))
    return {"regions": regions}


def load_regions() -> list[dict]:
    if not OUT_JSON.exists():
        return []
    try:
        return json.loads(OUT_JSON.read_text(encoding="utf-8")).get("regions", [])
    except Exception:
        return []


if __name__ == "__main__":
    build()
