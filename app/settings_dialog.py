"""设置窗口：代理 + B 站 Cookie + 清晰度（附 Cookie 获取方法说明）。"""
from __future__ import annotations

import asyncio
import threading

import customtkinter as ctk

from app.config import AppConfig, DEFAULT_QUALITY
from app.engine import DEFAULT_UA, ParseEngine
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

COOKIE_HELP = """在哪里找 Cookie（以 B 站为例）

方法一：开发者工具（推荐）
1. 用 Chrome / Edge 打开并登录 www.bilibili.com
2. 按 F12 打开开发者工具，切到「网络 Network」标签
3. 按 F5 刷新页面
4. 在请求列表里点击任意一条请求（如 api 接口）
5. 右侧「请求头 Request Headers」里找到以 Cookie 开头的一行，整行复制，
   粘贴到设置窗口的输入框即可

方法二：「应用 Application」面板
1. F12 →「应用 Application」→ 左侧「Cookie」
2. 展开 bilibili.com 域名，双击每个条目复制，拼成 名=值; 名=值 格式

小提示
- 只需关键字段 SESSDATA=...; bili_jct=... 即可解锁高清晰度
- Cookie 相当于你的登录凭证，请勿发给任何人
- 退出登录 / 修改密码后 Cookie 会失效，需重新获取
- 本工具仅在本机使用 Cookie 请求对应平台接口
"""


class SettingsDialog(ctk.CTkToplevel):
    """设置窗口：代理 + B 站 Cookie + 清晰度（附 Cookie 获取方法说明）。"""

    def __init__(self, master, config: AppConfig, engine_factory,
                 on_save, ui_post):
        super().__init__(master)
        self._on_save = on_save
        self._engine_factory = engine_factory  # 取当前引擎，保存重建后仍拿到新实例
        self._ui_post = ui_post  # 工作线程投递 UI 更新到主线程的通道

        self.title("设置")
        self.geometry("580x940")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.update_idletasks()
        max_h = self.winfo_screenheight() - 80
        if self.winfo_height() > max_h:
            self.geometry(f"580x{max_h}")
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.grid_columnconfigure(0, weight=1)

        # ── 代理 ─────────────────────────────────────
        proxy_head = ctk.CTkFrame(self, fg_color="transparent")
        proxy_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        proxy_head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(proxy_head, text="代理", font=font(14, "bold"),
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
            self, text="代理软件（Clash / v2ray 等）的本地地址，解析与下载全程生效",
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

        # ── Cookie ───────────────────────────────────
        ctk.CTkLabel(self, text="B 站 Cookie（可选，解锁高清晰度）",
                     font=font(14, "bold"),
                     anchor="w").grid(row=4, column=0, sticky="w",
                                      padx=18, pady=(18, 4))
        self.cookie_entry = ctk.CTkEntry(self, font=font(13))
        self.cookie_entry.grid(row=5, column=0, sticky="ew", padx=18, pady=(4, 4))
        if config.bilibili_cookie:
            self.cookie_entry.insert(0, config.bilibili_cookie)

        cookie_row = ctk.CTkFrame(self, fg_color="transparent")
        cookie_row.grid(row=6, column=0, sticky="ew", padx=18, pady=(2, 0))
        cookie_row.grid_columnconfigure(0, weight=1)
        self.show_cookie_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(cookie_row, text="显示明文", width=90,
                        command=self._toggle_cookie_show,
                        font=font(12)).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(cookie_row, text="如何获取 Cookie？", width=132, height=26,
                      font=font(12),
                      fg_color="transparent", border_width=1,
                      command=self._show_cookie_help).grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            self, text="只需填写 SESSDATA=...; bili_jct=... 即可解锁高清，获取方法见上方按钮",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w").grid(row=7, column=0, sticky="w", padx=18, pady=(4, 0))
        self._toggle_cookie_show()

        # ── 清晰度 ────────────────────────────────────
        ctk.CTkLabel(self, text="清晰度（B 站 / 可自选清晰度的平台）",
                     font=font(14, "bold"),
                     anchor="w").grid(row=8, column=0, sticky="w",
                                      padx=18, pady=(18, 4))
        quality_row = ctk.CTkFrame(self, fg_color="transparent")
        quality_row.grid(row=9, column=0, sticky="ew", padx=18, pady=(4, 0))
        quality_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(quality_row, text="最高清晰度", font=font(13),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 10))
        quality_key = config.quality if config.quality in QUALITY_LABELS else DEFAULT_QUALITY
        self.quality_menu = ctk.CTkOptionMenu(
            quality_row, values=list(QUALITY_LABELS.values()), font=font(12),
            width=210, height=28, anchor="w")
        self.quality_menu.set(QUALITY_LABELS[quality_key])
        self.quality_menu.grid(row=0, column=1, sticky="e")
        ctk.CTkLabel(
            self, text="B 站解析按此档位限制所选画质；YouTube 等 yt-dlp 平台只展示不高于该清晰度的档位",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w").grid(row=10, column=0, sticky="w", padx=18, pady=(4, 0))

        # ── yt-dlp Cookie（Instagram 等需要登录的平台）──────────
        ctk.CTkLabel(self, text="Instagram 等平台登录（yt-dlp Cookie，可选）",
                     font=font(14, "bold"),
                     anchor="w").grid(row=11, column=0, sticky="w",
                                      padx=18, pady=(18, 4))
        ydl_row = ctk.CTkFrame(self, fg_color="transparent")
        ydl_row.grid(row=12, column=0, sticky="ew", padx=18, pady=(4, 0))
        ydl_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(ydl_row, text="读取浏览器 Cookie", font=font(13),
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
        cookies_file_row.grid(row=13, column=0, sticky="ew", padx=18, pady=(4, 0))
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
            self, text="读取浏览器已登录的 Cookie，或选择 cookies.txt（Netscape 格式）；"
                       "适用于 Instagram 等需要登录的平台，解析与下载全程生效",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w", wraplength=520, justify="left").grid(row=14, column=0,
                                                             sticky="w",
                                                             padx=18, pady=(4, 0))

        # ── B 站扫码登录 ─────────────────────────────
        ctk.CTkLabel(self, text="B 站扫码登录", font=font(14, "bold"),
                     anchor="w").grid(row=15, column=0, sticky="w",
                                      padx=18, pady=(18, 4))
        login_row = ctk.CTkFrame(self, fg_color="transparent")
        login_row.grid(row=16, column=0, sticky="ew", padx=18, pady=(4, 0))
        login_row.grid_columnconfigure(1, weight=1)
        self.login_button = ctk.CTkButton(login_row, text="扫码登录", width=96,
                                          height=26, command=self._on_qr_login)
        self.login_button.grid(row=0, column=0, sticky="w")
        self.login_status = ctk.CTkLabel(login_row, text="", font=font(12),
                                         anchor="w", justify="left")
        self.login_status.grid(row=0, column=1, sticky="w", padx=(10, 0))
        ctk.CTkLabel(
            self, text="扫码登录后凭据自动保存到本地，下次启动免登录，比手动复制 Cookie 更稳定",
            font=font(11), text_color=("gray40", "gray60"),
            anchor="w").grid(row=17, column=0, sticky="w", padx=18, pady=(4, 0))
        self._refresh_login_status()

        # ── 保存 / 取消 ──────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=18, column=0, sticky="ew", padx=18, pady=(22, 18))
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

    # ── Cookie ────────────────────────────────────

    def _toggle_cookie_show(self) -> None:
        self.cookie_entry.configure(show="" if self.show_cookie_var.get() else "●")

    def _show_cookie_help(self) -> None:
        from tkinter import messagebox
        messagebox.showinfo("如何获取 Cookie", COOKIE_HELP, parent=self)

    def _on_browse_cookies(self) -> None:
        from tkinter import filedialog
        chosen = filedialog.askopenfilename(
            title="选择 cookies.txt", parent=self,
            filetypes=[("cookies 文件", "*.txt"), ("所有文件", "*.*")])
        if chosen:
            self.ydl_cookies_entry.delete(0, "end")
            self.ydl_cookies_entry.insert(0, chosen)

    # ── 保存 ──────────────────────────────────────

    # ── 扫码登录 ──────────────────────────────────

    def _refresh_login_status(self) -> None:
        self.login_status.configure(
            text=self._engine_factory().bilibili_auth_status())

    def _on_qr_login(self) -> None:
        QrLoginDialog(self, self._engine_factory(), ui_post=self._ui_post,
                      on_success=self._refresh_login_status)

    def _on_save_clicked(self) -> None:
        selected = self.quality_menu.get()
        quality_key = next(
            (key for key, label in QUALITY_LABELS.items() if label == selected),
            DEFAULT_QUALITY,
        )
        browser_map = {"Edge": "edge", "Chrome": "chrome", "Firefox": "firefox"}
        config = AppConfig(
            proxy_url=self.proxy_entry.get().strip() if self.proxy_switch.get() else "",
            bilibili_cookie=self.cookie_entry.get().strip(),
            quality=quality_key,
            ydl_cookies_from_browser=browser_map.get(self.ydl_browser_menu.get(), ""),
            ydl_cookies_file=self.ydl_cookies_entry.get().strip(),
        )
        self.destroy()
        self._on_save(config)


class QrLoginDialog(ctk.CTkToplevel):
    """B 站扫码登录窗口：展示二维码并轮询登录结果。"""

    QR_SIZE = 220

    def __init__(self, master, engine: ParseEngine, ui_post, on_success):
        super().__init__(master)
        self._engine = engine
        self._ui_post = ui_post
        self._on_success = on_success
        self._token = 0  # 重新生成时递增，作废旧线程的结果

        self.title("B 站扫码登录")
        self.geometry("360x440")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.grid_columnconfigure(0, weight=1)
        self.qr_label = ctk.CTkLabel(self, text="正在获取二维码…", width=self.QR_SIZE,
                                     height=self.QR_SIZE, corner_radius=8,
                                     fg_color=("gray85", "gray20"))
        self.qr_label.grid(row=0, column=0, padx=24, pady=(20, 8))
        self.status_label = ctk.CTkLabel(self, text="", font=font(12),
                                         wraplength=310, justify="left")
        self.status_label.grid(row=1, column=0, padx=24)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, pady=(14, 18))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(btn_row, text="重新生成", width=110, height=30,
                      fg_color="transparent", border_width=1,
                      command=self._on_regenerate).grid(row=0, column=0, padx=(0, 6))
        ctk.CTkButton(btn_row, text="关闭", width=110, height=30,
                      command=self.destroy).grid(row=0, column=1, padx=(6, 0))
        self._start_login()

    def _start_login(self) -> None:
        self._token += 1
        self.status_label.configure(text="请用 B 站手机 App 扫码…")
        threading.Thread(target=self._login_worker, args=(self._token,),
                         daemon=True).start()

    def _on_regenerate(self) -> None:
        self.qr_label.configure(text="正在获取二维码…", image=None)
        self._start_login()

    def _login_worker(self, token: int) -> None:
        import aiohttp
        import io
        from PIL import Image

        def _stale() -> bool:
            return token != self._token

        try:
            payload = self._engine.bilibili_qr_payload()
            if _stale():
                return
            qrcode_key = payload["qrcode_key"]

            async def _fetch() -> bytes:
                timeout = aiohttp.ClientTimeout(total=15)
                async with aiohttp.ClientSession(
                        headers={"User-Agent": DEFAULT_UA},
                        timeout=timeout) as session:
                    async with session.get(payload["qr_code_url"]) as resp:
                        resp.raise_for_status()
                        return await resp.read()

            data = asyncio.run(_fetch())
            if _stale():
                return
            img = Image.open(io.BytesIO(data))
            img.thumbnail((self.QR_SIZE, self.QR_SIZE))
            qr_image = ctk.CTkImage(light_image=img, dark_image=img,
                                    size=(img.width, img.height))
            self._ui_post(lambda: self.qr_label.configure(text="", image=qr_image))
            self._ui_post(lambda: self.status_label.configure(
                text="请用 B 站手机 App「扫一扫」登录\n等待扫码…（2 分钟有效）"))

            result = self._engine.bilibili_poll_login(qrcode_key, 120)
            if _stale():
                return
            status = result.get("status")
            if status == "success":
                self._ui_post(lambda: self.status_label.configure(
                    text="登录成功！凭据已保存"))
                self._ui_post(self._on_success)
                self._ui_post(lambda: (self.after(1200, self.destroy)
                                       if self.winfo_exists() else None))
            elif status == "expired":
                self._ui_post(lambda: self.status_label.configure(
                    text="二维码已过期，请点击「重新生成」"))
            else:
                self._ui_post(lambda: self.status_label.configure(
                    text="登录超时，请点击「重新生成」"))
        except Exception as exc:  # noqa: BLE001
            if not _stale():
                self._ui_post(lambda: self.status_label.configure(
                    text=f"获取二维码失败：{exc}"))
