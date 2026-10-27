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
import logos

# 到期时间按北京时间当天 23:59:59 算（Actions 跑在 UTC，必须显式指定时区）
CST = timezone(timedelta(hours=8))

# EPG（节目单）：统一由 zengzifeng520/IPTV 仓库的 gh-pages 提供。
# 该文件 = 用户原有的国内节目单 + 我们用 tools/build_epg.py 并入的港澳台节目单。
# raw.githubusercontent 国内不通，走 jsdelivr（实测 200 / 15MB）。
EPG_URL = "https://gcore.jsdelivr.net/gh/zengzifeng520/IPTV@gh-pages/e_all.xml"
# 港澳台频道名 -> epg.pw 的 channel id（数字）。没映射的就不加 tvg-id，
# 播放器显示「无节目信息」——epg.pw 确实没有那些台的节目单，不硬凑。
_EPG_MAP: dict[str, str] | None = None

# EPG 里实际存在的 channel id（启动时从 data/public/epg.xml.gz 读一次）。
# 组播源的频道名和 EPG 的 id 对不齐（我们是 CCTV-1，EPG 里是「CCTV-1 综合」），
# 所以 tvg-id 不能直接写频道名，要按候选列表去撞，撞上哪个用哪个。
_EPG_IDS: set[str] | None = None

# 台标解析缓存：同一个频道名一次运行里只算一遍（一次生成要写几十个 m3u）
_MISS = object()
_logo_cache: dict[str, str | None | object] = {}

PROXY_JSON = config.WEB_DATA_DIR / "proxy.json"
# 酒店源：HLS 直连（/hls/x/index.m3u8、/tsfile/live/x.m3u8?key=txiptv），
# 不受地区限制，单独作为「酒店源」地区呈现，由 hotel_pool.py 生成。
HOTEL_JSON = config.WEB_DATA_DIR / "proxy_hotel.json"
# 港澳台：台湾台 + 凤凰系列 + 澳门莲花，大陆可直连的 tsfile 源，
# 由 gangaotai_pool.py 生成，同样作为独立分类呈现。
GANGAOTAI_JSON = config.WEB_DATA_DIR / "proxy_gangaotai.json"
# 国外：境外 FAST / 公共广播 / 新闻频道的公开 HLS，由 intl_pool.py 生成，
# 第三个独立分类。频道按国家分组（group-title="国外·日本" 这种）。
INTL_JSON = config.WEB_DATA_DIR / "proxy_intl.json"
REGIONS_JSON = config.WEB_DATA_DIR / "regions.json"
SUB_DIR = config.WEB_DATA_DIR / "sub"
INDEX_JSON = SUB_DIR / "index.json"

USERS_JSON = config.WEB_DATA_DIR / "users.json"
USERS_DIR = config.WEB_DATA_DIR / "users"

# 公开数据：只有频道名/分类/条数，**不含任何播放地址和服务器 IP**。
# 页面浏览用它；真正的地址只出现在每个会员自己的 data/users/<token>/ 下。
PUBLIC_DIR = config.WEB_DATA_DIR / "public"
PUBLIC_JSON = PUBLIC_DIR / "channels.json"
# 酒店源独立目录：前端单独一个页面，不进地区网格
HOTEL_PUBLIC = PUBLIC_DIR / "hotel.json"
# 港澳台独立目录：前端单独一个页面
GANGAOTAI_PUBLIC = PUBLIC_DIR / "gangaotai.json"
INTL_PUBLIC = PUBLIC_DIR / "intl.json"

# 免费订阅：按「到期日」分目录，滚动保留未来 7 天，过期目录直接删掉
FREE_DIR = config.WEB_DATA_DIR / "free"
FREE_DAYS = 7

# 公开订阅链接的有效期（天）：页面发出去的地址就是「今天 + 30 天」那一份
SUB_DAYS = 30

# token 盐值：前端 assets/js/auth.js 里的 TOKEN_SALT 必须与此一致
TOKEN_SALT = "zzf-sub-2026"

# 到期后写入的空订阅（保留 #EXTM3U 头，播放器当合法列表处理，只是没有频道）
EMPTY_SUB = "#EXTM3U\n# 会员已到期，订阅已停止更新，续费后立即恢复\n"


def token_of(sid: str) -> str:
    """赞助码 -> 16 位订阅 token（与前端 assets/js/auth.js 的 tokenOf 一致）。"""
    raw = f"{TOKEN_SALT}|{str(sid).strip().upper()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _epg_ids() -> set[str]:
    """读 EPG 里所有 channel id（只读一次）"""
    global _EPG_IDS
    if _EPG_IDS is None:
        _EPG_IDS = set()
        f = PUBLIC_DIR / "epg.xml.gz"
        if f.exists():
            try:
                import gzip
                import re as _re
                raw = gzip.open(f, "rb").read(60_000_000).decode("utf-8", "ignore")
                _EPG_IDS = set(_re.findall(r'<channel id="([^"]+)"', raw))
                print(f"  [subs] EPG 载入 {len(_EPG_IDS)} 个 channel id")
            except Exception as e:  # noqa: BLE001
                print(f"  [subs] EPG 读取失败：{e}")
    return _EPG_IDS


def _resolve_epg_id(name: str) -> str | None:
    """频道名 -> EPG 里真实存在的 id；撞不上返回 None（不加 tvg-id，不硬凑）"""
    ids = _epg_ids()
    if not ids:
        return None
    if name in ids:
        return name
    # 变体：去空格、去横线、繁转简后的写法
    cands = [
        name.replace(" ", ""), name.replace("-", ""), name.replace("·", ""),
        name.replace("-", "").replace(" ", ""),
    ]
    for c in cands:
        if c in ids:
            return c
    # 前缀匹配：「CCTV-1」-> 「CCTV-1 综合」；只认 "名字 + 空格" 开头，避免
    # CCTV-1 误配到 CCTV-10
    for eid in ids:
        if eid.startswith(name + " ") or eid.startswith(name + "(") or eid == name + "HD":
            return eid
    return None


def _epg_map() -> dict:
    global _EPG_MAP
    if _EPG_MAP is None:
        f = Path(__file__).parent / "data" / "epg_map.json"
        try:
            _EPG_MAP = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except Exception:  # noqa: BLE001
            _EPG_MAP = {}
    return _EPG_MAP


def _extinf(ch: dict) -> str:
    """EXTINF 行。台标能找到就加 tvg-logo，找不到就不加——
    只往属性里加东西，播放地址（下一行）一个字符都不改。"""
    name = ch["display"]
    # 国外频道走严格匹配：英文名做包含匹配会串台
    strict = str(ch.get("type") or "").startswith("国外")
    ck = (name, strict)
    logo = _logo_cache.get(ck, _MISS)
    if logo is _MISS:
        logo = logos.resolve(name, strict=strict)
        _logo_cache[ck] = logo
    logo_attr = f' tvg-logo="{logo}"' if logo else ""
    # tvg-id 用于匹配 EPG：港澳台走 epg.pw 的数字 id，其余分类用频道名本身
    # （用户那份国内节目单的 id 就是频道名）
    if ch.get("type") == "港澳台":
        eid = _epg_map().get(name)
    else:
        eid = _resolve_epg_id(name)
    id_attr = f' tvg-id="{eid}"' if eid else ""
    return (
        f'#EXTINF:-1{id_attr} tvg-name="{name}"{logo_attr} '
        f'group-title="{ch["type"]}",{name}'
    )


def _write(path: Path, channels: list[dict], host_set: set[str] | None = None) -> tuple[int, int]:
    """写一个 m3u，返回 (频道数, 地址数)。host_set 为空表示不限服务器。"""
    lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
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


def cleanup_legacy_hotel() -> None:
    """删掉旧版「HOTEL 当地区」留下的 HOTEL.m3u / urls/HOTEL.json。

    注意：只在旧文件确实是大写命名时才删。Windows 上大小写不敏感，
    如果只剩小写 hotel.m3u，说明已经是新版，跳过。
    """
    if FREE_DIR.exists():
        for d in FREE_DIR.iterdir():
            if not d.is_dir():
                continue
            for p in d.glob("*.m3u"):
                if p.stem == "HOTEL":
                    p.unlink(missing_ok=True)
    if USERS_DIR.exists():
        for d in USERS_DIR.iterdir():
            if not d.is_dir():
                continue
            for p in d.glob("*.m3u"):
                if p.stem == "HOTEL":
                    p.unlink(missing_ok=True)
            for p in (d / "urls").glob("*.json") if (d / "urls").exists() else []:
                if p.stem == "HOTEL":
                    p.unlink(missing_ok=True)


def load_hotel() -> dict | None:
    """读酒店源（独立模块，不塞进 regions）。

    返回 {"channels": [...], "hosts": [...], "host_set": set} 或 None。
    """
    if not HOTEL_JSON.exists():
        return None
    try:
        hd = json.loads(HOTEL_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [subs] 酒店源解析失败，跳过：{exc}")
        return None
    chans = hd.get("channels") or []
    hosts = [x["h"] for x in (hd.get("hosts") or []) if x.get("h")]
    if not chans or not hosts:
        return None
    return {"channels": chans, "hosts": hosts, "host_set": set(hosts)}


def load_gangaotai() -> dict | None:
    """读港澳台源（独立模块，不塞进 regions），结构与酒店源一致。"""
    if not GANGAOTAI_JSON.exists():
        return None
    try:
        gd = json.loads(GANGAOTAI_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [subs] 港澳台源解析失败，跳过：{exc}")
        return None
    chans = gd.get("channels") or []
    hosts = [x["h"] for x in (gd.get("hosts") or []) if x.get("h")]
    if not chans or not hosts:
        return None
    return {"channels": chans, "hosts": hosts, "host_set": set(hosts)}


def load_intl() -> dict | None:
    """读国外源（独立模块，不塞进 regions），结构与酒店源一致。"""
    if not INTL_JSON.exists():
        return None
    try:
        gd = json.loads(INTL_JSON.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [subs] 国外源解析失败，跳过：{exc}")
        return None
    chans = gd.get("channels") or []
    hosts = [x["h"] for x in (gd.get("hosts") or []) if x.get("h")]
    if not chans or not hosts:
        return None
    return {"channels": chans, "hosts": hosts, "host_set": set(hosts)}


def build_hotel_public(hotel: dict | None) -> dict:
    """酒店源的公开目录：频道名 + 每频道条数，**没有任何地址**。"""
    if not hotel:
        print("  [subs] 无酒店源，跳过 public/hotel.json")
        return {}
    chans = hotel["channels"]
    out = [
        {
            "key": c["key"],
            "display": c.get("display") or c["key"],
            "count": len(c.get("streams") or []),
        }
        for c in chans
        if c.get("streams")
    ]
    out.sort(key=lambda c: (-c["count"], c["key"]))
    total = sum(c["count"] for c in out)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts": len(hotel["hosts"]),
            "channels": len(out),
            "streams": total,
        },
        # 与地区一致：公开中转服务器列表（只有域名/IP:端口，不含任何播放地址）
        "hosts": hotel["hosts"],
        "hostCount": len(hotel["hosts"]),
        "channels": out,
    }
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    HOTEL_PUBLIC.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  [subs] public/hotel.json  {len(out)} 频道 / {total} 条（仅名称，无地址）")
    return payload


def build_gangaotai_public(gangaotai: dict | None) -> dict:
    """港澳台源的公开目录：频道名 + 每频道条数，**没有任何地址**。"""
    if not gangaotai:
        print("  [subs] 无港澳台源，跳过 public/gangaotai.json")
        return {}
    chans = gangaotai["channels"]
    out = [
        {
            "key": c["key"],
            "display": c.get("display") or c["key"],
            # 线路类型：移动专线（只有移动宽带能连）/ 全国通用
            "line": c.get("line") or "全国通用",
            "count": len(c.get("streams") or []),
        }
        for c in chans
        if c.get("streams")
    ]
    out.sort(key=lambda c: (-c["count"], c["key"]))
    total = sum(c["count"] for c in out)
    n_mobile = sum(1 for c in out if c["line"] == "移动专线")
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts": len(gangaotai["hosts"]),
            "mobileOnly": n_mobile,
            "anyLine": len(out) - n_mobile,
            "channels": len(out),
            "streams": total,
        },
        "hosts": gangaotai["hosts"],
        "hostCount": len(gangaotai["hosts"]),
        "channels": out,
    }
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    GANGAOTAI_PUBLIC.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  [subs] public/gangaotai.json  {len(out)} 频道 / {total} 条（仅名称，无地址）")
    return payload


def build_intl_public(intl: dict | None) -> dict:
    """国外源的公开目录：频道名 + 每频道条数 + 按国家分组，**没有任何地址**。"""
    if not intl:
        print("  [subs] 无国外源，跳过 public/intl.json")
        return {}
    chans = intl["channels"]
    out = [
        {
            "key": c["key"],
            "display": c.get("display") or c["key"],
            "region": c.get("region") or "其他",
            "count": len(c.get("streams") or []),
        }
        for c in chans
        if c.get("streams")
    ]
    # 按国家归并，国家顺序沿用 proxy_intl.json 里的 regions
    by_region: dict[str, list] = {}
    for c in out:
        by_region.setdefault(c["region"], []).append(c)
    for arr in by_region.values():
        arr.sort(key=lambda x: (-x["count"], x["key"].lower()))
    order = [r["name"] for r in (json.loads(INTL_JSON.read_text(encoding="utf-8")).get("regions") or [])] \
        if INTL_JSON.exists() else []
    regions_out = [{"name": k, "channels": len(by_region[k])}
                   for k in order if k in by_region]
    regions_out += [{"name": k, "channels": len(v)}
                    for k, v in by_region.items() if k not in {r["name"] for r in regions_out}]
    total = sum(c["count"] for c in out)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            "hosts": len(intl["hosts"]),
            "channels": len(out),
            "streams": total,
            "countries": len(by_region),
        },
        "hosts": intl["hosts"],
        "hostCount": len(intl["hosts"]),
        "regions": regions_out,
        "channels": out,
    }
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    INTL_PUBLIC.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"  [subs] public/intl.json  {len(out)} 频道 / {total} 条 / "
          f"{len(by_region)} 国（仅名称，无地址）")
    return payload


def build_free(channels: list[dict], regions: list[dict],
               hotel: dict | None = None, gangaotai: dict | None = None,
               intl: dict | None = None) -> None:
    """免费订阅：按「到期日」分目录，只保留未来 FREE_DAYS 天。

    目录名就是到期日期（YYYYMMDD），前端按「选地区当天 + 7 天」拼地址。
    过了那一天目录被删除 -> 播放器 404 / 空列表，免费订阅自然失效。
    8 个目录内容完全相同，Git 只存一份 blob，仓库不会被撑大。
    """
    today = datetime.now(CST).date()
    keep: set[str] = set()
    valid = {r["key"] for r in regions}
    has_hotel = bool(hotel and hotel.get("host_set"))
    if has_hotel:
        # 酒店源单独一个 hotel.m3u，不占地区位
        valid.add("hotel")
    has_gangaotai = bool(gangaotai and gangaotai.get("host_set"))
    if has_gangaotai:
        valid.add("gangaotai")
    has_intl = bool(intl and intl.get("host_set"))
    if has_intl:
        valid.add("intl")

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
        if has_hotel:
            target = d / "hotel.m3u"
            c, _s = _write(target, hotel["channels"], hotel["host_set"])
            if not c:
                target.write_text(EMPTY_SUB, encoding="utf-8")
        if has_intl:
            target = d / "intl.m3u"
            c, _st = _write(target, intl["channels"], intl["host_set"])
            if not c:
                target.write_text(EMPTY_SUB, encoding="utf-8")
        if has_gangaotai:
            target = d / "gangaotai.m3u"
            c, _s = _write(target, gangaotai["channels"], gangaotai["host_set"])
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


def build_public(channels: list[dict], regions: list[dict],
                 hotel: dict | None = None, gangaotai: dict | None = None,
                 intl: dict | None = None) -> dict:
    """生成公开的频道目录：只有名字、分类、各地区的条数，**没有任何地址**。

    前端付费墙全靠它：未赞助的人就算把浏览器调试面板打开，
    拿到的也只有「CCTV-1 央视频道 安徽 3 条」这种信息，看不到 host 和 url。
    """
    region_of_host: dict[str, str] = {}
    for r in regions:
        for h in r.get("hosts") or []:
            region_of_host[h] = r["key"]

    out_channels = []
    total_streams = 0
    for ch in channels:
        per: dict[str, int] = {}
        for s in ch["streams"]:
            key = region_of_host.get(s["h"])
            if not key:
                continue
            per[key] = per.get(key, 0) + 1
            total_streams += 1
        if not per:
            continue
        out_channels.append(
            {
                "key": ch["key"],
                "display": ch.get("display") or ch["key"],
                "type": ch.get("type") or "",
                "regions": per,
            }
        )

    hosts = sorted({h for r in regions for h in (r.get("hosts") or [])})
    out_regions = [
        {
            "key": r["key"],
            "name": r["name"],
            "isp": r.get("isp") or "",
            "channels": r.get("channels") or 0,
            "streams": r.get("streams") or 0,
            "hosts": r.get("hosts") or [],
            "hostCount": len(r.get("hosts") or []),
        }
        for r in regions
        if (r.get("channels") or 0) > 0
    ]

    # 酒店源是独立模块：这里只统计，不进 regions
    h_ch = (hotel or {}).get("channels") or []
    h_hosts = (hotel or {}).get("hosts") or []
    hotel_streams = sum(len(c["streams"]) for c in h_ch)
    # 港澳台同样是独立模块
    g_ch = (gangaotai or {}).get("channels") or []
    g_hosts = (gangaotai or {}).get("hosts") or []
    gangaotai_streams = sum(len(c["streams"]) for c in g_ch)
    i_ch = (intl or {}).get("channels") or []
    i_hosts = (intl or {}).get("hosts") or []
    intl_streams = sum(len(c["streams"]) for c in i_ch)
    all_keys = {c["key"] for c in channels} | {c["key"] for c in h_ch} | {c["key"] for c in g_ch}

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {
            # 组播中转
            "hosts": len(hosts),
            "channels": len(out_channels),
            "streams": total_streams,
            "regions": len(out_regions),
            "relayHosts": len(hosts),
            "relayStreams": total_streams,
            # 酒店源（独立分类）
            "hotelHosts": len(h_hosts),
            "hotelChannels": len(h_ch),
            "hotelStreams": hotel_streams,
            # 港澳台（独立分类）
            "gangaotaiHosts": len(g_hosts),
            "gangaotaiChannels": len(g_ch),
            "gangaotaiStreams": gangaotai_streams,
            # 国外（按国家分组）
            "intlHosts": len(i_hosts),
            "intlChannels": len(i_ch),
            "intlStreams": intl_streams,
            "intlCountries": len({c.get("region") or "" for c in i_ch}) if i_ch else 0,
            # 合计（频道去重）
            "channelsTotal": len(all_keys),
            "streamsTotal": total_streams + hotel_streams + gangaotai_streams + intl_streams,
            # 订阅链接有效期（前端据此拼 data/public/sub/<到期日>/ 路径）
            "subDays": SUB_DAYS,
            "subExpire": (datetime.now(CST).date() + timedelta(days=SUB_DAYS)).strftime("%Y-%m-%d"),
        },
        "regions": out_regions,
        "channels": out_channels,
    }
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(
        f"  [subs] public/channels.json  {len(out_channels)} 频道 / "
        f"{total_streams} 条（仅名称，无地址）"
    )
    return payload


def _write_urls(path: Path, channels: list[dict], host_set: set[str] | None = None) -> int:
    """写某个会员某个地区的地址表：{频道key: [[host, url], ...]}"""
    out: dict[str, list] = {}
    for ch in channels:
        arr = [
            [s["h"], s["u"]]
            for s in ch["streams"]
            if host_set is None or s["h"] in host_set
        ]
        if arr:
            out[ch["key"]] = arr
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return len(out)


def _m3u_text(channels: list[dict], host_set: set[str] | None = None) -> str:
    """把频道列表拼成 m3u 文本（同一份内容要写进多个有效期的目录，先算一次）。"""
    lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
    for ch in channels:
        picked = ch["streams"] if host_set is None else [s for s in ch["streams"] if s["h"] in host_set]
        if not picked:
            continue
        head = _extinf(ch)
        for s in picked:
            lines.append(head)
            lines.append(s["u"])
    return "\n".join(lines) + "\n"


def build_public_subs(channels: list[dict], regions: list[dict],
                      hotel: dict | None = None, gangaotai: dict | None = None,
                      intl: dict | None = None) -> dict:
    """生成公开订阅文件：全量 + 分地区 + 酒店源 + 各地区地址表。

    两层目录：
      data/public/*.m3u                稳定路径（导航、桌面收藏用，实际不对外承诺永久）
      data/public/sub/<到期日>/*.m3u   带有效期的订阅地址，有效期 SUB_DAYS 天

    有效期做法：每次运行都把「今天 ~ 今天+30 天」这 31 个目录写一遍（内容完全一样，
    Git 按内容哈希去重，只会多存一份 blob），比今天早的目录直接删掉。
    这样：今天发出去的链接 30 天内一定能播；到期后目录消失变 404，
    用户回站点重新复制，拿到的又是新一份 30 天链接 —— 自动续期。
    """
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    urls_dir = PUBLIC_DIR / "urls"
    urls_dir.mkdir(parents=True, exist_ok=True)

    # 先把每种订阅的内容算成文本，避免 31 个目录重复拼字符串
    texts: dict[str, str] = {}
    n_chan, n_stream = _write(PUBLIC_DIR / "all.m3u", channels)
    texts["all.m3u"] = _m3u_text(channels)

    for r in regions:
        host_set = set(r.get("hosts") or [])
        if not host_set:
            (PUBLIC_DIR / f"{r['key']}.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            texts[f"{r['key']}.m3u"] = EMPTY_SUB
            continue
        _write(PUBLIC_DIR / f"{r['key']}.m3u", channels, host_set)
        texts[f"{r['key']}.m3u"] = _m3u_text(channels, host_set)
        _write_urls(urls_dir / f"{r['key']}.json", channels, host_set)

    if hotel:
        _write(PUBLIC_DIR / "hotel.m3u", hotel["channels"], hotel["host_set"])
        texts["hotel.m3u"] = _m3u_text(hotel["channels"], hotel["host_set"])
        _write_urls(urls_dir / "hotel.json", hotel["channels"], hotel["host_set"])

    if intl:
        _write(PUBLIC_DIR / "intl.m3u", intl["channels"], intl["host_set"])
        texts["intl.m3u"] = _m3u_text(intl["channels"], intl["host_set"])
        _write_urls(urls_dir / "intl.json", intl["channels"], intl["host_set"])
    if gangaotai:
        _write(PUBLIC_DIR / "gangaotai.m3u", gangaotai["channels"], gangaotai["host_set"])
        texts["gangaotai.m3u"] = _m3u_text(gangaotai["channels"], gangaotai["host_set"])
        _write_urls(urls_dir / "gangaotai.json", gangaotai["channels"], gangaotai["host_set"])

    # ---- 带有效期的订阅目录 ----
    today = datetime.now(CST).date()
    sub_root = PUBLIC_DIR / "sub"
    sub_root.mkdir(parents=True, exist_ok=True)
    keep = set()
    for i in range(SUB_DAYS + 1):
        key = (today + timedelta(days=i)).strftime("%Y%m%d")
        keep.add(key)
        d = sub_root / key
        d.mkdir(parents=True, exist_ok=True)
        for name, text in texts.items():
            (d / name).write_text(text, encoding="utf-8")
    # 过期目录（比今天早的）删掉 -> 老链接自然 404
    for p in sub_root.iterdir():
        if p.is_dir() and p.name not in keep:
            shutil.rmtree(p, ignore_errors=True)

    expire = (today + timedelta(days=SUB_DAYS)).strftime("%Y-%m-%d")
    print(
        f"  [subs] public/*.m3u 全量 {n_chan} 频道 / {n_stream} 条"
        f"（不含酒店源，公开可下载）"
    )
    print(f"  [subs] 订阅有效期 {SUB_DAYS} 天：{min(keep)} ~ {max(keep)}（到期日 {expire}）")
    return {"channels": n_chan, "streams": n_stream, "expire": expire, "days": SUB_DAYS}


def build_users(channels: list[dict], regions: list[dict],
                hotel: dict | None = None, gangaotai: dict | None = None,
                intl: dict | None = None) -> dict:
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
            if hotel:
                (d / "hotel.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            if intl:
                (d / "intl.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            if gangaotai:
                (d / "gangaotai.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            # 地址表直接删掉，过期后连调试面板也看不到地址
            shutil.rmtree(d / "urls", ignore_errors=True)
            n_exp += 1
            print(f"  [subs] users/{token}  已过期 -> 订阅清空")
            continue

        # 全量订阅：只含组播中转（酒店源单独 hotel.m3u）
        c, s = _write(d / "all.m3u", channels)
        for r in regions:
            host_set = set(r.get("hosts") or [])
            if not host_set:
                (d / f"{r['key']}.m3u").write_text(EMPTY_SUB, encoding="utf-8")
                continue
            rc, rs = _write(d / f"{r['key']}.m3u", channels, host_set)
            if not rc:
                (d / f"{r['key']}.m3u").write_text(EMPTY_SUB, encoding="utf-8")
                continue
            # 页面展示用的地址表，按地区分开，前端只拉当前地区那份
            _write_urls(d / "urls" / f"{r['key']}.json", channels, host_set)
        # 酒店源：独立订阅 + 独立地址表
        if hotel:
            hc, _hs = _write(d / "hotel.m3u", hotel["channels"], hotel["host_set"])
            if not hc:
                (d / "hotel.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            else:
                _write_urls(d / "urls" / "hotel.json", hotel["channels"], hotel["host_set"])
        # 港澳台：独立订阅 + 独立地址表
        # 国外：独立订阅 + 独立地址表
        if intl:
            ic, _is = _write(d / "intl.m3u", intl["channels"], intl["host_set"])
            if not ic:
                (d / "intl.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            else:
                _write_urls(d / "urls" / "intl.json", intl["channels"], intl["host_set"])
        if gangaotai:
            gc, _gs = _write(d / "gangaotai.m3u", gangaotai["channels"], gangaotai["host_set"])
            if not gc:
                (d / "gangaotai.m3u").write_text(EMPTY_SUB, encoding="utf-8")
            else:
                _write_urls(d / "urls" / "gangaotai.json", gangaotai["channels"], gangaotai["host_set"])
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

    # ---- 酒店源：独立模块（不塞进 regions，不参与地区网格）----
    hotel = load_hotel()
    if hotel:
        print(
            "  [subs] 酒店源：%d 台 / %d 频道 / %d 条（独立分类）"
            % (len(hotel["hosts"]), len(hotel["channels"]),
               sum(len(c["streams"]) for c in hotel["channels"]))
        )

    # ---- 港澳台：独立模块（同样不进 regions）----
    gangaotai = load_gangaotai()
    if gangaotai:
        print(
            "  [subs] 港澳台：%d 台 / %d 频道 / %d 条（独立分类）"
            % (len(gangaotai["hosts"]), len(gangaotai["channels"]),
               sum(len(c["streams"]) for c in gangaotai["channels"]))
        )

    # ---- 国外：独立模块（不塞进 regions，不参与地区网格）----
    intl = load_intl()
    if intl:
        print(
            "  [subs] 国外：%d 台 / %d 频道 / %d 条 / %d 国（独立分类）"
            % (len(intl["hosts"]), len(intl["channels"]),
               sum(len(c["streams"]) for c in intl["channels"]),
               len({c.get("region") for c in intl["channels"]}))
        )

    # 公开目录：只有频道名 + 各地区条数，没有任何地址
    payload = build_public(channels, regions, hotel, gangaotai, intl)
    for r in payload["regions"]:
        print(
            f"  [subs] region/{r['key']:<4}       "
            f"{r['channels']:>4} 频道 / {r['streams']:>5} 条  {r['name']}"
        )

    # 酒店源 + 港澳台：独立的公开目录 + 独立订阅文件
    build_hotel_public(hotel)
    build_gangaotai_public(gangaotai)
    build_intl_public(intl)

    # 清掉旧版「HOTEL 当地区」留下的文件。必须放在生成 hotel.m3u **之前**：
    # Windows 文件系统大小写不敏感，"HOTEL.m3u" 与 "hotel.m3u" 是同一个文件，
    # 放到后面清理会把刚生成的一起删掉。
    cleanup_legacy_hotel()

    # 传原始 regions（含频道为 0 的地区），保证每个目录下每个地区都有文件
    build_free(channels, regions, hotel, gangaotai, intl)
    build_users(channels, regions, hotel, gangaotai, intl)

    # 公开订阅：免费可下载的完整订阅（打赏自愿，不做付费墙）
    build_public_subs(channels, regions, hotel, gangaotai, intl)

    # 清掉老版本留下的公开全量文件与索引（data/sub 整个目录都不再需要）
    if SUB_DIR.exists():
        shutil.rmtree(SUB_DIR, ignore_errors=True)
        print("  [subs] 已删除历史 data/sub 目录（公开的全量 m3u 不再生成）")
    return payload


def main() -> None:
    build()


if __name__ == "__main__":
    main()
