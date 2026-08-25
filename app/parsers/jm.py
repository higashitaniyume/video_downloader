"""JMComic (禁漫天堂) 解析与下载模块。

基于 jmcomic-crawler-python (jmcomic) 库实现：
- 支持字符串格式：“jm132456”、“jm 123456”（不区分大小写）及各类禁漫网页链接。
- 支持将解析的漫画转换为 PDF 文件或解密保存为图片文件夹。
- 兼容跨平台环境（桌面端与 Android Chaquopy）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from app.common import DownloadSummary, DownloadedFile, sanitize_filename, unique_path
from app.control import DownloadControl, TaskCancelled
from app.engine import MediaItem, ParseResult

logger = logging.getLogger(__name__)

# 匹配 jm 标识符（如 jm123456、jm 123456、JM 123456、JM:123456）
_JM_PATTERN = re.compile(r"(?i)\bjm\s*[:：]?\s*(\d{4,9})\b")
# 匹配禁漫相关域名网页链接中的 album/photo ID
_JM_URL_PATTERN = re.compile(
    r"https?://(?:[^/\s]+\.)?(?:18comic|jmcomic)[^/\s]*/(?:album|photo)/(\d+)",
    re.IGNORECASE,
)
_JM_URL_PARAM_PATTERN = re.compile(
    r"https?://(?:[^/\s]+\.)?(?:18comic|jmcomic)[^/\s]*[?&]id=(\d+)",
    re.IGNORECASE,
)


def extract_jm_id(text: str) -> Optional[str]:
    """从文本或链接中提取 JM 漫画 ID（数字字符串）。"""
    text = (text or "").strip()
    if not text:
        return None

    # 1. 匹配网址
    m_url = _JM_URL_PATTERN.search(text)
    if m_url:
        return m_url.group(1)
    m_param = _JM_URL_PARAM_PATTERN.search(text)
    if m_param:
        return m_param.group(1)

    # 2. 匹配 jm123456 / jm 123456 等字符串
    m_code = _JM_PATTERN.search(text)
    if m_code:
        return m_code.group(1)

    # 3. 纯数字如果带有 jm 前缀或直接为合法 ID
    if text.lower().startswith("jm"):
        digits = "".join(c for c in text if c.isdigit())
        if digits:
            return digits

    return None


def extract_all_jm_targets(text: str) -> list[str]:
    """提取文本中所有 JM 相关的目标标识符（例如 'jm123456'）或链接。"""
    found: list[str] = []
    seen: set[str] = set()

    # 提取 jm 编码
    for match in _JM_PATTERN.finditer(text):
        full_match = match.group(0).strip()
        aid = match.group(1)
        normalized = f"jm{aid}"
        if normalized not in seen:
            seen.add(normalized)
            found.append(full_match)

    # 提取 jm 相关 URL
    for match in _JM_URL_PATTERN.finditer(text):
        url = match.group(0).strip()
        aid = match.group(1)
        normalized = f"jm{aid}"
        if normalized not in seen:
            seen.add(normalized)
            found.append(url)

    return found


class JMParser:
    """JMComic 漫画解析器。"""

    def __init__(self, proxy: str = ""):
        self.proxy = (proxy or "").strip()

    @classmethod
    def can_parse(cls, target: str) -> bool:
        """检查目标是否为 JM 漫画代码或禁漫网页链接。"""
        if not target:
            return False
        return extract_jm_id(target) is not None

    def _build_jm_option(self):
        """构建兼容桌面端与 Android 端（Chaquopy）的 JmOption。"""
        import jmcomic

        client_cfg: dict[str, Any] = {
            "postman": {
                "type": "requests",
                "meta_data": {
                    "impersonate": "chrome",
                    "proxies": {},
                },
            },
            "retry_times": 3,
        }

        if self.proxy:
            client_cfg["postman"]["meta_data"]["proxies"] = {
                "http": self.proxy,
                "https": self.proxy,
            }

        return jmcomic.JmOption.construct(
            {
                "log": False,
                "client": client_cfg,
                "download": {
                    "cache": True,
                    "image": {"decode": True},
                },
            }
        )

    def parse_sync(self, target: str) -> Optional[ParseResult]:
        """同步解析 JM 漫画详情（可在后台线程中调用）。"""
        aid = extract_jm_id(target)
        if not aid:
            return None

        try:
            import jmcomic

            option = self._build_jm_option()
            client = option.build_jm_client()

            # 获取本子详情
            album = client.get_album_detail(aid)
            if not album:
                return ParseResult(
                    url=target,
                    platform="jm",
                    parser_name="jm",
                    error=f"未能获取到 JM{aid} 的漫画信息",
                )

            title = album.name or f"JM{aid}"
            author = album.author or (album.authors[0] if album.authors else "未知作者")
            desc_parts = []
            if album.tags:
                desc_parts.append(f"标签: {', '.join(album.tags[:10])}")
            if album.works:
                desc_parts.append(f"作品: {', '.join(album.works[:5])}")
            if album.actors:
                desc_parts.append(f"角色: {', '.join(album.actors[:5])}")
            desc_parts.append(f"总页数: {album.page_count}P")
            desc = " | ".join(desc_parts)

            # 封面图
            cover_url = jmcomic.JmcomicText.get_album_cover_url(aid)
            cover_urls = [cover_url] if cover_url else []

            # 构造 MediaItem 清单
            items: list[MediaItem] = []
            item_index = 1

            # 1. 默认全本项
            items.append(
                MediaItem(
                    index=item_index,
                    kind="pdf",
                    name="全部章节 (PDF文件)",
                    format_id="pdf:all",
                    urls=[f"jm://{aid}/all/pdf"],
                )
            )
            item_index += 1

            items.append(
                MediaItem(
                    index=item_index,
                    kind="image",
                    name="全部章节 (图片文件夹)",
                    format_id="images:all",
                    urls=[f"jm://{aid}/all/images"],
                )
            )
            item_index += 1

            # 2. 如果存在多个章节，补充单章节可选条目
            if len(album.episode_list) > 1:
                for ep_id, ep_idx, ep_title, *rest in album.episode_list:
                    items.append(
                        MediaItem(
                            index=item_index,
                            kind="pdf",
                            name=f"第{ep_idx}话 (PDF) - {ep_title}",
                            format_id=f"pdf:{ep_id}:{ep_idx}",
                            urls=[f"jm://{aid}/ep/{ep_id}/pdf"],
                        )
                    )
                    item_index += 1

                    items.append(
                        MediaItem(
                            index=item_index,
                            kind="image",
                            name=f"第{ep_idx}话 (图片) - {ep_title}",
                            format_id=f"images:{ep_id}:{ep_idx}",
                            urls=[f"jm://{aid}/ep/{ep_id}/images"],
                        )
                    )
                    item_index += 1

            return ParseResult(
                url=target,
                platform="jm",
                parser_name="jm",
                title=f"[JM{aid}] {title}",
                author=author,
                desc=desc,
                timestamp=album.pub_date or "",
                duration_ms=0,
                cover_urls=cover_urls,
                items=items,
                raw={
                    "album_id": aid,
                    "name": album.name,
                    "scramble_id": album.scramble_id,
                    "page_count": album.page_count,
                    "episode_list": album.episode_list,
                },
            )

        except Exception as exc:
            logger.exception("JMComic 解析失败: %s", exc)
            return ParseResult(
                url=target,
                platform="jm",
                parser_name="jm",
                error=f"JM 解析失败: {exc}",
            )

    async def parse(self, target: str) -> Optional[ParseResult]:
        """异步解析入口。"""
        return await asyncio.to_thread(self.parse_sync, target)


class JMDownloader:
    """JMComic 漫画下载器：支持图片解密保存与 PDF 格式合成。"""

    def __init__(self, out_dir: str | Path, proxy: str = ""):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = (proxy or "").strip()

    def _build_jm_option(self):
        import jmcomic

        client_cfg: dict[str, Any] = {
            "postman": {
                "type": "requests",
                "meta_data": {
                    "impersonate": "chrome",
                    "proxies": {},
                },
            },
            "retry_times": 3,
        }

        if self.proxy:
            client_cfg["postman"]["meta_data"]["proxies"] = {
                "http": self.proxy,
                "https": self.proxy,
            }

        return jmcomic.JmOption.construct(
            {
                "log": False,
                "client": client_cfg,
                "download": {
                    "cache": True,
                    "image": {"decode": True},
                },
            }
        )

    def download_result_sync(
        self,
        result: ParseResult,
        items: list[MediaItem],
        progress: Optional[Callable[[str, int, Optional[int]], None]] = None,
        control: Optional[DownloadControl] = None,
    ) -> DownloadSummary:
        """同步执行 JM 漫画下载与转换。"""
        import jmcomic

        summary = DownloadSummary()
        aid = result.raw.get("album_id") or extract_jm_id(result.url)
        if not aid:
            summary.errors.append(f"无效的 JM 目标: {result.url}")
            return summary

        try:
            option = self._build_jm_option()
            client = option.build_jm_client()

            album = client.get_album_detail(aid)
            if not album:
                summary.errors.append(f"获取 JM{aid} 章节失败")
                return summary

            album_safe_title = sanitize_filename(f"JM{aid}_{album.name}")
            base_album_dir = self.out_dir / album_safe_title
            base_album_dir.mkdir(parents=True, exist_ok=True)

            selected_items = items or result.items
            download_pdf_all = any(it.format_id == "pdf:all" for it in selected_items)
            download_images_all = any(it.format_id == "images:all" for it in selected_items)

            # 收集需要处理的章节 ID
            episodes_to_fetch = []
            for item in selected_items:
                if item.format_id.startswith("pdf:") and item.format_id != "pdf:all":
                    parts = item.format_id.split(":")
                    if len(parts) >= 2:
                        episodes_to_fetch.append((parts[1], "pdf", item.name))
                elif item.format_id.startswith("images:") and item.format_id != "images:all":
                    parts = item.format_id.split(":")
                    if len(parts) >= 2:
                        episodes_to_fetch.append((parts[1], "images", item.name))

            # 判断是否需要下载全部章节
            needs_all = download_pdf_all or download_images_all or (not episodes_to_fetch)
            target_ep_ids = set(ep[0] for ep in episodes_to_fetch)

            # 筛选需要下载的章节列表
            all_photos: list[tuple[str, str, str, Path]] = []
            for ep_info in album.episode_list:
                ep_id, ep_idx, ep_title = str(ep_info[0]), str(ep_info[1]), str(ep_info[2])
                if needs_all or ep_id in target_ep_ids:
                    ep_safe_name = sanitize_filename(f"ep{ep_idx}_{ep_title}")
                    ep_dir = base_album_dir / ep_safe_name
                    all_photos.append((ep_id, ep_idx, ep_title, ep_dir))

            # 统计总图片数并获取章节详情
            photo_details = []
            total_images_count = 0
            for ep_id, ep_idx, ep_title, ep_dir in all_photos:
                if control and control.is_cancelled:
                    raise TaskCancelled()
                if progress:
                    progress(f"正在读取章节信息 [{ep_title}]...", 0, 0)
                p_detail = client.get_photo_detail(ep_id)
                photo_details.append((p_detail, ep_idx, ep_title, ep_dir))
                total_images_count += len(p_detail)

            # 收集全部待下载图片任务
            download_tasks = []
            downloaded_img_paths_by_ep: dict[str, list[Path]] = {}
            all_downloaded_images: list[Path] = []

            for p_detail, ep_idx, ep_title, ep_dir in photo_details:
                ep_dir.mkdir(parents=True, exist_ok=True)
                downloaded_img_paths_by_ep[p_detail.photo_id] = []
                for img_detail in p_detail:
                    img_filename = f"{img_detail.index:05d}.jpg"
                    img_dest = ep_dir / img_filename
                    downloaded_img_paths_by_ep[p_detail.photo_id].append(img_dest)
                    all_downloaded_images.append(img_dest)
                    download_tasks.append((img_detail, img_dest, ep_idx))

            import threading
            from concurrent.futures import ThreadPoolExecutor

            done_images = 0
            progress_lock = threading.Lock()

            def _download_worker(task):
                nonlocal done_images
                if control and control.is_cancelled:
                    return
                img_det, img_dst, ep_i = task
                if not img_dst.exists() or img_dst.stat().st_size == 0:
                    client.download_by_image_detail(
                        img_det,
                        str(img_dst),
                        decode_image=True,
                    )
                with progress_lock:
                    done_images += 1
                    cur_done = done_images
                if progress:
                    pct = int(cur_done * 100 / total_images_count) if total_images_count > 0 else 0
                    progress(
                        f"JMComic 下载解密中: {cur_done}/{total_images_count}P ({pct}%)",
                        cur_done,
                        total_images_count,
                    )

            # 并发执行图片下载（6个并发工作线程）
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(_download_worker, t) for t in download_tasks]
                for f in futures:
                    if control and control.is_cancelled:
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise TaskCancelled()
                    f.result()

            # ──────────────────── 输出处理 ────────────────────

            # 1. 保存为图片文件夹 (全本)
            if download_images_all:
                summary.files.append(
                    DownloadedFile(
                        path=base_album_dir,
                        label=f"[JM{aid}] 全本图片文件夹",
                        kind="image",
                        size_bytes=sum(p.stat().st_size for p in all_downloaded_images if p.exists()),
                    )
                )

            # 2. 保存为单章节图片文件夹
            for ep_id, kind, item_name in episodes_to_fetch:
                if kind == "images" and not download_images_all:
                    ep_paths = downloaded_img_paths_by_ep.get(ep_id, [])
                    if ep_paths:
                        ep_dir = ep_paths[0].parent
                        summary.files.append(
                            DownloadedFile(
                                path=ep_dir,
                                label=f"[JM{aid}] {item_name}",
                                kind="image",
                                size_bytes=sum(p.stat().st_size for p in ep_paths if p.exists()),
                            )
                        )

            # 3. 合成全本 PDF
            if download_pdf_all:
                if progress:
                    progress("正在合成全本 PDF...", done_images, total_images_count)
                all_sorted_images = sorted(all_downloaded_images, key=lambda p: (str(p.parent), p.name))
                pdf_path = unique_path(self.out_dir, f"{album_safe_title}.pdf")
                self._create_pdf(all_sorted_images, pdf_path)
                summary.files.append(
                    DownloadedFile(
                        path=pdf_path,
                        label=f"[JM{aid}] 全本 PDF",
                        kind="pdf",
                        size_bytes=pdf_path.stat().st_size if pdf_path.exists() else 0,
                    )
                )

            # 4. 合成分章节 PDF
            for ep_id, kind, item_name in episodes_to_fetch:
                if kind == "pdf":
                    ep_paths = downloaded_img_paths_by_ep.get(ep_id, [])
                    if ep_paths:
                        ep_idx = ""
                        for p_det, p_idx, _, _ in photo_details:
                            if p_det.photo_id == ep_id:
                                ep_idx = p_idx
                                break
                        ep_pdf_name = f"{album_safe_title}_第{ep_idx}话.pdf"
                        ep_pdf_path = unique_path(self.out_dir, ep_pdf_name)
                        if progress:
                            progress(f"正在合成第{ep_idx}话 PDF...", done_images, total_images_count)
                        self._create_pdf(ep_paths, ep_pdf_path)
                        summary.files.append(
                            DownloadedFile(
                                path=ep_pdf_path,
                                label=f"[JM{aid}] {item_name}",
                                kind="pdf",
                                size_bytes=ep_pdf_path.stat().st_size if ep_pdf_path.exists() else 0,
                            )
                        )

            # 如果既未勾选全本也没选具体项（例如 CLI 直接下载全部）
            if not summary.files and not summary.errors:
                # 默认全本 PDF 与 图片均产出
                pdf_path = unique_path(self.out_dir, f"{album_safe_title}.pdf")
                self._create_pdf(all_downloaded_images, pdf_path)
                summary.files.append(
                    DownloadedFile(
                        path=pdf_path,
                        label=f"[JM{aid}] 全本 PDF",
                        kind="pdf",
                        size_bytes=pdf_path.stat().st_size if pdf_path.exists() else 0,
                    )
                )
                summary.files.append(
                    DownloadedFile(
                        path=base_album_dir,
                        label=f"[JM{aid}] 全本图片文件夹",
                        kind="image",
                        size_bytes=sum(p.stat().st_size for p in all_downloaded_images if p.exists()),
                    )
                )

        except TaskCancelled:
            logger.info("JM 下载任务已被用户取消")
            raise
        except Exception as exc:
            logger.exception("JM 下载处理发生异常: %s", exc)
            summary.errors.append(f"下载失败: {exc}")

        return summary

    @staticmethod
    def _create_pdf(image_paths: list[Path], output_pdf: Path) -> None:
        """将一组图片合成为单个 PDF 文件（优先 img2pdf 无损合成，Pillow 作为兼容兜底）。"""
        valid_paths = [p for p in image_paths if p.exists() and p.stat().st_size > 0]
        if not valid_paths:
            raise RuntimeError("没有可用于合成 PDF 的图片")

        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        try:
            import img2pdf

            with open(output_pdf, "wb") as f:
                f.write(img2pdf.convert([str(p) for p in valid_paths]))
            return
        except Exception as exc:
            logger.debug("img2pdf 转换失败，使用 Pillow 兜底: %s", exc)

        from PIL import Image
        import io

        images: list[Image.Image] = []
        try:
            for p in valid_paths:
                img = None
                try:
                    img = Image.open(p)
                except Exception:
                    try:
                        from android.graphics import BitmapFactory, Bitmap
                        from java.io import ByteArrayOutputStream
                        with open(p, "rb") as f:
                            raw = f.read()
                        bmp = BitmapFactory.decodeByteArray(raw, 0, len(raw))
                        if bmp is not None:
                            stream = ByteArrayOutputStream()
                            bmp.compress(Bitmap.CompressFormat.PNG, 100, stream)
                            png_bytes = bytes(stream.toByteArray())
                            bmp.recycle()
                            img = Image.open(io.BytesIO(png_bytes))
                    except BaseException:
                        pass
                if img is None:
                    continue
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                images.append(img)

            if images:
                images[0].save(
                    str(output_pdf),
                    save_all=True,
                    append_images=images[1:],
                    resolution=100.0,
                )
        finally:
            for img in images:
                try:
                    img.close()
                except Exception:
                    pass
