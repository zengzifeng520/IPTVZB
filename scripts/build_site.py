# -*- coding: utf-8 -*-
"""把仓库里「该公开的」站点文件挑出来，组装到 dist/ 供 Cloudflare Pages 发布。

只发布这些：
  index.html / account.html / region.html / hotel.html / login.html
  assets/css、assets/img、assets/js（**排除 admin.js**）
  data/public/**（+ data/users/**，若存在用户专属订阅）
  robots.txt

不发布：spider/、worker/、scripts/、.github/、admin.*、wrangler.toml、CNAME、README 等
—— 源码、后台管理页和仓库信息一律不进静态产物。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

PAGES = ["index.html", "account.html", "region.html", "hotel.html", "login.html"]
TREES = [
    ("assets/css", "assets/css"),
    ("assets/img", "assets/img"),
    ("assets/js", "assets/js"),
    ("data/public", "data/public"),
    ("data/users", "data/users"),
]
SKIP_FILES = {"assets/js/admin.js"}


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    n = 0
    for name in PAGES:
        src = ROOT / name
        if not src.exists():
            print(f"  [build] 缺少 {name}，跳过")
            continue
        shutil.copy2(src, DIST / name)
        n += 1

    for src_rel, dst_rel in TREES:
        src = ROOT / src_rel
        if not src.exists():
            continue
        dst = DIST / dst_rel
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(ROOT).as_posix()
            if rel in SKIP_FILES:
                continue
            target = DIST / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            n += 1

    robots = ROOT / "robots.txt"
    if robots.exists():
        shutil.copy2(robots, DIST / "robots.txt")
        n += 1

    # 兜底检查：产物里不允许出现 GitHub 账号/仓库名
    bad = []
    for f in DIST.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in {".html", ".js", ".json", ".txt", ".css", ".m3u"}:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "zengzifeng" in text:
            bad.append(f.relative_to(DIST).as_posix())

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"  [build] dist/ 共 {n} 个文件，{total / 1024 / 1024:.1f} MB")
    if bad:
        print("  [build] 警告：以下产物仍含 GitHub 用户名 ->", ", ".join(bad[:10]))
        return 1
    print("  [build] 产物中没有出现 GitHub 用户名 zengzifeng")
    return 0


if __name__ == "__main__":
    sys.exit(main())
