"""解析引擎：文本提链 → 路由 → 并发解析 → 归一化结果。

复用机器人（HIKARI_BOT_NEO）的 astrbot_plugin_media_parser 解析核心，
本文件只做薄封装，产出 GUI/CLI 共用的 ParseResult 数据类。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)

from parser_core.parser import ParserManager
from parser_core.parser.platform import (
    BilibiliParser,
    DouyinParser,
    KuaishouParser,
    TikTokParser,
    ToutiaoParser,
    TwitterParser,
    WeiboParser,
    XianyuParser,
    XiaoheiheParser,
    XiaohongshuParser,
)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# B 站扫码登录凭据文件（GUI 与 CLI 共享，放在程序当前目录，随工具一起移动）
DEFAULT_BILIBILI_CREDENTIAL_PATH = str(
    Path.cwd() / "bilibili_credentials.json"
)


@dataclass
class MediaItem:
    """单个媒体资源（视频/图片/音频），urls 为可用直链的回退列表。

    format_id 仅在 yt-dlp 兜底结果中使用，指示下载时传给 yt-dlp 的格式标识。
    """

    index: int
    kind: str  # "video" | "image" | "audio"
    urls: list[str] = field(default_factory=list)
    name: str = ""
    format_id: str = ""


@dataclass
class ParseResult:
    """单个链接的解析结果，GUI/CLI 共用的归一化视图。"""

    url: str
    platform: str
    parser_name: str
    title: str = ""
    author: str = ""
    desc: str = ""
    timestamp: str = ""
    duration_ms: int = 0
    cover_urls: list[str] = field(default_factory=list)
    items: list[MediaItem] = field(default_factory=list)
    video_headers: dict[str, str] = field(default_factory=dict)
    image_headers: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_error(self) -> bool:
        return bool(self.error)

    @property
    def has_media(self) -> bool:
        return any(item.urls for item in self.items)

    @property
    def duration_text(self) -> str:
        if self.duration_ms <= 0:
            return ""
        total_seconds = self.duration_ms // 1000
        minutes, seconds = divmod(total_seconds, 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "ParseResult":
        """把解析核心产出的元数据字典转成统一视图。"""
        error = raw.get("error")
        video_urls: list[list[str]] = raw.get("video_urls") or []
        image_urls: list[list[str]] = raw.get("image_urls") or []
        covers: list[list[str]] = (
            raw.get("video_cover_url_lists")
            or raw.get("video_cover_urls")
            or []
        )

        items: list[MediaItem] = []
        for index, urls in enumerate(video_urls, start=1):
            if urls:
                items.append(MediaItem(index=index, kind="video", urls=list(urls)))
        for index, urls in enumerate(image_urls, start=1):
            if urls:
                items.append(MediaItem(index=index, kind="image", urls=list(urls)))

        return cls(
            url=raw.get("source_url") or raw.get("url") or "",
            platform=raw.get("platform", ""),
            parser_name=raw.get("parser_name", ""),
            title=raw.get("title", "") or "",
            author=raw.get("author", "") or "",
            desc=raw.get("desc", "") or "",
            timestamp=raw.get("timestamp", "") or "",
            duration_ms=int(raw.get("timelength_ms") or 0),
            cover_urls=[u for chain in covers for u in (chain or [])],
            items=items,
            video_headers=raw.get("video_headers") or {},
            image_headers=raw.get("image_headers") or {},
            raw=raw,
            error=error,
        )


def build_parser_manager(
    *,
    bilibili_cookie: str = "",
    bilibili_credential_path: str = "",
    bilibili_quality: str = "auto",
    tiktok_use_proxy: bool = False,
    tiktok_proxy_url: str = "",
) -> ParserManager:
    """构建解析器管理器。

    Args:
        bilibili_cookie: 可选 B 站登录 Cookie（形如 "SESSDATA=...; bili_jct=..."），
            提供后可解锁更高清晰度；留空则匿名解析（低清晰度可用）。
        bilibili_quality: B 站清晰度档位（QUALITY_PRESETS 的键，如 "auto"/"1080p"），
            限制解析所选视频流的最高画质；默认 "auto" 为最高可用。
        tiktok_use_proxy: 是否通过代理访问 TikTok。
        tiktok_proxy_url: 代理地址，形如 "http://127.0.0.1:7890"。
    """
    from .config import migrate_legacy_config, quality_to_bilibili_qn

    # 首次运行时把旧位置（~/.video_downloader）的配置/凭据迁移到当前目录
    migrate_legacy_config()

    # 启用鉴权运行时的条件：手动配置了 Cookie，或本地存在扫码登录凭据文件。
    # 之后（同会话内）扫码登录成功时凭据会写入该实例，无需重建引擎即生效。
    runtime_enabled = bool(bilibili_cookie) or bool(
        bilibili_credential_path and Path(bilibili_credential_path).exists()
    )
    parsers = [
        BilibiliParser(
            cookie_runtime_enabled=runtime_enabled,
            configured_cookie=bilibili_cookie,
            credential_path=bilibili_credential_path,
            max_quality=quality_to_bilibili_qn(bilibili_quality),
        ),
        DouyinParser(),
        KuaishouParser(),
        TikTokParser(use_proxy=tiktok_use_proxy, proxy_url=tiktok_proxy_url),
        WeiboParser(),
        XiaohongshuParser(),
        XianyuParser(),
        ToutiaoParser(),
        XiaoheiheParser(),
        TwitterParser(),
    ]
    return ParserManager(parsers)


class ParseEngine:
    """解析引擎：对一段文本提取全部可解析链接并逐个解析。"""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        bilibili_cookie: str = "",
        bilibili_credential_path: str = DEFAULT_BILIBILI_CREDENTIAL_PATH,
        quality: str = "auto",
        proxy: str = "",
        tiktok_use_proxy: bool = False,
        tiktok_proxy_url: str = "",
        ydl_enabled: bool = True,
        ydl_proxy: str = "",
        ydl_cookies_from_browser: str = "",
        ydl_cookies_file: str = "",
    ):
        self.timeout = timeout
        self.proxy = proxy.strip()
        # 全局代理：同时作用于 parser_core 请求、TikTok 专用代理与 yt-dlp 兜底
        if self.proxy:
            tiktok_use_proxy = True
            tiktok_proxy_url = self.proxy
            ydl_proxy = self.proxy
        self.quality = (quality or "auto").strip().lower()
        self.manager = build_parser_manager(
            bilibili_cookie=bilibili_cookie,
            bilibili_credential_path=bilibili_credential_path,
            bilibili_quality=self.quality,
            tiktok_use_proxy=tiktok_use_proxy,
            tiktok_proxy_url=tiktok_proxy_url,
        )
        self.ydl_enabled = ydl_enabled
        self._ydl_engine: Optional["YdlEngine"] = None
        if ydl_enabled:
            from .config import quality_to_max_height
            from .ydl import YdlEngine
            self._ydl_engine = YdlEngine(
                timeout=timeout, proxy=ydl_proxy,
                max_height=quality_to_max_height(self.quality),
                cookies_from_browser=ydl_cookies_from_browser,
                cookies_file=ydl_cookies_file,
            )

    def extract_links(self, text: str) -> list[str]:
        """同步提取文本中的可解析链接（按出现顺序、去重）。"""
        seen: set[str] = set()
        links: list[str] = []
        for url, _ in self.manager.extract_all_links(text):
            if url not in seen:
                seen.add(url)
                links.append(url)
        return links

    async def parse_text(self, text: str) -> list[ParseResult]:
        """解析文本中的所有链接。

        parser_core 能识别的平台优先；其余 URL 交给 yt-dlp 兜底。
        """
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        session_kwargs: dict = {"headers": {"User-Agent": DEFAULT_UA}, "timeout": timeout}
        if self.proxy:
            session_kwargs["proxy"] = self.proxy
        async with aiohttp.ClientSession(**session_kwargs) as session:
            raw_list = await self.manager.parse_text(text, session)
        results = [ParseResult.from_raw(raw) for raw in raw_list]

        if self.ydl_enabled:
            covered = {r.url for r in results}
            from .ydl import extract_all_urls
            for url in extract_all_urls(text):
                if url in covered:
                    continue
                ydl_result, ydl_error = await asyncio.to_thread(
                    self._ydl_engine.extract, url)
                if ydl_result is None:
                    results.append(ParseResult(
                        url=url, platform="yt-dlp", parser_name="yt-dlp",
                        error=ydl_error or "yt-dlp 未能解析该链接",
                    ))
                else:
                    results.append(ydl_result)
        ok = sum(1 for r in results if not r.is_error)
        logger.info(
            "解析完成：共 %d 条，成功 %d 条，失败 %d 条",
            len(results), ok, len(results) - ok,
        )
        for r in results:
            if r.is_error:
                logger.warning("解析失败 [%s] %s: %s", r.platform, r.url, r.error)
        return results

    async def parse_urls(self, urls: list[str]) -> list[ParseResult]:
        """直接解析 URL 列表。"""
        return await self.parse_text("\n".join(urls))

    def parse_text_sync(self, text: str) -> list[ParseResult]:
        """同步入口，供 GUI 后台线程 / CLI 调用。"""
        return asyncio.run(self.parse_text(text))

    def parse_urls_sync(self, urls: list[str]) -> list[ParseResult]:
        return asyncio.run(self.parse_urls(urls))

    # ── B 站扫码登录 ─────────────────────────────────

    def bilibili_auth(self) -> Any:
        """返回 BilibiliParser 内部的鉴权运行时（含扫码登录、凭据持久化）。"""
        for parser in self.manager.parsers:
            if isinstance(parser, BilibiliParser):
                return parser.auth_runtime
        raise RuntimeError("BilibiliParser 未注册")

    def bilibili_auth_status(self) -> str:
        """B 站登录态描述：未登录 / 已扫码登录 / 已配置 Cookie。"""
        auth = self.bilibili_auth()
        source, _cookie = auth.get_active_cookie_source()
        if source == "runtime":
            return "已扫码登录"
        if source == "configured":
            return "已配置 Cookie"
        return "未登录"

    def bilibili_qr_payload(self) -> dict:
        """生成 B 站扫码登录载荷（含二维码图片 URL 与 qrcode_key）。"""
        async def _run() -> dict:
            async with aiohttp.ClientSession() as session:
                return await self.bilibili_auth().generate_login_payload(session)
        return asyncio.run(_run())

    def bilibili_poll_login(self, qrcode_key: str, timeout_seconds: int = 180) -> dict:
        """轮询 B 站扫码登录结果；成功时凭据自动保存到本地文件。"""
        async def _run() -> dict:
            async with aiohttp.ClientSession() as session:
                return await self.bilibili_auth().poll_login_until_complete(
                    session, qrcode_key, timeout_seconds)
        return asyncio.run(_run())
