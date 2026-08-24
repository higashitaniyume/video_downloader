# 开发规范与多端同步准则 (Development Guidelines)

## 1. 多端功能同步要求 (Cross-Platform Feature Parity)

* **核心原则**：
  * 凡是在**桌面端（Desktop GUI / CLI / 核心引擎）**实现或优化的新功能（例如：新增平台解析器、多链接批量解析处理、下载流式优化、元数据提取、代理配置等），**必须尽可能同时同步实现到安卓端（Android Jetpack Compose + Chaquopy）**。
  * **唯一例外**：桌面端特有的 Web HTTP 服务托管及浏览器端展示功能（`app/web/`）无需迁移至安卓端。

* **安卓端同步实施要点**：
  1. **Python 核心层同步**：确保 `app/` 目录中的改动能通过 `android/app/build.gradle.kts` 的 `syncPythonFiles` 顺利同步至 `android/app/src/main/python/app/`。
  2. **Kotlin UI 与 Service 适配**：同步更新 `android/app/src/main/java/top/valency/videodownloader/` 下的 Compose UI（`ui/screens/`）、数据模型（`models/`）以及后台下载服务（`DownloadService.kt`），确保安卓用户能获得与桌面端一致的核心能力与体验。
  3. **交互体验对齐**：关注移动端特有交互细节（例如软键盘弹出、深色主题适配、权限管理、通知栏进度提示等）。

---

## 2. 构建与命名规范

* 桌面端（EXE / ZIP）与安卓端（APK）构建产物均严格采用 `项目名-版本号` 规则命名（如 `video-downloader-v1.0.0.apk`、`video-downloader-v1.0.0.exe`），版本号统一与 `build.gradle.kts` / 配置保持同步。
