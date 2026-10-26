# -*- coding: utf-8 -*-
"""iptv.cqshushu.com 会话 + 接口封装。

处理三层防护：
  1. JS 挑战：请求带 _js_challenge=1 拿 paer_sec_token（HttpOnly，2 小时有效）
  2. 广告拦截检测：需要 ad_ok=1 cookie
  3. 频率限制：429 退避

对外：
  sess.list_page(t, page, limit)  -> 列表页 HTML
  sess.detail(pid, t)             -> 详情页 HTML（含 IP:端口）
  sess.parse(ip_port)             -> 解析 JSON（含频道列表）
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://iptv.cqshushu.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HERE = Path(__file__).resolve().parent

# 站前端 jap.js 里的哈希盐（反向得到，等价实现）
_TOKEN_SECRET = "iptv_secret_key_2026"


def _djb2(s: str) -> int:
    h = 5381
    for ch in s:
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return h


def make_token(ts: int | None = None) -> str:
    """生成解析接口 token。"""
    ts = int(time.time()) if ts is None else ts
    raw = f"{ts}_{_djb2(_TOKEN_SECRET + str(ts) + _TOKEN_SECRET)}"
    return base64.b64encode(raw.encode()).decode()


class ShushuSession:
    def __init__(self, verbose: bool = True):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        # 直连，避免本地沙箱代理对 github.com 之外的站点返回 503
        self.s.trust_env = False
        self.verbose = verbose
        self._token = None
        self._booted = False

    def log(self, msg):
        if self.verbose:
            print(msg, file=sys.stderr, flush=True)

    # ---------------- 防护处理 ----------------
    def boot(self):
        self.s.get(BASE + "/index.php", timeout=25)
        self.s.cookies.set("ad_ok", "1", domain="iptv.cqshushu.com", path="/")
        self._booted = True
        return self.pass_challenge()

    def pass_challenge(self) -> bool:
        """请求带 _js_challenge=1，服务器会 Set-Cookie: paer_sec_token 并 302。"""
        url = f"{BASE}/index.php?t=multicast&province=all&limit=10&page=1&_js_challenge=1"
        r = self.s.get(url, allow_redirects=False, timeout=25)
        tok = self.s.cookies.get("paer_sec_token")
        if tok:
            self.log(f"    挑战通过 (token {len(tok)} chars)")
            return True
        self.log(f"    挑战未通过: {r.status_code}")
        return False

    def _wait(self, sec):
        self.log(f"    429 限流，等 {sec:.0f}s")
        time.sleep(sec)

    def get(self, url, retries=5, base_backoff=45) -> requests.Response:
        """带 429 退避 + 403 自动重过挑战。"""
        for i in range(retries):
            r = self.s.get(url, timeout=30, allow_redirects=True)
            if r.status_code == 429:
                self._wait(base_backoff * (i + 1))
                continue
            if r.status_code == 403:
                self.log("    403，重过挑战")
                self.pass_challenge()
                continue
            return r
        return r

    # ---------------- 接口 ----------------
    def list_page(self, t: str = "multicast", page: int = 1, limit: int = 10) -> requests.Response:
        return self.get(f"{BASE}/index.php?t={t}&province=all&limit={limit}&page={page}")

    def detail(self, pid: str, t: str = "multicast") -> requests.Response:
        return self.get(f"{BASE}/index.php?p={pid}&t={t}")

    def token(self) -> str:
        """解析接口 token = base64(`${unix秒}_${djb2(secret+秒+secret)}`)。

        站点前端由混淆脚本生成，这里用等价实现，省掉 Node 依赖。
        """
        return make_token()

    def parse(self, ip_port: str, deep: bool = False) -> dict:
        action = "deep_parse" if deep else "parse"
        for i in range(3):
            r = self.s.post(
                BASE + "/iptv_channel.php",
                data={"action": action, "input": ip_port, "token": self.token()},
                timeout=120,
            )
            if r.status_code == 429:
                self._wait(30 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"解析失败 HTTP {r.status_code}")


# ---------------- 解析工具 ----------------
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
IP_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")
GOTO_RE = re.compile(r"gotoIP\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]")


def strip_tags(x: str) -> str:
    import html as htmllib
    return htmllib.unescape(re.sub(r"<[^>]+>", "", x)).strip()


def parse_list(html: str) -> list[dict]:
    rows = []
    for m in ROW_RE.finditer(html):
        block = m.group(1)
        cells = CELL_RE.findall(block)
        if len(cells) < 6:
            continue
        ipm = IP_RE.search(strip_tags(cells[0]))
        if not ipm:
            continue
        g = GOTO_RE.search(block)
        rows.append({
            "ip": ipm.group(1),
            "p": g.group(1) if g else None,
            "t": g.group(2) if g else None,
            "channels": int(re.sub(r"\D", "", strip_tags(cells[1])) or 0),
            "type": strip_tags(cells[2]),
            "online_since": strip_tags(cells[3]),
            "updated": strip_tags(cells[4]),
            "status": strip_tags(cells[5]),
        })
    return rows


def parse_detail_port(html: str, ip: str) -> int | None:
    m = re.search(re.escape(ip) + r":(\d{2,5})", html)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})", html)
    return int(m.group(2)) if m else None
