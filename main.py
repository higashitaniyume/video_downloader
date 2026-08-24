"""视频/媒体解析下载工具 —— GUI 与 Web 综合入口。

用法：
    python main.py                     # 启动 GUI 桌面客户端（后台自动运行 Web 服务）
    python main.py --web-only          # 仅启动 Web 服务并自动打开浏览器（无 GUI 窗口）
    python main.py --web-only -p 5200  # 指定端口启动 Web 服务
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import webbrowser

from app.logging_setup import get_log_dir, setup_logging
from app.portable import setup_portable_env


def parse_args():
    parser = argparse.ArgumentParser(description="视频/媒体解析与下载工具")
    parser.add_argument(
        "--web-only", "-w", action="store_true",
        help="仅启动 Web 网页端服务（不显示桌面 GUI 窗口）",
    )
    parser.add_argument(
        "--port", "-p", type=int, default=None,
        help="指定 Web 服务端口（默认读取配置或 5200）",
    )
    parser.add_argument(
        "--open-browser", "-b", action="store_true", default=True,
        help="启动 Web 服务后自动在默认浏览器中打开（默认开启）",
    )
    parser.add_argument(
        "--no-browser", dest="open_browser", action="store_false",
        help="启动 Web 服务后不自动打开浏览器",
    )
    return parser.parse_args()


def run_web_only(port: int | None, open_browser: bool = True):
    from aiohttp import web
    from app.web.server import WebServerManager, find_available_port

    target_port = find_available_port(port or 5200)
    manager = WebServerManager(host="127.0.0.1", port=target_port)
    app = manager.create_app()

    logging.info("正在以 Web-Only 模式启动服务: %s", manager.server_url)
    print(f"\n⚡ Video Downloader Web 服务已启动: {manager.server_url}")
    print("按 Ctrl+C 可停止服务\n")

    if open_browser:
        def _open():
            time.sleep(0.6)
            webbrowser.open(manager.server_url)
        import threading
        threading.Thread(target=_open, daemon=True).start()

    try:
        web.run_app(app, host="127.0.0.1", port=manager.active_port, print=None)
    except (KeyboardInterrupt, SystemExit):
        print("\nWeb 服务已停止。")


def main():
    setup_portable_env()
    setup_logging()
    args = parse_args()

    if args.web_only:
        run_web_only(args.port, open_browser=args.open_browser)
        return

    from app.gui import MediaToolApp
    logging.info("GUI 启动（日志目录：%s）", get_log_dir())
    app = MediaToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
