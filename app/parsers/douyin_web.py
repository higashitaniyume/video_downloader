"""抖音 Web 详情接口传输层。

负责会话状态（ttwid）维护与 a_bogus 签名请求发送。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from http.cookies import SimpleCookie
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import aiohttp

from .douyin_sign import generate_abogus

logger = logging.getLogger(__name__)

DOUYIN_WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
)
DOUYIN_DETAIL_API = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
DOUYIN_TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
DOUYIN_REFERER = "https://www.douyin.com/"
DEFAULT_TTWID_TTL = 6 * 60 * 60
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class DouyinWebClient:
    """管理 Web API 的签名请求和生命周期 ttwid 会话。"""

    def __init__(self) -> None:
        self._ttwid = ""
        self._ttwid_expires_at = 0.0
        self._ttwid_lock = asyncio.Lock()

    @staticmethod
    def _build_params(item_id: str) -> Dict[str, Any]:
        return {
            "device_platform": "webapp",
            "aid": "6383",
            "channel": "channel_pc_web",
            "aweme_id": str(item_id),
        }

    @staticmethod
    def _registration_payload() -> Dict[str, Any]:
        return {
            "region": "cn",
            "aid": 1768,
            "needFid": False,
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https",
            "union": True,
        }

    @staticmethod
    def _parse_ttwid(response: aiohttp.ClientResponse) -> tuple[str, int]:
        morsel = response.cookies.get("ttwid")
        if morsel is not None and morsel.value:
            try:
                max_age = int(morsel["max-age"] or 0)
            except (TypeError, ValueError):
                max_age = 0
            return morsel.value, max_age

        for header in response.headers.getall("Set-Cookie", []):
            cookie = SimpleCookie()
            try:
                cookie.load(header)
            except Exception:
                continue
            morsel = cookie.get("ttwid")
            if morsel is None or not morsel.value:
                continue
            try:
                max_age = int(morsel["max-age"] or 0)
            except (TypeError, ValueError):
                max_age = 0
            return morsel.value, max_age
        return "", 0

    def _has_valid_ttwid(self) -> bool:
        return bool(self._ttwid and time.monotonic() < self._ttwid_expires_at)

    async def _get_ttwid(
        self,
        session: aiohttp.ClientSession,
        *,
        force_refresh: bool = False,
        stale_ttwid: str = "",
    ) -> str:
        if not force_refresh and self._has_valid_ttwid():
            return self._ttwid

        async with self._ttwid_lock:
            if not force_refresh and self._has_valid_ttwid():
                return self._ttwid
            if force_refresh:
                if self._has_valid_ttwid() and (
                    not stale_ttwid or self._ttwid != stale_ttwid
                ):
                    return self._ttwid
                self._ttwid = ""
                self._ttwid_expires_at = 0.0

            headers = {
                "User-Agent": DOUYIN_WEB_USER_AGENT,
                "Content-Type": "application/json; charset=utf-8",
            }
            try:
                async with session.post(
                    DOUYIN_TTWID_URL,
                    json=self._registration_payload(),
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    if response.status >= 400:
                        return ""
                    await response.read()
                    ttwid, max_age = self._parse_ttwid(response)
            except Exception as exc:
                logger.debug("注册 ttwid 异常: %s", exc)
                return ""

            if not ttwid:
                return ""
            ttl = max_age if max_age > 0 else DEFAULT_TTWID_TTL
            ttl = min(ttl, DEFAULT_TTWID_TTL)
            self._ttwid = ttwid
            self._ttwid_expires_at = time.monotonic() + max(ttl, 60)
            return self._ttwid

    @staticmethod
    def _contains_target(data: Dict[str, Any], item_id: str) -> bool:
        candidates = []
        detail = data.get("aweme_detail")
        if isinstance(detail, dict):
            candidates.append(detail)
        for key in ("aweme_details", "aweme_list", "item_list"):
            value = data.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
        return any(
            str(item.get("aweme_id") or item.get("id") or "") == str(item_id)
            for item in candidates
        )

    async def _request_once(
        self,
        session: aiohttp.ClientSession,
        item_id: str,
        referer: str,
        ttwid: str,
    ) -> tuple[Optional[Dict[str, Any]], bool]:
        params = self._build_params(item_id)
        param_string = urlencode(params)
        signature = generate_abogus(
            param_string,
            body="",
            user_agent=DOUYIN_WEB_USER_AGENT,
            options=[0, 1, 8],
        )
        url = f"{DOUYIN_DETAIL_API}?{param_string}&a_bogus={signature}"
        headers = {
            "User-Agent": DOUYIN_WEB_USER_AGENT,
            "Referer": referer or DOUYIN_REFERER,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Cookie": f"ttwid={ttwid}",
        }
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status in {401, 403}:
                    return None, True
                if response.status >= 400:
                    return None, False
                body = await response.text()
        except Exception:
            return None, False

        if not body or not body.lstrip().startswith("{"):
            return None, True
        try:
            data = json.loads(body)
        except Exception:
            return None, True

        if not self._contains_target(data, item_id):
            return None, True
        return data, False

    async def fetch_detail(
        self,
        session: aiohttp.ClientSession,
        item_id: str,
        referer: str = "",
    ) -> Optional[Dict[str, Any]]:
        """获取目标作品详情，遇鉴权失效自动重试刷新 ttwid。"""
        if not item_id:
            return None

        ttwid = await self._get_ttwid(session)
        if not ttwid:
            logger.debug("未获取到有效 ttwid")
            return None

        data, retry = await self._request_once(session, item_id, referer, ttwid)
        if data:
            return data
        if not retry:
            return None

        # 刷新会话重试一次
        fresh_ttwid = await self._get_ttwid(
            session, force_refresh=True, stale_ttwid=ttwid
        )
        if not fresh_ttwid:
            return None

        data, _ = await self._request_once(session, item_id, referer, fresh_ttwid)
        return data
