#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从参考项目的 iptv_data.sql 中提取频道别名字典，转换为 categories.json。

原表 iptv_category 结构：id, name, type, enable, psw(别名列表,逗号分隔), logo
输出：[{id, name, type, aliases: [...]}]
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT.parent / "ref_spider" / "data" / "iptv_data.sql"
OUT_PATH = ROOT / "data" / "categories.json"

# 已知的字典污染：CCTV4K 的别名里误塞了"中央1"，会导致 CCTV1 的源被误判成 4K
FIXUPS = {
    "CCTV4K": ["CCTV4K", "CCTV-4K", "CCTV4K50p", "CCTV4K超高清", "中央4k", "中央4K"],
}

# 分类修正：原表把 CGTN 系列放在"国教频道"，实际是央视下属的国际频道
TYPE_FIX = {
    "CGTN": "央视频道",
    "CGTN法语": "央视频道",
    "CGTN俄语": "央视频道",
    "CGTN阿语": "央视频道",
    "CGTN西语": "央视频道",
    "CGTN纪录": "央视频道",
}

ROW_RE = re.compile(
    r"INSERT INTO `iptv_category` VALUES \(\s*(\d+),\s*'([^']*)',\s*'([^']*)',\s*(\d+),\s*'([^']*)',\s*(NULL|'[^']*')\s*\)"
)


def main() -> None:
    text = SQL_PATH.read_text(encoding="utf-8", errors="ignore")
    rows = []
    for m in ROW_RE.finditer(text):
        cid, name, ctype, enable, psw, logo = m.groups()
        if enable != "1":
            continue
        aliases = FIXUPS.get(name)
        if aliases is None:
            aliases = [a.strip() for a in psw.split(",") if a.strip()]
        # 去重并保证主名在首位
        seen, cleaned = set(), []
        for a in [name, *aliases]:
            if a and a not in seen:
                seen.add(a)
                cleaned.append(a)
        rows.append(
            {
                "id": int(cid),
                "name": name,
                "type": TYPE_FIX.get(name, ctype),
                "aliases": cleaned,
                "logo": logo.strip("'") if logo != "NULL" else None,
            }
        )

    # 合并补充字典（原项目缺失的高频知名频道）
    extra_path = ROOT / "data" / "extra_channels.json"
    if extra_path.exists():
        extra = json.loads(extra_path.read_text(encoding="utf-8")).get("channels", [])
        existing = {r["name"] for r in rows}
        base_id = 900000
        for i, item in enumerate(extra):
            if item["name"] in existing:
                continue
            aliases = [item["name"], *[a for a in item.get("aliases", []) if a != item["name"]]]
            seen_e, cleaned_e = set(), []
            for a in aliases:
                if a and a not in seen_e:
                    seen_e.add(a)
                    cleaned_e.append(a)
            rows.append(
                {
                    "id": base_id + i,
                    "name": item["name"],
                    "type": item["type"],
                    "aliases": cleaned_e,
                    "logo": None,
                }
            )
        print(f"[ok] 合并补充频道 {len(extra)} 条")

    # 按分类聚合顺序：央视 → 卫视 → 影视 → 电影 → 主题 → 明星 → 国教 → 港澳 → 数字
    order = [
        "央视频道", "卫视频道", "体育频道", "影视频道", "电影频道", "电视剧频道",
        "少儿频道", "纪实频道", "主题频道", "明星频道", "国教频道", "港澳频道",
        "数字频道", "地方频道",
    ]
    rank = {t: i for i, t in enumerate(order)}
    rows.sort(key=lambda r: (rank.get(r["type"], 99), r["id"]))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter

    print(f"[ok] 提取 {len(rows)} 个频道 -> {OUT_PATH}")
    for t, n in Counter(r["type"] for r in rows).most_common():
        print(f"     {t}: {n}")
    print("     示例:", json.dumps(rows[0], ensure_ascii=False))
    print("     示例:", json.dumps(rows[40], ensure_ascii=False))


if __name__ == "__main__":
    main()
