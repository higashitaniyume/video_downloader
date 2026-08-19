"""命令行入口：解析视频/媒体链接，可下载。

用法：
    python cli.py "https://www.bilibili.com/video/BVxxxx" ...
    python cli.py --download --out ./downloads "链接文本或URL"
    python cli.py --json "链接"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.downloader import MediaDownloader
from app.engine import ParseEngine
from app.logging_setup import setup_logging
from app.portable import setup_portable_env


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 / 1024 / 1024:.1f} GB"


def _print_result(result, index: int = 0) -> None:
    prefix = f"[{index}] " if index else ""
    if result.is_error:
        print(f"{prefix}[{result.platform}] 解析失败: {result.error}")
        print(f"    {result.url}")
        return
    print(f"{prefix}[{result.platform}] {result.title or '(无标题)'}")
    meta_parts = [result.author, result.duration_text, result.timestamp]
    meta_line = " | ".join(p for p in meta_parts if p)
    if meta_line:
        print(f"    作者: {meta_line}")
    if result.desc and result.desc.strip():
        print(f"    简介: {result.desc.strip()[:120]}")
    for item in result.items:
        print(f"    {item.kind} {item.index}: {item.urls[0] if item.urls else '(无直链)'}")
    if not result.has_media:
        print("    (无可用媒体直链)")
    print(f"    链接: {result.url}")


async def _download_all(downloader: MediaDownloader, results, out_dir: Path) -> None:
    from app.downloader import DownloadSummary

    async def _progress(label: str, done: int, total: int | None) -> None:
        if total:
            print(f"\r    {label}: {_format_bytes(done)} / {_format_bytes(total)}", end="", flush=True)
        else:
            print(f"\r    {label}: {_format_bytes(done)}", end="", flush=True)

    for result in results:
        if result.is_error or not result.has_media:
            continue
        print(f"  下载: [{result.platform}] {result.title or result.url}")
        async with __import__("aiohttp").ClientSession() as session:
            summary = await downloader.download_result(session, result, _progress)
        print()
        for f in summary.files:
            print(f"    ✓ {f.path.name} ({_format_bytes(f.size_bytes)})")
        for err in summary.errors:
            print(f"    ✗ {err}")
        if not summary.files:
            print("    (未下载到任何文件)")


def main() -> None:
    setup_portable_env()
    setup_logging()
    parser = argparse.ArgumentParser(
        description="视频/媒体链接解析与下载工具（复用 HIKARI_BOT_NEO 解析核心）",
    )
    parser.add_argument("text", nargs="*", help="链接或包含链接的文本；不提供则从 stdin 读取")
    parser.add_argument("--download", action="store_true", help="解析后下载媒体")
    parser.add_argument("--out", default="downloads", help="下载输出目录（默认 downloads/）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出解析结果")
    parser.add_argument("--bilibili-cookie", default="", help="B站登录 Cookie（可选，解锁高清晰度）")
    parser.add_argument("--quality", default="auto",
                        choices=["auto", "4k", "1080p", "720p", "480p", "360p"],
                        help="最高清晰度：B站解析与 yt-dlp 兜底平台（YouTube 等）生效（默认 auto=最高可用）")
    parser.add_argument("--proxy", default="", help="全局代理地址（解析+下载），如 http://127.0.0.1:7890")
    parser.add_argument("--ydl-proxy", default="", help="yt-dlp 兜底引擎的代理地址，如 http://127.0.0.1:7890")
    parser.add_argument("--no-ydl", action="store_true", help="禁用 yt-dlp 兜底（仅用 parser_core）")
    args = parser.parse_args()

    if args.text:
        text = "\n".join(args.text)
    else:
        text = sys.stdin.read()

    if not text.strip():
        parser.print_help()
        sys.exit(1)

    proxy = args.proxy or args.ydl_proxy  # --proxy 全局代理优先，兼容旧 --ydl-proxy
    engine = ParseEngine(
        bilibili_cookie=args.bilibili_cookie,
        quality=args.quality,
        ydl_enabled=not args.no_ydl,
        proxy=proxy,
    )
    results = engine.parse_text_sync(text)

    if args.json:
        payload = [
            {
                "url": r.url,
                "platform": r.platform,
                "title": r.title,
                "author": r.author,
                "desc": r.desc,
                "timestamp": r.timestamp,
                "duration_ms": r.duration_ms,
                "items": [
                    {"kind": it.kind, "index": it.index, "name": it.name,
                     "format_id": it.format_id, "urls": it.urls}
                    for it in r.items
                ],
                "error": r.error,
            }
            for r in results
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not results:
        print("未识别到可解析的链接。")
        sys.exit(1)

    for index, result in enumerate(results, start=1):
        _print_result(result, index)
        print()

    if args.download:
        out_dir = Path(args.out)
        downloader = MediaDownloader(out_dir, proxy=proxy)
        try:
            asyncio.run(_download_all(downloader, results, out_dir))
        finally:
            downloader.shutdown()


if __name__ == "__main__":
    main()
