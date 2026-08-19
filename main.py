"""视频/媒体解析下载工具 —— GUI 入口。

用法：python main.py
"""
from app.gui import MediaToolApp
from app.portable import setup_portable_env


def main():
    setup_portable_env()
    app = MediaToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
