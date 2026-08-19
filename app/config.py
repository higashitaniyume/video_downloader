"""应用配置：代理、Cookie 与清晰度等 GUI 设置的持久化。

配置文件放在程序当前目录（config.json），扫码登录凭据与下载缓存也在当前目录，
整个工具可随文件夹一起移动使用。
"""
from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.cwd()
CONFIG_FILE = CONFIG_DIR / "config.json"

# 旧版本配置目录（~/.video_downloader）：首次运行时自动迁移到当前目录
_LEGACY_CONFIG_DIR = Path.home() / ".video_downloader"


def _migrate_file(new_path: Path, legacy_name: str) -> None:
    """新位置不存在但旧位置有同名文件时，复制一份过去（保留旧文件）。"""
    if new_path.exists():
        return
    legacy = _LEGACY_CONFIG_DIR / legacy_name
    if not legacy.exists():
        return
    try:
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, new_path)
    except OSError:
        pass


def migrate_legacy_config() -> None:
    """把旧位置（~/.video_downloader）的配置与扫码凭据迁移到当前目录。"""
    _migrate_file(CONFIG_FILE, "config.json")
    _migrate_file(CONFIG_DIR / "bilibili_credentials.json", "bilibili_credentials.json")

# ── 清晰度档位 ──────────────────────────────────────────
# 配置键 → (B 站 qn 上限, yt-dlp 最大高度)：
#   - B 站：解析时限制所选流不超过该 qn（0=不限，取平台允许的最高档）
#   - yt-dlp 兜底平台（YouTube 等）：解析结果只展示不高于该高度的档位
#     （0=不限，保留全部档位）
QUALITY_PRESETS: dict[str, tuple[int, int]] = {
    "auto": (0, 0),        # 自动（最高可用）
    "4k": (120, 2160),
    "1080p": (80, 1080),
    "720p": (64, 720),
    "480p": (32, 480),
    "360p": (16, 360),
}
DEFAULT_QUALITY = "auto"


def quality_to_bilibili_qn(quality: str) -> int:
    """把清晰度配置键转为 B 站 qn 上限（0=不限）。"""
    return QUALITY_PRESETS.get((quality or "").strip().lower(), QUALITY_PRESETS[DEFAULT_QUALITY])[0]


def quality_to_max_height(quality: str) -> int:
    """把清晰度配置键转为 yt-dlp 档位最大高度（0=不限）。"""
    return QUALITY_PRESETS.get((quality or "").strip().lower(), QUALITY_PRESETS[DEFAULT_QUALITY])[1]


@dataclass
class AppConfig:
    """GUI 可配置项。

    proxy_url: 代理地址，形如 "http://127.0.0.1:7890"（Clash/v2ray 等代理软件
        的本地地址）；留空表示不启用代理。解析与下载全程生效。
    bilibili_cookie: B 站登录 Cookie（形如 "SESSDATA=...; bili_jct=..."），
        可解锁高清晰度；留空则匿名解析（低清晰度可用）。
    quality: 清晰度档位，取值见 QUALITY_PRESETS（如 "auto"/"1080p"/"720p"）。
        对 B 站解析生效（限制最高画质），也作用于 yt-dlp 兜底平台
        （YouTube 等可自选清晰度的平台，限制展示的最高分辨率）。
    """

    proxy_url: str = ""
    bilibili_cookie: str = ""
    quality: str = DEFAULT_QUALITY

    @property
    def proxy_enabled(self) -> bool:
        return bool(self.proxy_url.strip())

    @classmethod
    def load(cls) -> "AppConfig":
        """从磁盘加载配置；文件缺失或损坏时返回默认配置。"""
        migrate_legacy_config()
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        return cls(
            proxy_url=str(data.get("proxy_url", "") or "").strip(),
            bilibili_cookie=str(data.get("bilibili_cookie", "") or "").strip(),
            quality=str(data.get("quality", DEFAULT_QUALITY) or DEFAULT_QUALITY).strip().lower(),
        )

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
