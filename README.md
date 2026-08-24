# video_downloader

这是一个为强大命令行媒体下载工具 `yt-dlp` 开发的现代图形界面包装器（Windows 桌面 GUI + CLI 双入口）。

粘贴一个链接即可自动通过 `yt-dlp` 解析出标题、作者、时长、封面和全部可用的媒体格式档位，勾选后即可一键下载到本地。支持国内外 1900+ 平台的解析与下载。

## 功能特性

- **GUI 桌面工具**（深色主题）：粘贴多行链接 → 解析卡片（平台/标题/作者/时长/封面）→ 勾选媒体格式（如不同分辨率视频/单独音频）→ 实时下载进度。
- **CLI 命令行工具**：解析链接、输出 JSON 格式元数据、批量下载，方便脚本化集成。
- **下载能力强**：支持通过 `yt-dlp` 进行视频流下载，对于音视频分离的平台，自动调用本地 `ffmpeg` 进行合并。
- **平台登录 Cookie 读取**：可在设置中配置直接读取浏览器已登录的 Cookie（Edge / Chrome / Firefox）或指定本地 `cookies.txt` 文件，让 B站高清、YouTube 限制内容、Instagram 等需要登录的平台也能解析和下载。
- **清晰度上限控制**：支持全局设置最高清晰度（自动 / 4K / 1080P / 720P / 480P / 360P），自动隐藏/过滤高于该清晰度的格式。
- **全局代理**：设置中可一键启用并测试本地代理，确保海外平台（YouTube 等）解析和下载的连通性。

## 支持的平台

支持包括 YouTube、Bilibili (B站)、抖音、快手、微博、小红书、TikTok、Twitter/X、Vimeo 等在内的 1900+ 平台，极具通用性。

## 安装

```bash
# 使用项目虚拟环境（推荐）
.venv\Scripts\activate
pip install -e .

# 或手动装依赖
pip install customtkinter pillow "yt-dlp[default]"
```

音视频合并需要系统安装 ffmpeg（`ffmpeg` 在 PATH 中即可）。

## 用法

### GUI

```bash
python main.py
```

粘贴链接（可多行） → 点击「解析链接」 → 勾选卡片上的格式 → 点击「下载全部」。

在左下角点击「设置」，可以配置：
1. **代理配置**：支持填写本地代理（如 `http://127.0.0.1:7890`），点「测试代理」可测试网络连通性。
2. **最高清晰度上限**：限制获取的格式档位。
3. **平台登录 Cookie**：选择已登录相应平台的浏览器（Edge/Chrome/Firefox），使 yt-dlp 能读取登录态。

### CLI

```bash
python cli.py "https://www.bilibili.com/video/BVxxxxxx"
python cli.py --download --out ./downloads "https://www.youtube.com/watch?v=xxxxxx"
python cli.py --json "https://weibo.com/xxx"
python cli.py --quality 1080p --download "https://www.youtube.com/watch?v=xxx"
python cli.py --proxy http://127.0.0.1:7890 --download "https://www.youtube.com/watch?v=xxx"
python cli.py --ydl-cookies-from-browser edge "https://www.instagram.com/p/xxx"
```

## 项目结构

```
main.py           GUI 入口（customtkinter）
cli.py            CLI 入口
app/
  common.py       共享模型与文件名净化工具
  engine.py       解析引擎：提取链接，调用 YdlEngine 解析元数据
  ydl.py          yt-dlp 引擎包装与下载器（格式精选、进度钩子、合并逻辑）
  downloader.py   媒体下载器：将下载委托给 YdlDownloader 执行
  config.py       应用配置持久化（代理、清晰度、Cookie 配置 -> config.json）
  logging_setup.py  日志系统（-> logs/ 滚动日志）
  portable.py     便携运行支持（EXE 打包支持）
  theme.py        UI 字体工具
  settings_dialog.py  设置窗口（代理 + 清晰度 + 浏览器 Cookie）
  gui.py          图形界面主窗口
```
## 已知限制

- 部分平台（微博长视频、Twitter、Vimeo、Instagram 等）需要登录态，解析或下载可能失败；可在设置/CLI 中为 yt-dlp 配置浏览器 Cookie 或 cookies.txt 后重试。
- 数据中心/海外 IP 访问部分平台（YouTube、SoundCloud、网易云音乐等）可能被风控拒绝，可配置代理。
- 音视频合并依赖系统 ffmpeg。
