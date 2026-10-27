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
import copy
import gzip
import json
import re
import shutil
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



# ---------------------------------------------------------------- 国内频道改名
# 用户的 EPG（国内 615 个台）id 命名与我们 m3u 的频道名不完全一致：
#   我们 m3u          EPG id
#   CCTV世界地理   →   世界地理
#   CCTV兵器科技   →   兵器科技
#   中国教育1      →   中国教育1台
#   梨园频道       →   梨园
# 播放器若按名字匹配（实测酷9 就是），这些台全都显示不出节目单。
# 做法：把 EPG 的 channel id 直接**改成我们 m3u 里的名字**（同时把我们名字
# 排到 display-name 第一位），节目表的 channel 引用一并改写。
# 这样按 id 匹配、按名字匹配都命中，而且**不复制节目，文件不变大**。
STRIP_PREFIX = ["CCTV", "央视", "中央"]
STRIP_SUFFIX = ["频道", "高清", "HD", "台"]
ADD_SUFFIX = ["", "台", "频道"]


def _variants(name: str) -> list[str]:
    """频道名的候选写法，按优先级排。"""
    out = [name]
    # 去横线/空格：CCTV-1 -> CCTV1，CCTV-5+ 不变（+ 保留）
    flat = name.replace("-", "").replace("·", "").replace(" ", "")
    if flat != name:
        out.append(flat)
    # 去前缀
    for pre in STRIP_PREFIX:
        if name.upper().startswith(pre.upper()) and len(name) > len(pre) + 1:
            out.append(name[len(pre):])
    # 去后缀
    for suf in STRIP_SUFFIX:
        if name.upper().endswith(suf.upper()) and len(name) > len(suf) + 1:
            out.append(name[: -len(suf)])
            # 去前缀 + 去后缀
            for pre in STRIP_PREFIX:
                if name.upper().startswith(pre.upper()) and len(name) > len(pre) + len(suf) + 1:
                    out.append(name[len(pre): -len(suf)])
    return out


def _resolve(name: str, ids: set[str], dn2id: dict[str, str]) -> str | None:
    """我们的频道名 -> EPG 里的 id；找不到返回 None（不瞎猜）。"""
    if name in ids:
        return name
    if name in dn2id:
        return dn2id[name]
    for v in _variants(name):
        if v in ids:
            return v
        if v in dn2id:
            return dn2id[v]
        for suf in ADD_SUFFIX:
            if suf and (v + suf) in ids:
                return v + suf
    return None


def load_our_names() -> list[str]:
    """从三个地址池里取我们 m3u 用的频道名。"""
    names: list[str] = []
    seen: set[str] = set()
    for f in ["data/proxy.json", "data/proxy_hotel.json"]:
        fp = ROOT / f
        if not fp.exists():
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for c in d.get("channels") or []:
            nm = (c.get("display") or c.get("key") or "").strip()
            if nm and nm not in seen:
                seen.add(nm)
                names.append(nm)
    return names


def fetch(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- 时区归一 + 去重
# 用户反馈「有些台的节目单对不上现在播的节目」，排查出两个坑：
#
# 坑一：时区标错。epg.pw 的港澳台、以及国内 e.xml 里一部分上游，节目时间写的
#   其实是**当地钟点**（翡翠台 06:00 香港早晨 / 13:00 午间新闻 / 23:15 晚间新闻，
#   CCTV-1 12:00 新闻30分、19:00 新闻联播），但 offset 字段却写成 +0000。
#   播放器按 +0000 解析再换算成北京时间，整张表往后挪 8 小时 ——
#   晚上 8 点看到的是中午的节目名，自然全对不上。
#   处理：数值一个不动，offset 统一改写成 +0800。
#
# 坑二：同一个频道挂了几套节目。国内 e.xml 是多个上游合并出来的，像东方卫视
#   同时有一份正常节目单（东方新闻 18:00 / 转播中央台新闻联播 19:00 / 画梦录 19:30）
#   和一份粗糙节目单（「电视剧：xxx」，时间还歪 2 分钟），两套在时间上互相重叠。
#   播放器先撞到哪套全看运气，重叠处就显示错的节目。
#   处理：同一频道的节目按「时间不重叠」切分成若干套，只留一套
#   （窗口内覆盖时长最长，一样长时挑节目名信息量大的），再用其它套补 60 分钟以上的空洞。
_GENERIC = {
    "电视剧", "电影", "剧场", "动画片", "纪录片", "广告", "节目预告",
    "电视台无节目", "精彩看点", "栏目", "节目", "上午剧场", "下午剧场",
    "晚间剧场", "午夜剧场", "周末剧场", "黄金剧场", "电视剧场",
}
_GENERIC_PREFIX = ("电视剧：", "电视剧:", "电影：", "电影:")


def _wall(s: str) -> tuple[str, "object"]:
    """'20261027193000 +0000' -> (数值字符串, 当作北京时间解析的 datetime)"""
    from datetime import datetime as _dt
    num = (s or "").strip().split(" ")[0]
    return num, _dt.strptime(num, "%Y%m%d%H%M%S")


def _quality(title: str) -> int:
    t = (title or "").strip()
    if not t or t in _GENERIC or t.startswith(_GENERIC_PREFIX):
        return 0
    return 1


def _normalize_and_dedupe(tv: ET.Element) -> None:
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    cst = _tz(_td(hours=8))
    today = _dt.now(cst).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    win_s, win_e = today - _td(days=1), today + _td(days=3)

    by_ch: dict[str, list[tuple]] = {}
    fixed = bad = 0
    for pr in list(tv.findall("programme")):
        try:
            st, a = _wall(pr.get("start") or "")
            _, b = _wall(pr.get("stop") or "")
        except ValueError:
            tv.remove(pr)
            bad += 1
            continue
        if b <= a:
            tv.remove(pr)
            bad += 1
            continue
        if (pr.get("start") or "").strip() != f"{st} +0800":
            fixed += 1
        pr.set("start", f"{st} +0800")
        pr.set("stop", f"{b:%Y%m%d%H%M%S} +0800")
        by_ch.setdefault(pr.get("channel") or "", []).append(
            (a, b, (pr.findtext("title") or "").strip(), pr))

    drop: list[ET.Element] = []
    kept = 0
    for items in by_ch.values():
        items.sort(key=lambda x: (x[0], x[1]))
        # 1) 区间着色：同一套里的节目时间互不重叠
        sets: list[dict] = []
        for it in items:
            for s in sets:
                if s["end"] <= it[0]:
                    s["items"].append(it)
                    s["end"] = it[1]
                    break
            else:
                sets.append({"items": [it], "end": it[1]})

        # 2) 选一套：输出窗口内覆盖时长 → 节目名信息量 → 条数
        def score(s):
            mins = q = n = 0
            for a, b, t, _ in s["items"]:
                lo, hi = max(a, win_s), min(b, win_e)
                if hi > lo:
                    mins += (hi - lo).total_seconds() / 60
                    q += _quality(t)
                    n += 1
            return (round(mins / 60), round(q / n, 2) if n else 0.0, n)

        sets.sort(key=score, reverse=True)
        keep = list(sets[0]["items"])

        # 3) 其它套补空洞（只补 60 分钟以上的空档，避免又混进另一套的时间线）
        def gaps(occ):
            return [(occ[i - 1][1], occ[i][0])
                    for i in range(1, len(occ))
                    if (occ[i][0] - occ[i - 1][1]).total_seconds() > 3600]

        for s in sets[1:]:
            occ = sorted((a, b) for a, b, _, _ in keep)
            for g_lo, g_hi in gaps(occ):
                for it in s["items"]:
                    if it[0] >= g_lo and it[1] <= g_hi:
                        keep.append(it)

        keep_ids = {id(it[3]) for it in keep}
        for it in items:
            if id(it[3]) not in keep_ids:
                drop.append(it[3])
        kept += len(keep)

    for el in drop:
        tv.remove(el)
    print(f"  时区归一 {fixed} 条（→ +0800），去掉重复/过期节目 {len(drop)} 条，"
          f"保留 {kept} 条" + (f"，异常节目 {bad} 条" if bad else ""))

    # 自检：以后有人改这段代码、或者上游又换格式，这里会在 Actions 日志里报警，
    # 而不是又变成「有些台对不上」让用户在播放器里发现。
    left_tz = sum(1 for pr in tv.findall("programme")
                  if (pr.get("start") or "").strip().split()[-1] != "+0800")
    left_ov = 0
    per: dict[str, list] = {}
    for pr in tv.findall("programme"):
        try:
            _, a = _wall(pr.get("start") or "")
            _, b = _wall(pr.get("stop") or "")
        except ValueError:
            continue
        per.setdefault(pr.get("channel") or "", []).append((a, b))
    for v in per.values():
        v.sort()
        end = None
        for a, b in v:
            if end and a < end - _td(minutes=1):
                left_ov += 1
            end = max(end, b) if end else b
    if left_tz or left_ov:
        print(f"  ⚠ 自检未通过：非 +0800 残留 {left_tz} 条 / 重叠 {left_ov} 处")
    else:
        print("  自检通过：时区全部 +0800，同频道无重叠节目")


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

    # ★ 关键：把**我们 m3u 里的频道名放到 display-name 的第一个**。
    # 原因（实测踩到的坑）：epg.pw 原名是繁体（亞洲劇台 / 民視 / 大愛電視），
    # 我们 m3u 用简体（亚洲剧台 / 民视 / 大爱）。酷9 这类播放器只取
    # `<display-name>` 的**第一个**做匹配，繁简一差就全对不上——
    # 用户实测 64 个台只有 10 个能显示节目单，正好是名字本来就相同的
    # 英文台（SUPER Music / ZooMoo / Thrill / ROCK Action）+ 翡翠台。
    # 做法：删掉原有 display-name，按「我们的名字在前、原名在后」重排，
    # 并放回 channel 的第一个子元素位置（有些解析器只看第一个子元素）。
    reordered = 0
    for ch in channels:
        cid = ch.get("id") or ""
        ours = rev.get(cid) or []
        if not ours:
            continue
        olds = ch.findall("display-name")
        order: list[str] = []
        for nm in ours:
            if nm and nm not in order:
                order.append(nm)
        for d in olds:
            t = (d.text or "").strip()
            if t and t not in order:
                order.append(t)
        for d in olds:
            ch.remove(d)
        for i, nm in enumerate(order):
            el = ET.Element("display-name", {"lang": "zh"})
            el.text = nm
            ch.insert(i, el)
        reordered += 1
    if reordered:
        print(f"  重排 display-name {reordered} 个频道（简体名在前）")

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
    # ---- 国内频道改名（把 EPG id 换成我们 m3u 的频道名）----
    our_names = load_our_names()
    base_ids = set(base_ch.keys())
    dn2id: dict[str, str] = {}
    for cid, ch in base_ch.items():
        for d in ch.findall("display-name"):
            t = (d.text or "").strip()
            if t:
                dn2id.setdefault(t, cid)
    renamed_ch: list[ET.Element] = []   # 改过名的 channel（必须单独收着，pop 出来要放回去）
    rename: dict[str, str] = {}      # 原 id -> 我们的名字
    used: set[str] = set()
    for nm in our_names:
        if nm in base_ids:               # 已经是同名，不用改
            continue
        cid = _resolve(nm, base_ids, dn2id)
        if cid and cid not in rename and nm not in used:
            rename[cid] = nm
            used.add(nm)
    for cid, nm in rename.items():
        ch = base_ch.pop(cid)
        ch.set("id", nm)
        renamed_ch.append(ch)
        # 我们的名字放 display-name 第一位
        olds = ch.findall("display-name")
        order = [nm]
        for d in olds:
            t = (d.text or "").strip()
            if t and t not in order:
                order.append(t)
        for d in olds:
            ch.remove(d)
        for i, x in enumerate(order):
            el = ET.Element("display-name", {"lang": "zh"})
            el.text = x
            ch.insert(i, el)
    if rename:
        moved = 0
        for pr in base_pr:
            new = rename.get(pr.get("channel") or "")
            if new:
                pr.set("channel", new)
                moved += 1
        print(f"  国内频道改名 {len(rename)} 个，改写节目 {moved} 条")

    # ★ 别名频道方案：每个港澳台台单独生成一个 **id 就是频道名** 的 EPG 条目。
    # 为什么不用 epg.pw 的数字 id：
    #   - 播放器按 tvg-id 匹配 → tvg-id 写频道名也能命中
    #   - 播放器按频道名匹配 → display-name 就是同一个字符串，必然命中
    #   - 播放器只读第一个 display-name → 别名条目的第一个就是我们的名字
    #   - 一个 id 挂多个名字（美亚电影台 / 美亚电影台原声 同为 368348）也能分开
    # 代价是节目要复制一份，11k 条变 22k 条，gz 只大 2~3 百 KB，可接受。
    by_id = {ch.get("id"): ch for ch in channels}
    groups: dict[str, list] = {}
    for pr in programmes:
        groups.setdefault(pr.get("channel") or "", []).append(pr)

    alias_ch: list[ET.Element] = []
    alias_pr: list[ET.Element] = []
    no_data: list[str] = []
    for our, cid in ch_map.items():
        src = by_id.get(cid)
        if src is None:
            no_data.append(our)
            continue
        nc = copy.deepcopy(src)
        nc.set("id", our)
        alias_ch.append(nc)
        for pr in groups.get(cid, []):
            p2 = copy.deepcopy(pr)
            p2.set("channel", our)
            alias_pr.append(p2)
    print(f"  别名频道 {len(alias_ch)} 个 / {len(alias_pr)} 条节目"
          f"（无数据 {len(no_data)} 个：{'、'.join(no_data[:8])}）")

    # 用户自己的国内 EPG 在前（港澳台同名 id 跳过，避免重复）
    alias_ids = {c.get("id") for c in alias_ch}
    for cid, ch in base_ch.items():
        if cid not in alias_ids:
            tv.append(ch)
    # 改过名的国内频道（之前 pop 出来忘了放回，导致「世界地理/兵器科技」等直接消失）
    for ch in renamed_ch:
        if ch.get("id") not in alias_ids:
            tv.append(ch)
    for ch in alias_ch:
        tv.append(ch)
    for pr in base_pr:
        if pr.get("channel") not in alias_ids:
            tv.append(pr)
    for pr in alias_pr:
        tv.append(pr)

    # ---- 时区归一 + 每频道只留一套节目 ----
    _normalize_and_dedupe(tv)

    # ---- 瘦身：播放器解析 13.5MB XML 很慢（实测要几十秒）----
    # 体积构成：<desc>（节目简介）占 9.3MB / 13.5MB = 69%，但对播放器列表毫无用处
    # （只显示节目名+时间）。删掉它，文件直接砍到 4MB 左右。
    # 同时只保留 [今天-1天, 今天+2天] 的节目，7 天改 4 天。
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    _cst = _tz(_td(hours=8))
    _today = _dt.now(_cst).date()
    allowed_dates = {(_today + _td(days=d)).strftime("%Y%m%d") for d in (-1, 0, 1, 2)}

    dropped_desc = dropped_pr = 0
    keep_ids: set[str] = set()
    for pr in list(tv.findall("programme")):
        st = pr.get("start") or ""
        if st[:8] and st[:8] not in allowed_dates:
            tv.remove(pr)
            dropped_pr += 1
            continue
        keep_ids.add(pr.get("channel") or "")
        for child in list(pr):
            if child.tag != "title":
                pr.remove(child)
                dropped_desc += 1
    # 没有任何节目的 channel 也删掉（播放器不用为空台保留槽位）
    dropped_ch = 0
    for ch in list(tv.findall("channel")):
        if (ch.get("id") or "") not in keep_ids:
            tv.remove(ch)
            dropped_ch += 1
    print(f"  瘦身：删节目 {dropped_pr} 条（超出日期窗口）、"
          f"删子元素 {dropped_desc} 个（desc 等）、删空频道 {dropped_ch} 个")

    xml = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
    out_gz = Path(out_base + ".gz") if out_base else OUT_GZ
    out_gz.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out_gz, "wb", compresslevel=9) as f:
        f.write(xml)
    if out_base:
        Path(out_base).write_bytes(xml)

    # 再写一份到站点根目录，给播放器用的**短地址**：
    #   https://zzf.new.tg/epg.xml.gz
    # data/public/epg.xml.gz 那边保留（路径稳定，历史订阅可能引用）
    short = ROOT / "epg.xml.gz"
    try:
        shutil.copyfile(out_gz, short)
        print(f"  短地址 -> {short.name}  {short.stat().st_size/1024:.0f}KB")
    except Exception as e:  # noqa: BLE001
        print(f"  短地址写入失败：{e}")

    # 再给一份**未压缩**的 epg.xml：部分播放器/电视盒子不认 .gz
    #   短地址 https://zzf.new.tg/epg.xml
    try:
        plain = ROOT / "epg.xml"
        plain.write_bytes(xml)
        print(f"  短地址 -> {plain.name}  {plain.stat().st_size/1024/1024:.1f}MB（未压缩）")
    except Exception as e:  # noqa: BLE001
        print(f"  epg.xml 写入失败：{e}")

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
