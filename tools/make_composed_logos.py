# -*- coding: utf-8 -*-
"""给台标库里找不到的频道自制台标图片。

做法
----
按频道名生成 240x144 的圆角卡片式台标：
  - 背景色由频道名 hash 决定（同一频道永远同一颜色，不同频道颜色错开）
  - 频道名白色居中，字号自动适配（长名字自动缩小 + 折行）
  - 输出到 site_repo/data/logos/<md5>.png
  - 映射写进 spider/data/composed_logos.json，logos.py 回退查询

为什么放仓库里
--------------
站点本身就是 GitHub Pages，`data/logos/*.png` 天然有公网地址
（https://zzf.new.tg/data/logos/xxx.png），m3u 里直接引用即可，
不依赖任何第三方图床（第三方图床挂掉台标就全裂了）。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent      # E:\fuke
SITE = ROOT / "site_repo"
OUT_DIR = SITE / "data" / "logos"
MAP_JSON = SITE / "spider" / "data" / "composed_logos.json"
BASE_URL = "https://zzf.new.tg/data/logos/"

W, H = 240, 144
# 优先黑体单文件（simhei.ttf）——.ttc 是字体集合，PIL 取 index 0 常拿到
# 不含中文的子字体，会把汉字渲染成方块，所以单文件字体排第一
FONT_PATHS = [
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# 一组明快但不太刺眼的底色，按 hash 取
PALETTE = [
    (198, 40, 40), (173, 20, 87), (106, 27, 154), (69, 39, 160),
    (40, 53, 147), (21, 101, 192), (2, 119, 189), (0, 121, 107),
    (27, 94, 32), (51, 105, 30), (130, 119, 23), (230, 81, 0),
    (216, 67, 21), (136, 14, 79), (74, 20, 140), (26, 35, 126),
    (1, 87, 155), (0, 105, 92), (46, 125, 50), (158, 157, 36),
    (239, 108, 0), (84, 110, 122), (55, 71, 79), (69, 90, 100),
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_PATHS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


def _color(name: str) -> tuple[int, int, int]:
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16)
    return PALETTE[h % len(PALETTE)]


def _fit(text: str, max_w: int, max_h: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """找一个能放下的字号，必要时折行"""
    for size in range(52, 15, -3):
        f = _font(size)
        # 单行能放下
        if f.getlength(text) <= max_w:
            return f, [text]
        # 两行：从中间或空格断开
        if len(text) >= 4:
            mid = len(text) // 2
            parts = [text[:mid], text[mid:]]
            if all(f.getlength(p) <= max_w for p in parts):
                if size * 2 + 6 <= max_h:
                    return f, parts
    return _font(20), [text[:12]]


def make(name: str) -> Path:
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
    path = OUT_DIR / f"{digest}.png"
    if path.exists():
        return path

    bg = _color(name)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # 左侧竖向亮条，让卡片有层次
    d.rectangle([0, 0, 6, H], fill=(255, 255, 255))
    # 右下角淡色三角
    d.polygon([(W, H), (W - 54, H), (W, H - 40)], fill=tuple(min(255, c + 34) for c in bg))

    # 去掉括号里的补充说明，只留主名
    show = name
    for a, b in (("(", ")"), ("（", "）"), ("[", "]")):
        if a in show and b in show:
            show = show.split(a)[0] or name
    show = show.strip() or name

    f, lines = _fit(show, W - 34, H - 40)
    lh = f.size + 6
    total = lh * len(lines)
    y = (H - total) // 2 - 2
    for ln in lines:
        tw = f.getlength(ln)
        # 描边增强可读性
        d.text(((W - tw) / 2 + 1, y + 1), ln, font=f, fill=(0, 0, 0))
        d.text(((W - tw) / 2, y), ln, font=f, fill=(255, 255, 255))
        y += lh

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG", optimize=True)
    return path


def main() -> None:
    names = json.load(open(sys.argv[1], encoding="utf-8")) if len(sys.argv) > 1 else []
    if not names:
        print("用法: python make_composed_logos.py <names.json>")
        return
    mapping = {}
    if MAP_JSON.exists():
        mapping = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    before = len(mapping)
    for i, nm in enumerate(names, 1):
        if nm in mapping:
            continue
        p = make(nm)
        mapping[nm] = BASE_URL + p.name
        if i % 100 == 0:
            print(f"  生成 {i}/{len(names)}", flush=True)
    MAP_JSON.parent.mkdir(parents=True, exist_ok=True)
    MAP_JSON.write_text(json.dumps(mapping, ensure_ascii=False, indent=0), encoding="utf-8")
    total = sum(1 for _ in OUT_DIR.glob("*.png"))
    size_mb = sum(p.stat().st_size for p in OUT_DIR.glob("*.png")) / 1024 / 1024
    print(f"台标完成：新增 {len(mapping)-before} 个，共 {len(mapping)} 条映射")
    print(f"图片文件 {total} 个 / {size_mb:.1f}MB -> {OUT_DIR}")


if __name__ == "__main__":
    main()
