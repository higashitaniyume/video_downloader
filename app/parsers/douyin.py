"""抖音解析器实现：支持无需登录 Cookie 的无水印视频、高清图集与 BGM 原声解析。

借鉴自 astrbot_plugin_media_parser (drdon1234)。
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from app.engine import DEFAULT_UA, MediaItem, ParseResult
from .douyin_web import DOUYIN_WEB_USER_AGENT, DouyinWebClient

logger = logging.getLogger(__name__)

DOUYIN_MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U Build/R16NW) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/116.0.0.0 Mobile Safari/537.36"
)
DOUYIN_REFERER = "https://www.douyin.com/"


class DouyinParser:
    """抖音平台专属解析器。"""

    def __init__(self, proxy: str = ""):
        self.proxy = proxy.strip()
        self.web_client = DouyinWebClient()

    @classmethod
    def can_parse(cls, url: str) -> bool:
        """判断是否为抖音相关链接。"""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            host = (parsed.netloc or "").lower().split(":")[0]
        except Exception:
            return False
        if any(h in host for h in ("douyin.com", "iesdouyin.com", "douyinvod.com")):
            return True
        return False

    @staticmethod
    def extract_item_id_from_url(url: str) -> Optional[str]:
        """从 URL 路径或参数中提取 19 位左右的作品 ID。"""
        m = re.search(r"/(?:video|note|slides|share/video)/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"modal_id=(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"(\d{19})", url)
        if m:
            return m.group(1)
        return None

    async def resolve_real_url_and_id(
        self, session: aiohttp.ClientSession, url: str
    ) -> tuple[str, Optional[str]]:
        """跟踪短链重定向并提取作品 ID。"""
        direct_id = self.extract_item_id_from_url(url)
        if direct_id and "v.douyin.com" not in url:
            return url, direct_id

        headers = {
            "User-Agent": DOUYIN_MOBILE_UA,
            "Referer": "https://www.douyin.com/?is_from_mobile_home=1&recommend=1",
        }
        try:
            async with session.get(
                url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                real_url = str(resp.url)
                item_id = self.extract_item_id_from_url(real_url) or direct_id
                return real_url, item_id
        except Exception as exc:
            logger.debug("抖音重定向追踪失败: %s", exc)
            return url, direct_id

    async def parse(
        self, url: str, session: Optional[aiohttp.ClientSession] = None
    ) -> Optional[ParseResult]:
        """异步解析单个抖音链接。"""
        should_close_session = False
        if session is None:
            session_kwargs: dict[str, Any] = {
                "headers": {"User-Agent": DOUYIN_WEB_USER_AGENT},
                "timeout": aiohttp.ClientTimeout(total=20),
            }
            if self.proxy:
                session_kwargs["proxy"] = self.proxy
            session = aiohttp.ClientSession(**session_kwargs)
            should_close_session = True

        try:
            real_url, item_id = await self.resolve_real_url_and_id(session, url)
            if not item_id:
                logger.warning("未能从抖音链接提取到作品 ID: %s", url)
                return None

            data = await self.web_client.fetch_detail(
                session, item_id, referer=real_url or DOUYIN_REFERER
            )
            if not data:
                return None

            aweme = data.get("aweme_detail")
            if not aweme and "item_list" in data and data["item_list"]:
                aweme = data["item_list"][0]
            if not aweme:
                return None

            return self._build_parse_result(url, aweme)
        except Exception as exc:
            logger.warning("抖音专属解析器异常: %s", exc)
            return None
        finally:
            if should_close_session:
                await session.close()

    def _build_parse_result(self, raw_url: str, aweme: dict[str, Any]) -> ParseResult:
        title = aweme.get("desc") or "（无标题）"
        author_info = aweme.get("author") or {}
        author = author_info.get("nickname") or ""

        # 发布时间
        create_time = aweme.get("create_time")
        timestamp_str = ""
        if create_time:
            try:
                dt = datetime.datetime.fromtimestamp(create_time)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        # 封面提取
        video_data = aweme.get("video") or {}
        cover_urls: list[str] = []
        for c_key in ("cover", "origin_cover", "dynamic_cover"):
            urls = (video_data.get(c_key) or {}).get("url_list") or []
            for u in urls:
                if u and u not in cover_urls:
                    cover_urls.append(u)

        duration_ms = int(video_data.get("duration") or 0)
        items: list[MediaItem] = []
        item_counter = 1

        # 1. 检查是否为图集 (Images)
        images = aweme.get("images") or aweme.get("image_post_info", {}).get("images") or []
        if images:
            for idx, img in enumerate(images, 1):
                img_urls = img.get("url_list") or []
                display_urls = [u for u in img_urls if u]
                if display_urls:
                    items.append(
                        MediaItem(
                            index=item_counter,
                            kind="image",
                            urls=display_urls,
                            name=f"图片 {idx}",
                            format_id=f"image_{idx}",
                        )
                    )
                    item_counter += 1
            if not cover_urls and items and items[0].urls:
                cover_urls.append(items[0].urls[0])

        # 2. 视频流提取 (Video，仅在非图集作品时提取)
        if not images:
            play_addr = video_data.get("play_addr") or {}
            play_urls_raw = play_addr.get("url_list") or []
            video_urls: list[str] = []
            for pu in play_urls_raw:
                # 替换 playwm 为 play 获取无水印原画直链
                clean_u = pu.replace("playwm", "play")
                if clean_u and clean_u not in video_urls:
                    video_urls.append(clean_u)

            if video_urls:
                items.append(
                    MediaItem(
                        index=item_counter,
                        kind="video",
                        urls=video_urls,
                        name="无水印高清视频 (MP4)",
                        format_id="best_video",
                    )
                )
                item_counter += 1

        # 3. 提取 BGM / 原声音频 (Audio)
        music_data = aweme.get("music") or {}
        music_urls = (music_data.get("play_url") or {}).get("url_list") or []
        clean_music_urls = [u for u in music_urls if u]
        if clean_music_urls:
            music_title = music_data.get("title") or "背景音乐"
            items.append(
                MediaItem(
                    index=item_counter,
                    kind="audio",
                    urls=clean_music_urls,
                    name=f"原声音频 ({music_title})",
                    format_id="audio",
                )
            )

        # 重新规整 index
        for idx, item in enumerate(items, 1):
            item.index = idx

        return ParseResult(
            url=raw_url,
            platform="douyin",
            parser_name="douyin",
            title=title,
            author=author,
            desc=title,
            timestamp=timestamp_str,
            duration_ms=duration_ms,
            cover_urls=cover_urls,
            items=items,
            video_headers={
                "User-Agent": DOUYIN_WEB_USER_AGENT,
                "Referer": DOUYIN_REFERER,
            },
            image_headers={
                "User-Agent": DOUYIN_WEB_USER_AGENT,
                "Referer": DOUYIN_REFERER,
            },
            raw=aweme,
        )
