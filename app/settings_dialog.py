"""设置窗口：代理 + 清晰度 + yt-dlp Cookie。"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import customtkinter as ctk

from app.config import AppConfig, DEFAULT_QUALITY
from app.theme import font

# 清晰度档位的展示名（QUALITY_PRESETS 键 → 下拉框文案）
QUALITY_LABELS: dict[str, str] = {
    "auto": "自动（最高可用）",
    "4k": "4K（2160P）",
    "1080p": "1080P",
    "720p": "720P",
    "480p": "480P",
    "360p": "360P",
}


class SettingsDialog(ctk.CTkToplevel):
    """设置窗口：代理 + 清晰度 + yt-dlp Cookie。"""

    def __init__(self, master, config: AppConfig, engine_factory,
                 on_save, ui_post):
        super().__init__(master)
        self._on_save = on_save
        self._engine_factory = engine_factory
        self._ui_post = ui_post

        self.title("设置")
        self.geometry("540x560")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.update_idletasks()
        
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.grid_columnconfigure(0, weight=1)

        # ── 代理 ─────────────────────────────────────
        proxy_head = ctk.CTkFrame(self, fg_color="transparent")
        proxy_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        proxy_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(proxy_head, text="代理配置", font=font(14, "bold"),
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.proxy_switch = ctk.CTkSwitch(proxy_head, text="启用",
                                          command=self._toggle_proxy_entry)
        self.proxy_switch.grid(row=0, column=1, sticky="e")

        self.proxy_entry = ctk.CTkEntry(
            self, placeholder_text="http://127.0.0.1:7890",
            font=font(13))
        self.proxy_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(4, 4))
        if config.proxy_url:
            self.proxy_entry.insert(0, config.proxy_url)
            self.proxy_switch.select()

        ctk.CTkLabel(
            self, text="本地代理客户端地址，解析与下载全程生效（如 Clash / v2ray）",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w").grid(row=2, column=0, sticky="w", padx=18)

        test_row = ctk.CTkFrame(self, fg_color="transparent")
        test_row.grid(row=3, column=0, sticky="ew", padx=18, pady=(6, 0))
        test_row.grid_columnconfigure(1, weight=1)
        self.test_button = ctk.CTkButton(test_row, text="测试代理", width=96,
                                         height=26, command=self._on_test_proxy)
        self.test_button.grid(row=0, column=0, sticky="w")
        self.test_result = ctk.CTkLabel(
            test_row, text="", font=font(12),
            text_color=("gray40", "gray60"), anchor="w", justify="left")
        self.test_result.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self._toggle_proxy_entry()

        # ── 清晰度 ────────────────────────────────────
        ctk.CTkLabel(self, text="清晰度设置（对可自选清晰度的平台生效）",
                     font=font(14, "bold"),
                     anchor="w").grid(row=4, column=0, sticky="w",
                                      padx=18, pady=(18, 4))
        quality_row = ctk.CTkFrame(self, fg_color="transparent")
        quality_row.grid(row=5, column=0, sticky="ew", padx=18, pady=(4, 0))
        quality_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(quality_row, text="最高清晰度上限", font=font(13),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 10))
        quality_key = config.quality if config.quality in QUALITY_LABELS else DEFAULT_QUALITY
        self.quality_menu = ctk.CTkOptionMenu(
            quality_row, values=list(QUALITY_LABELS.values()), font=font(12),
            width=210, height=28, anchor="w")
        self.quality_menu.set(QUALITY_LABELS[quality_key])
        self.quality_menu.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            self, text="yt-dlp 将只展示和下载不高于此清晰度的视频格式，以节省带宽与存储",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w").grid(row=6, column=0, sticky="w", padx=18, pady=(4, 0))

        # ── yt-dlp Cookie（部分需要登录的平台）──────────
        ctk.CTkLabel(self, text="平台登录 Cookie（可选，用于解决需要登录的平台）",
                     font=font(14, "bold"),
                     anchor="w").grid(row=7, column=0, sticky="w",
                                      padx=18, pady=(18, 4))
        ydl_row = ctk.CTkFrame(self, fg_color="transparent")
        ydl_row.grid(row=8, column=0, sticky="ew", padx=18, pady=(4, 0))
        ydl_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ydl_row, text="读取浏览器已登录的 Cookie", font=font(13),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.ydl_browser_menu = ctk.CTkOptionMenu(
            ydl_row, values=["禁用", "Edge", "Chrome", "Firefox"], font=font(12),
            width=150, height=28, anchor="w")
        browser_key = config.ydl_cookies_from_browser or ""
        self.ydl_browser_menu.set(
            {"edge": "Edge", "chrome": "Chrome", "firefox": "Firefox"}.get(
                browser_key, "禁用"))
        self.ydl_browser_menu.grid(row=0, column=1, sticky="e")

        cookies_file_row = ctk.CTkFrame(self, fg_color="transparent")
        cookies_file_row.grid(row=9, column=0, sticky="ew", padx=18, pady=(4, 0))
        cookies_file_row.grid_columnconfigure(0, weight=1)
        self.ydl_cookies_entry = ctk.CTkEntry(cookies_file_row, font=font(12))
        if config.ydl_cookies_file:
            self.ydl_cookies_entry.insert(0, config.ydl_cookies_file)
        self.ydl_cookies_entry.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(cookies_file_row, text="浏览…", width=60, height=26,
                      font=font(12),
                      command=self._on_browse_cookies).grid(row=0, column=1,
                                                            padx=(6, 0))
        ctk.CTkLabel(
            self, text="可读取浏览器（Chrome/Edge/Firefox）的已登录 Cookie 状态，"
                       "或选择 Netscape 格式的 cookies.txt 文件。适用于 B站高清、YouTube、Instagram等需要登录态的平台。",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w", wraplength=500, justify="left").grid(row=10, column=0,
                                                             sticky="w",
                                                             padx=18, pady=(4, 0))

        # ── 保存 / 取消 ──────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=11, column=0, sticky="ew", padx=18, pady=(22, 18))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(bottom, text="取消", height=32,
                      fg_color="transparent", border_width=1,
                      command=self.destroy).grid(row=0, column=0, sticky="ew",
                                                 padx=(0, 6))
        ctk.CTkButton(bottom, text="保存", height=32,
                      command=self._on_save_clicked).grid(row=0, column=1,
                                                          sticky="ew", padx=(6, 0))

    # ── 代理 ─────────────────────────────────────

    def _toggle_proxy_entry(self) -> None:
        enabled = bool(self.proxy_switch.get())
        self.proxy_entry.configure(state="normal" if enabled else "disabled")
        self.test_button.configure(state="normal" if enabled else "disabled")
        if not enabled:
            self.test_result.configure(text="")

    def _on_test_proxy(self) -> None:
        url = self.proxy_entry.get().strip()
        if not url:
            self.test_result.configure(text="请先填写代理地址")
            return
        self.test_button.configure(state="disabled")
        self.test_result.configure(text="测试中…")
        threading.Thread(target=self._test_proxy_worker, args=(url,),
                         daemon=True).start()

    def _test_proxy_worker(self, url: str) -> None:
        import aiohttp

        async def _check() -> str:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(proxy=url, timeout=timeout) as session:
                async with session.get("https://www.gstatic.com/generate_204") as resp:
                    status = resp.status
            return "代理可用（HTTP 204）" if status == 204 else f"代理响应异常（HTTP {status}）"

        try:
            msg = asyncio.run(_check())
        except Exception as exc:  # noqa: BLE001
            msg = f"代理不可用：{exc}"
        self._ui_post(lambda: self.test_result.configure(text=msg))
        self._ui_post(lambda: self.test_button.configure(state="normal"))

    def _on_browse_cookies(self) -> None:
        from tkinter import filedialog
        chosen = filedialog.askopenfilename(
            title="选择 cookies.txt", parent=self,
            filetypes=[("cookies 文件", "*.txt"), ("所有文件", "*.*")])
        if chosen:
            self.ydl_cookies_entry.delete(0, "end")
            self.ydl_cookies_entry.insert(0, chosen)

    # ── 保存 ──────────────────────────────────────

    def _on_save_clicked(self) -> None:
        selected = self.quality_menu.get()
        quality_key = next(
            (key for key, label in QUALITY_LABELS.items() if label == selected),
            DEFAULT_QUALITY,
        )
        browser_map = {"Edge": "edge", "Chrome": "chrome", "Firefox": "firefox"}
        config = AppConfig(
            proxy_url=self.proxy_entry.get().strip() if self.proxy_switch.get() else "",
            quality=quality_key,
            ydl_cookies_from_browser=browser_map.get(self.ydl_browser_menu.get(), ""),
            ydl_cookies_file=self.ydl_cookies_entry.get().strip(),
        )
        self.destroy()
        self._on_save(config)
