"""应用日志系统：输出到程序所在目录下的 logs/ 文件夹。

- 日志文件：<程序目录>/logs/video_downloader.log（UTF-8，5MB 滚动，保留 5 份）
- 控制台：开发模式（python main.py / cli.py）下同时输出到终端；
  打包后的 windowed exe 没有 stderr，自动跳过控制台输出
- 未捕获异常：通过 sys.excepthook 写入日志（GUI exe 无控制台，排障全靠它）
- 级别：默认 INFO，可用环境变量 VIDEO_DOWNLOADER_LOG_LEVEL 覆盖（如 DEBUG）
- 幂等：setup_logging 可安全重复调用
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "video_downloader.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 记住 setup_logging 配置过的目录，供 get_log_dir() 复用
_log_dir: Optional[Path] = None


def program_dir() -> Path:
    """程序所在文件夹：打包运行时为 exe 所在目录，开发模式为当前工作目录。"""
    _android_data = os.environ.get("ANDROID_DATA_DIR")
    if _android_data:
        return Path(_android_data)
    if getattr(sys, "frozen", False):
        try:
            return Path(sys.executable).resolve().parent
        except Exception:  # noqa: BLE001
            pass
    return Path.cwd()


def get_log_dir() -> Path:
    """返回日志目录（未初始化时按默认位置推导）。"""
    if _log_dir is not None:
        return _log_dir
    return program_dir() / LOG_DIR_NAME


def setup_logging(
    log_dir: Optional[Path] = None,
    level: Optional[int | str] = None,
) -> Path:
    """初始化应用日志，返回日志文件路径。

    Args:
        log_dir: 日志目录；默认 <程序目录>/logs。
        level: 日志级别（logging 常量或名字）；默认取环境变量
            VIDEO_DOWNLOADER_LOG_LEVEL，未设置则为 INFO。
    """
    global _log_dir

    log_dir = Path(log_dir) if log_dir is not None else get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME
    _log_dir = log_dir

    root = logging.getLogger()
    # 幂等：已安装过本模块的 handler 则直接返回
    if any(getattr(h, "_vd_handler", False) for h in root.handlers):
        return log_file

    if level is None:
        level = os.environ.get("VIDEO_DOWNLOADER_LOG_LEVEL", "INFO")
    if isinstance(level, str):
        level = getattr(logging, level.strip().upper(), logging.INFO)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    file_handler._vd_handler = True
    root.addHandler(file_handler)

    # windowed exe 没有 stderr，跳过控制台输出，避免 StreamHandler 报错
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        console.setLevel(level)
        console._vd_handler = True
        root.addHandler(console)

    root.setLevel(level)
    logging.captureWarnings(True)

    # 未捕获异常写入日志文件，再交给默认处理（保留原退出行为）
    def _excepthook(exc_type, exc_value, exc_tb) -> None:
        logging.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    logging.info("日志系统初始化完成：%s（级别 %s）", log_file, logging.getLevelName(level))
    return log_file
