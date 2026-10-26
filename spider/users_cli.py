# -*- coding: utf-8 -*-
"""用户订阅管理（本地命令行）。

用法（在 spider 目录下运行）：
    python users_cli.py add 13800138000 --days 30       # 开通 30 天
    python users_cli.py add 13800138000 --expire 2026-11-25
    python users_cli.py list                            # 查看全部用户与订阅地址
    python users_cli.py remove 13800138000              # 删除（下次生成后订阅失效）

改完 data/users.json 后，提交并推送，或等每日自动任务重建订阅文件：
    git add -f data/users.json && git commit -m "user: ..." && git push
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta

import config
from subs import CST, TOKEN_SALT, USERS_JSON, token_of  # noqa: F401

BASE_URL = "https://zzf.new.tg"


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


def ts_of(date_str: str) -> int:
    """YYYY-MM-DD -> 北京时间当天 23:59:59 的时间戳（用户能用满最后一天）。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, tzinfo=CST
    )
    return int(dt.timestamp())


def show(phone: str, info: dict) -> None:
    tok = info.get("token") or token_of(phone)
    ts = int(info.get("ts") or 0)
    now = int(time.time())
    if ts and ts < now:
        state = "已过期"
    else:
        state = f"剩 {max(0, (ts - now) // 86400)} 天" if ts else "长期"
    mark = "" if ts and ts < now else "  ✔"
    print(f"[{phone}] 到期 {info.get('expire', '—')}（{state}）{mark}")
    print(f"  全量 {BASE_URL}/data/users/{tok}/all.m3u")


def main() -> None:
    ap = argparse.ArgumentParser(description="用户订阅管理")
    ap.add_argument("action", choices=["add", "list", "remove"])
    ap.add_argument("phone", nargs="?", help="手机号")
    ap.add_argument("--days", type=int, help="开通天数（从现在起算）")
    ap.add_argument("--expire", help="到期日期 YYYY-MM-DD")
    args = ap.parse_args()

    users = load()

    if args.action == "remove":
        if not args.phone:
            print("请指定手机号")
            return
        if args.phone in users:
            del users[args.phone]
            save(users)
            print(f"已删除 {args.phone}，订阅文件将在下次生成时清空")
        else:
            print(f"不存在：{args.phone}")
        return

    if args.action == "add":
        if not args.phone:
            print("请指定手机号")
            return
        if args.expire:
            exp = args.expire
        elif args.days:
            exp = (datetime.now() + timedelta(days=args.days)).strftime("%Y-%m-%d")
        else:
            print("请用 --days N 或 --expire YYYY-MM-DD 指定有效期")
            return
        old = users.get(args.phone) or {}
        users[args.phone] = {
            "token": token_of(args.phone),
            "expire": exp,
            "ts": str(ts_of(exp)),
            "created": old.get("created") or datetime.now().strftime("%Y-%m-%d"),
        }
        save(users)
        print(f"已开通 {args.phone} -> {exp}")
        show(args.phone, users[args.phone])
        return

    # list
    if not users:
        print("暂无用户")
        return
    now = int(time.time())
    rows = sorted(users.items(), key=lambda kv: int(kv[1].get("ts") or 0))
    valid = sum(1 for _p, i in rows if int(i.get("ts") or 0) >= now)
    print(f"共 {len(rows)} 个用户，有效 {valid} 个\n" + "-" * 46)
    for p, i in rows:
        show(p, i)


if __name__ == "__main__":
    main()
