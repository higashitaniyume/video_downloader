"""Web 服务与 API 后端：基于 aiohttp.web 提供现代化 Web 界面与 RESTful API。"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import socket
import sys
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

import aiohttp
from aiohttp import web

from app.common import DownloadSummary, sanitize_filename
from app.config import AppConfig, DEFAULT_QUALITY, QUALITY_PRESETS
from app.control import DownloadControl, TaskCancelled
from app.downloader import MediaDownloader
from app.engine import DEFAULT_UA, MediaItem, ParseEngine, ParseResult
from app.logging_setup import get_log_dir

logger = logging.getLogger(__name__)


def get_static_dir() -> Path:
    """获取静态资源文件目录（兼容源码运行与 PyInstaller 打包环境）。"""
    if hasattr(sys, "_MEIPASS"):
        bundle_dir = Path(sys._MEIPASS) / "app" / "web" / "static"
        if bundle_dir.exists():
            return bundle_dir
    return Path(__file__).resolve().parent / "static"


def find_available_port(start_port: int = 5200, max_attempts: int = 30) -> int:
    """查找可用的本地 TCP 端口。"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start_port


class TaskState:
    """单个下载任务的实时状态。"""

    def __init__(self, task_id: str, title: str, platform: str, total_items: int = 1):
        self.task_id = task_id
        self.title = title
        self.platform = platform
        self.status = "pending"  # pending, downloading, paused, completed, failed, cancelled
        self.total_items = total_items
        self.current_item_index = 0
        self.item_label = ""
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.percent = 0.0
        self.speed_bytes_per_sec = 0.0
        self.speed_text = ""
        self.eta_seconds = 0
        self.eta_text = ""
        self.error = ""
        self.created_at = time.time()
        self.finished_at: Optional[float] = None
        self.control = DownloadControl()
        self._last_calc_time = time.time()
        self._last_calc_bytes = 0

    def update_progress(self, label: str, done_bytes: int, total_bytes: Optional[int]) -> None:
        now = time.time()
        self.item_label = label
        self.downloaded_bytes = done_bytes
        if total_bytes and total_bytes > 0:
            self.total_bytes = total_bytes
            self.percent = min(100.0, round((done_bytes / total_bytes) * 100, 1))

        # 计算瞬时下载速度
        dt = now - self._last_calc_time
        if dt >= 0.5:
            delta_bytes = done_bytes - self._last_calc_bytes
            if delta_bytes >= 0:
                self.speed_bytes_per_sec = delta_bytes / dt
                self.speed_text = self._format_speed(self.speed_bytes_per_sec)
                if self.total_bytes > done_bytes and self.speed_bytes_per_sec > 0:
                    self.eta_seconds = int((self.total_bytes - done_bytes) / self.speed_bytes_per_sec)
                    self.eta_text = self._format_eta(self.eta_seconds)
                else:
                    self.eta_text = ""
            self._last_calc_time = now
            self._last_calc_bytes = done_bytes

    @staticmethod
    def _format_speed(speed: float) -> str:
        if speed < 1024:
            return f"{speed:.0f} B/s"
        if speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        return f"{speed / (1024 * 1024):.2f} MB/s"

    @staticmethod
    def _format_eta(seconds: int) -> str:
        if seconds <= 0:
            return ""
        if seconds < 60:
            return f"{seconds}s"
        m, s = divmod(seconds, 60)
        return f"{m}m {s}s"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "platform": self.platform,
            "status": self.status,
            "item_label": self.item_label,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "percent": self.percent,
            "speed_text": self.speed_text,
            "eta_text": self.eta_text,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "is_paused": self.control.is_paused,
        }


class WebServerManager:
    """管理 Web 应用生命周期、路由处理与后台下载调度。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5200, out_dir: Optional[Path] = None):
        self.host = host
        self.preferred_port = port
        self.active_port = port
        self.out_dir = out_dir or Path.cwd() / "downloads"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.config = AppConfig.load()
        self.engine = self._build_engine()
        self.tasks: dict[str, TaskState] = {}
        self._tasks_lock = threading.Lock()

        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._is_running = False

    @property
    def server_url(self) -> str:
        return f"http://{self.host}:{self.active_port}"

    @property
    def is_running(self) -> bool:
        return self._is_running

    def _build_engine(self) -> ParseEngine:
        return ParseEngine(
            quality=self.config.quality,
            proxy=self.config.proxy_url,
            ydl_cookies_from_browser=self.config.ydl_cookies_from_browser,
            ydl_cookies_file=self.config.ydl_cookies_file,
        )

    def create_app(self) -> web.Application:
        app = web.Application(client_max_size=32 * 1024 * 1024)
        static_dir = get_static_dir()

        # API 路由
        app.router.add_get("/api/status", self.handle_get_status)
        app.router.add_get("/api/config", self.handle_get_config)
        app.router.add_post("/api/config", self.handle_post_config)
        app.router.add_post("/api/proxy/test", self.handle_post_proxy_test)
        app.router.add_post("/api/parse", self.handle_post_parse)
        app.router.add_post("/api/download", self.handle_post_download)
        app.router.add_get("/api/tasks", self.handle_get_tasks)
        app.router.add_post("/api/tasks/{task_id}/pause", self.handle_task_pause)
        app.router.add_post("/api/tasks/{task_id}/resume", self.handle_task_resume)
        app.router.add_post("/api/tasks/{task_id}/cancel", self.handle_task_cancel)
        app.router.add_post("/api/tasks/clear", self.handle_tasks_clear)
        app.router.add_post("/api/open-folder", self.handle_open_folder)
        app.router.add_get("/api/cover", self.handle_cover_proxy)
        app.router.add_get("/api/logs", self.handle_get_logs)

        # 静态文件路由
        app.router.add_get("/", self.handle_index)
        app.router.add_static("/static", path=str(static_dir), name="static")

        return app

    # ── 路由处理器 ─────────────────────────────

    async def handle_index(self, request: web.Request) -> web.Response:
        static_dir = get_static_dir()
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return web.Response(text="Web UI static files not found.", status=404)
        return web.FileResponse(index_path)

    async def handle_get_status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "version": "1.0.0",
            "host": self.host,
            "port": self.active_port,
            "server_url": self.server_url,
            "out_dir": str(self.out_dir),
            "quality_presets": list(QUALITY_PRESETS.keys()),
        })

    async def handle_get_config(self, request: web.Request) -> web.Response:
        return web.json_response({
            "proxy_url": self.config.proxy_url,
            "quality": self.config.quality,
            "ydl_cookies_from_browser": self.config.ydl_cookies_from_browser,
            "ydl_cookies_file": self.config.ydl_cookies_file,
            "web_port": self.config.web_port,
            "out_dir": str(self.out_dir),
        })

    async def handle_post_config(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        if "proxy_url" in data:
            self.config.proxy_url = str(data["proxy_url"]).strip()
        if "quality" in data:
            quality = str(data["quality"]).strip().lower()
            if quality in QUALITY_PRESETS:
                self.config.quality = quality
        if "ydl_cookies_from_browser" in data:
            self.config.ydl_cookies_from_browser = str(data["ydl_cookies_from_browser"]).strip().lower()
        if "ydl_cookies_file" in data:
            self.config.ydl_cookies_file = str(data["ydl_cookies_file"]).strip()
        if "out_dir" in data and str(data["out_dir"]).strip():
            new_out = Path(str(data["out_dir"]).strip())
            new_out.mkdir(parents=True, exist_ok=True)
            self.out_dir = new_out

        self.config.save()
        self.engine = self._build_engine()
        return web.json_response({"status": "ok", "message": "设置已保存并生效"})

    async def handle_post_proxy_test(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            proxy = str(data.get("proxy_url", "")).strip() or self.config.proxy_url
        except Exception:
            proxy = self.config.proxy_url

        if not proxy:
            return web.json_response({"success": False, "error": "代理地址为空"})

        test_url = "https://www.google.com/generate_204"
        start_time = time.time()
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(test_url, proxy=proxy) as resp:
                    latency = round((time.time() - start_time) * 1000, 1)
                    if resp.status in (200, 204):
                        return web.json_response({
                            "success": True,
                            "latency_ms": latency,
                            "message": f"连接成功（{latency} ms）",
                        })
                    return web.json_response({
                        "success": False,
                        "error": f"代理响应异常 (HTTP {resp.status})",
                    })
        except Exception as exc:
            return web.json_response({"success": False, "error": f"连接失败: {exc}"})

    async def handle_post_parse(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            text = str(data.get("text", "")).strip()
        except Exception:
            return web.json_response({"error": "Invalid request body"}, status=400)

        if not text:
            return web.json_response({"error": "请输入需要解析的链接或文本"}, status=400)

        loop = asyncio.get_running_loop()
        results: list[ParseResult] = await loop.run_in_executor(None, self.engine.parse_text_sync, text)

        serialized = []
        for r in results:
            items = []
            for item in r.items:
                items.append({
                    "index": item.index,
                    "name": item.name,
                    "kind": item.kind,
                    "quality": item.quality,
                    "size_bytes": item.size_bytes,
                    "format_id": item.format_id,
                    "ext": item.ext,
                })
            serialized.append({
                "platform": r.platform,
                "url": r.url,
                "title": r.title or "（无标题）",
                "author": r.author or "",
                "duration_text": r.duration_text or "",
                "timestamp": r.timestamp or "",
                "cover_urls": r.cover_urls,
                "items": items,
                "is_error": r.is_error,
                "error": r.error or "",
                "has_media": r.has_media,
                "raw_info": r.raw,
            })

        return web.json_response({"results": serialized, "count": len(serialized)})

    async def handle_post_download(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            tasks_data = data.get("tasks", [])
            custom_out_dir = str(data.get("out_dir", "")).strip()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        if not tasks_data:
            return web.json_response({"error": "未选择任何下载任务"}, status=400)

        target_out_dir = Path(custom_out_dir) if custom_out_dir else self.out_dir
        target_out_dir.mkdir(parents=True, exist_ok=True)

        created_task_ids = []
        for t_info in tasks_data:
            result_dict = t_info.get("result", {})
            selected_indices = set(t_info.get("selected_indices", []))
            if not result_dict:
                continue

            # 还原 ParseResult
            items: list[MediaItem] = []
            for item_dict in result_dict.get("items", []):
                idx = item_dict.get("index", 0)
                if selected_indices and idx not in selected_indices:
                    continue
                items.append(MediaItem(
                    index=idx,
                    name=item_dict.get("name", ""),
                    kind=item_dict.get("kind", "video"),
                    quality=item_dict.get("quality", ""),
                    size_bytes=item_dict.get("size_bytes", 0),
                    format_id=item_dict.get("format_id", ""),
                    ext=item_dict.get("ext", "mp4"),
                ))

            if not items:
                continue

            parse_res = ParseResult(
                platform=result_dict.get("platform", "video"),
                url=result_dict.get("url", ""),
                title=result_dict.get("title", ""),
                author=result_dict.get("author", ""),
                duration_text=result_dict.get("duration_text", ""),
                timestamp=result_dict.get("timestamp", ""),
                cover_urls=result_dict.get("cover_urls", []),
                items=items,
                raw=result_dict.get("raw_info", {}),
            )

            task_id = f"task_{uuid.uuid4().hex[:8]}"
            task_state = TaskState(
                task_id=task_id,
                title=parse_res.title or parse_res.platform,
                platform=parse_res.platform,
                total_items=len(items),
            )

            with self._tasks_lock:
                self.tasks[task_id] = task_state

            created_task_ids.append(task_id)

            # 在后台线程启动下载
            threading.Thread(
                target=self._run_download_task,
                args=(task_state, parse_res, target_out_dir),
                daemon=True,
            ).start()

        return web.json_response({"task_ids": created_task_ids, "status": "queued"})

    def _run_download_task(self, task_state: TaskState, result: ParseResult, out_dir: Path) -> None:
        task_state.status = "downloading"
        downloader = MediaDownloader(
            out_dir=out_dir,
            proxy=self.config.proxy_url,
            ydl_cookies_from_browser=self.config.ydl_cookies_from_browser,
            ydl_cookies_file=self.config.ydl_cookies_file,
        )

        def _progress(label: str, done: int, total: Optional[int]) -> None:
            task_state.update_progress(label, done, total)

        try:
            summary = downloader.download_result_sync(
                result=result,
                progress=_progress,
                control=task_state.control,
            )
            if summary.errors:
                task_state.status = "failed"
                task_state.error = "；".join(summary.errors)
            else:
                task_state.status = "completed"
                task_state.percent = 100.0
        except TaskCancelled:
            task_state.status = "cancelled"
            task_state.error = "用户已取消"
        except Exception as exc:
            task_state.status = "failed"
            task_state.error = str(exc)
        finally:
            task_state.finished_at = time.time()

    async def handle_get_tasks(self, request: web.Request) -> web.Response:
        with self._tasks_lock:
            task_list = [t.to_dict() for t in self.tasks.values()]
        # 按创建时间倒序排
        task_list.sort(key=lambda x: x["created_at"], reverse=True)
        return web.json_response({"tasks": task_list})

    async def handle_task_pause(self, request: web.Request) -> web.Response:
        task_id = request.match_info.get("task_id", "")
        with self._tasks_lock:
            task = self.tasks.get(task_id)
        if not task:
            return web.json_response({"error": "Task not found"}, status=404)
        task.control.pause()
        task.status = "paused"
        return web.json_response({"status": "ok"})

    async def handle_task_resume(self, request: web.Request) -> web.Response:
        task_id = request.match_info.get("task_id", "")
        with self._tasks_lock:
            task = self.tasks.get(task_id)
        if not task:
            return web.json_response({"error": "Task not found"}, status=404)
        task.control.resume()
        task.status = "downloading"
        return web.json_response({"status": "ok"})

    async def handle_task_cancel(self, request: web.Request) -> web.Response:
        task_id = request.match_info.get("task_id", "")
        with self._tasks_lock:
            task = self.tasks.get(task_id)
        if not task:
            return web.json_response({"error": "Task not found"}, status=404)
        task.control.cancel()
        task.status = "cancelled"
        task.error = "用户已取消"
        return web.json_response({"status": "ok"})

    async def handle_tasks_clear(self, request: web.Request) -> web.Response:
        with self._tasks_lock:
            self.tasks = {k: v for k, v in self.tasks.items() if v.status in ("downloading", "paused")}
        return web.json_response({"status": "ok"})

    async def handle_open_folder(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            folder = str(data.get("folder", "")).strip() or str(self.out_dir)
        except Exception:
            folder = str(self.out_dir)

        path = Path(folder)
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
            return web.json_response({"status": "ok", "folder": str(path)})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_cover_proxy(self, request: web.Request) -> web.Response:
        url = request.query.get("url", "").strip()
        if not url:
            return web.Response(status=400, text="Missing url param")

        headers = {
            "User-Agent": DEFAULT_UA,
            "Referer": "https://www.bilibili.com/" if "bili" in url or "hdslb" in url else (
                "https://www.douyin.com/" if "douyin" in url or "byteimg" in url else ""
            ),
        }
        headers = {k: v for k, v in headers.items() if v}

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            session_kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
            if self.config.proxy_url:
                session_kwargs["proxy"] = self.config.proxy_url

            async with aiohttp.ClientSession(**session_kwargs) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "image/jpeg")
                        body = await resp.read()
                        return web.Response(body=body, content_type=content_type)
                    return web.Response(status=resp.status)
        except Exception as exc:
            logger.warning("封面代理拉取失败 (%s): %s", url, exc)
            return web.Response(status=502, text=f"Cover proxy error: {exc}")

    async def handle_get_logs(self, request: web.Request) -> web.Response:
        log_file = get_log_dir() / "video_downloader.log"
        if not log_file.exists():
            return web.json_response({"logs": ["（暂无日志文件）"]})
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            return web.json_response({"logs": lines[-120:]})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=500)

    # ── 服务线程管理 ─────────────────────────

    def start_in_thread(self, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
        if self._is_running:
            return

        self.host = host
        target_port = port or self.config.web_port or self.preferred_port
        self.active_port = find_available_port(target_port)

        ready_event = threading.Event()
        start_error: list[Exception] = []

        def _thread_target():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            app = self.create_app()
            self._runner = web.AppRunner(app)

            async def _start():
                try:
                    await self._runner.setup()
                    self._site = web.TCPSite(self._runner, self.host, self.active_port)
                    await self._site.start()
                    self._is_running = True
                    logger.info("Web 服务已启动: %s", self.server_url)
                    ready_event.set()
                except Exception as e:
                    start_error.append(e)
                    ready_event.set()

            self._loop.create_task(_start())
            try:
                self._loop.run_forever()
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=_thread_target, name="WebServerThread", daemon=True)
        self._thread.start()
        ready_event.wait(timeout=5.0)

        if start_error:
            logger.error("Web 服务启动失败: %s", start_error[0])
            raise start_error[0]

    def stop(self) -> None:
        if not self._is_running or not self._loop:
            return
        self._is_running = False

        async def _shutdown():
            if self._runner:
                await self._runner.cleanup()
            self._loop.stop()

        asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Web 服务已停止")
