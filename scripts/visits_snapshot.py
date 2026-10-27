#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""访问量快照：把公开计数器的当前值落进 data/visits.json。

用途：后台「访问统计」面板除了读计数器实时值，还会读这份仓库快照取较大值。
这样即使计数服务哪天被重置 / 挂了，总访问量也不会变小（永久累计）。
每次只写「比快照更大」的值，所以可以安全地反复运行。
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

NS = "zzf-tg-site"
API = "https://abacus.jasoncameron.dev/get/%s/" % NS
PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "visits.json")
CST = timezone(timedelta(hours=8))
KEEP_DAYS = 90


def get(key: str):
    try:
        with urllib.request.urlopen(API + key, timeout=20) as r:
            return json.load(r).get("value")
    except Exception:
        return None


def load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def maxnum(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def main() -> None:
    old = load()
    today = datetime.now(CST).date()

    days = dict(old.get("days") or {})
    duv = dict(old.get("duv") or {})

    for i in range(0, 8):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        key = d.replace("-", "")
        days[d] = maxnum(days.get(d), get("d-" + key))
        duv[d] = maxnum(duv.get(d), get("duv-" + key))

    keep = {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(KEEP_DAYS)}
    days = {k: v for k, v in days.items() if k in keep and v is not None}
    duv = {k: v for k, v in duv.items() if k in keep and v is not None}

    data = {
        "updated": datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "views": maxnum(old.get("views"), get("views")),
        "visitors": maxnum(old.get("visitors"), get("visitors")),
        "days": dict(sorted(days.items())),
        "duv": dict(sorted(duv.items())),
    }

    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("views=%s visitors=%s days=%d" % (data["views"], data["visitors"], len(days)))


if __name__ == "__main__":
    main()
