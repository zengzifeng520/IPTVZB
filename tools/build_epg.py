# -*- coding: utf-8 -*-
"""给港澳台频道生成 EPG（电视节目单）。

数据来源
--------
epg.pw（就是我们港澳台部分源站用的那个站），提供分地区 XMLTV：
  https://epg.pw/xmltv/epg_HK.xml   香港 230 个频道
  https://epg.pw/xmltv/epg_TW.xml   台湾 519 个频道
实测 2026-10-27 可用，节目覆盖 7 天。

为什么自己生成而不是直接用 epg.pw 地址
----------------------------------
1. 播放器只吃一个 EPG 地址，而我们需要 HK + TW 两份
2. epg.pw 原文件带 749 个频道、几十 MB，我们只要其中 38 个
3. 放自己站上不受第三方可用性影响

流程
----
拉 HK + TW XML（流式解析，不吃内存）
  -> 只保留 CH_MAP 里映射到的频道（channel + 对应 programme）
  -> 输出 data/public/epg.xml.gz

频道映射（CH_MAP）
----------------
是我们频道名 -> epg.pw channel id 的手工对照表，见 spider/data/epg_map.json。
没映射到的频道就是 epg.pw 确实没有节目单，m3u 里不加 tvg-id，
播放器显示「无节目信息」——这是正常情况，不要硬凑。

用法
----
  python tools/build_epg.py
  python tools/build_epg.py --days 7
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # site_repo
MAP_JSON = ROOT / "spider" / "data" / "epg_map.json"
OUT_GZ = ROOT / "data" / "public" / "epg.xml.gz"

SOURCES = [
    "https://epg.pw/xmltv/epg_HK.xml",
    "https://epg.pw/xmltv/epg_TW.xml",
]

# 用户自己的 EPG（国内频道为主，615 个频道，港澳台只有 3 个）
# 仓库 zengzifeng520/IPTV 的 gh-pages 分支。raw.githubusercontent 国内不通，
# 走 jsdelivr（实测 200 / 702KB）。
BASE_EPG = "https://gcore.jsdelivr.net/gh/zengzifeng520/IPTV@gh-pages/e.xml.gz"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def build(days: int = 7, base_file: str = "", out_base: str = "") -> None:
    if not MAP_JSON.exists():
        print(f"  缺少映射表 {MAP_JSON}")
        return
    ch_map = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    want = set(ch_map.values())
    print(f"  需要 {len(want)} 个频道（来自 {len(ch_map)} 条映射）")

    channels: list[ET.Element] = []
    programmes: list[ET.Element] = []
    got: set[str] = set()

    for url in SOURCES:
        try:
            raw = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"  {url.split('/')[-1]} 拉取失败：{type(e).__name__}")
            continue
        print(f"  {url.split('/')[-1]}  {len(raw)/1024/1024:.1f}MB")
        try:
            root = ET.fromstring(raw)
        except Exception as e:  # noqa: BLE001
            print(f"    解析失败：{e}")
            continue
        for ch in root.findall("channel"):
            cid = ch.get("id")
            if cid in want:
                channels.append(ch)
                got.add(cid)
        for pr in root.findall("programme"):
            if pr.get("channel") in want:
                programmes.append(pr)

    if not channels:
        print("  一个频道都没匹配到，放弃生成")
        return

    # 关键：给每个 channel 补上我们 m3u 里用的**简体频道名**。
    # epg.pw 的 display-name 是繁体（亞洲劇台 / 民視 / 大愛電視），
    # 而我们 m3u 是简体。播放器（酷9 这类）如果按频道名匹配而不是 tvg-id，
    # 简体频道就会全部匹配不上 —— 实测用户反馈「只有一部分频道有节目单」。
    # XMLTV 允许一个 channel 挂多个 display-name，所以把简体名追加进去，
    # 按 id 匹配和按名字匹配都能命中。
    rev: dict[str, list[str]] = {}
    for our_name, cid in ch_map.items():
        rev.setdefault(cid, []).append(our_name)
    added = 0
    for ch in channels:
        cid = ch.get("id") or ""
        exist = {(d.text or "").strip() for d in ch.findall("display-name")}
        for nm in rev.get(cid, []):
            if nm and nm not in exist:
                ET.SubElement(ch, "display-name").text = nm
                added += 1
        # channel 一般还带 icon 子元素，SubElement 会把 display-name 放到
        # icon 后面；XMLTV 对顺序无要求，播放器都能解析
    if added:
        print(f"  追加简体名 {added} 个")

    # 先并入已有的国内节目单：优先用本地文件（--base），没有再走网络
    base_ch: dict[str, ET.Element] = {}
    base_pr: list[ET.Element] = []
    try:
        if base_file and Path(base_file).exists():
            raw = Path(base_file).read_bytes()
            if base_file.endswith(".gz"):
                import gzip as _gz
                raw = _gz.decompress(raw)
            print(f"  读本地国内节目单 {base_file}  {len(raw)/1024/1024:.1f}MB")
        else:
            raw = fetch(BASE_EPG, timeout=120)
            import gzip as _gz
            if BASE_EPG.endswith(".gz"):
                raw = _gz.decompress(raw)
        broot = ET.fromstring(raw)
        for ch in broot.findall("channel"):
            base_ch[ch.get("id") or ""] = ch
        base_pr = list(broot.findall("programme"))
        print(f"  并入用户 EPG：{len(base_ch)} 频道 / {len(base_pr)} 条节目")
    except Exception as e:  # noqa: BLE001
        print(f"  用户 EPG 拉取失败（{type(e).__name__}），只输出港澳台部分")

    tv = ET.Element("tv", {
        "generator-info-name": "zzf.new.tg",
        "generator-info-url": "https://zzf.new.tg/",
    })
    # 用户频道在前，港澳台同名 id 覆盖
    for cid, ch in base_ch.items():
        if cid not in got:
            tv.append(ch)
    for ch in channels:
        tv.append(ch)
    for pr in base_pr:
        if pr.get("channel") not in got:
            tv.append(pr)
    for pr in programmes:
        tv.append(pr)

    xml = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
    out_gz = Path(out_base + ".gz") if out_base else OUT_GZ
    out_gz.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_gz, "wb", compresslevel=9) as f:
        f.write(xml)
    if out_base:
        Path(out_base).write_bytes(xml)

    miss = want - got
    total_ch = len(channels) + len([c for c in base_ch if c not in got])
    print(f"  合并后 {total_ch} 频道，港澳台 {len(channels)} 个 / {len(programmes)} 条节目"
          f"  -> {out_gz.name}  {out_gz.stat().st_size/1024:.0f}KB")
    if miss:
        print(f"  未取到节目单的 id：{','.join(sorted(miss))}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--base", default="", help="已有的国内节目单文件（.xml/.xml.gz）")
    ap.add_argument("--out", default="", help="输出路径前缀（不带后缀），留空写到本站 public")
    args = ap.parse_args()
    t0 = time.time()
    print("[epg] 开始生成节目单")
    build(args.days, args.base, args.out)
    print(f"[epg] 用时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
