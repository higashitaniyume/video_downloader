"""应用配置：代理与 Cookie 等 GUI 设置的持久化。

配置文件位于 ~/.video_downloader/config.json（与下载缓存同级目录）。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".video_downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    """GUI 可配置项。

    proxy_url: 代理地址，形如 "http://127.0.0.1:7890"（Clash/v2ray 等代理软件
        的本地地址）；留空表示不启用代理。解析与下载全程生效。
    bilibili_cookie: B 站登录 Cookie（形如 "SESSDATA=...; bili_jct=..."），
        可解锁高清晰度；留空则匿名解析（低清晰度可用）。
    """

    proxy_url: str = ""
    bilibili_cookie: str = ""

    @property
    def proxy_enabled(self) -> bool:
        return bool(self.proxy_url.strip())

    @classmethod
    def load(cls) -> "AppConfig":
        """从磁盘加载配置；文件缺失或损坏时返回默认配置。"""
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(
            proxy_url=str(data.get("proxy_url", "") or "").strip(),
            bilibili_cookie=str(data.get("bilibili_cookie", "") or "").strip(),
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
