"""解析引擎：文本提链 → 并发解析（完全基于 yt-dlp）。"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class MediaItem:
    """单个媒体资源（视频/图片/音频），urls 为可用直链的回退列表。

    format_id 指示下载时传给 yt-dlp 的格式标识。
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


class ParseEngine:
    """解析引擎：对一段文本提取全部可解析链接并逐个解析（完全基于 yt-dlp）。"""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        quality: str = "auto",
        proxy: str = "",
        ydl_enabled: bool = True,
        ydl_proxy: str = "",
        ydl_cookies_from_browser: str = "",
        ydl_cookies_file: str = "",
    ):
        self.timeout = timeout
        self.proxy = proxy.strip()
        if self.proxy:
            ydl_proxy = self.proxy
        self.quality = (quality or "auto").strip().lower()
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

        from .parsers.douyin import DouyinParser
        from .parsers.jm import JMParser
        self.douyin_parser = DouyinParser(proxy=self.proxy)
        self.jm_parser = JMParser(proxy=self.proxy)

    def extract_links(self, text: str) -> list[str]:
        """同步提取文本中的可解析链接与 JM 标识符（按出现顺序、去重）。"""
        from .parsers.jm import extract_all_jm_targets
        from .ydl import extract_all_urls

        urls = extract_all_urls(text)
        jm_targets = extract_all_jm_targets(text)

        combined: list[str] = []
        seen: set[str] = set()
        for item in urls + jm_targets:
            normalized = item.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                combined.append(item.strip())
        return combined

    async def parse_text(self, text: str) -> list[ParseResult]:
        """解析文本中的所有链接与漫画标识符。"""
        results: list[ParseResult] = []
        if not self.ydl_enabled or not self._ydl_engine:
            return results

        from .parsers.douyin import DouyinParser
        from .parsers.jm import JMParser
        urls = self.extract_links(text)

        async def parse_one(url: str) -> ParseResult:
            # 1. 优先使用 JM 专属解析器（支持 jm123456、jm 123456、18comic 等）
            if JMParser.can_parse(url):
                try:
                    jm_result = await self.jm_parser.parse(url)
                    if jm_result:
                        return jm_result
                except Exception as exc:
                    logger.debug("JM 解析器未能解析，转入兜底: %s", exc)

            # 2. 优先使用抖音专属解析器（无需 Cookie、支持无水印与图集）
            if DouyinParser.can_parse(url):
                try:
                    dy_result = await self.douyin_parser.parse(url)
                    if dy_result:
                        return dy_result
                except Exception as exc:
                    logger.debug("抖音解析器未能解析，转入 yt-dlp 兜底: %s", exc)

            # 3. yt-dlp 兜底
            ydl_result, ydl_error = await asyncio.to_thread(
                self._ydl_engine.extract, url)
            if ydl_result is None:
                return ParseResult(
                    url=url, platform="yt-dlp", parser_name="yt-dlp",
                    error=ydl_error or "yt-dlp 未能解析该链接",
                )
            return ydl_result

        if urls:
            tasks = [parse_one(url) for url in urls]
            results = list(await asyncio.gather(*tasks))

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
