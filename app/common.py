"""共享模型与工具：下载结果、文件名净化。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

_INVALID_FILENAME_CHARS = re.compile(r'[\/:*?"<>|\x00-\x1f]')


def sanitize_filename(name: str, max_len: int = 60) -> str:
    """清理文件名中的非法字符并截断。"""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "untitled"
    return cleaned[:max_len].rstrip(" .")


def unique_path(directory: Path, filename: str) -> Path:
    """返回不覆盖已有文件的路径，冲突时追加 (1)、(2)…。"""
    candidate = directory / filename
    stem, suffix = os.path.splitext(filename)
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


@dataclass
class DownloadedFile:
    path: Path
    label: str = ""
    size_bytes: int = 0
    kind: str = "video"



@dataclass
class DownloadSummary:
    files: list[DownloadedFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.files)
