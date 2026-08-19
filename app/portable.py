"""便携运行支持：打包为 exe 后自动找到随包分发的 ffmpeg。

GitHub Actions 构建时会在 exe 同目录放置 ffmpeg.exe / ffprobe.exe，
程序启动时把 exe 所在目录加入 PATH，DASH/m3u8 合并与 yt-dlp 无需用户
手动安装 ffmpeg。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def setup_portable_env() -> None:
    """把可执行文件所在目录加入 PATH（仅 PyInstaller 打包运行时生效）。

    开发模式（python main.py）下为 no-op。
    """
    if not getattr(sys, "frozen", False):
        return
    try:
        base = str(Path(sys.executable).resolve().parent)
    except Exception:  # noqa: BLE001
        return
    if not base or not os.path.isdir(base):
        return
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if base not in parts:
        os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
