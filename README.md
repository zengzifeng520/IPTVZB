# 光影直播 · 全国直播源按地区取用

把公开采集到的 IPTV 组播地址，经过探测、去重、按地区归类后，做成一个「手机号注册 → 查看本省频道 → 扫码开通全部地区」的订阅站。

纯静态站点，没有后端，直接跑在 GitHub Pages 上。

---

## 页面

| 页面 | 作用 |
|---|---|
| `index.html` | 首页：赞助状态条 + 统计 + 11 个地区卡片 |
| `account.html` | 赞助页：四档档位、扫码付款、订阅地址、本机赞助码 |
| `region.html` | 频道页：按地区切换、频道地址逐条复制、订阅地址 |
| `login.html` | 已废弃，自动跳回首页 |

**不赞助**：11 个地区的频道地址全部可看、可逐条复制；订阅链接只能选 **1 个地区**，选定后不可更改。
**赞助后**：全部 11 个地区的订阅 + 专属订阅地址，到期自动停止更新。

---

## 赞助与付费

没有服务端，也**不需要注册**。整套体系是纯前端 + 本地存储：

- **赞助码**：首次访问自动生成 12 位码（去掉了 0/O/1/I，方便抄写），存在 `localStorage`，
  赞助页「本机赞助码」处可查看、可复制
- **换设备**：把赞助码填回赞助页「恢复」即可，不用重新付款
- **免费额度**：每个浏览器可选 1 个地区拿订阅地址，选定后不可更改
- **付费**：展示微信收款码，用户付款后点「我已完成付款」即解锁
- 套餐（4 档，续费按所选档位在原到期日上累加，过期后从当天重新起算）：

  | 套餐 | 价格 | 时长 |
  |---|---|---|
  | 体验版 | ￥2 | 1 天 |
  | 月付 | ￥8 | 30 天 |
  | 季付 | ￥20 | 90 天 |
  | 年付 | ￥80 | 365 天 |

- **到期行为**：专属订阅文件被改写为空列表（只有 `#EXTM3U` 和一行提示），
  播放器下次刷新即拉到 0 个频道。URL 不变、不返回 404，所以不会留下可用的旧列表；
  页面显示「赞助已到期」并引导重新赞助。

**必须知道的局限**（纯静态站的固有限制，不是实现遗漏）：

1. **不做付款核验**。个人微信收款码没有到账回调，无法知道谁付了钱。当前实现是「用户点一下就解锁」，等于信任用户。想真正核验，需要微信商户号 + 支付回调接口 + 一台公网后端。
2. **赞助码默认只在本机**。填了「开通登记接口」（`worker/claim.js` + `CLAIM_URL`）后，服务端会记下赞助码与到期时间，换设备输入赞助码即可自动恢复；没配接口时，换设备要站长手工补录。
3. **免费额度是前端限制**。换个浏览器或清缓存就能再选一个地区，纯静态站挡不住。真正限制需要后端按设备/账号下发。
4. **到期有最长约 10 分钟延迟**。GitHub Pages 的 CDN 缓存 `max-age=600`，到期后最多 10 分钟才彻底变空。
5. **频道地址本身是公开的**。`data/proxy.json` 和 `data/sub/*.m3u` 都能直接请求，付费买的是「订阅链接 + 全部地区 + 到期管理」，不是内容保密。

---

## 数据管线

```
公开源 m3u / Quake 测绘地址
        │
        ▼
  udpxy.py          探测 /status，只留可达的中转服务器（存活 33 台）
        │
        ▼
  shushu_enrich.py  存活主机 → 解析接口，让服务器自报全量频道
        │            （13 台可解析 / 2461 条地址）
        ▼
  regions.py        IP 归属地（ip-api 批量，缓存 30 天）→ 按省份聚合
        │
        ▼
  proxy.json        566 频道 / 4450 条地址
  regions.json      11 个地区
        │
        ▼
  subs.py           all.m3u（全量）+ region/<KEY>.m3u（分地区）+ index.json
```

按地区拆分的原因：udpxy 中转服务器基本只在本省运营商网内可达，跨省地址大多连不上。

## 日常运行

```bash
cd spider
python run.py              # 采集 + 探测公开源
python shushu_enrich.py    # 存活主机喂解析接口
python shushu_import.py    # 转 m3u 合并
python udpxy.py            # 合并两个源并汇聚
python regions.py          # 生成地区分组
python subs.py             # 生成订阅文件
```

GitHub Actions 每天北京时间 03:20 自动跑一遍并提交数据（`.github/workflows/site-data.yml`）。

## 目录

```
index.html / login.html / account.html / region.html
assets/
  css/app.css
  js/auth.js      账号与套餐（本地存储）
  js/app.js       首页
  js/login.js     注册登录
  js/account.js   账户中心 + 付款
  js/region.js    地区频道页
  img/wxpay.jpg   微信收款码
data/
  proxy.json      频道 + 地址
  regions.json    地区分组
  sub/index.json  订阅索引
  sub/all.m3u     全量订阅
  sub/region/     分地区订阅
spider/           采集与构建脚本
```

## 改套餐

`assets/js/auth.js` 顶部的 `PLANS` 一处改完即可（价格、天数、标签都在这）：

```js
var PLANS = [
  { key: "day",     name: "体验版", price: 2,  days: 1,   unit: "天", tag: "先试一天" },
  { key: "month",   name: "月付",   price: 8,  days: 30,  unit: "天", tag: "最灵活" },
  { key: "quarter", name: "季付",   price: 20, days: 90,  unit: "天", tag: "更划算" },
  { key: "year",    name: "年付",   price: 80, days: 365, unit: "天", tag: "最超值", hot: true },
];
var DEFAULT_PLAN = "month";   // 默认选中的档位
```

页面上所有价格、天数、按钮文案都由这份配置渲染，不用再改 HTML。

## 换收款码

替换 `assets/img/wxpay.jpg` 即可，页面上按 232px 宽展示。

## 赞助订阅与到期

每个赞助码有一份专属订阅，地址里带由赞助码推导的 token：

```
https://zzf.new.tg/data/users/<token>/all.m3u     全量
https://zzf.new.tg/data/users/<token>/SX.m3u      单地区（key 见 data/sub/index.json）
```

`token = sha256("zzf-sub-2026|赞助码")` 的前 16 位（赞助码统一转大写）。
前端 `auth.js`、`spider/subs.py`、`worker/claim.js` 三处用同一算法，
所以用户表里**只要写赞助码和到期日期就够了**，不用手算 token 和时间戳。

免费用户拿到的是公共文件 `data/sub/region/<KEY>.m3u`，不生成专属目录。

### 用户表 `data/users.json`

```json
{
  "U4QRKBVU336R": { "expire": "2026-11-25" },
  "A1B2C3D4E5F6": { "expire": "2027-03-01", "created": "2026-10-26" }
}
```

`expire` 按北京时间当天 23:59:59 生效，用户能用满最后一天。

### 加赞助用户（三种方式，任选）

**方式一：网页改（最简单，手机也能操作）**

打开仓库里的 `data/users.json` → 编辑 → 加一行 `"赞助码": { "expire": "到期日期" },` → Commit。
提交后自动触发 Actions 重建，约 1 分钟生效。

**方式二：本地命令**

```bash
cd spider
python users_cli.py add U4QRKBVU336R --days 30    # 或 --expire 2026-11-25
python users_cli.py list                          # 查看全部与剩余天数
python users_cli.py remove U4QRKBVU336R           # 删除
```

**方式三：全自动（可选，推荐）**

部署 `worker/claim.js` 到 Cloudflare Worker（配一个 `GH_TOKEN` 环境变量，只授权本仓库 Contents 读写），
再把 Worker 地址填进 `assets/js/auth.js` 顶部的 `CLAIM_URL`。
之后用户点「我已完成付款」会自动登记，不用人工加人，换设备也能自动恢复。

### 到期后会发生什么

每日任务会把该赞助码目录下所有 m3u **改写为空列表**：

```
#EXTM3U
# 会员已到期，订阅已停止更新，续费后立即恢复
```

订阅 URL 保持不变、不返回 404（避免播放器报错），播放器下次刷新就拉到 0 个频道，
因此本地不会留下可以继续使用的旧列表。续费后第二天（或提交用户表后 1 分钟）自动恢复。

## 免责声明

本站不存储、不制作、不转播任何视频内容。播放地址由第三方中转服务器提供，仅做地址汇聚与可用性检测，版权归原权利人所有。
