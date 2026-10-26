# -*- coding: utf-8 -*-
"""赞助用户管理（本地命令行）。

用户在没有注册的网站上，赞助码由浏览器自动生成并显示在「赞助」页。
把用户发来的赞助码登记进来，他刷新页面就能拿到专属订阅地址。

用法（在 spider 目录下运行）：
    python users_cli.py add A1B2C3D4E5F6 --days 30        # 开通 30 天
    python users_cli.py add A1B2C3D4E5F6 --expire 2026-11-25
    python users_cli.py list                             # 查看全部与剩余天数
    python users_cli.py remove A1B2C3D4E5F6              # 删除（下次生成后订阅失效）

改完 data/users.json 后提交推送，会自动触发 Actions 重建，约 1 分钟生效。
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timedelta

from subs import CST, USERS_JSON, token_of

BASE_URL = "https://zzf.new.tg"
CODE_RE = re.compile(r"^[A-Z0-9]{8,32}$")


def load() -> dict:
    if not USERS_JSON.exists():
        return {}
    try:
        return json.loads(USERS_JSON.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save(users: dict) -> None:
    USERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    USERS_JSON.write_text(
        json.dumps(users, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def norm_code(v: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())


def ts_of(date_str: str) -> int:
    """YYYY-MM-DD -> 北京时间当天 23:59:59 的时间戳（用户能用满最后一天）。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=CST
    )
    return int(dt.timestamp())


def group(code: str) -> str:
    return " ".join(code[i : i + 4] for i in range(0, len(code), 4))


def show(code: str, info: dict) -> None:
    tok = info.get("token") or token_of(code)
    ts = int(info.get("ts") or 0)
    now = int(time.time())
    if ts and ts < now:
        state = "已过期"
    elif ts:
        state = f"剩 {max(0, (ts - now) // 86400)} 天"
    else:
        state = "未设到期"
    print(f"[{group(code)}] 到期 {info.get('expire', '—')}（{state}）")
    print(f"  订阅 {BASE_URL}/data/users/{tok}/all.m3u")


def main() -> None:
    ap = argparse.ArgumentParser(description="赞助用户管理")
    ap.add_argument("action", choices=["add", "list", "remove"])
    ap.add_argument("code", nargs="?", help="赞助码（用户页面上的 12 位码）")
    ap.add_argument("--days", type=int, help="开通天数（从现在起算）")
    ap.add_argument("--expire", help="到期日期 YYYY-MM-DD")
    args = ap.parse_args()

    users = load()

    if args.action == "list":
        if not users:
            print("暂无赞助用户")
            return
        now = int(time.time())
        rows = sorted(users.items(), key=lambda kv: int(kv[1].get("ts") or 0))
        valid = sum(1 for _k, i in rows if int(i.get("ts") or 0) >= now)
        print(f"共 {len(rows)} 个，有效 {valid} 个\n" + "-" * 46)
        for c, i in rows:
            show(c, i)
        return

    code = norm_code(args.code)
    if not CODE_RE.match(code):
        print("赞助码格式不对（应为 8~32 位大写字母/数字）")
        return

    if args.action == "remove":
        if code in users:
            del users[code]
            save(users)
            print(f"已删除 {group(code)}，下次生成时订阅会变空")
        else:
            print("没有这个赞助码")
        return

    # add
    if args.expire:
        exp = args.expire
    elif args.days:
        exp = (datetime.now() + timedelta(days=args.days)).strftime("%Y-%m-%d")
    else:
        print("请用 --days N 或 --expire YYYY-MM-DD 指定有效期")
        return

    old = users.get(code) or {}
    users[code] = {
        "token": token_of(code),
        "expire": exp,
        "ts": str(ts_of(exp)),
        "created": old.get("created") or datetime.now().strftime("%Y-%m-%d"),
    }
    save(users)
    print(f"已开通 {group(code)} -> {exp}")
    show(code, users[code])


if __name__ == "__main__":
    main()
