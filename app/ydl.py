"""yt-dlp 兜底引擎：支持 parser_core 未覆盖的 1900+ 平台。

路由策略：parser_core（机器人解析核心）优先处理国内平台；
本模块兜底其余全部平台（YouTube、Twitch、SoundCloud、Instagram、网易云音乐…）。
下载一律走 yt-dlp 自身（自动选择最佳格式并用 ffmpeg 合并音视频）。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

import yt_dlp

from .control import DownloadControl, TaskCancelled
from .engine import MediaItem, ParseResult
from .common import DownloadSummary, DownloadedFile, sanitize_filename, unique_path

# 通用 URL 提取：去尾中文/英文标点
_URL_RE = re.compile(r"https?://[^\s<>\"'\u3000]+")
_TRAILING_PUNCT = re.compile(r"[，。！？；：、,.;:!?)\]}>”’]+$")

MAX_VIDEO_FORMATS = 6


def extract_all_urls(text: str) -> list[str]:
    """提取文本中所有 http(s) URL（去重、去尾标点），按出现顺序。"""
    seen: set[str] = set()
    urls: list[str] = []
    for raw in _URL_RE.findall(text):
        url = _TRAILING_PUNCT.sub("", raw)
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _info_to_result(url: str, info: dict) -> ParseResult:
    """把 yt-dlp 的 info dict 映射为 ParseResult。"""
    platform = (info.get("extractor_key") or "ydl").lower()

    # 精选展示档位：按高度去重（含音频的视频格式优先），最多 MAX_VIDEO_FORMATS 档
    formats = info.get("formats") or [info]
    best_audio: Optional[dict] = None
    by_height: dict[int, dict] = {}

    def _video_key(fmt: dict) -> int:
        return int(fmt.get("height") or 0)

    for fmt in formats:
        if not fmt.get("url"):
            continue
        vcodec = fmt.get("vcodec") or ""
        acodec = fmt.get("acodec") or ""
        if vcodec and vcodec != "none" and (acodec and acodec != "none"):
            key = _video_key(fmt)
            if key and key not in by_height:
                by_height[key] = fmt
        elif (not vcodec or vcodec == "none") and acodec and acodec != "none":
            if best_audio is None or (fmt.get("abr") or 0) > (best_audio.get("abr") or 0):
                best_audio = fmt

    items: list[MediaItem] = []
    for index, height in enumerate(sorted(by_height, reverse=True), start=1):
        fmt = by_height[height]
        label = fmt.get("format_note") or fmt.get("format") or f"{height}p"
        items.append(MediaItem(
            index=index,
            kind="video",
            urls=[fmt["url"]],
            name=label,
            format_id=str(fmt.get("format_id") or ""),
        ))
    if best_audio:
        items.append(MediaItem(
            index=len(items) + 1,
            kind="audio",
            urls=[best_audio["url"]],
            name=f"audio {best_audio.get('abr', '')}k",
            format_id=str(best_audio.get("format_id") or ""),
        ))
    if not items:
        # 无法拆出格式时兜底整体为一项
        items.append(MediaItem(index=1, kind="video", urls=[], name="best",
                               format_id="best"))

    thumbnails = info.get("thumbnails") or []
    covers = [t.get("url") for t in thumbnails if t.get("url")]
    if not covers and info.get("thumbnail"):
        covers = [info["thumbnail"]]

    return ParseResult(
        url=url,
        platform=platform,
        parser_name="yt-dlp",
        title=info.get("title") or "",
        author=info.get("uploader") or info.get("channel") or "",
        desc=(info.get("description") or "").strip(),
        timestamp=str(info.get("timestamp") or ""),
        duration_ms=int((info.get("duration") or 0) * 1000),
        cover_urls=covers,
        items=items,
        raw={"ydl": True, "webpage_url": info.get("webpage_url") or url},
    )


class YdlEngine:
    """yt-dlp 解析引擎：提取单个 URL 的元数据。"""

    def __init__(self, *, timeout: float = 60.0, proxy: str = ""):
        self.timeout = timeout
        self.proxy = proxy

    def _base_opts(self) -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": self.timeout,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        return opts

    def extract(self, url: str) -> Optional[ParseResult]:
        """提取单个 URL。失败返回 None（错误信息由调用方包装）。"""
        with yt_dlp.YoutubeDL(dict(self._base_opts(), skip_download=True)) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except yt_dlp.utils.DownloadError:
                return None
        if not info:
            return None
        return _info_to_result(url, info)


class YdlDownloader:
    """yt-dlp 下载器：按所选 format_id 下载，yt-dlp 负责格式选择与合并。"""

    def __init__(self, out_dir: Path, *, proxy: str = "", timeout: float = 60.0):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = proxy
        self.timeout = timeout

    def _base_opts(self) -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": self.timeout,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        return opts

    def download_result_sync(
        self,
        result: ParseResult,
        items: list[MediaItem],
        progress=None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        """逐个下载勾选的格式档位，返回文件清单与错误。

        control 非空时支持取消（item 间生效）；TaskCancelled 向上传播。
        """
        summary = DownloadSummary()
        webpage_url = result.raw.get("webpage_url") or result.url
        base_name = sanitize_filename(result.title or result.platform)

        for n, item in enumerate(items, start=1):
            if control:
                control.sync_checkpoint()
            label = f"{result.platform} · {item.name or f'{item.kind}{item.index}'}"
            try:
                path = self._download_one(
                    webpage_url, item, base_name, n, label, progress, control)
                if path:
                    summary.files.append(DownloadedFile(path=path, label=label,
                                                        size_bytes=path.stat().st_size))
            except TaskCancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                summary.errors.append(f"{label} 下载失败: {exc}")
        return summary

    def _download_one(
        self,
        webpage_url: str,
        item: MediaItem,
        base_name: str,
        n: int,
        label: str,
        progress,
        control: Optional[DownloadControl] = None,
    ) -> Optional[Path]:
        format_spec = item.format_id or "best"
        # 视频档补音频合并（yt-dlp 无 ffmpeg 时自动降级）
        if item.kind == "video" and item.format_id:
            format_spec = f"{item.format_id}+bestaudio/{item.format_id}/best"
        tmp_dir = self.out_dir / ".ydl_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        state: dict = {"finished": False}

        def hook(d: dict) -> None:
            # 取消时抛异常，让 yt-dlp 中断本次下载
            if control and control.is_cancelled:
                raise TaskCancelled()
            if d.get("status") == "downloading" and progress:
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                progress(label, int(d.get("downloaded_bytes") or 0), int(total or 0))
            elif d.get("status") == "finished":
                state["finished"] = True
                if progress:
                    progress(label, int(d.get("total_bytes") or 0), int(d.get("total_bytes") or 0))

        opts = {
            **self._base_opts(),
            "format": format_spec,
            "outtmpl": str(tmp_dir / f"tmp_{n}.%(ext)s"),
            "progress_hooks": [hook],
            "nopart": True,
            "overwrites": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    ydl.download([webpage_url])
                except yt_dlp.utils.DownloadError as exc:
                    if control and control.is_cancelled:
                        raise TaskCancelled() from exc
                    raise RuntimeError(str(exc) or "yt-dlp 下载失败") from exc
        except TaskCancelled:
            # 清理被中断下载的残留临时文件
            for leftover in tmp_dir.glob(f"tmp_{n}.*"):
                try:
                    leftover.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

        files = sorted(tmp_dir.glob(f"tmp_{n}.*"))
        if not files:
            raise RuntimeError("yt-dlp 未产出任何文件")
        src = files[0]
        ext = src.suffix or ".mp4"
        dest = unique_path(self.out_dir, f"{base_name}_{item.name or item.kind}{ext}")
        src.rename(dest)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass  # 目录非空（有其它并发下载）则保留
        return dest
