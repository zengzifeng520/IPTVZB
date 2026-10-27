# -*- coding: utf-8 -*-
"""把深度体检结果并入 verify_report.json，供各处 probe 复用。

为什么需要这个文件
------------------
「保证播放器里能看」不能靠一次性验活，也不能靠轻量 HTTP 探测：
  - 轻量探测只看播放列表能不能打开、分片能不能下 8KB，
    但 VOD 回看（#EXT-X-ENDLIST）也能通过 —— 播放器拉到尾就停
  - H.265 / AC3 的源也能通过 —— 部分播放器黑屏或没声音
  - 开头有画面、几秒后断流的源也能通过 —— 用户看两分钟就卡死

所以真正发布前要用 tools/deep_verify.py 拉 12~20 秒实测，
把 A（流畅）/ B（能播有瑕疵）/ C（编码不兼容、VOD、严重丢帧）/ D（拉不起来）
的结论落到 verify_report.json。probe 时：
  A / B -> 直接放行（不再重复探测，省时间也避免误杀）
  C / D -> 直接拒绝（这是「播放器里看不了」的主要来源）
报告超过 MAX_AGE_DAYS 天视为过期，回退到实时探测。

用法
----
  python tools/merge_verify_report.py data/_deep_hk.json
  python tools/merge_verify_report.py data/_deep_intl.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "spider" / "data" / "verify_report.json"


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python tools/merge_verify_report.py <deep_verify输出.json> [...]")
        return

    # 除第一个参数外，--by 指定这批结论的来源视角
    by = "local"
    args = sys.argv[1:]
    if "--by" in args:
        i = args.index("--by")
        by = args[i + 1]
        args = args[:i] + args[i + 2:]

    cur: dict = {"generated_at": "", "urls": {}}
    if REPORT.exists():
        try:
            cur = json.loads(REPORT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    urls: dict = cur.get("urls") or {}
    before = len(urls)

    today = time.strftime("%Y-%m-%d")
    for arg in args:
        p = Path(arg)
        if not p.exists():
            print(f"跳 {p}（不存在）")
            continue
        rows = json.loads(p.read_text(encoding="utf-8"))
        n_new = 0
        for r in rows:
            u = r.get("url")
            if not u:
                continue
            # 本地（大陆网络）结论优先：Actions 是美国视角，只补充技术问题，
            # 不能覆盖「大陆实测过」的判断，否则会把大陆能通的源误杀
            if by == "actions" and (urls.get(u) or {}).get("by") == "local":
                continue
            urls[u] = {
                "grade": r.get("grade") or "D",
                "why": r.get("why") or "",
                "vcodec": r.get("vcodec") or "",
                "acodec": r.get("acodec") or "",
                "res": r.get("res") or "",
                "drop": r.get("drop"),
                "by": r.get("by") or by,
                "at": today,
            }
            n_new += 1
        print(f"{p.name}: 并入 {n_new} 条")

    cur["urls"] = urls
    cur["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(cur, ensure_ascii=False, indent=0), encoding="utf-8")

    from collections import Counter
    c = Counter(v.get("grade") for v in urls.values())
    from collections import Counter
    nby = Counter(v.get("by") for v in urls.values())
    print(f"\n报告共 {len(urls)} 条（原 {before}），视角分布: {dict(nby)}")
    for g in "ABCD":
        if c.get(g):
            print(f"  {g}: {c[g]}")
    print(f"-> {REPORT}  ({REPORT.stat().st_size/1024:.0f}KB)")


if __name__ == "__main__":
    main()
