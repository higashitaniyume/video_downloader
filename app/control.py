"""下载任务控制：暂停 / 继续 / 取消（线程安全）。

GUI 主线程调用 pause()/resume()/cancel()；下载协程通过 checkpoint()
（或同步的 sync_checkpoint()）在合适的时机响应。取消优先级高于暂停。
"""
from __future__ import annotations

import asyncio
import threading
import time

# 轮询间隔：暂停/取消的响应延迟上限
_POLL_INTERVAL = 0.2


class TaskCancelled(Exception):
    """下载任务被用户取消。"""


class DownloadControl:
    """一个下载批次共享的控制对象。

    - 暂停：checkpoint() 阻塞等待，恢复后继续；
    - 取消：checkpoint() 抛 TaskCancelled，各层 finally 负责清理 .part 等。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._paused = False
        self._cancelled = False

    # ── 控制接口（任意线程可调）──────────────────────

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            self._paused = False

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    # ── 异步检查点（下载协程调用）────────────────────

    async def checkpoint(self) -> None:
        """暂停时阻塞等待；已取消时抛 TaskCancelled。"""
        while True:
            with self._lock:
                cancelled = self._cancelled
                paused = self._paused
            if cancelled:
                raise TaskCancelled()
            if not paused:
                return
            await asyncio.sleep(_POLL_INTERVAL)

    # ── 同步检查点（yt-dlp hook / 工作线程调用）──────

    def sync_checkpoint(self) -> None:
        """同步版本：阻塞轮询；已取消时抛 TaskCancelled。"""
        while True:
            with self._lock:
                cancelled = self._cancelled
                paused = self._paused
            if cancelled:
                raise TaskCancelled()
            if not paused:
                return
            time.sleep(_POLL_INTERVAL)
