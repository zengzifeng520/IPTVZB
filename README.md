# IPTV 组播源聚合工具

自动抓取全网 IPTV 组播源，每日定时更新，支持 **M3U / TXT** 双格式输出，可直接导入 TVBox、Kodi、TiviMate、OTT Navigator 等播放器使用。

> ⚠️ **声明**：本工具仅提供技术框架，所有内容仅供个人测试研究使用，**不得用于任何商业用途**。使用任何直播源前，请确保已获得合法授权。

---

## 功能特性

- **组播源自动抓取**：通过组播列表提取 API（`extract_multicast`）自动抓取全网组播源，按区域/运营商自动归组
- **模板分组**：按 `template.txt` 模板将频道归入规范分组（央视频道、卫视频道、4K节目、港台节目、各省节目、地方频道、IPTV 等 20+ 分组），未命中的频道自动进入「其他频道」
- **彩色分组图标**：每个分组自动附带专属彩色 emoji 台标（仓库自托管 + CDN 加速加载），播放器分组列表更直观
- **双引擎质量检测**：
  - 第一层 · HTTP 快筛：aiohttp 高并发探测（30 并发 / 单链接超时 5 秒），过滤失效源
  - 第二层 · FFprobe 探流：逐流提取分辨率、码率、编解码器信息（单链接超时 5 秒）
  - 每频道最多保留 30 条线路，按实测速度从快到慢排序
  - 组播 / rtp 流云端探测常读不到元数据：HTTP 快筛通过或超时的源按配置保留，避免误杀本地可用的组播
- **信息标注**：输出 URL 末尾自动附加分辨率与码率，如 `【1920x1080@256kbps】`
- **EPG 电子节目单**：M3U 头部内置多组 EPG 地址，支持 TiviMate、Kodi 等播放器
- **公告支持**：可在直播源头部插入公告条目，支持自动日期占位符
- **每日自动更新**：GitHub Actions 定时任务，北京时间每天 06:00 / 12:00 / 18:00 自动运行并推送，全程无人值守

---

## 运行方式

### 方式一：Fork 到 GitHub 自动运行（推荐）

1. Fork 本仓库到你的 GitHub 账号
2. 编辑 `config.py`，按需配置抓取开关与检测参数
3. 进入仓库 **Actions** 页启用 Workflow，此后每天定时自动运行
4. 运行成功后，生成的 `live.m3u` / `live.txt` 提交回仓库根目录，可直接导入播放器

### 方式二：本地运行

```bash
# 1. 克隆项目到本地
git clone https://github.com/zengzifeng520/IPTVZB.git
cd IPTVZB

# 2. 安装依赖
pip install -r requirements.txt

# 3. 编辑 config.py 配置抓取开关（必须操作）

# 4. 运行脚本
python main.py

# 生成的 live.m3u / live.txt 位于项目根目录，可直接导入播放器
```

> ⚠️ **重要提示**：Fork 后的仓库是您个人的独立副本，请确保您使用的所有直播源均已获得合法授权，任何因使用本脚本导致的版权或合规问题，均由使用者自行承担。

---

## 输出文件

| 文件 | 说明 |
|------|------|
| `live.m3u` | M3U 格式（含 EPG、分组台标） |
| `live.txt` | TXT 格式（TVBox / 影视类 App 直接使用） |
| `function.log` | 运行日志（含失效域名黑名单建议） |

---

## 配置说明

所有配置集中在 `config.py` 中修改：

```python
# 组播源提取 API 配置
mcast_config = {
    "mcast_api": "https://api.809899.xyz",        # 列表提取 API 地址
    "mcast_api_auth": "iptv-tools-official-v1",   # API 签名头 X-App-Auth
    "mcast_keyword": "",                          # 关键字过滤（空=全部）
    "enabled": True,                              # True=启用组播源抓取
}

# 分组模板（频道名 -> 规范分组 映射）
# 见仓库根目录 template.txt

# 质量检测参数
enable_quality_check = True      # True=启用检测（过滤失效源），False=直接输出
check_timeout    = 5.0           # HTTP 快筛单链接超时（秒）
check_max_conn   = 30            # HTTP 快筛最大并发数
ffprobe_timeout = 5.0            # FFprobe 探流单链接超时（秒）
max_lines_per_channel = 30       # 每频道最多保留的线路数（按速度排序）
min_resolution  = "720"          # 低于该分辨率的源淘汰

# 组播流特殊策略
keep_http_passed = True         # HTTP 快筛通过的源即保留
keep_timeout_sources = True     # 探测超时的源保留（云端连不上运营商组播网不代表本地不可用）

# 分组彩色 emoji 台标
group_emoji = { ... }            # 分组 -> emoji 编码 映射
group_logo_base = "https://cdn.jsdelivr.net/gh/zengzifeng520/IPTVZB@main/icons"

# EPG 地址列表
epg_urls = [ ... ]

# 公告条目（写在直播源头部）
announcements = [ ... ]
```

---

## 技术说明

- 质量检测分两层：**HTTP 快筛**（验证可达性）→ **FFprobe 探流**（提取画质信息），组播/rtp 流按特殊策略保留，避免误杀本地可用的源
- 抓取到的源文件全部频道都会输出，按模板分组后写入订阅文件
- 运行日志记录每轮失效域名，方便持续优化黑名单
