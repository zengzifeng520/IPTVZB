# -*- coding: utf-8 -*-
"""把外站台标图片镜像到本站 data/logos/lib/，让所有订阅的台标都走自己的域名。

为什么
------
台标表 logos.json 里大部分条目指向公共台标库（yuanzl77 / wanglinl 等，
托管在 jsdelivr）。姊妹仓库 china-iptv-sources 那边的播放列表要靠这张表，
但用户看到的还是「jsdelivr 的地址」，既不是本站域名，国内访问也不稳
（jsdelivr 对 @分支 有最长 7 天缓存，之前 EPG 就吃过这个亏）。

做法
----
1. 给定一批 m3u（默认扫姊妹仓库的成品订阅），收集里面所有 tvg-logo 地址
2. 把**非本站**的图片下载到 data/logos/lib/<url hash>.<ext>
3. 记到 spider/data/logo_mirror.json：{原地址: 本站地址}
4. build_logo_map.py 生成 logos.json 时按这张表把地址换成本站的

这样台标表里就不再出现第三方图床地址；镜像失败（404/超时）的保持原样，
不会把可用地址弄丢。

用法
----
  python tools/mirror_logos.py --from-m3u ../china-iptv-sources/output
  python tools/mirror_logos.py --from-m3u a.m3u b.m3u --workers 24
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_DIR = ROOT / "data" / "logos" / "lib"
MIRROR_JSON = ROOT / "spider" / "data" / "logo_mirror.json"
BASE_URL = "https://zzf.new.tg/data/logos/lib/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
LOGO_RE = re.compile(r'tvg-logo="([^"]+)"')
MAX_BYTES = 400 * 1024      # 单张超过 400KB 的跳过（多半是海报不是台标）


def collect_urls(paths: list[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for p in paths:
        fp = Path(p)
        files = sorted(fp.rglob("*.m3u")) if fp.is_dir() else [fp]
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            for u in LOGO_RE.findall(text):
                if "zzf.new.tg" in u or u in seen:
                    continue
                seen.add(u)
                urls.append(u)
    return urls


def _ext_of(url: str, data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:5] in (b"<?xml", b"<svg "):
        return ".svg"
    tail = Path(urllib.parse.urlparse(url).path).suffix.lower()
    return tail if tail in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg") else ".png"


def fetch(url: str) -> tuple[str, bytes] | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read(MAX_BYTES + 1)
        if not data or len(data) > MAX_BYTES:
            return None
        return url, data
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-m3u", nargs="+", required=True, help="m3u 文件或目录")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    urls = collect_urls(args.from_m3u)
    print(f"待处理外站台标 {len(urls)} 个")
    mirror: dict[str, str] = {}
    if MIRROR_JSON.exists():
        try:
            mirror = json.loads(MIRROR_JSON.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            mirror = {}
    before = len(mirror)

    LIB_DIR.mkdir(parents=True, exist_ok=True)
    done = fail = 0

    def work(u: str) -> tuple[str, str] | None:
        if u in mirror and (ROOT / mirror[u].replace(BASE_URL, "data/logos/lib/")):
            pass
        res = fetch(u)
        if not res:
            return None
        _, data = res
        name = hashlib.md5(u.encode("utf-8")).hexdigest()[:12] + _ext_of(u, data)
        (LIB_DIR / name).write_bytes(data)
        return u, BASE_URL + name

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(work, urls):
            if r:
                mirror[r[0]] = r[1]
                done += 1
            else:
                fail += 1
            if (done + fail) % 100 == 0:
                print(f"  {done + fail}/{len(urls)}", flush=True)

    MIRROR_JSON.parent.mkdir(parents=True, exist_ok=True)
    MIRROR_JSON.write_text(json.dumps(mirror, ensure_ascii=False, indent=0), encoding="utf-8")
    total = sum(p.stat().st_size for p in LIB_DIR.glob("*"))
    print(f"镜像完成：成功 {done}，失败 {fail}，映射共 {len(mirror)} 条（新增 {len(mirror)-before}）")
    print(f"图片目录 {LIB_DIR}  {total/1024/1024:.1f}MB / {len(list(LIB_DIR.glob('*')))} 张")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"用时 {time.time()-t0:.0f}s")
