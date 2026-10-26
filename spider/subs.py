# -*- coding: utf-8 -*-
"""生成订阅文件：全量 + 分地区。

输出（都在 data/sub/ 下，供 GitHub Pages 直接下载）：
  all.m3u                 全量订阅（所有存活服务器）
  region/<KEY>.m3u        按中转服务器所在省份拆分
  index.json              订阅索引（前端读这个渲染）

分地区的原因：udpxy 中转服务器通常只在本省运营商网内可达，
跨省地址基本连不上，按地区拆开用户体验才好。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import config

PROXY_JSON = config.WEB_DATA_DIR / "proxy.json"
REGIONS_JSON = config.WEB_DATA_DIR / "regions.json"
SUB_DIR = config.WEB_DATA_DIR / "sub"
INDEX_JSON = SUB_DIR / "index.json"


def _extinf(ch: dict) -> str:
    return (
        f'#EXTINF:-1 tvg-name="{ch["display"]}" group-title="{ch["type"]}",{ch["display"]}'
    )


def _write(path: Path, channels: list[dict], host_set: set[str] | None = None) -> tuple[int, int]:
    """写一个 m3u，返回 (频道数, 地址数)。host_set 为空表示不限服务器。"""
    lines = ["#EXTM3U"]
    n_chan = 0
    n_stream = 0
    for ch in channels:
        picked = ch["streams"] if host_set is None else [s for s in ch["streams"] if s["h"] in host_set]
        if not picked:
            continue
        n_chan += 1
        head = _extinf(ch)
        for s in picked:
            lines.append(head)
            lines.append(s["u"])
            n_stream += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n_chan, n_stream


def build() -> dict:
    if not PROXY_JSON.exists():
        print("  [subs] 缺少 data/proxy.json，请先运行 udpxy.py")
        return {}

    proxy = json.loads(PROXY_JSON.read_text(encoding="utf-8"))
    channels = proxy.get("channels", [])
    if not channels:
        print("  [subs] proxy.json 无频道数据，跳过")
        return {}

    regions = []
    if REGIONS_JSON.exists():
        regions = json.loads(REGIONS_JSON.read_text(encoding="utf-8")).get("regions", [])

    # 全量
    n_chan, n_stream = _write(SUB_DIR / "all.m3u", channels)
    print(f"  [subs] all.m3u            {n_chan:>4} 频道 / {n_stream:>5} 条")

    # 分地区
    index_regions = []
    for r in regions:
        host_set = set(r.get("hosts") or [])
        if not host_set:
            continue
        path = SUB_DIR / "region" / f"{r['key']}.m3u"
        c, s = _write(path, channels, host_set)
        if not c:
            continue
        index_regions.append(
            {
                "key": r["key"],
                "name": r["name"],
                "isp": r.get("isp") or "",
                "sub": f"data/sub/region/{r['key']}.m3u",
                "channels": c,
                "streams": s,
                "hosts": len(host_set),
            }
        )
        print(f"  [subs] region/{r['key']:<4}       {c:>4} 频道 / {s:>5} 条  {r['name']}")

    index_regions.sort(key=lambda x: -x["streams"])
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "all": {
            "sub": "data/sub/all.m3u",
            "channels": n_chan,
            "streams": n_stream,
        },
        "regions": index_regions,
    }
    INDEX_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  [subs] 索引 {len(index_regions)} 个地区 -> {INDEX_JSON.name}")
    return payload


def main() -> None:
    build()


if __name__ == "__main__":
    main()
