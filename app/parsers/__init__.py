"""专属平台解析器模块。"""
from .douyin import DouyinParser
from .jm import JMDownloader, JMParser

__all__ = ["DouyinParser", "JMParser", "JMDownloader"]
