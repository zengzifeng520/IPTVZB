# 光影直播 · IPTV 直播源聚合站

> 在线访问：**https://zzf.new.tg**

自动抓取全网公开 IPTV 直播源 → 逐条探测可用性 / 分辨率 / 码率 → 生成可视化站点与订阅文件，每天由 GitHub Actions 自动更新。

## 特性

- **真的在测**：每条源都会实际拉流，解析分辨率、帧率、下载速度和是否允许跨域，不是简单罗列地址
- **纯静态**：没有后端、没有数据库服务，全部是静态文件 + 一个每天跑一次的 Python 脚本，托管成本为零
- **不依赖 FFmpeg**：用纯 Python 解析 H.264 SPS 拿分辨率，任何环境都能跑
- **在线播放**：内置 hls.js 播放器，支持多线路切换、失败自动降级、画中画、全屏
- **订阅导出**：一键下载 M3U / TXT，可直接导入 PotPlayer、VLC、TiviMate、APTV

## 目录结构

```
├── index.html              频道墙（首页）
├── watch.html              播放页
├── assets/                 CSS / JS / 本地化的 hls.js
├── data/
│   ├── channels.json       站点数据（构建产物）
│   ├── playlist.m3u        订阅文件（M3U）
│   └── playlist.txt        订阅文件（TXT）
├── spider/                 采集检测引擎
│   ├── config.py           源列表与检测参数
│   ├── sources.py          抓取与解析 m3u/txt
│   ├── normalize.py        频道名归一化（别名匹配 + 地方台兜底）
│   ├── probe.py            可用性/分辨率/测速探测（含 SPS 解析）
│   ├── store.py            SQLite 存储
│   ├── build.py            编译站点数据与订阅文件
│   └── run.py              主流程 CLI
└── .github/workflows/site-data.yml   每日自动更新
```

## 本地运行

```bash
pip install requests urllib3

cd spider
python run.py                # 全量：抓源 → 探测 → 生成站点数据
python run.py --limit 200    # 快速试跑
python run.py --build-only   # 只用已有数据库重新生成
python run.py --recheck      # 忽略历史结果全量重测
```

生成完后用任意静态服务器预览：

```bash
python -m http.server 8000
# 打开 http://127.0.0.1:8000
```

## 数据更新

GitHub Actions 每天北京时间 03:20 自动执行 `.github/workflows/site-data.yml`，重新抓取探测后提交 `data/`，Pages 自动发布。

也可以到 **Actions → Update site data → Run workflow** 手动触发，支持填写 `limit` 与 `recheck` 参数。

## 常见问题

**为什么有些频道点开黑屏？**
直播源由第三方提供，随时可能失效或限速。页面会自动提示并可以切换其他线路；部分源限制跨域，只能复制地址到本地播放器打开。

**为什么分辨率显示 HLS？**
表示探测时没能拿到视频流的分辨率信息（源响应太慢或流被加密），但确认是可用的 HLS 直播流。

**覆盖多少频道？**
当前收录 450+ 个频道、数百条可用线路，覆盖央视、卫视、影视、体育、少儿、港澳、地方台等分类。

## 免责声明

本项目不存储、不制作、不转播任何音视频内容，所有播放地址均来自互联网公开资源，版权归原权利人所有。项目仅提供技术层面的地址聚合与可用性检测，供学习与研究使用。

如权利人认为内容侵权，请提交 Issue，核实后将移除相关索引。

## License

Apache-2.0
