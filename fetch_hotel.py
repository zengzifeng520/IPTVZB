"""
酒店源/组播源抓取模块 — 从 IPTV 列表 API（如 api.809899.xyz）获取直播节点并按区域解析

接口说明（对接 IPTV 搜索神器同款 Cloudflare Worker）：
    GET {hotel_api}/extract_hotel     ?keyword={keyword}   → 酒店源节点
    GET {hotel_api}/extract_multicast ?keyword={keyword}   → 组播源节点
    Header: X-App-Auth: {hotel_api_auth}
    返回 JSON: {"results": [{"ip": ..., "region": "广东省 电信", "channels": [{"name": ..., "url": ...}]}]}
"""
import asyncio
import json
import logging
import aiohttp
import config

logger = logging.getLogger(__name__)

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _api_headers():
    """列表/提取 API 的请求头：签名头来自配置，可随上游变更调整。"""
    auth = config.hotel_config.get("hotel_api_auth", "iptv-tools-official-v1")
    return {"User-Agent": DEFAULT_UA, "Connection": "close", "X-App-Auth": auth}


async def _fetch_json(session, url, timeout):
    """通用 JSON 请求（带签名头）"""
    try:
        async with session.get(url, headers=_api_headers(), timeout=timeout) as resp:
            resp.raise_for_status()
            text = await resp.text()
            return json.loads(text)
    except Exception as e:
        logger.warning("[列表API] 请求失败: %s", e)
        return None


def _append_node(channels, node):
    """把单个节点的 channels 写入 channels 字典（{cat: {name: [urls]}}）"""
    cat = node.get("_cat", "")
    if not cat:
        return
    for ch in node.get("channels") or []:
        name = (ch.get("name") or "").strip()
        channel_url = (ch.get("url") or "").strip()
        if name and channel_url and name not in ("查询更多", "Channel"):
            channels.setdefault(cat, {}).setdefault(name, []).append(channel_url)


async def fetch_all_from_hotel():
    """
    主入口：调用列表提取 API（/extract_hotel 与 /extract_multicast），返回 channels 格式。
    返回: {category: {channel_name: [urls]}}
    category 形如 "酒店源-广东省 电信" / "组播源-安徽省 安徽电信"
    """
    hotel_api = (config.hotel_config.get("hotel_api") or "").rstrip("/")
    if not hotel_api:
        logger.warning("[酒店源] 未配置 hotel_api")
        return {}
    keyword = config.hotel_config.get("hotel_keyword", "") or ""
    timeout = aiohttp.ClientTimeout(total=60)
    connector = aiohttp.TCPConnector(limit=5, ssl=False)
    channels = {}

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # 酒店源
        data = await _fetch_json(session, f"{hotel_api}/extract_hotel?keyword={keyword}", 60)
        results = (data or {}).get("results") or []
        for node in results:
            region = (node.get("region") or "").strip()
            node["_cat"] = f"酒店源-{region}" if region else "酒店源"
            _append_node(channels, node)
        logger.info(f"[酒店源] 获取 {len(results)} 个酒店节点")
        # 组播源
        data = await _fetch_json(session, f"{hotel_api}/extract_multicast?keyword={keyword}", 60)
        results = (data or {}).get("results") or []
        for node in results:
            region = (node.get("region") or "").strip()
            node["_cat"] = f"组播源-{region}" if region else "组播源"
            _append_node(channels, node)
        logger.info(f"[酒店源] 获取 {len(results)} 个组播节点")

    # 按 频道名 去重（同名频道保留不同 URL）
    for cat in channels:
        for name in channels[cat]:
            channels[cat][name] = list(dict.fromkeys(channels[cat][name]))
    total = sum(len(urls) for ch in channels.values() for urls in ch.values())
    logger.info(f"[酒店源] 解析完成，共 {len(channels)} 个分类、{total} 个频道-URL 组合")
    return channels
