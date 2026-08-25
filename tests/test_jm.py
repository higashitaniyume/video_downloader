import os
import tempfile
from pathlib import Path
import pytest
from PIL import Image

from app.parsers.jm import (
    JMParser,
    JMDownloader,
    extract_jm_id,
    extract_all_jm_targets,
)
from app.engine import ParseEngine


def test_extract_jm_id():
    assert extract_jm_id("jm123456") == "123456"
    assert extract_jm_id("jm 123456") == "123456"
    assert extract_jm_id("JM123456") == "123456"
    assert extract_jm_id("JM 123456") == "123456"
    assert extract_jm_id("Jm 987654") == "987654"
    assert extract_jm_id("jm:123456") == "123456"
    assert extract_jm_id("JM：123456") == "123456"
    assert extract_jm_id("https://18comic.vip/album/456789") == "456789"
    assert extract_jm_id("https://18comic.org/photo/456789") == "456789"
    assert extract_jm_id("https://jmcomic.me/album/456789?id=456789") == "456789"
    assert extract_jm_id("推荐看这本：jm 132456，很棒") == "132456"
    assert extract_jm_id("invalid string without jm") is None


def test_can_parse():
    assert JMParser.can_parse("jm123456") is True
    assert JMParser.can_parse("jm 123456") is True
    assert JMParser.can_parse("JM 123456") is True
    assert JMParser.can_parse("https://18comic.vip/album/123456") is True
    assert JMParser.can_parse("https://www.bilibili.com/video/BV1xx411c7mD") is False


def test_engine_extract_links_with_jm():
    engine = ParseEngine(ydl_enabled=False)
    text = (
        "分享一个视频 https://www.douyin.com/video/7123456789012345678 "
        "以及两本漫画 jm123456 和 JM 654321，还有 https://18comic.vip/album/999999"
    )
    links = engine.extract_links(text)
    assert "https://www.douyin.com/video/7123456789012345678" in links
    assert "jm123456" in links or "jm 123456" in [l.lower() for l in links]
    assert any("654321" in l for l in links)
    assert "https://18comic.vip/album/999999" in links


def test_pdf_creation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # 创建两张测试图片
        img1_path = tmp_path / "00001.jpg"
        img2_path = tmp_path / "00002.jpg"

        img1 = Image.new("RGB", (200, 300), color=(255, 0, 0))
        img1.save(img1_path)

        img2 = Image.new("RGB", (200, 300), color=(0, 0, 255))
        img2.save(img2_path)

        pdf_out = tmp_path / "output.pdf"
        JMDownloader._create_pdf([img1_path, img2_path], pdf_out)

        assert pdf_out.exists()
        assert pdf_out.stat().st_size > 0
