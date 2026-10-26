#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""频道名标准化：把各来源五花八门的频道名归并到统一的频道字典。

参考项目用的是简单的 `if alias in name` 子串匹配，会把 CCTV10 误判成 CCTV1、
把 CCTV4欧洲 误判成 CCTV4。这里改成：
  1. 先剔除清晰度/线路/语言等噪声后缀；
  2. 用「全局长别名优先 + 数字边界校验」匹配；
  3. 对 CCTV4K/8K 这类本身含数字的台标做前置处理。
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

# 噪声词：出现在频道名里但不影响频道身份
NOISE_WORDS = [
    "超高清", "高清", "标清", "流畅", "蓝光", "原画", "超清", "极速",
    "1080p60", "1080p50", "1080p", "720p", "2160p", "4k", "8k", "uhd", "fhd", "hd", "sd",
    "hdr", "hlg", "hevc", "h265", "h264", "avc", "50p", "60p", "25p",
    "ipv6", "ipv4", "ipv4v6",
    "备用", "测试", "线路", "直播", "高清直播", "无插件", "官方",
]
# 括号类内容整体剔除
BRACKET_RE = re.compile(r"[\(（\[【\{][^\)）\]】\}]*[\)）\]】\}]")
# 常见的多线路后缀：CCTV1-1 / CCTV1_2 / CCTV1 线路2
ROUTE_SUFFIX_RE = re.compile(r"[-_·\s]*(线路)?\s*\d{1,2}\s*$")
# 需要保留数字语义的台标（不能被当成噪声）
PROTECTED = ["CCTV4K", "CCTV8K", "CCTV4EURO", "CCTV4AME"]
COMPACT_DROP = re.compile(r"[\s\-_·、,，.。:：'\"·\|/\\]+")

# 少量英文台名映射（iptv-org 等国际源使用）
EN_ALIASES = {
    "cctv1": ["cctv-1", "cctv 1", "cctv1"],
    "cctv2": ["cctv-2"],
    "cctv3": ["cctv-3"],
    "cctv4": ["cctv-4"],
    "cctv5": ["cctv-5"],
    "cctv5+": ["cctv-5+", "cctv5 plus"],
    "cctv6": ["cctv-6"],
    "cctv7": ["cctv-7"],
    "cctv8": ["cctv-8"],
    "cctv9": ["cctv-9"],
    "cctv10": ["cctv-10"],
    "cctv11": ["cctv-11"],
    "cctv12": ["cctv-12"],
    "cctv13": ["cctv-13"],
    "cctv14": ["cctv-14"],
    "cctv15": ["cctv-15"],
    "cctv16": ["cctv-16"],
    "cctv17": ["cctv-17"],
}
# 省级卫视英文名
EN_PROVINCE = {
    "安徽卫视": ["anhui tv", "anhui satellite"],
    "北京卫视": ["beijing tv", "beijing satellite"],
    "东方卫视": ["dragon tv", "eastern tv", "shanghai dragon tv"],
    "天津卫视": ["tianjin tv"],
    "重庆卫视": ["chongqing tv"],
    "湖南卫视": ["hunan tv", "hunan satellite"],
    "浙江卫视": ["zhejiang tv"],
    "江苏卫视": ["jiangsu tv"],
    "广东卫视": ["guangdong tv"],
    "深圳卫视": ["shenzhen tv"],
    "山东卫视": ["shandong tv"],
    "四川卫视": ["sichuan tv"],
    "湖北卫视": ["hubei tv"],
    "河南卫视": ["henan tv"],
    "河北卫视": ["hebei tv"],
    "福建东南卫视": ["southeast tv", "fujian southeast"],
    "江西卫视": ["jiangxi tv"],
    "辽宁卫视": ["liaoning tv"],
    "黑龙江卫视": ["heilongjiang tv"],
    "吉林卫视": ["jilin tv"],
    "山西卫视": ["shanxi tv"],
    "陕西卫视": ["shaanxi tv"],
    "甘肃卫视": ["gansu tv"],
    "宁夏卫视": ["ningxia tv"],
    "青海卫视": ["qinghai tv"],
    "新疆卫视": ["xinjiang tv"],
    "西藏卫视": ["tibet tv", "xizang tv"],
    "云南卫视": ["yunnan tv"],
    "贵州卫视": ["guizhou tv"],
    "广西卫视": ["guangxi tv"],
    "内蒙古卫视": ["inner mongolia tv", "nei mongol tv"],
    "海南卫视": ["hainan tv"],
    "东南卫视": ["southeast tv"],
    "凤凰中文": ["phoenix chinese", "phoenix info"],
    "凤凰资讯": ["phoenix info"],
    "凤凰香港": ["phoenix hong kong"],
}


def display_name(key: str) -> str:
    """把内部 key 变成好看的展示名：CCTV1 -> CCTV-1。"""
    m = re.fullmatch(r"CCTV(\d+)(\+?)", key)
    if m:
        return f"CCTV-{m.group(1)}{m.group(2)}"
    m = re.fullmatch(r"CCTV(4|8)K", key)
    if m:
        return f"CCTV-{m.group(1)}K"
    return key


def _fold(text: str) -> str:
    """统一 Unicode（全角转半角）并小写。"""
    return unicodedata.normalize("NFKC", text).lower()


def clean(name: str) -> str:
    """清洗频道原始名，尽量只留下台标本体。"""
    s = _fold(name or "").strip()
    if not s:
        return ""
    # 去掉 URL 编码残留
    s = s.replace("%20", " ")
    # 先保护 CCTV4K / CCTV8K
    protected_hit = None
    for p in PROTECTED:
        if p.lower() in s.replace("-", "").replace(" ", ""):
            protected_hit = p
            break
    s = BRACKET_RE.sub(" ", s)
    # 去掉噪声词
    for w in NOISE_WORDS:
        s = s.replace(w, " ")
    if protected_hit:
        s = s + " " + protected_hit
    # 去掉尾部线路号（"北京卫视 2" -> "北京卫视"），但要避免吃掉 "CCTV5+" 的 +
    s = re.sub(r"[\s\-_·]+(线路)?\s*\d{1,2}\s*$", "", s)
    # 去掉常见分隔符残留
    s = re.sub(r"[\(（\[【].*?[\)）\]】]", " ", s)
    s = re.sub(r"[·•]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -_·:：")
    return s


def compact(s: str) -> str:
    """紧凑化：去掉所有分隔符，用于子串匹配。"""
    return COMPACT_DROP.sub("", s)


# ---------------------------------------------------------------- 地方台兜底
# 原项目只认 211 个主流频道，地方台（邯郸公共、义乌新闻综合…）全部丢弃。
# 这里按「省级行政区 + 频道类型词」把地方台收进统一的"地方频道"分类。
PROVINCES = [
    "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
    "广东", "广西", "海南", "四川", "贵州", "云南", "西藏", "陕西", "甘肃",
    "青海", "宁夏", "新疆", "内蒙古", "香港", "澳门", "台湾",
]
# 常见地级市（用于识别不带省名的城市台）
CITIES = [
    "石家庄", "唐山", "秦皇岛", "邯郸", "邢台", "保定", "张家口", "承德", "沧州", "廊坊", "衡水",
    "太原", "大同", "阳泉", "长治", "晋城", "朔州", "晋中", "运城", "忻州", "临汾", "吕梁",
    "呼和浩特", "包头", "乌海", "赤峰", "通辽", "鄂尔多斯", "呼伦贝尔", "巴彦淖尔", "乌兰察布",
    "沈阳", "大连", "鞍山", "抚顺", "本溪", "丹东", "锦州", "营口", "阜新", "辽阳", "盘锦", "铁岭", "朝阳", "葫芦岛",
    "长春", "四平", "辽源", "通化", "白山", "松原", "白城", "延边",
    "哈尔滨", "齐齐哈尔", "鸡西", "鹤岗", "双鸭山", "大庆", "伊春", "佳木斯", "七台河", "牡丹江", "黑河", "绥化",
    "南京", "无锡", "徐州", "常州", "苏州", "南通", "连云港", "淮安", "盐城", "扬州", "镇江", "泰州", "宿迁",
    "杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州", "舟山", "台州", "丽水",
    "合肥", "芜湖", "蚌埠", "淮南", "马鞍山", "淮北", "铜陵", "安庆", "黄山", "滁州", "阜阳", "宿州", "六安", "亳州", "池州", "宣城",
    "福州", "厦门", "莆田", "三明", "泉州", "漳州", "南平", "龙岩", "宁德",
    "南昌", "景德镇", "萍乡", "九江", "新余", "鹰潭", "赣州", "吉安", "宜春", "抚州", "上饶",
    "济南", "青岛", "淄博", "枣庄", "东营", "烟台", "潍坊", "济宁", "泰安", "威海", "日照", "临沂", "德州", "聊城", "滨州", "菏泽",
    "郑州", "开封", "洛阳", "平顶山", "安阳", "鹤壁", "新乡", "焦作", "濮阳", "许昌", "漯河", "三门峡", "南阳", "商丘", "信阳", "周口", "驻马店",
    "武汉", "黄石", "十堰", "宜昌", "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁", "随州", "恩施",
    "长沙", "株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "张家界", "益阳", "郴州", "永州", "怀化", "娄底", "湘西",
    "广州", "韶关", "深圳", "珠海", "汕头", "佛山", "江门", "湛江", "茂名", "肇庆", "惠州", "梅州", "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮",
    "南宁", "柳州", "桂林", "梧州", "北海", "防城港", "钦州", "贵港", "玉林", "百色", "贺州", "河池", "来宾", "崇左",
    "海口", "三亚", "儋州",
    "成都", "自贡", "攀枝花", "泸州", "德阳", "绵阳", "广元", "遂宁", "内江", "乐山", "南充", "眉山", "宜宾", "广安", "达州", "雅安", "巴中", "资阳",
    "贵阳", "六盘水", "遵义", "安顺", "毕节", "铜仁",
    "昆明", "曲靖", "玉溪", "保山", "昭通", "丽江", "普洱", "临沧", "大理", "红河",
    "拉萨", "西安", "铜川", "宝鸡", "咸阳", "渭南", "延安", "汉中", "榆林", "安康", "商洛",
    "兰州", "嘉峪关", "金昌", "白银", "天水", "武威", "张掖", "平凉", "酒泉", "庆阳", "定西", "陇南",
    "西宁", "银川", "石嘴山", "吴忠", "固原", "中卫",
    "乌鲁木齐", "克拉玛依", "喀什", "伊犁", "阿克苏",
]
LOCAL_HINTS = [
    "综合", "新闻", "公共", "都市", "生活", "影视", "科教", "财经", "经济",
    "农业", "乡村", "文体", "旅游", "图文", "法制", "法治", "少儿", "一套",
    "二套", "三套", "四套", "频道",
]
LOCAL_SUFFIX = re.compile(r"(电视台|频道|台)$")


class Matcher:
    """频道名匹配器。"""

    def __init__(self, categories_path: Path):
        raw = json.loads(Path(categories_path).read_text(encoding="utf-8"))
        self.channels: list[dict] = raw
        self.by_key: dict[str, dict] = {c["name"]: c for c in raw}

        index: list[tuple[str, str]] = []  # (紧凑别名, 频道 key)
        for ch in raw:
            for alias in ch["aliases"]:
                a = compact(clean(alias))
                if a:
                    index.append((a, ch["name"]))
            key_c = compact(clean(ch["name"]))
            if key_c:
                index.append((key_c, ch["name"]))

        for key, extras in EN_ALIASES.items():
            if key in self.by_key:
                for e in extras:
                    index.append((compact(e), key))
        for key, extras in EN_PROVINCE.items():
            if key in self.by_key:
                for e in extras:
                    index.append((compact(e), key))

        # 去重 + 长别名优先
        seen = set()
        self.index: list[tuple[str, str]] = []
        for alias, key in sorted(index, key=lambda x: -len(x[0])):
            if (alias, key) in seen:
                continue
            seen.add((alias, key))
            self.index.append((alias, key))

    @staticmethod
    def _boundary_ok(text: str, start: int, end: int, alias: str) -> bool:
        """别名以数字结尾时，后面不能紧跟数字或 '+'，避免 CCTV1 命中 CCTV10 / CCTV5+。"""
        if not alias or not alias[-1].isdigit():
            return True
        if end >= len(text):
            return True
        nxt = text[end]
        if nxt.isdigit():
            return False
        # CCTV5 vs CCTV5+：'+' 属于更长台标
        if nxt == "+":
            return False
        return True

    def match(self, raw_name: str) -> str | None:
        """返回频道 key，匹配不到返回 None。"""
        name = clean(raw_name)
        if not name:
            return None
        c = compact(name)
        if not c:
            return None
        for alias, key in self.index:
            if alias not in c:
                continue
            pos = c.find(alias)
            if self._boundary_ok(c, pos, pos + len(alias), alias):
                return key
        return None

    def get(self, key: str) -> dict | None:
        return self.by_key.get(key)

    # ---------------------------------------------------------- 地方台兜底
    def match_or_local(self, raw_name: str) -> tuple[str, bool] | None:
        """先查字典；查不到则判断是否为地方台，是则返回 (频道key, True)。"""
        hit = self.match(raw_name)
        if hit:
            return hit, False
        name = clean(raw_name)
        if not name:
            return None
        # 只处理纯中文名，英文/拼音台（Tonghua TV 等）噪声太大
        han = re.sub(r"[\u4e00-\u9fa5]", "", name)
        if len(han) > max(2, len(name) * 0.5):
            return None
        if not (2 <= len(name) <= 14):
            return None
        # 排除明显的非频道名
        if re.fullmatch(r"[\d\W_]+", name):
            return None

        has_region = any(p in name for p in PROVINCES) or any(c in name for c in CITIES)
        has_hint = any(h in name for h in LOCAL_HINTS)
        if not (has_region or has_hint):
            return None
        # 至少要像"某地+某频道"，避免把"高清影视"这类无主词收进来
        if not has_region and not any(h in name for h in ("新闻", "综合", "公共", "都市", "生活", "科教", "文旅")):
            return None

        key = LOCAL_SUFFIX.sub("", name).strip(" -_·")
        if len(key) < 2:
            return None
        return key, True


def load_matcher(categories_path: Path) -> Matcher:
    return Matcher(categories_path)


if __name__ == "__main__":
    import sys

    cfg_dir = Path(__file__).resolve().parent / "data" / "categories.json"
    m = load_matcher(cfg_dir)
    cases = [
        "CCTV-1 综合", "CCTV1高清", "CCTV10科教", "CCTV-5+ 体育赛事",
        "CCTV5+体育赛事", "CCTV-4 中文国际欧洲", "CCTV-4 中文国际",
        "北京卫视4K", "湖南卫视-高清", "东方卫视", "翡翠台", "凤凰中文",
        "CCTV4K", "CCTV-8K", "Anhui TV", "Hunan TV", "广东珠江", "深圳都市",
        "CCTV1", "CCTV17农业农村", "CCTV-1", "CETV1", "中国教育1台",
    ]
    for case in cases:
        print(f"{case:<24} -> {m.match(case)}")
