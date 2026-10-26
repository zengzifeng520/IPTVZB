#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全局配置：公开源列表、检测参数、路径。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "iptv.db"
CATEGORIES_PATH = DATA_DIR / "categories.json"
WEB_DATA_DIR = BASE_DIR.parent / "data"

# ---------------------------------------------------------------- 公开源列表
# 说明：每个源可配置多个镜像前缀，脚本会按顺序尝试，第一个成功的即采用。
# raw.githubusercontent.com 在部分网络环境不可直连，因此默认走加速镜像。
GH_MIRRORS = [
    "https://ghproxy.net/",
    "https://gh-proxy.com/",
    "",
]

SOURCES = [
    {
        "id": "suxuang",
        "name": "suxuang/myIPTV",
        "url": "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
        "mirrored": True,
        "weight": 10,  # 源可信度，越高越优先展示
    },
    {
        "id": "zbefine",
        "name": "zbefine/iptv",
        "url": "https://raw.githubusercontent.com/zbefine/iptv/main/iptv.m3u",
        "mirrored": True,
        "weight": 8,
    },
    {
        "id": "vbskycn",
        "name": "vbskycn/iptv",
        "url": "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.m3u",
        "mirrored": True,
        "weight": 7,
    },
    {
        "id": "yuechan",
        "name": "YueChan/Live",
        "url": "https://raw.githubusercontent.com/YueChan/Live/main/IPTV.m3u",
        "mirrored": True,
        "weight": 6,
    },
    {
        "id": "wwb521",
        "name": "wwb521/live",
        "url": "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
        "mirrored": True,
        "weight": 5,
    },
    {
        "id": "kimentanm",
        "name": "kimentanm/aptv",
        "url": "https://raw.githubusercontent.com/kimentanm/aptv/master/m3u/iptv.m3u",
        "mirrored": True,
        "weight": 5,
    },
    {
        "id": "iptvorg-hk",
        "name": "iptv-org/hk",
        "url": "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/hk.m3u",
        "mirrored": True,
        "weight": 4,
    },
    {
        "id": "iptvorg-mo",
        "name": "iptv-org/mo",
        "url": "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/mo.m3u",
        "mirrored": True,
        "weight": 3,
    },
    {
        "id": "iptvorg-cn",
        "name": "iptv-org/cn",
        "url": "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
        "mirrored": True,
        "weight": 4,
    },
    {
        "id": "iptvorg-zho",
        "name": "iptv-org/zho",
        "url": "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/zho.m3u",
        "mirrored": True,
        "weight": 3,
    },
]

# 直接可访问（非 github）的源
DIRECT_SOURCES = [
    {
        "id": "iptvorg-pages",
        "name": "iptv-org/pages",
        "url": "https://iptv-org.github.io/iptv/countries/cn.m3u",
        "mirrored": False,
        "weight": 3,
    },
]

# ---------------------------------------------------------------- 抓取参数
FETCH_TIMEOUT = 30
FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------- 检测参数
PROBE_CONNECT_TIMEOUT = 6.0      # 建立连接超时（秒）
PROBE_READ_TIMEOUT = 8.0         # 读取超时（秒）
PROBE_SAMPLE_BYTES = 480 * 1024  # 测速采样字节数
PROBE_MAX_SEGMENTS = 3           # 最多拉取的分片数
PROBE_WORKERS = 32               # 并发线程
PROBE_SKIP_LOCAL = True          # 跳过内网/组播地址（个人机器无法播放）

# 视为"可播放"的最低标准
MIN_WIDTH = 640                  # 低于此宽度视为低清，默认丢弃
KEEP_UNKNOWN_RESOLUTION = True    # 探测不出分辨率是否保留
MAX_STREAMS_PER_CHANNEL = 12     # 每个频道最多保留的源数量

# 只保留这些协议（rtp/udp/rtsp 需要组播网络，普通用户无法直接播放）
ALLOWED_SCHEMES = ("http", "https")

# ---------------------------------------------------------------- 站点信息
SITE_NAME = "光影直播"
SITE_DESC = "全网公开直播源聚合 · 实时可用性检测 · 一键订阅"
