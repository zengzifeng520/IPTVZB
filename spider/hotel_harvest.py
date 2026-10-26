# -*- coding: utf-8 -*-
"""从「酒店 IPTV 系统」抓频道（FOFA 导出 CSV 的后续处理）。

为什么走这条路
--------------
udpxy（server="udpxy"）是盲转发，只给主机不给频道，实测 2852 台零命中。
酒店 IPTV 系统不一样：它自带频道清单接口，直接告诉你有哪 个台、什么地址：

    GET http://<host>/iptv/live/1000.json?key=txiptv
    -> {"count": N, "data": [{"name": "CCTV-1", "url": "/tsfile/live/0001_1.m3u8"}, ...]}

其中 url 若是 /rtp/ 或 /udp/，就是组播中转（直接进池子）；
若是 /tsfile/ 或 .m3u8，是 HLS 直连（另存，不进组播池）。

输入
----
  --csv   FOFA 导出的 CSV（自动识别 host/ip/port/city/org 列）
  --hosts 纯文本，每行一个 host:port

用法
----
  python hotel_harvest.py --csv "C:\\path\\资产数据.csv"
  python hotel_harvest.py --csv xxx.csv --limit 200     # 只跑前 200 台
  python hotel_harvest.py --hosts my.txt --workers 40

输出
----
  spider/data/hotel_hosts.json  {host: {region, isp, src:"hotel", channels:[[name,url]]}}
  spider/data/proxy_hotel.m3u   给 udpxy.py 合并
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import config

DATA_DIR = config.DATA_DIR
OUT_JSON = DATA_DIR / "hotel_hosts.json"
OUT_M3U = DATA_DIR / "proxy_hotel.m3u"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# FOFA 的 city 是英文，映射到中文省份（组播按省聚合）
CITY2PROV = {
    # 直辖市
    "Beijing": "北京", "Shanghai": "上海", "Tianjin": "天津", "Chongqing": "重庆",
    # 广东
    "Guangzhou": "广东", "Shenzhen": "广东", "Shantou": "广东", "Dongguan": "广东",
    "Foshan": "广东", "Zhuhai": "广东", "Zhongshan": "广东", "Huizhou": "广东",
    "Jiangmen": "广东", "Zhanjiang": "广东", "Maoming": "广东", "Zhaoqing": "广东",
    "Qingyuan": "广东", "Jieyang": "广东", "Chaozhou": "广东", "Shaoguan": "广东",
    "Meizhou": "广东", "Shanwei": "广东", "Heyuan": "广东", "Yangjiang": "广东",
    "Yunfu": "广东",
    # 江苏
    "Nanjing": "江苏", "Wuxi": "江苏", "Suzhou": "江苏", "Changzhou": "江苏",
    "Nantong": "江苏", "Xuzhou": "江苏", "Yangzhou": "江苏", "Yancheng": "江苏",
    "Zhenjiang": "江苏", "Taizhou": "江苏", "Huai'an": "江苏", "Lianyungang": "江苏",
    "Suqian": "江苏",
    # 浙江
    "Hangzhou": "浙江", "Ningbo": "浙江", "Wenzhou": "浙江", "Jiaxing": "浙江",
    "Huzhou": "浙江", "Shaoxing": "浙江", "Jinhua": "浙江", "Quzhou": "浙江",
    "Zhoushan": "浙江", "Taizhou-ZJ": "浙江", "Lishui": "浙江",
    # 山东
    "Jinan": "山东", "Qingdao": "山东", "Yantai": "山东", "Weifang": "山东",
    "Linyi": "山东", "Zibo": "山东", "Jining": "山东", "Tai'an": "山东",
    "Weihai": "山东", "Rizhao": "山东", "Dezhou": "山东", "Liaocheng": "山东",
    "Heze": "山东", "Binzhou": "山东", "Zaozhuang": "山东", "Dongying": "山东",
    # 河南
    "Zhengzhou": "河南", "Luoyang": "河南", "Kaifeng": "河南", "Xinxiang": "河南",
    "Nanyang": "河南", "Anyang": "河南", "Shangqiu": "河南", "Xuchang": "河南",
    "Pingdingshan": "河南", "Zhoukou": "河南", "Zhumadian": "河南", "Jiaozuo": "河南",
    "Xinyang": "河南", "Puyang": "河南", "Sanmenxia": "河南", "Hebi": "河南",
    # 四川
    "Chengdu": "四川", "Mianyang": "四川", "Leshan": "四川", "Deyang": "四川",
    "Nanchong": "四川", "Yibin": "四川", "Luzhou": "四川", "Zigong": "四川",
    "Dazhou": "四川", "Neijiang": "四川", "Suining": "四川", "Meishan": "四川",
    "Guang'an": "四川", "Panzhihua": "四川", "Bazhong": "四川", "Ya'an": "四川",
    # 湖北
    "Wuhan": "湖北", "Yichang": "湖北", "Xiangyang": "湖北", "Jingzhou": "湖北",
    "Huangshi": "湖北", "Shiyan": "湖北", "Xiaogan": "湖北", "Jingmen": "湖北",
    "Huanggang": "湖北", "Xianning": "湖北", "Suizhou": "湖北", "Enshi": "湖北",
    # 湖南
    "Changsha": "湖南", "Zhuzhou": "湖南", "Xiangtan": "湖南", "Hengyang": "湖南",
    "Yueyang": "湖南", "Changde": "湖南", "Chenzhou": "湖南", "Yiyang": "湖南",
    "Shaoyang": "湖南", "Huaihua": "湖南", "Loudi": "湖南", "Zhangjiajie": "湖南",
    # 河北
    "Shijiazhuang": "河北", "Tangshan": "河北", "Baoding": "河北", "Handan": "河北",
    "Langfang": "河北", "Cangzhou": "河北", "Xingtai": "河北", "Hengshui": "河北",
    "Zhangjiakou": "河北", "Chengde": "河北", "Qinhuangdao": "河北",
    # 山西
    "Taiyuan": "山西", "Jinzhong": "山西", "Xinzhou": "山西", "Datong": "山西",
    "Linfen": "山西", "Yuncheng": "山西", "Changzhi": "山西", "Jincheng": "山西",
    "Yangquan": "山西", "Shuozhou": "山西", "Lvliang": "山西",
    # 陕西
    "Xi'an": "陕西", "Xian": "陕西", "Xianyang": "陕西", "Baoji": "陕西",
    "Weinan": "陕西", "Hanzhong": "陕西", "Yulin-SN": "陕西", "Ankang": "陕西",
    "Shangluo": "陕西", "Yan'an": "陕西", "Tongchuan": "陕西",
    # 安徽
    "Hefei": "安徽", "Wuhu": "安徽", "Bengbu": "安徽", "Anqing": "安徽",
    "Ma'anshan": "安徽", "Fuyang": "安徽", "Suzhou-AH": "安徽", "Lu'an": "安徽",
    "Huainan": "安徽", "Chuzhou": "安徽", "Huaibei": "安徽", "Tongling": "安徽",
    "Xuancheng": "安徽", "Chizhou": "安徽", "Huangshan": "安徽", "Bozhou": "安徽",
    # 福建
    "Fuzhou": "福建", "Xiamen": "福建", "Quanzhou": "福建", "Zhangzhou": "福建",
    "Putian": "福建", "Ningde": "福建", "Longyan": "福建", "Sanming": "福建",
    "Nanping": "福建",
    # 江西
    "Nanchang": "江西", "Ganzhou": "江西", "Jiujiang": "江西", "Yichun-JX": "江西",
    "Shangrao": "江西", "Ji'an": "江西", "Fuzhou-JX": "江西", "Pingxiang": "江西",
    "Jingdezhen": "江西", "Xinyu": "江西", "Yingtan": "江西",
    # 辽宁
    "Shenyang": "辽宁", "Dalian": "辽宁", "Anshan": "辽宁", "Fushun": "辽宁",
    "Yingkou": "辽宁", "Jinzhou": "辽宁", "Dandong": "辽宁", "Panjin": "辽宁",
    "Fuxin": "辽宁", "Liaoyang": "辽宁", "Tieling": "辽宁", "Chaoyang": "辽宁",
    "Huludao": "辽宁", "Benxi": "辽宁",
    # 吉林
    "Changchun": "吉林", "Jilin": "吉林", "Siping": "吉林", "Tonghua": "吉林",
    "Yanbian": "吉林", "Baicheng": "吉林", "Songyuan": "吉林", "Baishan": "吉林",
    "Liaoyuan": "吉林",
    # 黑龙江
    "Harbin": "黑龙江", "Daqing": "黑龙江", "Qiqihar": "黑龙江", "Mudanjiang": "黑龙江",
    "Jiamusi": "黑龙江", "Suihua": "黑龙江", "Jixi": "黑龙江", "Hegang": "黑龙江",
    "Shuangyashan": "黑龙江", "Yichun-HLJ": "黑龙江", "Daxing'anling": "黑龙江",
    # 其他省会/重点
    "Kunming": "云南", "Guiyang": "贵州", "Nanning": "广西", "Haikou": "海南",
    "Lanzhou": "甘肃", "Xining": "青海", "Yinchuan": "宁夏", "Urumqi": "新疆",
    "Hohhot": "内蒙古", "Lhasa": "西藏", "Sanya": "海南", "Guilin": "广西",
    "Baotou": "内蒙古", "Wulumuqi": "新疆",
    # 港澳台
    "Hong Kong": "香港", "Hongkong": "香港", "Macau": "澳门", "Macao": "澳门",
    "Taipei": "台湾", "Kaohsiung": "台湾", "Taichung": "台湾",
}


def prov_of(city: str, org: str = "") -> str:
    city = (city or "").strip()
    if city in CITY2PROV:
        return CITY2PROV[city]
    # FOFA 的 city 有时直接给中文
    for p in ("香港", "澳门", "台湾"):
        if p in city:
            return p
    return "未知"


def isp_of(org: str) -> str:
    o = (org or "").lower()
    if "telecom" in o or "chinanet" in o or "ctc" in o:
        return "电信"
    if "unicom" in o or "cucc" in o:
        return "联通"
    if "mobile" in o or "cmnet" in o or "cmcc" in o:
        return "移动"
    if "broadnet" in o or "radio" in o or "cbn" in o:
        return "广电"
    return ""


def read_hosts(csv_path: str = "", txt_path: str = "") -> list[dict]:
    """读 FOFA CSV 或纯 host 列表，返回 [{host, city, org}]。"""
    out: list[dict] = []
    if csv_path:
        raw = Path(csv_path).read_bytes()
        txt = ""
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                txt = raw.decode(enc)
                break
            except Exception:
                continue
        rows = list(csv.DictReader(io.StringIO(txt)))
        for r in rows:
            host = (r.get("host") or "").strip()
            if not host:
                ip, port = (r.get("ip") or "").strip(), (r.get("port") or "").strip()
                if ip and port:
                    host = "%s:%s" % (ip, port)
            if not host:
                continue
            out.append({
                "host": host,
                "city": (r.get("city") or "").strip(),
                "org": (r.get("org") or "").strip(),
            })
    elif txt_path:
        for line in Path(txt_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append({"host": line, "city": "", "org": ""})
    return out


def fetch_json(host: str, timeout: float = 6.0) -> list[dict]:
    """请求酒店频道清单。返回 [{name,url}]（url 已补全成绝对地址）。"""
    url = "http://%s/iptv/live/1000.json?key=txiptv" % host
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            raw = r.read()
        if len(raw) < 30:
            return []
        d = json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return []

    data = d.get("data") if isinstance(d, dict) else None
    if not isinstance(data, list):
        return []
    out = []
    for it in data:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        u = str(it.get("url") or "").strip()
        if not name or not u:
            continue
        if u.startswith("/"):
            u = "http://%s%s" % (host, u)
        out.append({"name": name, "url": u})
    return out


# 组播中转地址（能进池子的）
PROXY_RE = re.compile(r"^https?://[A-Za-z0-9._\-]+:\d+/(?:rtp|udp)/\d{1,3}(?:\.\d{1,3}){3}:\d{1,5}$")


def main() -> None:
    ap = argparse.ArgumentParser(description="从酒店 IPTV 系统抓频道")
    ap.add_argument("--csv", default="", help="FOFA 导出的 CSV")
    ap.add_argument("--hosts", default="", help="纯文本 host 列表（每行一个）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 台")
    ap.add_argument("--workers", type=int, default=30, help="并发")
    args = ap.parse_args()

    if not args.csv and not args.hosts:
        print("需要 --csv 或 --hosts")
        sys.exit(1)

    items = read_hosts(args.csv, args.hosts)
    if args.limit:
        items = items[: args.limit]
    print("[hotel] 待探测 %d 台 ..." % len(items))

    hosts: dict[str, dict] = {}
    empty = 0

    def work(it):
        chans = fetch_json(it["host"])
        if not chans:
            return it, None
        return it, chans

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, it) for it in items]
        done = 0
        for f in as_completed(futs):
            done += 1
            it, chans = f.result()
            if not chans:
                empty += 1
                continue
            prov = prov_of(it["city"], it["org"])
            isp = isp_of(it["org"])
            bucket = hosts.setdefault(it["host"], {
                "region": prov, "isp": isp, "src": "hotel", "channels": [],
            })
            for c in chans:
                bucket["channels"].append([c["name"], c["url"]])
            if done % 100 == 0:
                print("  进度 %d/%d，命中 %d 台" % (done, len(items), len(hosts)))

    # 统计：其中多少是真正的组播中转
    proxy_hosts = {
        h: v for h, v in hosts.items()
        if any(PROXY_RE.match(u) for _n, u in v["channels"])
    }
    print("[hotel] 有频道清单 %d 台，其中含组播中转 %d 台" % (len(hosts), len(proxy_hosts)))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(hosts, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # 只把含 rtp/udp 的那部分写进 m3u，交给 udpxy.py 合并
    lines = ["#EXTM3U"]
    n = 0
    for h, v in proxy_hosts.items():
        for name, u in v["channels"]:
            if not PROXY_RE.match(u):
                continue
            lines.append('#EXTINF:-1 tvg-name="%s" group-title="%s",%s' % (name, v["region"], name))
            lines.append(u)
            n += 1
    OUT_M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[hotel] 写入 %d 条组播地址 -> %s" % (n, OUT_M3U))
    print("[hotel] 全量 -> %s" % OUT_JSON)


if __name__ == "__main__":
    main()
