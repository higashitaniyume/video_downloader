"""媒体下载器。

所有下载一律交给 yt-dlp 自身（调用 YdlDownloader，自动选择最佳格式并用 ffmpeg 合并音视频）。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

import aiohttp

logger = logging.getLogger(__name__)

from .common import DownloadSummary, DownloadedFile, sanitize_filename, unique_path
from .control import DownloadControl, TaskCancelled
from .engine import MediaItem, ParseResult

ProgressCallback = Callable[[str, int, Optional[int]], None]
"""进度回调 (label, done_bytes, total_bytes)；total 为 None 表示未知总长。"""


class MediaDownloader:
    """把 ParseResult 的媒体项下载到输出目录（完全基于 yt-dlp）。"""

    def __init__(
        self,
        out_dir: str | Path,
        cache_dir: Optional[str | Path] = None,
        *,
        max_video_size_mb: float = 0.0,
        proxy: str = "",
        ydl_cookies_from_browser: str = "",
        ydl_cookies_file: str = "",
    ):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = proxy.strip()
        self.ydl_cookies_from_browser = (ydl_cookies_from_browser or "").strip().lower()
        self.ydl_cookies_file = (ydl_cookies_file or "").strip()

    async def download_result(
        self,
        session: aiohttp.ClientSession,
        result: ParseResult,
        progress: Optional[ProgressCallback] = None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        """下载一个解析结果的全部媒体项，返回文件清单与错误（异步，供 CLI 使用）。"""
        return await asyncio.to_thread(self._download_ydl, result, progress, control)

    def download_result_sync(
        self,
        result: ParseResult,
        progress: Optional[ProgressCallback] = None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        """同步入口，供 GUI 后台线程调用。"""
        return self._download_ydl(result, progress, control)

    def _download_ydl(
        self,
        result: ParseResult,
        progress: Optional[ProgressCallback] = None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        from .ydl import YdlDownloader
        downloader = YdlDownloader(
            self.out_dir, proxy=self.proxy,
            cookies_from_browser=self.ydl_cookies_from_browser,
            cookies_file=self.ydl_cookies_file,
        )
        return downloader.download_result_sync(result, result.items, progress, control)

    def cancel_active(self) -> None:
        """取消当前批次仍在运行的下载任务（在 yt-dlp 模式下由 control 控制即可）。"""
        pass

    def shutdown(self) -> None:
        """释放下载器。"""
        pass
