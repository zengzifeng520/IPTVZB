#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把数据库里的检测结果编译成前端可用的 JSON + 订阅文件。"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

import config
import normalize
import store

CATEGORY_ORDER = [
    "央视频道", "卫视频道", "体育频道", "影视频道", "电影频道", "电视剧频道",
    "少儿频道", "纪实频道", "主题频道", "港澳频道", "国教频道", "明星频道",
    "数字频道", "地方频道",
]
CATEGORY_ALIAS = {
    "央视频道": "央视",
    "卫视频道": "卫视",
    "体育频道": "体育",
    "影视频道": "影视",
    "电影频道": "电影",
    "电视剧频道": "剧场",
    "少儿频道": "少儿",
    "纪实频道": "纪实",
    "主题频道": "主题",
    "港澳频道": "港澳",
    "国教频道": "国教",
    "明星频道": "明星",
    "数字频道": "数字",
    "地方频道": "地方",
}


def quality_label(w: int, h: int) -> str:
    if w >= 3800 or h >= 2100:
        return "8K"
    if w >= 2500 or h >= 1400:
        return "4K"
    if w >= 1900 or h >= 1000:
        return "1080P"
    if w >= 1200 or h >= 700:
        return "720P"
    if w > 0:
        return "SD"
    return "HLS"


def build_web_data(db_path: Path | None = None) -> dict:
    matcher = normalize.load_matcher(config.CATEGORIES_PATH)
    rows = store.healthy_streams(db_path=db_path)

    # 频道 -> 源列表
    grouped: dict[str, list[dict]] = defaultdict(list)
    seen_url: set[str] = set()
    for r in rows:
        if r["url"] in seen_url:
            continue
        seen_url.add(r["url"])
        grouped[r["channel"]].append(r)

    channels = []
    for key, streams in grouped.items():
        meta = matcher.get(key)
        if meta:
            ch_type = meta.get("type", "其他")
            logo = meta.get("logo") or ""
        else:
            # 字典外的频道都是地方台兜底收进来的
            ch_type = "地方频道"
            logo = ""
        # 排序：有 CORS > 清晰度高 > 速度快
        streams.sort(key=lambda s: (s["cors"], s["width"] * s["height"], s["speed"]), reverse=True)
        streams = streams[: config.MAX_STREAMS_PER_CHANNEL]
        best = streams[0]
        channels.append(
            {
                "key": key,
                "name": key,
                "display": normalize.display_name(key),
                "type": ch_type,
                "logo": logo,
                "best": {
                    "w": best["width"],
                    "h": best["height"],
                    "fps": round(best["fps"], 1),
                    "speed": best["speed"],
                    "cors": bool(best["cors"]),
                    "q": quality_label(best["width"], best["height"]),
                },
                "streams": [
                    {
                        "url": s["url"],
                        "w": s["width"],
                        "h": s["height"],
                        "fps": round(s["fps"], 1),
                        "speed": s["speed"],
                        "cors": bool(s["cors"]),
                        "q": quality_label(s["width"], s["height"]),
                        "host": s["host"],
                    }
                    for s in streams
                ],
            }
        )

    # 分类聚合
    by_type: dict[str, list[dict]] = defaultdict(list)
    for ch in channels:
        by_type[ch["type"]].append(ch)
    categories = []
    for t in CATEGORY_ORDER:
        items = by_type.get(t)
        if not items:
            continue
        items.sort(key=lambda c: _channel_sort_key(c["key"]))
        categories.append(
            {
                "key": t,
                "name": CATEGORY_ALIAS.get(t, t),
                "count": len(items),
                "streams": sum(len(c["streams"]) for c in items),
                "channels": [c["key"] for c in items],
            }
        )
    # 兜底：不在预设顺序里的分类
    for t, items in by_type.items():
        if t in CATEGORY_ORDER:
            continue
        items.sort(key=lambda c: c["key"])
        categories.append(
            {
                "key": t,
                "name": t,
                "count": len(items),
                "streams": sum(len(c["streams"]) for c in items),
                "channels": [c["key"] for c in items],
            }
        )

    # 输出顺序 = 分类顺序 + 分类内频道序，前端直接按数组顺序渲染
    type_rank = {t: i for i, t in enumerate(CATEGORY_ORDER)}
    channels.sort(key=lambda c: (type_rank.get(c["type"], 99), _channel_sort_key(c["key"])))

    total_streams = sum(len(c["streams"]) for c in channels)
    payload = {
        "site": {"name": config.SITE_NAME, "desc": config.SITE_DESC},
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "channels": len(channels),
            "streams": total_streams,
            "fhd": sum(1 for c in channels if c["best"]["w"] >= 1900),
            "uhd": sum(1 for c in channels if c["best"]["w"] >= 2500),
            "cors": sum(1 for c in channels if c["best"]["cors"]),
        },
        "categories": categories,
        "channels": channels,
    }
    return payload


def _channel_sort_key(key: str) -> tuple:
    """让 CCTV-1..17 按数字排，其余按字典序。"""
    import re

    m = re.fullmatch(r"CCTV(\d+)(\+?)", key)
    if m:
        return (0, int(m.group(1)), m.group(2))
    m = re.fullmatch(r"CCTV(4|8)K", key)
    if m:
        return (0, int(m.group(1)) + 0.5, "K")
    return (1, key, "")


def write_json(payload: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "channels.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def write_m3u(payload: dict, out_dir: Path, name: str = "playlist.m3u") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    lines = ['#EXTM3U x-tvg-url=""']
    for cat in payload["categories"]:
        for key in cat["channels"]:
            ch = next((c for c in payload["channels"] if c["key"] == key), None)
            if not ch:
                continue
            for s in ch["streams"]:
                q = s["q"]
                label = f'{ch["display"]}'
                lines.append(
                    f'#EXTINF:-1 tvg-name="{ch["display"]}" tvg-logo="{ch["logo"]}" '
                    f'group-title="{cat["key"]}",{label} [{q}]'
                )
                lines.append(s["url"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_txt(payload: dict, out_dir: Path, name: str = "playlist.txt") -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    lines = []
    for cat in payload["categories"]:
        lines.append(f'{cat["key"]},#genre#')
        for key in cat["channels"]:
            ch = next((c for c in payload["channels"] if c["key"] == key), None)
            if not ch:
                continue
            for s in ch["streams"]:
                lines.append(f'{ch["display"]}[{s["q"]}],{s["url"]}')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> dict:
    payload = build_web_data()
    j = write_json(payload, config.WEB_DATA_DIR)
    m = write_m3u(payload, config.WEB_DATA_DIR)
    t = write_txt(payload, config.WEB_DATA_DIR)
    st = payload["stats"]
    print(
        f"[build] 频道 {st['channels']} 个 / 源 {st['streams']} 条 "
        f"(1080P+ {st['fhd']}, 4K+ {st['uhd']}, 可网页播放 {st['cors']})"
    )
    for p in (j, m, t):
        print(f"        -> {p}  ({p.stat().st_size/1024:.1f} KB)")
    return payload


if __name__ == "__main__":
    main()
