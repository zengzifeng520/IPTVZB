# 光影直播 · Token 中转播放地址站

> 在线访问：**https://zzf.new.tg**

输入 Token → 分配可用的 udpxy 中转服务器 → 生成专属播放地址与 M3U 订阅。每天由 GitHub Actions 自动探测中转服务器存活性并更新地址池。

## 工作方式

```
Quake 测绘采集 ──► proxy_source.m3u（63 台中转服务器 / 7584 条地址）
IPTV神器Pro接口 ─► proxy_shushu.m3u（每日增量，见下）
                        │
                        ▼
                 udpxy.py 探测 /status
                        │  存活 35 台
                        ▼
                  data/proxy.json（516 频道 / 3197 条地址）
                        │
                        ▼
        tokens.py 按 Token 分配服务器 ──► data/sub/<token>.m3u
                        │
                        ▼
              前端：输入 Token → 查表 → 展示地址
```

## 第二个数据源：IPTV神器Pro 接口

除 Quake 测绘的历史数据外，还会从公开站点 `iptv.cqshushu.com` 的接口增量抓取中转服务器。全程走接口，不在本地逐 IP 扫端口：

| 步骤 | 接口 | 说明 |
|---|---|---|
| 列表 | `index.php?t=<类型>&limit=10&page=N` | 拿 IP、类型、频道数、状态 |
| 详情 | `index.php?p=<加密ID>&t=<类型>` | 拿 `IP:端口` |
| 解析 | `POST iptv_channel.php` (`action=parse`) | 一次返回该服务器全部频道 + rtp 中转地址 |

要点：

- 页面有 JS 挑战，需先请求带 `_js_challenge=1` 拿到 `paer_sec_token` cookie，再加 `ad_ok=1`
- 解析接口需要签名 token：`base64("${秒}_${djb2('iptv_secret_key_2026'+秒+同样的盐)}")`，已用 Python 等价实现（`shushu_api.py`），无需 Node
- 有较严格的频率限制，脚本内做了 429 退避与断点续抓（`data/shushu_*.json`）
- 多数中转服务器带 ISP 白名单，只能在对应运营商网络内访问，因此抓到的地址仍要过一遍本地 `/status` 探测才算可用

```bash
cd spider
python shushu_crawl.py          # 采集 → data/shushu_relays.json → data/proxy_shushu.m3u
python shushu_crawl.py list     # 仅抓列表
python shushu_crawl.py detail   # 仅抓端口
python shushu_crawl.py parse    # 仅抓频道
python shushu_crawl.py import   # 仅转 m3u
```

## 页面

| 页面 | 内容 |
|---|---|
| `index.html` | Token 输入框、运行统计、频道预览（516 个） |
| `token.html?t=XXX` | 验证 Token → 套餐信息、专属订阅地址、已分配服务器、频道地址列表（可折叠、可筛选、逐条复制） |

## 目录结构

```
├── index.html              Token 首页
├── token.html              播放地址页
├── assets/                 CSS / JS
├── data/
│   ├── proxy.json          中转地址池（构建产物）
│   ├── tokens.json         Token → 服务器 / 订阅文件映射
│   └── sub/<token>.m3u     各 Token 的专属订阅
└── spider/
    ├── udpxy.py            解析 + 探测 + 汇聚中转地址
    ├── tokens.py           Token 分配与订阅生成
    ├── normalize.py        频道名归一化
    ├── config.py           路径与参数
    ├── data/
    │   ├── proxy_source.m3u  中转源数据（Quake 采集）
    │   └── tokens.json       Token 配置（要增删 Token 改这里）
    └── scripts/extract_categories.py  频道字典生成
```

## 添加 Token

编辑 `spider/data/tokens.json`：

```json
{
  "tokens": [
    { "token": "MY-2027-001", "name": "标准版", "servers": 3,
      "expire": "2027-06-30", "note": "3 台服务器轮换" }
  ]
}
```

`servers` 表示分配几台中转服务器（越多覆盖频道越广），`channels` 留空表示全部频道。改完重新生成：

```bash
cd spider
python tokens.py
```

## 本地运行

```bash
pip install requests urllib3

cd spider
python udpxy.py          # 探测中转服务器 + 生成 data/proxy.json
python tokens.py         # 生成各 Token 的订阅文件

cd ..
python -m http.server 8000
```

## 自动更新

`.github/workflows/site-data.yml` 每天北京时间 03:20 执行：探测 63 台中转服务器 → 重建地址池 → 重新生成全部 Token 订阅 → 提交 `data/`。也可在 Actions 页面手动触发。

## 重要说明

**Token 不是安全凭证。** 本站是纯静态托管，`data/tokens.json` 和 `data/sub/*.m3u` 都是公开文件，知道地址的人就能直接下载。Token 只起「分发凭证」作用 —— 区分不同用户拿到哪组中转服务器，无法阻止技术用户绕过。

**中转服务器是第三方的。** 地址池来自 Quake 测绘到的公网 udpxy 服务，属于他人设备。这些服务器随时可能下线、改端口或加 IP 白名单，所以每天探测一次；也正因如此，不要在上面跑大流量业务。

**要真正可控，需要自建中转。** 如果你有自己的服务器，可以在上面跑 udpxy 或 nginx + rtmp/hls 代理，把 `proxy_source.m3u` 换成自己的地址，再给 Token 绑定 IP 白名单 —— 那样才是真正的鉴权分发。

## 免责声明

本项目不存储、不制作、不转播任何音视频内容，所有播放地址由第三方提供，版权归原权利人所有。项目仅提供技术层面的地址汇聚与可用性检测，供学习研究使用。如权利人认为侵权，请提交 Issue，核实后移除。

## License

Apache-2.0
