# video_downloader

视频/媒体解析与下载小工具（Windows 桌面 GUI + CLI 双入口）。

粘贴一个链接就能解析出标题、作者、时长、封面和可用的媒体直链，勾选后即可下载到本地。
支持国内主流平台（B站、抖音、快手、微博、小红书、头条、闲鱼、小黑盒、TikTok、Twitter/X），
也支持 YouTube、SoundCloud、Instagram、Vimeo、网易云音乐等海外站点 —— 以及更多，
解析能力覆盖 1900+ 平台，大部分无需登录即可使用。

## 功能特性

- **GUI 桌面工具**（深色主题）：粘贴多行链接 → 解析卡片（平台徽章/标题/作者/时长/封面）→ 勾选媒体 → 实时下载进度
- **CLI**：解析、JSON 输出、批量下载，可脚本化
- **下载能力强**：直链流式下载（逐字节进度）、B站 DASH 分离流、HLS(m3u8) 流、自动格式选择 + ffmpeg 音视频合并
- **可选 B 站 Cookie**：解锁高清晰度（`--bilibili-cookie`）
- **清晰度可配置**：B 站解析与 yt-dlp 兜底平台（YouTube 等）可统一限制最高清晰度
  （自动 / 4K / 1080P / 720P / 480P / 360P，GUI 设置或 CLI `--quality`）
- **GUI 设置**：可在界面里配置全局代理（解析/下载全程生效，含测试按钮）、B 站 Cookie 与最高清晰度，
  配置自动保存（`~/.video_downloader/config.json`），内置「如何获取 Cookie」图文指引
- **B 站扫码登录**：设置里扫码即登录，凭据自动保存（`~/.video_downloader/bilibili_credentials.json`），
  无需手动复制 Cookie，下次启动免登录

## 支持的平台

| 平台 | 说明 |
| --- | --- |
| Bilibili | BV/AV 号、番剧 ep/ss、动态/opus、b23.tv 短链；无 Cookie 时低清晰度，配置 Cookie 可解锁高清晰度 |
| 抖音 Douyin | 分享短链、视频/图文/Slides |
| 快手 Kuaishou | 短链/长链/gifshow |
| 微博 Weibo | 桌面版/移动版/视频组件页，自动获取访客 Cookie |
| 小红书 Xiaohongshu | 短链/移动端/PC 端笔记 |
| TikTok | 需科学上网（可用代理） |
| 头条 Toutiao | |
| 闲鱼 Xianyu | 商品媒体 |
| 小黑盒 Xiaoheihe | 含 HLS(m3u8) 流 |
| Twitter / X | 多数内容需登录 |
| YouTube / SoundCloud / Instagram / Vimeo / 网易云音乐 等 | 及更多 1900+ 站点，解析后展示精选画质档位（如 `1080p` / `audio 129k`），下载时自动合并音视频 |

## 安装

```bash
# 使用项目虚拟环境（推荐）
.venv\Scripts\activate
pip install -e .

# 或手动装依赖
pip install aiohttp cryptography customtkinter pillow "yt-dlp[default]"
```

音视频合并需要系统安装 ffmpeg（`ffmpeg` 在 PATH 中即可）。

## 用法

### GUI（推荐）

```bash
python main.py
```

粘贴链接（可多行）→ 解析 → 勾选媒体 → 下载。输出目录可改，支持封面/平台徽章、逐字节下载进度。

侧栏「设置」按钮可配置：

- **代理**：填写代理软件（Clash / v2ray 等）的本地地址，如 `http://127.0.0.1:7890`，
  解析与下载全程生效，点「测试代理」可验证连通性；
- **B 站 Cookie**：解锁高清晰度，点「如何获取 Cookie？」有详细的获取步骤说明
  （F12 → 网络 Network → 刷新 → 复制请求头里的 Cookie 整行）。
- **B 站扫码登录**：点「扫码登录」弹出二维码，用 B 站手机 App 扫一扫即完成登录，
  凭据自动保存、免手动复制 Cookie；登录态优先于手动配置的 Cookie。
- **最高清晰度**：选择 B 站解析所选画质的上限（如 1080P）；对 YouTube 等 yt-dlp 兜底平台，
  解析结果只展示不高于该清晰度的档位。选「自动（最高可用）」则不限制。

### CLI

```bash
python cli.py "https://www.bilibili.com/video/BV1GJ411x7h7"
python cli.py --download --out ./downloads "https://v.douyin.com/xxxx/ 附带任意文本"
python cli.py --json "https://weibo.com/xxx"
python cli.py --bilibili-cookie "SESSDATA=...; bili_jct=..." --download "https://b23.tv/xxx"
python cli.py --quality 1080p --download "https://www.youtube.com/watch?v=xxx"
# --quality 可选 auto/4k/1080p/720p/480p/360p（默认 auto=最高可用），B站与 yt-dlp 平台均生效
python cli.py --proxy http://127.0.0.1:7890 --download "https://www.youtube.com/watch?v=xxx"
# --proxy 全局代理（解析+下载）；旧参数 --ydl-proxy 仍可用，仅作用于 yt-dlp
```

## 常见问题

**Q: 某个链接解析失败/无法下载？**
部分平台需要登录态（微博长视频、Twitter、Vimeo、Instagram），部分平台会风控数据中心/海外 IP。

**Q: YouTube 解析成功但下载 403？**
YouTube 对数据中心 IP 的下载请求直接拒绝，属平台风控。配置代理：
`python cli.py --ydl-proxy http://127.0.0.1:7890 --download "链接"`

**Q: B 站扫码登录了，解析出来还是 720P / 480P？**
请先重启程序再重新解析（登录态在启动时加载；同一会话内扫码后也需重新解析）。
另外注意：普通账号最高通常只能拿到 1080P；1080P60 / 1080P+ / 4K 等档位需要大会员；
部分视频上传时本身最高就只有 720P。可在设置里把「最高清晰度」设为「自动（最高可用）」。

**Q: 音视频分离没声音 / 提示需要 ffmpeg？**
合并音视频依赖系统 ffmpeg（`choco install ffmpeg` 或官网安装后加入 PATH）。

## 项目结构

```
main.py           GUI 入口（customtkinter）
cli.py            CLI 入口
app/
  common.py       共享模型（DownloadSummary、文件名净化）
  engine.py       解析引擎：平台路由与并发解析 → ParseResult
  ydl.py          通用站点引擎与下载器（格式档位精选、进度钩子、ffmpeg 合并）
  downloader.py   直链下载器：流式下载（进度）+ DASH/HLS 处理
  config.py       应用配置持久化（代理、Cookie → ~/.video_downloader/config.json）
  theme.py        UI 字体工具（使用系统默认字体）
  settings_dialog.py  设置窗口（代理 + Cookie + 扫码登录 + 获取方法说明）
  gui.py          图形界面
parser_core/      解析核心（内置各平台解析器与下载管理）
```

## 已知限制

- 部分平台（微博长视频、Twitter、Vimeo、Instagram 等）需要登录态，解析或下载可能失败
- 数据中心/海外 IP 访问部分平台（YouTube 下载、SoundCloud、网易云音乐等）会被风控拒绝，
  可用 `--ydl-proxy` 配置代理
- B 站 DASH 分离流无逐字节进度；音视频合并依赖系统 ffmpeg
- 抖音/快手等平台风控较严，频率过高可能触发验证
