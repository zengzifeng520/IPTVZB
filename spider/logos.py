# -*- coding: utf-8 -*-
"""台标解析：把频道名映射到台标 URL。

数据来源（两个中文台标库 + iptv-org）
------------------------------------
  1. yuanzl77/TVlogo    ~1034 张，中文命名为主（png/）
  2. wanglindl/TVlogo    ~934 张（img/）
  3. iptv-org logos      30501 个频道有台标（按 channel id / name 索引）

索引文件：spider/data/logo_index.json（由 tools/build_logo_index.py 生成）

匹配顺序
--------
  精确 → 剥后缀（台/频道/电视台/高清…）→ 手工别名 → 包含匹配（取最长，库名≥4字）

**找不到就返回 None，绝不猜测**——按需求「没找到的就不补」，
同时绝不动播放地址，只往 EXTINF 里加 tvg-logo 属性。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

INDEX_JSON = Path(__file__).parent / "data" / "logo_index.json"
# 台标库里找不到时，用 tools/make_composed_logos.py 自制的台标（图片在 data/logos/）
COMPOSED_JSON = Path(__file__).parent / "data" / "composed_logos.json"

# 清晰度/版本后缀，匹配前先剥掉
_SUFFIX = [
    "蓝光高清", "超高清", "高清版", "超清版", "高清", "超清", "标清", "蓝光",
    "FHD", "UHD", "4K", "8K", "HD", "SD",
]

# 手工别名：频道名（规范化后）-> 台标库里的名字
ALIAS: dict[str, str] = {
    # ---- CCTV 付费频道：库里是拼音缩写 ----
    "cctv兵器科技": "CCTVbqkj",
    "cctv世界地理": "CCTVsjdl",
    "cctv央视台球": "CCTVystq",
    "cctv女性时尚": "CCTVnxss",
    "cctv高网频道": "CCTVgefwq",
    "cctv高尔夫网球": "CCTVgefwq",
    "cctv央视精品": "CCTVyswhjp",
    "cctv央视文化精品": "CCTVyswhjp",
    "cctv风云足球": "CCTVfyzq",
    "cctv风云音乐": "CCTVfyyy",
    "cctv风云剧场": "CCTVfyjc",
    "cctv怀旧剧场": "CCTVhjjc",
    "cctv第一剧场": "CCTVdyjc",
    "cctv电影剧场": "CCTVdyjc",
    "cctv卫生健康": "CCTVwsjk",
    "cctv4欧洲": "CCTV4oz",
    "cctv4欧州": "CCTV4oz",
    "cctv4美洲": "CCTV4mz",
    "cctv4k": "CCTV4K",
    "cctv8k": "CCTV8K",
    "cctv5+": "CCTV5+",
    "cctv5plus": "CCTV5+",
    # ---- CGTN 各语种 ----
    "cgtn俄语": "CGTNey",
    "cgtn法语": "CGTNfy",
    "cgtn纪录": "CGTNjilu",
    "cgtn西语": "CGTNxbyy",
    "cgtn阿语": "CGTNalby",
    "cgtn阿拉伯语": "CGTNalby",
    "cgtn西班牙语": "CGTNxbyy",
    "cgtn俄语频道": "CGTNey",
    # ---- 教育台 ----
    "中国教育1": "CETV1",
    "中国教育2": "CETV2",
    "中国教育3": "CETV3",
    "中国教育4": "CETV4",
    "cetv1": "CETV1",
    "cetv2": "CETV2",
    "山东教育": "山东教育卫视",
    # ---- 卡通 ----
    "卡酷动画": "卡酷少儿",
    "北京卡酷动画": "北京卡酷少儿",
    # ---- 体育 ----
    "五星体育": "上海五星体育",
    "北京体育": "北京体育休闲",
    # ---- 电影 ----
    "chc影迷电影": "CHC高清电影",
    "chc家庭电影": "CHC家庭影院",
    # ---- 省级台简称（组播里常只写省名）----
    "深圳": "深圳卫视",
    "天津": "天津卫视",
    "山东": "山东卫视",
    "江苏": "江苏卫视",
    "浙江": "浙江卫视",
    "湖北": "湖北卫视",
    "湖南": "湖南卫视",
    "内蒙古": "内蒙古卫视",
    "广州": "广州综合",
    "河南": "河南卫视",
    "河北": "河北卫视",
    "广东": "广东卫视",
    "广西": "广西卫视",
    "辽宁": "辽宁卫视",
    "吉林": "吉林卫视",
    "黑龙江": "黑龙江卫视",
    "山西": "山西卫视",
    "陕西": "陕西卫视",
    "甘肃": "甘肃卫视",
    "青海": "青海卫视",
    "云南": "云南卫视",
    "贵州": "贵州卫视",
    "四川": "四川卫视",
    "安徽": "安徽卫视",
    "福建": "福建东南卫视",
    "江西": "江西卫视",
    "海南": "海南卫视",
    "宁夏": "宁夏卫视",
    "新疆": "新疆卫视",
    "西藏": "西藏卫视",
    # ---- 港澳台 ----
    "大爱": "大爱1",
    "大爱一台": "大爱1",
    "美好生活电视": "美好电视",
    "黄金翡翠台": "翡翠台",
    "亚洲剧台": "亚洲电视",
    "凤凰卫视": "凤凰卫视",
    "凤凰资讯": "凤凰资讯台",
    "动物星球": "animalplanet",
    "动物星球频道": "animalplanet",
}


def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[\(（\[【][^\)）\]】]*[\)）\]】]", "", s)
    changed = True
    while changed:
        changed = False
        for suf in _SUFFIX:
            if len(s) > len(suf) and s.upper().endswith(suf.upper()):
                s = s[: -len(suf)]
                changed = True
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "", s).lower()


@lru_cache(maxsize=1)
def _index() -> tuple[dict, dict, list]:
    """返回 (精确表, 别名表, 包含匹配用的(名,url)列表)"""
    if not INDEX_JSON.exists():
        return {}, {}, []
    raw = json.loads(INDEX_JSON.read_text(encoding="utf-8"))
    books = [raw.get("tvlogo") or {}, raw.get("wanglindl") or {}]

    exact: dict[str, str] = {}
    for book in books:
        for name, url in book.items():
            n = _norm(name)
            if not n:
                continue
            exact.setdefault(n, url)
            for suf in ("台", "频道", "电视台"):
                if len(n) > len(suf) and n.endswith(suf):
                    exact.setdefault(n[: -len(suf)], url)
                exact.setdefault(n + suf, url)

    # iptv-org 按频道名（主要给国外频道用）
    for name, url in (raw.get("iptvorgName") or {}).items():
        n = _norm(name)
        if n:
            exact.setdefault(n, url)

    alias = {}
    for k, v in ALIAS.items():
        u = exact.get(_norm(v))
        if u:
            alias[_norm(k)] = u

    # 包含匹配候选：只保留 >=4 字的名字，避免「新闻」匹配到「新闻综合」
    contain = [(n, u) for n, u in exact.items() if len(n) >= 4]
    contain.sort(key=lambda x: -len(x[0]))          # 降序：频道名包含库名，取最长的
    contain_asc = sorted(contain, key=lambda x: len(x[0]))  # 升序：库名包含频道名，取最短的
    return exact, alias, contain, contain_asc


def resolve(name: str) -> str | None:
    """频道名 -> 台标 URL；找不到返回 None（不猜）。

    顺序：精确 → 别名 → 正向包含 → 反向包含 → 自制台标。
    自制台标排在最后：现成的真实台标永远优先，只有都没有才用自制图。
    """
    exact, alias, contain, contain_asc = _index()
    n = _norm(name)
    if not n:
        return None
    if n in exact:
        return exact[n]
    if n in alias:
        return alias[n]
    # 正向：频道名里包含库名（"CCTV4欧洲" 含 "cctv4"）
    for cand, url in contain:
        if cand in n:
            return url
    # 反向：库名里包含频道名（"四川影视" ⊂ "四川影视文艺"），取最贴近的
    if len(n) >= 3:
        for cand, url in contain_asc:
            if n in cand and len(cand) <= len(n) + 8:
                return url
    # 自制台标（按原始频道名精确查，不做规范化，避免串色）
    composed = _composed()
    if name in composed:
        return composed[name]
    return None


@lru_cache(maxsize=1)
def _composed() -> dict:
    if not COMPOSED_JSON.exists():
        return {}
    try:
        return json.loads(COMPOSED_JSON.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def stats() -> dict:
    exact, alias, contain, contain_asc = _index()
    return {
        "exact": len(exact),
        "alias": len(alias),
        "composed": len(_composed()),
    }
