#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开直播源抓取与解析。

支持两种格式：
  * M3U/M3U8  —— #EXTINF 属性行 + 下一行地址，兼容 #EXTGRP 分组
  * TXT       —— "频道名,地址" 每行一条，"分组名,#genre#" 作为分节
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
import urllib3

import config

urllib3.disable_warnings()

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass
class RawEntry:
    name: str
    url: str
    logo: str = ""
    group: str = ""
    source_id: str = ""
    weight: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def url_hash(self) -> str:
        return hashlib.md5(self.url.strip().encode("utf-8")).hexdigest()


def _clean_name(name: str) -> str:
    name = name.strip().strip('"').strip(",")
    # 去掉分辨率标注 "(720p)" "[HD]" 等
    name = re.sub(r"[\(（\[【]\s*(?:\d{3,4}[pi]|hd|sd|fhd|uhd|4k|8k)[^\)）\]】]*[\)）\]】]",
                  "", name, flags=re.I)
    return name.strip()


def parse_m3u(text: str, source_id: str = "", weight: int = 0) -> list[RawEntry]:
    entries: list[RawEntry] = []
    lines = text.splitlines()
    pending: dict | None = None
    group_hint = ""

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTM3U"):
            continue
        if line.upper().startswith("#EXTINF"):
            attrs = dict(ATTR_RE.findall(line))
            # 逗号后的部分是展示名
            tail = line.rsplit(",", 1)[-1] if "," in line else ""
            name = attrs.get("tvg-name") or _clean_name(tail)
            pending = {
                "name": _clean_name(name),
                "logo": attrs.get("tvg-logo", ""),
                "group": attrs.get("group-title", "") or group_hint,
                "attrs": attrs,
            }
            continue
        if line.upper().startswith("#EXTGRP:"):
            group_hint = line.split(":", 1)[1].strip()
            continue
        if line.startswith("#"):
            continue
        # 这是一条地址行
        if pending is None:
            continue
        url = line.split("|", 1)[0].strip()
        entries.append(
            RawEntry(
                name=pending["name"],
                url=url,
                logo=pending["logo"],
                group=pending["group"],
                source_id=source_id,
                weight=weight,
            )
        )
        pending = None
    return entries


def parse_txt(text: str, source_id: str = "", weight: int = 0) -> list[RawEntry]:
    entries: list[RawEntry] = []
    group = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#genre#" in line:
            group = line.split(",")[0].strip()
            continue
        if "," not in line:
            continue
        parts = [p.strip() for p in line.split(",", 1)]
        if len(parts) != 2:
            continue
        name, url = parts
        if "://" not in url:
            continue
        entries.append(RawEntry(name=_clean_name(name), url=url, group=group,
                                source_id=source_id, weight=weight))
    return entries


def _fetch(url: str, timeout: int = config.FETCH_TIMEOUT) -> str | None:
    try:
        r = requests.get(
            url,
            headers={"User-Agent": config.FETCH_UA, "Accept": "*/*"},
            timeout=timeout,
            verify=False,
            allow_redirects=True,
        )
        if r.status_code != 200 or not r.content:
            return None
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except requests.RequestException:
        return None


def fetch_source(src: dict, cache_dir: Path | None = None, use_cache: bool = False) -> list[RawEntry]:
    """抓取单个源，自动尝试镜像。"""
    sid = src["id"]
    url = src["url"]
    cache_file = (cache_dir / f"{sid}.txt") if cache_dir else None

    if use_cache and cache_file and cache_file.exists():
        text = cache_file.read_text(encoding="utf-8", errors="ignore")
        print(f"  [{sid}] 命中本地缓存 ({len(text)} 字符)")
    else:
        text = None
        candidates = []
        if src.get("mirrored"):
            for prefix in config.GH_MIRRORS:
                candidates.append(prefix + url)
        else:
            candidates.append(url)
            for prefix in config.GH_MIRRORS:
                if prefix:
                    candidates.append(prefix + url)
        for cand in candidates:
            body = _fetch(cand)
            if body and ("#EXTINF" in body or "://" in body) and len(body) > 200:
                text = body
                print(f"  [{sid}] 抓取成功 <- {cand[:72]}... ({len(body)} 字符)")
                break
            print(f"  [{sid}] 失败 <- {cand[:72]}")
        if text is None:
            print(f"  [{sid}] 所有镜像均不可用，跳过")
            return []
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text, encoding="utf-8", errors="ignore")

    if url.endswith(".txt"):
        parsed = parse_txt(text, sid, src.get("weight", 0))
    else:
        parsed = parse_m3u(text, sid, src.get("weight", 0))
        if not parsed:
            parsed = parse_txt(text, sid, src.get("weight", 0))
    print(f"  [{sid}] 解析出 {len(parsed)} 条源")
    return parsed


def fetch_all(use_cache: bool = False) -> list[RawEntry]:
    all_entries: list[RawEntry] = []
    cache_dir = config.CACHE_DIR
    for src in config.SOURCES + config.DIRECT_SOURCES:
        t0 = time.time()
        try:
            entries = fetch_source(src, cache_dir, use_cache)
        except Exception as e:  # noqa: BLE001
            print(f"  [{src['id']}] 异常: {e}")
            entries = []
        print(f"  [{src['id']}] 耗时 {time.time()-t0:.1f}s")
        all_entries.extend(entries)
    return all_entries


if __name__ == "__main__":
    res = fetch_all()
    print(f"\n合计 {len(res)} 条原始源")
    from collections import Counter

    print("协议分布:", Counter(u.url.split("://")[0] for u in res).most_common(8))
    print("分组抽样:", Counter(u.group for u in res).most_common(10))
    for e in res[:8]:
        print(" ", e.name, "|", e.url[:60], "|", e.group)
