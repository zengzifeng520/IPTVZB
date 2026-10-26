# -*- coding: utf-8 -*-
"""从 FOFA 网络空间测绘抓组播中转服务器。

为什么需要它
------------
api.809899.xyz 只有 147 台，覆盖 21 个地区，港澳台 0 台。
FOFA/Quake 能直接搜全网 `Server: udpxy` 资产，是唯一能突破这个天花板的路子
（taoiptv.com 就是这么干的）。

两种认证方式
------------
  A. --cookie  「网页登录 Cookie」（推荐，消耗网页免费额度 1000）
     浏览器登录 fofa.info → F12 → Network → 任意请求 → 复制 Cookie 整串
     例：python fofa_harvest.py --cookie "sess=xxx; cf_clearance=yyy"

  B. --key     「API Key」（需账号开通 API 权限，免费账号默认 remain_api_query=0）
     例：python fofa_harvest.py --key "0c11dcb98b3a..."

搜索语句（默认按优先级跑一遍求并集）
------------------------------------
  server="udpxy"                  udpxy 中转服务器（最核心）
  body="/rtp/" && country="CN"    页面里带组播地址
  body="/iptv/live/zh_cn.js"      酒店/运营商 IPTV 播控（常带 rtp 转发）
  body="/tsfile/live/"            华为平台点播目录
  server="HMS Download Service"   华为 HMS 平台

输出
----
  spider/data/fofa_hosts.json  {host: {region, isp, src:"fofa", channels: []}}
  —— channels 为空，交给 api_harvest.py 的 foodie 滚雪球补频道，
     或由 udpxy.py 直接探测 /status。

用法
----
  python fofa_harvest.py --cookie "..."            # 跑全部语句
  python fofa_harvest.py --cookie "..." --pages 3  # 每句翻 3 页
  python fofa_harvest.py --key "..." --q 'server="udpxy"'
"""
from __future__ import annotations

import argparse
import base64
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import config

DATA_DIR = config.DATA_DIR
OUT_JSON = DATA_DIR / "fofa_hosts.json"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 默认搜索语句：从最核心的 udpxy 到各类 IPTV 播控平台
DEFAULT_QUERIES = [
    'server="udpxy"',
    'body="/rtp/" && country="CN"',
    'body="/iptv/live/zh_cn.js"',
    'body="/tsfile/live/"',
    'server="HMS Download Service"',
]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _get(url: str, headers: dict, timeout: int = 45) -> dict | None:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            raw = r.read().decode("utf-8", "replace")
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        print("  [fofa] 请求失败: %s: %s" % (type(exc).__name__, exc))
        return None


def search(q: str, page: int, size: int, key: str, cookie: str) -> list[list]:
    """跑一页搜索，返回 results（二维数组，顺序对应 fields）。"""
    qb = base64.b64encode(q.encode("utf-8")).decode()
    # 只用基础字段：免费账号对 province/city 等字段没权限（820001）
    fields = "host,ip,port"
    params = {
        "qbase64": qb,
        "page": str(page),
        "size": str(size),
        "fields": fields,
    }
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if key:
        params["key"] = key
    if cookie:
        headers["Cookie"] = cookie
        headers["Referer"] = "https://fofa.info/result?qbase64=" + urllib.parse.quote(qb)

    url = "https://fofa.info/api/v1/search/all?" + urllib.parse.urlencode(params)
    d = _get(url, headers)
    if not d:
        return []
    if d.get("error"):
        msg = d.get("errmsg") or ""
        if "820031" in msg:
            print("  [fofa] API 额度不足（免费账号默认不开 API，改用 --cookie）")
        elif "-700" in msg:
            print("  [fofa] 账号无效（Cookie 过期或未登录）")
        else:
            print("  [fofa] 接口报错: %s" % msg)
        return []
    return d.get("results") or []


def harvest(queries: list[str], pages: int, size: int, key: str, cookie: str) -> dict:
    hosts: dict[str, dict] = {}
    for q in queries:
        print("  [fofa] 搜索: %s" % q)
        for page in range(1, pages + 1):
            rows = search(q, page, size, key, cookie)
            if not rows:
                break
            added = 0
            for row in rows:
                # row = [host, ip, port]（基础字段；地区交给 regions.py 查归属地）
                if not isinstance(row, (list, tuple)) or not row:
                    continue
                host = str(row[0] or "").strip()
                if not host and len(row) >= 3:
                    ip, port = str(row[1] or ""), str(row[2] or "")
                    if ip and port:
                        host = "%s:%s" % (ip, port)
                if not host:
                    continue
                if host not in hosts:
                    hosts[host] = {
                        "region": "未知",
                        "isp": "",
                        "src": "fofa",
                        "channels": [],
                    }
                    added += 1
            print("    第 %d 页 %d 条（新增 %d）" % (page, len(rows), added))
            if len(rows) < size:
                break
            time.sleep(0.6)
        time.sleep(0.8)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(hosts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print("  [fofa] 共 %d 台 -> %s" % (len(hosts), OUT_JSON))
    return hosts


def main() -> None:
    ap = argparse.ArgumentParser(description="从 FOFA 抓组播中转服务器")
    ap.add_argument("--key", default="", help="FOFA API Key（需 API 权限）")
    ap.add_argument("--cookie", default="", help="网页登录 Cookie（消耗免费额度）")
    ap.add_argument("--q", default="", help="自定义查询语句（覆盖默认列表）")
    ap.add_argument("--pages", type=int, default=1, help="每条语句翻几页（默认 1）")
    ap.add_argument("--size", type=int, default=100, help="每页条数（默认 100）")
    args = ap.parse_args()

    if not args.key and not args.cookie:
        print("需要 --key 或 --cookie 之一")
        sys.exit(1)

    queries = [args.q] if args.q else DEFAULT_QUERIES
    print("[fofa] 开始采集（%d 条语句 × %d 页）..." % (len(queries), args.pages))
    harvest(queries, args.pages, args.size, args.key, args.cookie)


if __name__ == "__main__":
    main()
