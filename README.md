# video_downloader

视频/媒体链接解析与下载小工具（Windows 桌面 GUI + CLI 双入口）。

解析采用**双引擎路由**：

1. **parser_core**（复用 [HIKARI_BOT_NEO](https://github.com/higashitaniyume/HIKARI_BOT_NEO) 机器人
   `astrbot_plugin_media_parser` 插件，vendored 到 `parser_core/`）—— 优先处理国内平台，
   解析行为与机器人一致，无需登录即可解析大部分平台；
2. **yt-dlp 兜底**（`app/ydl.py`）—— parser_core 未识别的链接交给 yt-dlp，覆盖其支持的
   1900+ 站点（YouTube、Twitch、SoundCloud、Instagram、Vimeo、网易云音乐…）。
   下载由 yt-dlp 自身执行：自动选择最佳格式、用 ffmpeg 合并音视频。

## 功能特性

- **双引擎路由**：国内平台走机器人同款解析核心，其余 1900+ 站点由 yt-dlp 兜底
- **GUI 桌面工具**（customtkinter 深色主题）：粘贴多行链接 → 解析卡片（平台徽章/标题/作者/时长/封面）→ 勾选媒体 → 实时下载进度
- **CLI**：解析、JSON 输出、批量下载，可脚本化
- **下载能力强**：直链流式下载（逐字节进度）、B站 DASH 分离流、HLS(m3u8) 流、yt-dlp 自动格式选择 + ffmpeg 音视频合并
- **可选 B 站 Cookie**：解锁高清晰度（`--bilibili-cookie`）

## 支持的平台

**parser_core 优先处理（行为与机器人一致）：**

| 平台 | 说明 |
| --- | --- |
| Bilibili | BV/AV 号、番剧 ep/ss、动态/opus、b23.tv 短链；无 Cookie 时低清晰度，配置 Cookie 可解锁高清晰度 |
| 抖音 Douyin | 分享短链、视频/图文/Slides |
| 快手 Kuaishou | 短链/长链/gifshow |
| 微博 Weibo | 桌面版/移动版/视频组件页，自动获取访客 Cookie |
| 小红书 Xiaohongshu | 短链/移动端/PC 端笔记 |
| TikTok | 需科学上网（可用代理） |
| 头条 Toutiao | |
| 咸鱼 Xianyu | 商品媒体 |
| 小黑盒 Xiaoheihe | 含 HLS(m3u8) 流 |
| Twitter / X | 通过 fxTwitter 解析，多数内容需登录 |

**yt-dlp 兜底（其余全部平台）：** YouTube、Twitch、SoundCloud、Instagram、Vimeo、
网易云音乐、Twitter/X 备选链路、以及 yt-dlp 支持的全部 1900+ 站点。
解析后展示精选画质档位（如 `1080p` / `audio 129k`），下载时由 yt-dlp 自动合并音视频。

## 安装

```bash
pip install -e .          # 或 pip install aiohttp cryptography customtkinter pillow yt-dlp
```

音视频合并需要系统安装 ffmpeg（`ffmpeg` 在 PATH 中即可）。

## 用法

### GUI（推荐）

```bash
python main.py
```

粘贴链接（可多行）→ 解析 → 勾选媒体 → 下载。输出目录可改，支持封面/平台徽章、逐字节下载进度。

### CLI

```bash
python cli.py "https://www.bilibili.com/video/BV1GJ411x7h7"
python cli.py --download --out ./downloads "https://v.douyin.com/xxxx/ 附带任意文本"
python cli.py --json "https://weibo.com/xxx"
python cli.py --bilibili-cookie "SESSDATA=...; bili_jct=..." --download "https://b23.tv/xxx"
```

## 常见问题

**Q: 某个链接解析失败/无法下载？**
先确认平台归属：国内平台（B站/抖音/快手/微博/小红书等）由 parser_core 处理，其余由 yt-dlp。
部分平台需要登录态（微博长视频、Twitter、Vimeo、Instagram），部分会风控数据中心/海外 IP。

**Q: YouTube 解析成功但下载 403？**
YouTube 对数据中心 IP 的下载请求直接拒绝，属平台风控。配置代理：
`python cli.py --ydl-proxy http://127.0.0.1:7890 --download "链接"`

**Q: 音视频分离没声音 / 提示需要 ffmpeg？**
yt-dlp 合并音视频依赖系统 ffmpeg（`choco install ffmpeg` 或官网安装后加入 PATH）。
parser_core 的 B站 DASH 分离流同样依赖。

**Q: 怎么同步解析核心？**
`parser_core/` 对应 `HIKARI_BOT_NEO/third_party/astrbot_plugin_media_parser/core/`，
上游更新时覆盖对应目录即可（相对导入均在包内自洽）。

## 项目结构

```
main.py           GUI 入口（customtkinter）
cli.py            CLI 入口
app/
  common.py       共享模型（DownloadSummary、文件名净化）
  engine.py       解析引擎：parser_core 路由 + yt-dlp 兜底 → ParseResult
  ydl.py          yt-dlp 引擎与下载器（格式档位精选、进度钩子、ffmpeg 合并）
  downloader.py   直链下载器：流式下载（进度）+ dash/m3u8 交给 DownloadManager
  gui.py          图形界面
parser_core/      从 astrbot_plugin_media_parser 打包的解析核心
  parser/         10 个平台解析器（platform/）+ ParserManager 路由
  downloader/     机器人下载管理（dash/m3u8/range 处理）
  storage/        缓存与文件管理
```


## 已知限制

- 部分平台（微博长视频、Twitter、Vimeo、Instagram 等）需要登录态，解析或下载可能失败
- 数据中心/海外 IP 访问部分平台（YouTube 下载、SoundCloud、网易云音乐等）会被风控拒绝，
  可配置代理改善（CLI `--ydl-proxy`；GUI 暂未暴露，可改 `app/gui.py` 中 `ParseEngine()` 调用）
- B 站 DASH 分离流（`dash:` URL）由机器人的 DownloadManager 处理，无逐字节进度；音视频合并
  依赖系统 ffmpeg
- 抖音/快手等平台风控较严，频率过高可能触发验证
