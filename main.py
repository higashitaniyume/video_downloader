"""视频/媒体解析下载工具 —— GUI 入口。

用法：python main.py
"""
from app.gui import MediaToolApp


def main():
    app = MediaToolApp()
    app.mainloop()


if __name__ == "__main__":
    main()
