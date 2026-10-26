# -*- coding: utf-8 -*-
"""中转服务器池子巡检：每小时跑一次，把失效的剔出去。

判活两档：
  浅检   GET http://host/status        —— 看 udpxy 服务还在不在（快）
  深检   真的取一段组播流（默认 16KB）—— 看它到底能不能转出数据（准）
         udpxy 进程活着但上游组播没了，是最常见的「假存活」，只有深检能发现。

剔除规则：
  * 连续 FAIL_LIMIT（默认 2）次判死 → 从 proxy.json 里摘掉，并写进
    data/pool_drop.txt 拉黑 BAN_HOURS（默认 12）小时，
    这样每天全量重建时不会把它又捡回来。
  * 只要有一次判活，失败计数清零。
  * 全灭保护：一轮下来一台都活不了，视为本机网络问题，**不改任何数据**。

数据流：
  data/proxy.json 摘除死链 → regions.py 重算归属地 → subs.py 重发订阅
  （regions 有 30 天归属地缓存，不会重复查询）

用法：
  python pool_check.py               # 浅检 + 深检（推荐，每小时跑）
  python pool_check.py --shallow     # 只浅检，最快
  python pool_check.py --dry-run     # 只报告，不改文件
  python pool_check.py --all         # 连拉黑的也重测（用于复活）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import urllib3

import config

urllib3.disable_warnings()

PROXY_JSON = config.WEB_DATA_DIR / "proxy.json"
STATE_JSON = config.DATA_DIR / "pool_state.json"
DROP_TXT = config.DATA_DIR / "pool_drop.txt"

FAIL_LIMIT = 2
BAN_HOURS = 12
NEED_BYTES = 16 * 1024
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return fallback


def check_status(host: str, timeout: float = 6.0) -> dict:
    """浅检：/status 能访问就算活着。"""
    t0 = time.time()
    for path in ("/status", "/"):
        try:
            r = requests.get(
                "http://%s%s" % (host, path),
                timeout=(4.0, timeout),
                verify=False,
                stream=True,
                headers={"User-Agent": UA},
            )
            body = b""
            for chunk in r.iter_content(2048):
                body += chunk
                if len(body) > 2048:
                    break
            r.close()
            ms = int((time.time() - t0) * 1000)
            if r.status_code in (200, 206):
                return {"alive": True, "ms": ms, "code": r.status_code, "deep": None}
        except requests.RequestException:
            continue
    return {"alive": False, "ms": int((time.time() - t0) * 1000), "code": 0, "deep": None}


def check_stream(url: str, timeout: float = 8.0) -> tuple[bool, int]:
    """深检：真取一段流，拿到 NEED_BYTES 字节才算能播。"""
    got = 0
    try:
        r = requests.get(
            url,
            timeout=(4.0, timeout),
            verify=False,
            stream=True,
            headers={"User-Agent": UA},
        )
        if r.status_code not in (200, 206):
            r.close()
            return False, 0
        for chunk in r.iter_content(8192):
            got += len(chunk)
            if got >= NEED_BYTES:
                break
        r.close()
    except requests.RequestException:
        return False, got
    return got >= NEED_BYTES, got


def probe_host(host: str, sample_urls: list[str], deep: bool, timeout: float) -> dict:
    r = check_status(host, timeout)
    if not r["alive"] or not deep or not sample_urls:
        return r
    # 单条组播可能本身失效（频道下线 / 整批地址变了），不能因此判死整台主机。
    # 按均匀取样最多试 5 条，任意一条能出数据就算它能转流。
    for url in sample_urls[:5]:
        ok, got = check_stream(url, timeout)
        if ok:
            r["deep"] = True
            r["bytes"] = got
            r["alive"] = True
            return r
        r["bytes"] = got
    r["deep"] = False
    r["alive"] = False
    return r


def load_drop() -> dict[str, float]:
    """读拉黑表 {host: until_ts}，顺手清掉过期的。"""
    out: dict[str, float] = {}
    if not DROP_TXT.exists():
        return out
    now = time.time()
    for line in DROP_TXT.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            until = float(parts[1])
        except ValueError:
            continue
        if until > now:
            out[parts[0]] = until
    return out


def save_drop(drop: dict[str, float]) -> None:
    lines = ["# host  until_ts   巡检判死后拉黑，到期后重新给机会"]
    for h, until in sorted(drop.items()):
        lines.append("%s %d" % (h, int(until)))
    DROP_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prune(payload: dict, allowed: set[str]) -> tuple[dict, int, int]:
    """从 proxy.json 里摘掉 allowed 之外的主机，返回 (新 payload, 摘掉主机数, 摘掉地址数)。"""
    drop_hosts = {h["h"] for h in payload.get("hosts") or [] if h["h"] not in allowed}
    if not drop_hosts:
        return payload, 0, 0

    channels = []
    n_streams = 0
    for ch in payload.get("channels") or []:
        kept = [s for s in ch["streams"] if s["h"] not in drop_hosts]
        if not kept:
            continue
        ch = dict(ch)
        ch["streams"] = kept
        ch["hosts"] = sorted({s["h"] for s in kept})
        channels.append(ch)
        n_streams += len(kept)

    hosts = []
    for h in payload.get("hosts") or []:
        if h["h"] in drop_hosts:
            continue
        h = dict(h)
        h["n"] = sum(1 for c in channels for s in c["streams"] if s["h"] == h["h"])
        hosts.append(h)

    new = dict(payload)
    new["channels"] = channels
    new["hosts"] = hosts
    new["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    st = dict(new.get("stats") or {})
    st["hosts_alive"] = len(hosts)
    st["channels"] = len(channels)
    st["streams"] = n_streams
    new["stats"] = st
    return new, len(drop_hosts), sum(len(c["streams"]) for c in payload.get("channels") or []) - n_streams


def main() -> None:
    ap = argparse.ArgumentParser(description="中转服务器池子巡检")
    ap.add_argument("--shallow", action="store_true", help="只查 /status，不取流")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--workers", type=int, default=30)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--all", action="store_true", help="把拉黑名单也一起重测")
    args = ap.parse_args()

    t0 = time.time()
    payload = load_json(PROXY_JSON, {})
    hosts = payload.get("hosts") or []
    if not hosts:
        print("  [check] proxy.json 没有主机，跳过")
        return

    state: dict = load_json(STATE_JSON, {})
    drop = load_drop()
    now = time.time()

    # 深检样本：把每台主机在池子里的地址按频道顺序均匀抽 8 条。
    # 不能只取前 3 条 —— 同一运营商常整批换组播地址，
    # 前几条可能全废，会把一台好机器误判成死的。
    per_host: dict[str, list[str]] = {}
    for ch in payload.get("channels") or []:
        for s in ch.get("streams") or []:
            bucket = per_host.setdefault(s["h"], [])
            if s["u"] not in bucket:
                bucket.append(s["u"])

    sample: dict[str, list[str]] = {}
    for host, urls in per_host.items():
        n = len(urls)
        if n <= 8:
            sample[host] = urls
        else:
            idx = sorted({int(i * (n - 1) / 7) for i in range(8)})
            sample[host] = [urls[i] for i in idx]

    targets = [h["h"] for h in hosts]
    extra: list[str] = []
    if args.all:
        extra = [h for h in drop if h not in targets]
        targets += extra

    print(
        "  [check] 巡检 %d 台（深检%s）..."
        % (len(targets), "关闭" if args.shallow else "开启")
    )
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(probe_host, h, sample.get(h, []), not args.shallow, args.timeout): h
            for h in targets
        }
        for fut, h in futs.items():
            try:
                results[h] = fut.result()
            except Exception:  # noqa: BLE001
                results[h] = {"alive": False, "ms": 0, "code": 0, "deep": None}

    alive = [h for h, r in results.items() if r["alive"]]
    dead = [h for h, r in results.items() if not r["alive"]]

    # 全灭保护：本机网络问题不要动数据
    if not alive and len(targets) >= 3:
        print("  [check] 全部不可达（0/%d），疑似网络问题，本次不改动数据" % len(targets))
        return

    # 更新状态与拉黑表
    newly_dropped: list[str] = []
    revived: list[str] = []
    to_remove: set[str] = set()  # 只有「连续 FAIL_LIMIT 次判死」的才真摘除
    for h in targets:
        r = results[h]
        st = state.get(h) or {"fails": 0}
        st["last_check"] = int(now)
        st["ms"] = r.get("ms", 0)
        st["deep"] = r.get("deep")
        if r["alive"]:
            st["fails"] = 0
            st["last_ok"] = int(now)
            if h in drop:
                drop.pop(h, None)
                revived.append(h)
        else:
            st["fails"] = int(st.get("fails") or 0) + 1
            if st["fails"] >= FAIL_LIMIT:
                to_remove.add(h)
                was_banned = h in drop
                drop[h] = now + BAN_HOURS * 3600
                st["banned_at"] = int(now)
                if not was_banned:
                    newly_dropped.append(h)
        state[h] = st

    # 只保留「可疑」主机的状态（失败过、或正在拉黑）。
    # 健康主机的计数恒为 0，没必要每小时把 last_check 写进去，
    # 否则状态文件每小时都变，Actions 会空跑出一堆无意义提交。
    state = {k: v for k, v in state.items() if v.get("fails") or k in drop}

    print(
        "  [check] 存活 %d / %d 台；本轮新增摘除 %d，复活 %d"
        % (len(alive), len(targets), len(newly_dropped), len(revived))
    )
    for h in newly_dropped:
        print("          - %-24s 连续 %d 次失败" % (h, state[h]["fails"]))

    if args.dry_run:
        print("  [check] --dry-run，不写文件")
        return

    STATE_JSON.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    save_drop(drop)

    # 摘除：只处理「池内主机且已连续判死」的
    pool_hosts = {x["h"] for x in hosts}
    drop_from_pool = to_remove & pool_hosts
    if not drop_from_pool:
        print("  [check] 本轮没有需要摘除的主机，proxy.json 保持不动")
        return

    new_payload, n_host, n_stream = prune(payload, pool_hosts - drop_from_pool)
    PROXY_JSON.write_text(
        json.dumps(new_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print("  [check] 摘除 %d 台 / %d 条地址 -> proxy.json" % (n_host, n_stream))

    # 重算地区 + 重发订阅，保证前端拿到的都是活链
    try:
        import regions

        regions.build()
    except Exception as exc:  # noqa: BLE001
        print("  [check] regions 重算失败: %s" % exc)
    try:
        import subs

        subs.build()
    except Exception as exc:  # noqa: BLE001
        print("  [check] 订阅重发失败: %s" % exc)

    print("  [check] 完成，耗时 %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    main()
