"""媒体下载器。

- 普通直链 / ``range:`` 前缀 / 图片：本模块流式下载，带逐字节进度回调；
- ``dash:`` / ``m3u8:``（B站 DASH 分离流、小黑盒 HLS）：交给
  parser_core.downloader.DownloadManager（复用机器人下载逻辑），进度为整项级。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

import aiohttp

logger = logging.getLogger(__name__)

from parser_core.constants import Config
from parser_core.downloader import DownloadManager

from .common import DownloadSummary, DownloadedFile, sanitize_filename, unique_path
from .control import DownloadControl, TaskCancelled
from .engine import MediaItem, ParseResult

ProgressCallback = Callable[[str, int, Optional[int]], Awaitable[None]]
"""进度回调 (label, done_bytes, total_bytes)；total 为 None 表示未知总长。"""

CONTENT_TYPE_EXT = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
}

# 已知媒体扩展名：目标文件名已带其中之一时不再推断
KNOWN_EXTENSIONS = set(CONTENT_TYPE_EXT.values())

# 抖音等 CDN 直链常把类型放在查询参数里（如 mime_type=video_mp4）
_MIME_HINT_RE = re.compile(r"mime_type=(video|audio|image)_([a-z0-9]+)", re.IGNORECASE)
_MIME_TYPE_EXT = {
    "video_mp4": ".mp4",
    "video_webm": ".webm",
    "video_quicktime": ".mov",
    "audio_mp4": ".m4a",
    "audio_aac": ".aac",
    "audio_mpeg": ".mp3",
    "image_jpeg": ".jpg",
    "image_png": ".png",
    "image_webp": ".webp",
    "image_gif": ".gif",
}

_INVALID_FILENAME_CHARS = re.compile(r'[\/:*?"<>|\x00-\x1f]')

def sanitize_filename(name: str, max_len: int = 60) -> str:
    """清理文件名中的非法字符并截断。"""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_len].rstrip(" .")


def unique_path(directory: Path, filename: str) -> Path:
    """返回不覆盖已有文件的路径，冲突时追加 (1)、(2)…。"""
    candidate = directory / filename
    stem, suffix = os.path.splitext(filename)
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def strip_media_prefix(url: str) -> str:
    """去掉 range:/dash:/m3u8: 前缀，得到真实直链。"""
    for prefix in ("range:", "dash:", "m3u8:"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


def _ext_from_url(url: str) -> str:
    path = strip_media_prefix(url).split("?", 1)[0].split("#", 1)[0]
    _, ext = os.path.splitext(path)
    if ext:
        return ext.lower()
    # 兜底：从查询参数 mime_type=video_mp4 等推断扩展名（抖音 CDN 常见）
    m = _MIME_HINT_RE.search(url or "")
    if m:
        return _MIME_TYPE_EXT.get(f"{m.group(1)}_{m.group(2).lower()}", "")
    return ""


def _ext_from_content_type(content_type: str) -> str:
    mime = content_type.split(";", 1)[0].strip().lower()
    return CONTENT_TYPE_EXT.get(mime, "")


def _total_from_content_range(content_range: str) -> Optional[int]:
    """从 "bytes 0-1023/2048" 解析总长度；无总长返回 None。"""
    if not content_range or "/" not in content_range:
        return None
    total = content_range.rsplit("/", 1)[1].strip()
    try:
        return int(total)
    except ValueError:
        return None


async def download_stream(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
    dest: Path,
    progress: ProgressCallback,
    label: str,
    control: Optional[DownloadControl] = None,
) -> Path:
    """流式下载单个直链到 dest，返回实际落盘路径。

    ``range:`` 前缀表示服务器要求 Range 头；先写 .part 临时文件，成功后再改名。
    dest 无后缀时按 Content-Type 推断扩展名（返回的路径可能不同于入参）。
    control 非空时逐 chunk 检查暂停/取消；取消会清理 .part 且不落盘正式文件。
    """
    control = control or DownloadControl()
    use_range = url.startswith("range:")
    request_headers = dict(headers)
    if use_range:
        request_headers["Range"] = "bytes=0-"
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        async with session.get(strip_media_prefix(url), headers=request_headers) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            # 无扩展名或现有"后缀"不是已知媒体扩展（如标题含点导致
            # Path.suffix 误判成 .xxx_video1）时，按 Content-Type / URL 推断。
            if dest.suffix.lower() not in KNOWN_EXTENSIONS:
                ext = _ext_from_content_type(content_type) or _ext_from_url(url) or ".bin"
                if dest.suffix:
                    dest = dest.with_name(dest.name + ext)
                else:
                    dest = dest.with_suffix(ext)
                tmp = dest.with_suffix(dest.suffix + ".part")

            total: Optional[int] = None
            if use_range:
                total = _total_from_content_range(resp.headers.get("Content-Range", ""))
            if total is None:
                try:
                    total = int(resp.headers.get("Content-Length", "0") or 0) or None
                except ValueError:
                    total = None

            done = 0
            await control.checkpoint()
            await progress(label, 0, total)
            with open(tmp, "wb") as handle:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    await control.checkpoint()
                    handle.write(chunk)
                    done += len(chunk)
                    await progress(label, done, total)
        os.replace(tmp, dest)
        return dest
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


class MediaDownloader:
    """把 ParseResult 的媒体项下载到输出目录。"""

    def __init__(
        self,
        out_dir: str | Path,
        cache_dir: Optional[str | Path] = None,
        *,
        max_video_size_mb: float = 0.0,
        proxy: str = "",
    ):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = proxy.strip()
        if cache_dir is None:
            cache_dir = Path.cwd() / "cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # 复用机器人的下载管理器处理 dash:/m3u8: 等复杂流
        self._manager = DownloadManager(
            max_video_size_mb=max_video_size_mb,
            cache_dir=str(self.cache_dir),
        )

    @staticmethod
    def _is_light_item(item: MediaItem) -> bool:
        """普通直链（可直接流式下载）的媒体项。"""
        return all(
            not url.startswith(("dash:", "m3u8:"))
            for url in item.urls
        )

    def _friendly_name(self, result: ParseResult, item: MediaItem, ext: str) -> str:
        base = sanitize_filename(result.title or f"{result.platform}_{result.parser_name}")
        return f"{base}_{item.kind}{item.index}{ext}"

    async def _download_light(
        self,
        session: aiohttp.ClientSession,
        result: ParseResult,
        item: MediaItem,
        progress: ProgressCallback,
        control: DownloadControl,
    ) -> Optional[DownloadedFile]:
        headers = result.video_headers if item.kind == "video" else result.image_headers
        last_error: Optional[Exception] = None
        for url in item.urls:
            await control.checkpoint()
            label = f"{result.platform} · {item.kind}{item.index}"
            try:
                probe_ext = _ext_from_url(url)
                dest = unique_path(self.out_dir, self._friendly_name(result, item, probe_ext))
                dest = await download_stream(
                    session, url, headers, dest, progress, label, control)
                return DownloadedFile(
                    path=dest,
                    label=label,
                    size_bytes=dest.stat().st_size,
                )
            except (aiohttp.ClientError, OSError) as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        return None

    async def _download_heavy(
        self,
        session: aiohttp.ClientSession,
        result: ParseResult,
        heavy_items: list[MediaItem],
        control: DownloadControl,
    ) -> list[DownloadedFile]:
        """dash:/m3u8: 等复杂流：构造子元数据交给机器人的 DownloadManager。

        取消时由 watchdog 立即取消管理器内的下载任务；暂停通过
        on_sendable_media 钩子（每个媒体决策前）生效。
        """
        raw = dict(result.raw)
        raw["video_urls"] = [item.urls for item in heavy_items]
        raw["image_urls"] = []
        raw["video_headers"] = result.video_headers
        raw["image_headers"] = result.image_headers
        raw.pop("file_paths", None)
        if self.proxy:
            # 全局代理：让机器人的下载管理器对 dash/m3u8 流也走代理
            raw["proxy_url"] = self.proxy
            raw["use_video_proxy"] = True
            raw["use_image_proxy"] = True

        # 取消信号到达时，manager 内部的下载任务（await 中）感知不到
        # checkpoint，由 watchdog 直接取消它们（管理器保持可复用）。
        async def watchdog() -> None:
            while True:
                if control.is_cancelled:
                    self._manager.cancel_active_downloads()
                    return
                await asyncio.sleep(0.1)

        async def checkpoint_cb() -> None:
            await control.checkpoint()

        watch = asyncio.create_task(watchdog())
        try:
            await self._manager.process_metadata(
                session, raw, on_sendable_media=checkpoint_cb)
        except asyncio.CancelledError:
            raise TaskCancelled() from None
        finally:
            watch.cancel()
            try:
                await watch
            except asyncio.CancelledError:
                pass

        # 取消后不再把缓存文件搬运到输出目录
        await control.checkpoint()
        paths = raw.get("file_paths") or []

        files: list[DownloadedFile] = []
        for item, path in zip(heavy_items, paths):
            if not path or not os.path.exists(path):
                continue
            src = Path(path)
            ext = src.suffix or ".mp4"
            dest = unique_path(self.out_dir, self._friendly_name(result, item, ext))
            shutil.move(str(src), str(dest))
            files.append(DownloadedFile(
                path=dest,
                label=f"{result.platform} · {item.kind}{item.index}",
                size_bytes=dest.stat().st_size,
            ))
        return files

    async def download_result(
        self,
        session: aiohttp.ClientSession,
        result: ParseResult,
        progress: Optional[ProgressCallback] = None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        """下载一个解析结果的全部媒体项，返回文件清单与错误。

        control 非空时支持暂停/取消；TaskCancelled 向上传播不写入错误列表。
        """
        # yt-dlp 兜底结果：交给 YdlDownloader（格式选择/音视频合并由 yt-dlp 完成）
        if result.raw.get("ydl"):
            return await asyncio.to_thread(self._download_ydl, result, progress, control)
        control = control or DownloadControl()
        progress = progress or (lambda _label, _d, _t: asyncio.sleep(0))
        summary = DownloadSummary()

        light_items = [it for it in result.items if self._is_light_item(it)]
        heavy_items = [it for it in result.items if not self._is_light_item(it)]

        for item in light_items:
            try:
                file = await self._download_light(session, result, item, progress, control)
                if file:
                    summary.files.append(file)
                    logger.info(
                        "下载完成 [%s] %s -> %s（%.1f MB）",
                        result.platform, file.label, file.path.name,
                        file.size_bytes / 1024 / 1024,
                    )
            except (aiohttp.ClientError, OSError) as exc:
                summary.errors.append(f"{result.platform} {item.kind}{item.index} 下载失败: {exc}")
                logger.warning("下载失败 [%s] %s%d: %s", result.platform, item.kind, item.index, exc)
            except asyncio.CancelledError:
                raise

        if heavy_items:
            try:
                summary.files.extend(
                    await self._download_heavy(session, result, heavy_items, control)
                )
            except TaskCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 —— 下载失败不应中断整个任务
                summary.errors.append(f"{result.platform} 复杂流下载失败: {exc}")
                logger.exception("复杂流下载失败 [%s]: %s", result.platform, exc)

        if summary.files:
            logger.info(
                "任务完成 [%s]：成功 %d 个文件，失败 %d 条",
                result.platform, len(summary.files), len(summary.errors),
            )
        elif summary.errors:
            logger.warning("任务失败 [%s]：%s", result.platform, "；".join(summary.errors[:3]))
        return summary

    def _download_ydl(self, result: ParseResult,
                      progress: Optional[ProgressCallback] = None,
                      control: Optional[DownloadControl] = None) -> DownloadSummary:
        from .ydl import YdlDownloader
        downloader = YdlDownloader(self.out_dir, proxy=self.proxy)
        return downloader.download_result_sync(result, result.items, progress, control)

    def download_result_sync(
        self,
        result: ParseResult,
        progress: Optional[ProgressCallback] = None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        """同步入口，供 GUI 后台线程 / CLI 调用。"""
        async def _run() -> DownloadSummary:
            # 不限制总时长：大文件可能超过 aiohttp 默认 5 分钟，
            # 暂停/恢复期间也不应因总超时而中断
            session_kwargs: dict = {"timeout": aiohttp.ClientTimeout(total=None)}
            if self.proxy:
                session_kwargs["proxy"] = self.proxy
            async with aiohttp.ClientSession(**session_kwargs) as session:
                return await self.download_result(session, result, progress, control)
        return asyncio.run(_run())

    def cancel_active(self) -> None:
        """取消当前批次仍在运行的下载任务（管理器保持可复用）。"""
        try:
            asyncio.run(self._manager.cancel_active_downloads())
        except Exception:  # noqa: BLE001
            pass

    def shutdown(self) -> None:
        """释放下载器：仅取消活动任务，幂等且可安全重复调用。"""
        self.cancel_active()
