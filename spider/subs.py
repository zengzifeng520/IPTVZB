# -*- coding: utf-8 -*-
"""生成订阅文件：全量 + 分地区 + 按用户专属。

输出（都在 data/sub/ 下，供 GitHub Pages 直接下载）：
  all.m3u                 全量订阅（所有存活服务器）
  region/<KEY>.m3u        按中转服务器所在省份拆分
  index.json              订阅索引（前端读这个渲染）

用户专属订阅（data/users/<token>/ 下）：
  all.m3u                 该用户的全量订阅
  <KEY>.m3u               该用户的分地区订阅
  说明：用户表在 data/users.json，Actions 每次重建。
       会员到期后该目录下所有文件被改写为空列表（只有 #EXTM3U），
       播放器下次刷新即拿到 0 个频道 —— 不做删除，避免 404 报错，
       同时因为 URL 不变，本地也不会留下可用的旧缓存。

分地区的原因：udpxy 中转服务器通常只在本省运营商网内可达，
跨省地址基本连不上，按地区拆开用户体验才好。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config

# 到期时间按北京时间当天 23:59:59 算（Actions 跑在 UTC，必须显式指定时区）
CST = timezone(timedelta(hours=8))

PROXY_JSON = config.WEB_DATA_DIR / "proxy.json"
REGIONS_JSON = config.WEB_DATA_DIR / "regions.json"
SUB_DIR = config.WEB_DATA_DIR / "sub"
INDEX_JSON = SUB_DIR / "index.json"

USERS_JSON = config.WEB_DATA_DIR / "users.json"
USERS_DIR = config.WEB_DATA_DIR / "users"

# 免费订阅：按「到期日」分目录，滚动保留未来 7 天，过期目录直接删掉
FREE_DIR = config.WEB_DATA_DIR / "free"
FREE_DAYS = 7

# token 盐值：前端 assets/js/auth.js 里的 TOKEN_SALT 必须与此一致
TOKEN_SALT = "zzf-sub-2026"

# 到期后写入的空订阅（保留 #EXTM3U 头，播放器当合法列表处理，只是没有频道）
EMPTY_SUB = "#EXTM3U\n# 会员已到期，订阅已停止更新，续费后立即恢复\n"


def token_of(sid: str) -> str:
    """赞助码 -> 16 位订阅 token（与前端 assets/js/auth.js 的 tokenOf 一致）。"""
    raw = f"{TOKEN_SALT}|{str(sid).strip().upper()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _extinf(ch: dict) -> str:
    return (
        f'#EXTINF:-1 tvg-name="{ch["display"]}" group-title="{ch["type"]}",{ch["display"]}'
    )


def _write(path: Path, channels: list[dict], host_set: set[str] | None = None) -> tuple[int, int]:
    """写一个 m3u，返回 (频道数, 地址数)。host_set 为空表示不限服务器。"""
    lines = ["#EXTM3U"]
    n_chan = 0
    n_stream = 0
    for ch in channels:
        picked = ch["streams"] if host_set is None else [s for s in ch["streams"] if s["h"] in host_set]
        if not picked:
            continue
        n_chan += 1
        head = _extinf(ch)
        for s in picked:
            lines.append(head)
            lines.append(s["u"])
            n_stream += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n_chan, n_stream


def build_free(channels: list[dict], regions: list[dict]) -> None:
    """免费订阅：按「到期日」分目录，只保留未来 FREE_DAYS 天。

    目录名就是到期日期（YYYYMMDD），前端按「选地区当天 + 7 天」拼地址。
    过了那一天目录被删除 -> 播放器 404 / 空列表，免费订阅自然失效。
    8 个目录内容完全相同，Git 只存一份 blob，仓库不会被撑大。
    """
    today = datetime.now(CST).date()
    keep: set[str] = set()
    valid = {r["key"] for r in regions}

    for i in range(FREE_DAYS + 1):
        key = (today + timedelta(days=i)).strftime("%Y%m%d")
        keep.add(key)
        d = FREE_DIR / key
        d.mkdir(parents=True, exist_ok=True)
        for r in regions:
            host_set = set(r.get("hosts") or [])
            target = d / f"{r['key']}.m3u"
            if not host_set:
                target.write_text(EMPTY_SUB, encoding="utf-8")
                continue
            c, _s = _write(target, channels, host_set)
            if not c:
                target.write_text(EMPTY_SUB, encoding="utf-8")
        # 地区已经下线的旧文件要清掉，否则会留一批 0 频道的空壳
        for p in d.iterdir():
            if p.suffix == ".m3u" and p.stem not in valid:
                p.unlink(missing_ok=True)

    if FREE_DIR.exists():
        for p in FREE_DIR.iterdir():
            if p.is_dir() and p.name not in keep:
                shutil.rmtree(p, ignore_errors=True)

    print(f"  [subs] 免费订阅目录 {len(keep)} 天（{min(keep)} ~ {max(keep)}）")


def build_users(channels: list[dict], regions: list[dict]) -> dict:
    """为 users.json 里每个用户生成专属订阅；到期用户写成空列表。

    users.json 结构：
        {"A1B2C3D4E5F6": {"expire": "2026-11-25", "ts": "1795622399", "created": "2026-10-26"}}
    键是本机赞助码，token 由它推导，无需手填；info 里也可写 token 覆盖。
    """
    if not USERS_JSON.exists():
        print("  [subs] 无 data/users.json，跳过用户专属订阅")
        return {}

    try:
        users = json.loads(USERS_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [subs] users.json 解析失败，跳过：{exc}")
        return {}
    if not isinstance(users, dict) or not users:
        # 用户表被清空时，必须把旧的用户目录一起删掉，
        # 否则那条订阅链接还能继续下载，等于删号没生效
        if USERS_DIR.exists():
            for p in USERS_DIR.iterdir():
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    print(f"  [subs] 清理已删除用户的订阅目录 {p.name}")
        print("  [subs] users.json 为空，跳过用户专属订阅")
        return {}

    USERS_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    keep: set[str] = set()
    n_ok = n_exp = 0

    for sid, info in users.items():
        if not isinstance(info, dict):
            info = {}
        token = str(info.get("token") or token_of(sid))
        keep.add(token)
        d = USERS_DIR / token
        d.mkdir(parents=True, exist_ok=True)

        ts = 0
        try:
            ts = int(info.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        if not ts and info.get("expire"):
            # 只给了日期：按北京时间当天 23:59:59 算，用户能用满最后一天
            try:
                ts = int(
                    datetime.strptime(
                        f"{str(info['expire']).strip()} 23:59:59", "%Y-%m-%d %H:%M:%S"
                    )
                    .replace(tzinfo=CST)
                    .timestamp()
                )
            except Exception:  # noqa: BLE001
                ts = 0
        expired = bool(ts) and ts < now

        # 用户状态快照：前端换设备 / 清缓存后靠它恢复赞助状态（不含赞助码明文）
        meta = {
            "ts": ts,
            "expire": info.get("expire") or "",
            "created": info.get("created") or "",
            "valid": (not expired) and bool(ts),
        }
        (d / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )

        if expired:
            # 过期：所有文件改成空列表（保留文件，避免播放器 404 报错）
            (d / "all.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            for r in regions:
                (d / f"{r['key']}.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            n_exp += 1
            print(f"  [subs] users/{token}  已过期 -> 订阅清空")
            continue

        c, s = _write(d / "all.m3u", channels)
        for r in regions:
            host_set = set(r.get("hosts") or [])
            if not host_set:
                (d / f"{r['key']}.m3u").write_text(EMPTY_SUB, encoding="utf-8")
                continue
            rc, rs = _write(d / f"{r['key']}.m3u", channels, host_set)
            if not rc:
                (d / f"{r['key']}.m3u").write_text(EMPTY_SUB, encoding="utf-8")
        n_ok += 1
        left = max(0, int((ts - now) // 86400)) if ts else 0
        print(f"  [subs] users/{token}  {c:>4} 频道 / {s:>5} 条  剩 {left} 天")

    # 清理已被删除的用户目录
    for p in USERS_DIR.iterdir():
        if p.is_dir() and p.name not in keep:
            shutil.rmtree(p, ignore_errors=True)
            print(f"  [subs] 清理已删除用户的订阅目录 {p.name}")

    print(f"  [subs] 用户订阅：有效 {n_ok} 个，已过期 {n_exp} 个")
    return {"valid": n_ok, "expired": n_exp}


def build() -> dict:
    if not PROXY_JSON.exists():
        print("  [subs] 缺少 data/proxy.json，请先运行 udpxy.py")
        return {}

    proxy = json.loads(PROXY_JSON.read_text(encoding="utf-8"))
    channels = proxy.get("channels", [])
    if not channels:
        print("  [subs] proxy.json 无频道数据，跳过")
        return {}

    regions = []
    if REGIONS_JSON.exists():
        regions = json.loads(REGIONS_JSON.read_text(encoding="utf-8")).get("regions", [])

    # 全量：只在内存里统计，**不再落盘成公开文件**。
    # data/sub/all.m3u 这种文件放在仓库里等于把 4147 条地址免费公开，
    # 谁拿到 URL 都能直接下，跟「赞助才能看」完全冲突。
    n_chan = len(channels)
    n_stream = sum(len(c["streams"]) for c in channels)
    print(f"  [subs] 全量统计          {n_chan:>4} 频道 / {n_stream:>5} 条（不生成公开文件）")

    # 分地区：同样不落盘，只把「数量」写进索引给前端展示
    index_regions = []
    for r in regions:
        host_set = set(r.get("hosts") or [])
        if not host_set:
            continue
        c = 0
        s = 0
        for ch in channels:
            picked = [x for x in ch["streams"] if x["h"] in host_set]
            if picked:
                c += 1
                s += len(picked)
        if not c:
            continue
        index_regions.append(
            {
                "key": r["key"],
                "name": r["name"],
                "isp": r.get("isp") or "",
                "channels": c,
                "streams": s,
                "hosts": len(host_set),
            }
        )
        print(f"  [subs] region/{r['key']:<4}       {c:>4} 频道 / {s:>5} 条  {r['name']}")

    index_regions.sort(key=lambda x: -x["streams"])
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "all": {
            "channels": n_chan,
            "streams": n_stream,
        },
        "regions": index_regions,
        # 用户专属订阅路径模板，前端把 {token} 换成实际 token
        "user": {
            "all": "data/users/{token}/all.m3u",
            "region": "data/users/{token}/{key}.m3u",
        },
    }
    INDEX_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"  [subs] 索引 {len(index_regions)} 个地区 -> {INDEX_JSON.name}")

    # 传原始 regions（含频道为 0 的地区），保证每个目录下每个地区都有文件
    build_free(channels, regions)
    build_users(channels, regions)

    # 清掉历史遗留的公开全量文件（老版本会生成，留着等于免费公开全部地址）
    for stale in (SUB_DIR / "all.m3u", SUB_DIR / "region"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
            print(f"  [subs] 已删除历史公开文件 {stale.name}/")
        elif stale.exists():
            stale.unlink()
            print(f"  [subs] 已删除历史公开文件 {stale.name}")
    return payload


def main() -> None:
    build()


if __name__ == "__main__":
    main()
