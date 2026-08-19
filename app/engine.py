"""解析引擎：文本提链 → 路由 → 并发解析 → 归一化结果。

复用机器人（HIKARI_BOT_NEO）的 astrbot_plugin_media_parser 解析核心，
本文件只做薄封装，产出 GUI/CLI 共用的 ParseResult 数据类。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp

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
    tiktok_use_proxy: bool = False,
    tiktok_proxy_url: str = "",
) -> ParserManager:
    """构建解析器管理器。

    Args:
        bilibili_cookie: 可选 B 站登录 Cookie（形如 "SESSDATA=...; bili_jct=..."），
            提供后可解锁更高清晰度；留空则匿名解析（低清晰度可用）。
        tiktok_use_proxy: 是否通过代理访问 TikTok。
        tiktok_proxy_url: 代理地址，形如 "http://127.0.0.1:7890"。
    """
    parsers = [
        BilibiliParser(cookie_runtime_enabled=bool(bilibili_cookie), configured_cookie=bilibili_cookie),
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
        tiktok_use_proxy: bool = False,
        tiktok_proxy_url: str = "",
        ydl_enabled: bool = True,
        ydl_proxy: str = "",
    ):
        self.timeout = timeout
        self.manager = build_parser_manager(
            bilibili_cookie=bilibili_cookie,
            tiktok_use_proxy=tiktok_use_proxy,
            tiktok_proxy_url=tiktok_proxy_url,
        )
        self.ydl_enabled = ydl_enabled
        self._ydl_engine: Optional["YdlEngine"] = None
        if ydl_enabled:
            from .ydl import YdlEngine
            self._ydl_engine = YdlEngine(timeout=timeout, proxy=ydl_proxy)

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
        async with aiohttp.ClientSession(headers={"User-Agent": DEFAULT_UA}, timeout=timeout) as session:
            raw_list = await self.manager.parse_text(text, session)
        results = [ParseResult.from_raw(raw) for raw in raw_list]

        if self.ydl_enabled:
            covered = {r.url for r in results}
            from .ydl import extract_all_urls
            for url in extract_all_urls(text):
                if url in covered:
                    continue
                ydl_result = await asyncio.to_thread(self._ydl_engine.extract, url)
                if ydl_result is None:
                    results.append(ParseResult(
                        url=url, platform="yt-dlp", parser_name="yt-dlp",
                        error="yt-dlp 未能解析该链接",
                    ))
                else:
                    results.append(ydl_result)
        return results

    async def parse_urls(self, urls: list[str]) -> list[ParseResult]:
        """直接解析 URL 列表。"""
        return await self.parse_text("\n".join(urls))

    def parse_text_sync(self, text: str) -> list[ParseResult]:
        """同步入口，供 GUI 后台线程 / CLI 调用。"""
        return asyncio.run(self.parse_text(text))

    def parse_urls_sync(self, urls: list[str]) -> list[ParseResult]:
        return asyncio.run(self.parse_urls(urls))
