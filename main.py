"""视频/媒体解析下载工具 —— GUI 入口。

用法：python main.py
"""
import logging

from app.gui import MediaToolApp
from app.logging_setup import get_log_dir, setup_logging
from app.portable import setup_portable_env


def main():
    setup_portable_env()
    setup_logging()
    logging.info("GUI 启动（日志目录：%s）", get_log_dir())
    app = MediaToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
