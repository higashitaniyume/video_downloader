"""customtkinter 图形界面：粘贴链接 → 解析 → 选择媒体 → 下载。"""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
from dataclasses import replace
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from tkinter import filedialog

from app.common import DownloadSummary
from app.config import AppConfig
from app.control import DownloadControl, TaskCancelled
from app.settings_dialog import SettingsDialog
from app.theme import font
from app.downloader import MediaDownloader
from app.engine import DEFAULT_UA, MediaItem, ParseEngine, ParseResult

logger = logging.getLogger(__name__)

# 平台徽章配色（深色主题）
PLATFORM_COLORS = {
    "bilibili": "#FB7299",
    "douyin": "#FE2C55",
    "kuaishou": "#FF4906",
    "weibo": "#E6162D",
    "xiaohongshu": "#FF2442",
    "tiktok": "#25F4EE",
    "twitter": "#1D9BF0",
    "toutiao": "#D81E06",
    "xianyu": "#FF9500",
    "xiaoheihe": "#5AC8FA",
    "youtube": "#FF0000",
    "soundcloud": "#FF5500",
    "instagram": "#E1306C",
    "twitch": "#9146FF",
    "spotify": "#1DB954",
    "neteasemusic": "#C20C0C",
    "bilibili2": "#00A1D6",
    "vimeo": "#1AB7EA",
    "tumblr": "#36465D",
}
PLATFORM_DEFAULT_COLOR = "#8E8E93"

COVER_WIDTH = 176
COVER_HEIGHT = 99


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.1f} GB"


class ResultCard(ctk.CTkFrame):
    """单个解析结果卡片：元信息 + 封面 + 媒体勾选 + 下载进度。"""

    def __init__(self, master, result: ParseResult, on_download):
        super().__init__(master, corner_radius=10, fg_color=("gray92", "gray17"))
        self.result = result
        self._on_download = on_download
        self._checkboxes: list[tuple[MediaItem, ctk.CTkCheckBox]] = []
        self._cover_image: Optional[ctk.CTkImage] = None

        self.grid_columnconfigure(1, weight=1)

        platform_color = PLATFORM_COLORS.get(result.platform, PLATFORM_DEFAULT_COLOR)
        badge = ctk.CTkLabel(
            self, text=f" {result.platform} ", font=font(12, "bold"),
            fg_color=platform_color, corner_radius=6, text_color="black",
        )
        badge.grid(row=0, column=0, sticky="nw", padx=(12, 8), pady=(12, 0))

        title_label = ctk.CTkLabel(
            self, text=result.title or "(无标题)", font=font(15, "bold"),
            wraplength=560, anchor="w", justify="left",
        )
        title_label.grid(row=0, column=1, sticky="nw", padx=(0, 8), pady=(10, 0))

        self._cover_label = ctk.CTkLabel(self, text="加载封面…", width=COVER_WIDTH,
                                         height=COVER_HEIGHT, fg_color=("gray80", "gray25"))
        self._cover_label.grid(row=0, column=3, rowspan=2, sticky="ne",
                               padx=(8, 12), pady=(10, 0))
        if not result.cover_urls:
            self._cover_label.configure(
                text=result.platform, fg_color=platform_color,
                text_color="black", font=font(13, "bold"))

        meta_parts = [result.author, result.duration_text, result.timestamp]
        meta_line = " · ".join(p for p in meta_parts if p)
        meta = ctk.CTkLabel(self, text=meta_line or " ", font=font(12),
                            text_color=("gray40", "gray65"), anchor="w")
        meta.grid(row=1, column=1, sticky="nw", padx=(0, 8))

        if result.is_error:
            error = ctk.CTkLabel(
                self, text=f"解析失败：{result.error}", font=font(12),
                text_color="#FF5252", anchor="w", wraplength=560, justify="left",
            )
            error.grid(row=2, column=1, columnspan=2, sticky="nw", padx=(0, 8))
            self._cover_label.configure(text="")
            self._cover_label.grid_remove()
        elif not result.has_media:
            hint = ctk.CTkLabel(
                self, text="未解析到可用媒体直链", font=font(12),
                text_color=("gray40", "gray60"), anchor="w",
            )
            hint.grid(row=2, column=1, columnspan=2, sticky="nw", padx=(0, 8))

        # 媒体勾选行（每行最多 4 个，自动换行）
        checkbox_frame = ctk.CTkFrame(self, fg_color="transparent")
        checkbox_frame.grid(row=3, column=1, columnspan=2, sticky="w",
                            padx=(0, 8), pady=(6, 0))
        for col, item in enumerate(result.items):
            row, inner_col = divmod(col, 4)
            box = ctk.CTkCheckBox(checkbox_frame,
                                  text=item.name or f"{item.kind} {item.index}",
                                  font=font(13),
                                  checkbox_width=20, checkbox_height=20)
            box.select()
            box.grid(row=row, column=inner_col, sticky="w",
                     padx=(0, 12), pady=(2, 0))
            self._checkboxes.append((item, box))

        # 底部：下载按钮 + 进度条 + 状态
        self._download_button = ctk.CTkButton(
            self, text="下载全部", width=90, height=28,
            command=lambda: self._on_download(self),
        )
        self._download_button.grid(row=4, column=1, sticky="w", padx=(0, 8), pady=(8, 10))

        self._progress = ctk.CTkProgressBar(self, height=8)
        self._progress.set(0)
        self._progress.grid(row=4, column=2, sticky="ew", padx=(0, 8), pady=(14, 10))
        self.grid_columnconfigure(2, weight=1)

        self._status_label = ctk.CTkLabel(self, text="", font=font(11),
                                          text_color=("gray40", "gray60"), anchor="w")
        self._status_label.grid(row=5, column=1, columnspan=3, sticky="w",
                                padx=(12, 8), pady=(0, 8))

    # ── 对外接口 ─────────────────────────────

    def selected_items(self) -> list[MediaItem]:
        return [item for item, box in self._checkboxes if box.get()]

    def set_cover(self, image: Optional[ctk.CTkImage]) -> None:
        self._cover_image = image
        if image is None:
            self._cover_label.configure(text="无封面", image=None)
        else:
            self._cover_label.configure(text="", image=image)

    def set_downloading(self, downloading: bool) -> None:
        self._download_button.configure(
            state="disabled" if downloading else "normal",
            text="下载中…" if downloading else "下载全部",
        )

    def set_progress(self, label: str, done: int, total: Optional[int]) -> None:
        if total:
            self._progress.set(min(1.0, done / total))
            self._status_label.configure(
                text=f"{label}  {_format_bytes(done)} / {_format_bytes(total)}")
        else:
            self._status_label.configure(text=f"{label}  {_format_bytes(done)}")

    def finish_download(self, summary: DownloadSummary) -> None:
        self.set_downloading(False)
        self._progress.set(1.0)
        text = f"已下载 {summary.ok_count} 个文件"
        if summary.errors:
            text += "，" + "；".join(summary.errors[:2])
        self._status_label.configure(text=text)


class MediaToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("视频/媒体解析下载工具")
        self.geometry("1100x760")
        self.minsize(900, 600)

        self.config = AppConfig.load()
        self.engine = self._build_engine()
        self._downloader: Optional[MediaDownloader] = None
        self._out_dir = Path.cwd() / "downloads"
        self._cards: list[ResultCard] = []
        self._busy = False
        self._active_control: Optional[DownloadControl] = None
        self._ui_queue: queue.Queue = queue.Queue()
        self.after(50, self._drain_ui_queue)

        self._build_layout()
        if self.config.proxy_url:
            self.status_label.configure(text=f"代理已启用：{self.config.proxy_url}")

    # ── 布局 ─────────────────────────────────

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        sidebar = ctk.CTkFrame(self, width=430, corner_radius=10)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(12, 8), pady=12)
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sidebar, text="粘贴链接（支持多行，自动识别平台）",
                     font=font(13, "bold"),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))

        self.input_box = ctk.CTkTextbox(sidebar, height=150, wrap="word",
                                        font=font(13))
        self.input_box.grid(row=1, column=0, sticky="ew", padx=14)

        self.parse_button = ctk.CTkButton(sidebar, text="解析链接", height=36,
                                          command=self._on_parse)
        self.parse_button.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 4))
        btn_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=1)
        self.clear_button = ctk.CTkButton(btn_row, text="清空", height=28,
                                          fg_color="transparent", border_width=1,
                                          command=self._on_clear)
        self.clear_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.log_button = ctk.CTkButton(btn_row, text="日志", height=28,
                                        fg_color="transparent", border_width=1,
                                        command=self._open_logs_folder)
        self.log_button.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        self.settings_button = ctk.CTkButton(btn_row, text="设置", height=28,
                                             fg_color="transparent", border_width=1,
                                             command=self._open_settings)
        self.settings_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        ctk.CTkLabel(sidebar, text="输出目录", font=font(13, "bold"),
                     anchor="w").grid(row=4, column=0, sticky="w", padx=14, pady=(6, 4))

        out_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        out_row.grid(row=5, column=0, sticky="ew", padx=14)
        out_row.grid_columnconfigure(0, weight=1)
        self.out_entry = ctk.CTkEntry(out_row, font=font(12))
        self.out_entry.insert(0, str(self._out_dir))
        self.out_entry.grid(row=0, column=0, sticky="ew")
        self.out_entry.bind("<Return>", lambda _e: self._on_out_dir_changed())
        ctk.CTkButton(out_row, text="浏览", width=60, height=28,
                      command=self._on_browse_dir).grid(row=0, column=1, padx=(6, 0))

        self.download_selected_button = ctk.CTkButton(
            sidebar, text="下载所选（全部卡片勾选项）", height=34,
            command=self._on_download_selected)
        self.download_selected_button.grid(row=6, column=0, sticky="ew",
                                           padx=14, pady=(12, 4))

        # 下载控制：暂停/继续 + 取消（下载期间可用）
        ctrl_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        ctrl_row.grid(row=7, column=0, sticky="ew", padx=14)
        ctrl_row.grid_columnconfigure(0, weight=1)
        ctrl_row.grid_columnconfigure(1, weight=1)
        self.pause_button = ctk.CTkButton(ctrl_row, text="暂停", height=28,
                                          state="disabled",
                                          command=self._on_pause_toggle)
        self.pause_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.cancel_button = ctk.CTkButton(ctrl_row, text="取消下载", height=28,
                                           fg_color="#B03030", hover_color="#D04040",
                                           state="disabled",
                                           command=self._on_cancel_download)
        self.cancel_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.status_label = ctk.CTkLabel(sidebar, text="就绪", font=font(12),
                                         text_color=("gray40", "gray60"),
                                         anchor="w", wraplength=400, justify="left")
        self.status_label.grid(row=8, column=0, sticky="w", padx=14, pady=(8, 14))

        self.results_frame = ctk.CTkScrollableFrame(self, corner_radius=10,
                                                    fg_color="transparent")
        self.results_frame.grid(row=0, column=1, rowspan=2, sticky="nsew",
                                padx=(0, 12), pady=12)
        self.results_frame.grid_columnconfigure(0, weight=1)

    # ── 线程安全 UI 更新 ────────────────────────

    def _ui(self, func) -> None:
        """从工作线程投递 UI 更新到主线程队列。"""
        self._ui_queue.put(func)

    def _drain_ui_queue(self) -> None:
        """主线程轮询执行工作线程投递的 UI 更新。"""
        try:
            while True:
                func = self._ui_queue.get_nowait()
                try:
                    func()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.after(50, self._drain_ui_queue)

    # ── 解析流程 ─────────────────────────────

    def _set_busy(self, busy: bool, text: Optional[str] = None) -> None:
        self._busy = busy
        self.parse_button.configure(state="disabled" if busy else "normal",
                                    text="解析中…" if busy else "解析链接")
        if text is not None:
            self.status_label.configure(text=text)

    def _on_parse(self) -> None:
        if self._busy:
            return
        text = self.input_box.get("1.0", "end").strip()
        if not text:
            self.status_label.configure(text="请先粘贴链接")
            return
        logger.info("开始解析（文本 %d 字符）", len(text))
        self._set_busy(True, "正在解析…")
        threading.Thread(target=self._parse_worker, args=(text,), daemon=True).start()

    def _parse_worker(self, text: str) -> None:
        try:
            results = self.engine.parse_text_sync(text)
        except Exception as exc:  # noqa: BLE001
            self._ui(lambda: self._set_busy(False, f"解析出错：{exc}"))
            return
        self._ui(lambda: self._render_results(results))

    def _render_results(self, results: list[ParseResult]) -> None:
        self._clear_cards()
        if not results:
            logger.info("未识别到可解析的链接")
            self._set_busy(False, "未识别到可解析的链接")
            return
        for result in results:
            card = ResultCard(self.results_frame, result, self._on_card_download)
            card.grid(row=len(self._cards), column=0, sticky="ew", pady=(0, 10))
            self._cards.append(card)
            if result.cover_urls:
                threading.Thread(target=self._cover_worker,
                                 args=(card, result), daemon=True).start()
        logger.info("解析完成，共 %d 条", len(results))
        self._set_busy(False, f"解析完成，共 {len(results)} 条")

    def _clear_cards(self) -> None:
        for card in self._cards:
            card.destroy()
        self._cards = []

    def _on_clear(self) -> None:
        self.input_box.delete("1.0", "end")
        self._clear_cards()
        self.status_label.configure(text="已清空")

    # ── 设置 ─────────────────────────────────────

    def _build_engine(self) -> ParseEngine:
        return ParseEngine(quality=self.config.quality,
                           proxy=self.config.proxy_url,
                           ydl_cookies_from_browser=self.config.ydl_cookies_from_browser,
                           ydl_cookies_file=self.config.ydl_cookies_file)

    def _open_settings(self) -> None:
        SettingsDialog(self, self.config, lambda: self.engine,
                       on_save=self._apply_settings, ui_post=self._ui)

    def _open_logs_folder(self) -> None:
        """打开日志文件夹（程序目录下的 logs）。"""
        from app.logging_setup import get_log_dir
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(log_dir))  # Windows 资源管理器
        except Exception as exc:  # noqa: BLE001
            logger.warning("打开日志文件夹失败: %s", exc)
            self.status_label.configure(text=f"无法打开日志文件夹：{exc}")

    def _apply_settings(self, config: AppConfig) -> None:
        self.config = config
        config.save()
        self.engine = self._build_engine()
        self._downloader = None  # 下次下载时按新代理重建
        notes = []
        if config.proxy_url:
            notes.append(f"代理：{config.proxy_url}")
        if config.quality != "auto":
            notes.append(f"清晰度：{config.quality}")
        note = f"（{'，'.join(notes)}）" if notes else ""
        logger.info("设置已保存（代理=%s，清晰度=%s）", config.proxy_url or "-", config.quality)
        self.status_label.configure(text=f"设置已保存{note}")

    def _cover_worker(self, card: ResultCard, result: ParseResult) -> None:
        try:
            image = self._fetch_cover(result.cover_urls[0])
        except Exception:  # noqa: BLE001
            image = None
        self._ui(lambda: card.set_cover(image))

    def _fetch_cover(self, url: str):
        import io
        import aiohttp
        from PIL import Image

        async def _get() -> bytes:
            session_kwargs: dict = {"headers": {"User-Agent": DEFAULT_UA}}
            if self.config.proxy_url:
                session_kwargs["proxy"] = self.config.proxy_url
            async with aiohttp.ClientSession(**session_kwargs) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    resp.raise_for_status()
                    return await resp.read()

        data = asyncio.run(_get())
        img = Image.open(io.BytesIO(data))
        img.thumbnail((COVER_WIDTH, COVER_HEIGHT))
        return ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))

    # ── 下载流程 ─────────────────────────────

    def _ensure_downloader(self, out_dir: Path) -> MediaDownloader:
        if self._downloader is None or self._downloader.out_dir != out_dir:
            self._downloader = MediaDownloader(
                out_dir, proxy=self.config.proxy_url,
                ydl_cookies_from_browser=self.config.ydl_cookies_from_browser,
                ydl_cookies_file=self.config.ydl_cookies_file,
            )
            self._out_dir = out_dir
        return self._downloader

    def _on_out_dir_changed(self) -> None:
        self._downloader = None
        self.status_label.configure(text=f"输出目录：{self.out_entry.get().strip()}")

    def _on_browse_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(self._out_dir))
        if chosen:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, chosen)
            self._on_out_dir_changed()

    def _on_card_download(self, card: ResultCard) -> None:
        items = card.selected_items()
        if not items:
            self.status_label.configure(text="请先勾选要下载的媒体")
            return
        self._start_download_jobs([(card, card.result, items)])

    def _on_download_selected(self) -> None:
        jobs = [(card, card.result, card.selected_items())
                for card in self._cards if card.selected_items()]
        if not jobs:
            self.status_label.configure(text="没有勾选任何媒体")
            return
        self._start_download_jobs(jobs)

    # ── 下载控制（暂停/继续/取消）───────────────────

    def _set_control_buttons(self, active: bool, paused: bool = False) -> None:
        self.pause_button.configure(
            state="normal" if active else "disabled",
            text="继续" if paused else "暂停",
        )
        self.cancel_button.configure(state="normal" if active else "disabled")

    def _on_pause_toggle(self) -> None:
        control = self._active_control
        if control is None:
            return
        if control.is_paused:
            control.resume()
            self.pause_button.configure(text="暂停")
            self.status_label.configure(text="继续下载…")
        else:
            control.pause()
            self.pause_button.configure(text="继续")
            self.status_label.configure(text="已暂停")

    def _on_cancel_download(self) -> None:
        control = self._active_control
        if control is None:
            return
        control.cancel()
        self.cancel_button.configure(state="disabled")
        self.status_label.configure(text="正在取消…")

    # ── 下载执行 ────────────────────────────────

    def _start_download_jobs(self, jobs) -> None:
        if self._busy:
            self.status_label.configure(text="正在处理中，请稍候")
            return
        for card, _result, _items in jobs:
            card.set_downloading(True)
        total_items = sum(len(items) for _, _, items in jobs)
        logger.info("开始下载 %d 个媒体项（输出目录：%s）", total_items, out_dir)
        self._set_busy(True, f"开始下载 {total_items} 个媒体…")
        out_dir = Path(self.out_entry.get().strip() or str(self._out_dir))
        control = DownloadControl()
        self._active_control = control
        self._set_control_buttons(True)
        threading.Thread(target=self._download_worker, args=(jobs, out_dir, control),
                         daemon=True).start()

    def _download_worker(self, jobs, out_dir: Path, control: DownloadControl) -> None:
        downloader = self._ensure_downloader(out_dir)
        done_cards: set = set()
        cancelled = False
        try:
            for card, result, items in jobs:
                sub_result = replace(result, items=items)

                def progress(label, done, total, c=card):
                    self._ui(lambda l=label, d=done, t=total:
                               c.set_progress(l, d, t))

                summary = downloader.download_result_sync(sub_result, progress, control)
                done_cards.add(card)
                self._ui(lambda s=summary, c=card: c.finish_download(s))
            self._ui(lambda: self._set_busy(False, "下载完成"))
        except TaskCancelled:
            cancelled = True
            self._ui(lambda: self._set_busy(False, "下载已取消"))
        except Exception as exc:  # noqa: BLE001
            self._ui(lambda: self._set_busy(False, f"下载出错：{exc}"))
        finally:
            for card, _result, _items in jobs:
                if card not in done_cards:
                    # 取消/出错时把未完成卡片的按钮恢复可用
                    self._ui(lambda c=card: c.set_downloading(False))
            if cancelled:
                # 中断下载管理器内可能仍在运行的任务（管理器保持可复用）
                downloader.cancel_active()
            self._ui(lambda: self._set_control_buttons(False))
            self._active_control = None
            downloader.shutdown()
