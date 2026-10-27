# -*- coding: utf-8 -*-
"""导出台标映射表 logos.json —— 给姊妹仓库 china-iptv-sources 用。

背景
----
china-iptv-sources 那边的 m3u 是「猜地址」：
    https://gcore.jsdelivr.net/gh/yuanzl77/TVlogo@master/png/{频道名}.png
频道名对不上文件名就是 404。实测抽 12 个，11 个是死的（汕头经济生活、
CCTV-1 高清、三门峡新闻综合……）。所以那边大部分台其实没有台标。

本站这边是**真的解析过**的（spider/logos.py：精确 → 别名 → 包含匹配 →
自制台标），最终写进各 m3u 的 tvg-logo 就是可用地址。这个脚本把这些
结果导出成一张表，让另一个仓库直接查表，不用再自己猜。

输出
----
  logos.json              站点根目录（短地址 https://zzf.new.tg/logos.json）
  data/public/logos.json  同内容，路径稳定，给历史引用

格式
----
  {
    "updated": "2026-10-27 20:10:00",
    "count": 4800,
    "logos": {"CCTV-1": "https://...", "cctv1": "https://...", ...}
  }
键里已经展开常用变体（去空格/横线、小写、去「高清」等后缀），
对方按 name → 规范化 name 两跳就能查到。

用法
----
  python tools/build_logo_map.py
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "data" / "public"
OUT_SHORT = ROOT / "logos.json"
OUT_PUBLIC = PUBLIC / "logos.json"

EXTINF_RE = re.compile(r'^#EXTINF:-?\d*[^,]*?tvg-logo="([^"]*)"[^,]*,(.+)$')

# 匹配前剥掉的清晰度/版本后缀
_SUFFIX = ["蓝光高清", "超高清", "高清版", "超清版", "标清版", "高清", "超清",
           "标清", "蓝光", "FHD", "UHD", "4K", "8K", "HD", "SD"]


def norm(name: str) -> str:
    """规范化：去空格/中点/横线/下划线，全角括号转半角，转小写。"""
    s = (name or "").strip()
    s = s.replace("（", "(").replace("）", ")").replace("《", "").replace("》", "")
    s = re.sub(r"[\s·\-_.—–]", "", s)
    return s.lower()


def strip_suffix(name: str) -> str:
    """湖南卫视高清 -> 湖南卫视；CCTV-1HD -> CCTV-1"""
    s = (name or "").strip()
    up = s.upper()
    for suf in _SUFFIX:
        if up.endswith(suf.upper()) and len(s) > len(suf) + 1:
            return s[: -len(suf)].strip()
    return s


def variants(name: str) -> list[str]:
    out = [name, norm(name)]
    base = strip_suffix(name)
    if base != name:
        out += [base, norm(base)]
    # CCTV-1 / CCTV1 互认
    flat = name.replace("-", "")
    if flat != name:
        out.append(flat)
    # 品牌前缀互认：BRTV北京卫视 -> 北京卫视，BTV国际频道 -> 国际频道
    # （另一个仓库的名字带 BRTV / BTV / TVB 这类前缀，我们库里是裸名）
    for s in (name, base):
        m = re.match(r"^([A-Za-z]{2,6})[\s\-]?(.+)$", s)
        if m and re.search(r"[\u4e00-\u9fff]", m.group(2)) and len(m.group(2)) >= 2:
            out += [m.group(2), norm(m.group(2))]
    return [x for x in dict.fromkeys(out) if x]


def collect() -> dict[str, str]:
    logos: dict[str, str] = {}
    src: dict[str, str] = {}
    files = sorted(PUBLIC.glob("*.m3u"))
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        for line in text.replace("\r\n", "\n").split("\n"):
            if not line.startswith("#EXTINF"):
                continue
            m = EXTINF_RE.match(line.strip())
            if not m:
                continue
            url, name = m.group(1).strip(), m.group(2).strip()
            if not url or not name or name.endswith("更新") or name.startswith("有效期"):
                continue
            if name in src:
                continue
            src[name] = url
    # 自制台标单独再兜一遍（有些台只在 JSON 里，m3u 里没写）
    comp = ROOT / "spider" / "data" / "composed_logos.json"
    if comp.exists():
        try:
            for name, url in json.loads(comp.read_text(encoding="utf-8")).items():
                src.setdefault(name, url)
        except Exception:  # noqa: BLE001
            pass

    # 再并进两个中文台标库的**全量**条目：我们的播放列表只覆盖本站 4000 多个台，
    # 姊妹仓库里还有大量市县台（汕头经济生活 / 三门峡新闻综合 …）不在这批里，
    # 但库里可能有。播放列表解析出来的地址优先（那是挑过的），库里条目兜底。
    idx_fp = ROOT / "spider" / "data" / "logo_index.json"
    if idx_fp.exists():
        try:
            idx = json.loads(idx_fp.read_text(encoding="utf-8"))
            for lib in ("tvlogo", "wanglindl"):
                for name, url in (idx.get(lib) or {}).items():
                    if name and url and not name.isdigit():
                        src.setdefault(name.strip(), url)
        except Exception:  # noqa: BLE001
            pass

    for name, url in src.items():
        for key in variants(name):
            logos.setdefault(key, url)
    return logos


def main() -> None:
    t0 = time.time()
    logos = collect()

    # 外站图片换成本站镜像（tools/mirror_logos.py 会把图片下载到 data/logos/lib/）。
    # 目的：订阅里的 tvg-logo 全部走自己的域名，不再依赖 jsdelivr —— 那边
    # 对 @分支 有最长 7 天缓存，EPG 之前就吃过这个亏。
    mirror_fp = ROOT / "spider" / "data" / "logo_mirror.json"
    if mirror_fp.exists():
        try:
            mirror = json.loads(mirror_fp.read_text(encoding="utf-8"))
            n = 0
            for k, v in list(logos.items()):
                m = mirror.get(v)
                if m:
                    logos[k] = m
                    n += 1
            print(f"[logo] 外站图片换本站镜像 {n} 个键")
        except Exception as e:  # noqa: BLE001
            print(f"[logo] 镜像表读取失败：{e}")

    payload = {
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(logos),
        "source": "https://zzf.new.tg/",
        "note": "键已展开常用变体（原样 / 去空格横线小写 / 去高清后缀），直接 dict.get 即可",
        "logos": dict(sorted(logos.items())),
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    OUT_SHORT.write_bytes(data)
    OUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    OUT_PUBLIC.write_bytes(data)
    print(f"[logo] 导出 {len(logos)} 个键 -> logos.json {len(data)/1024:.0f}KB "
          f"（用时 {time.time()-t0:.1f}s）")


if __name__ == "__main__":
    main()
