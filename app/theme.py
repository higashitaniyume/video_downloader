"""UI 主题工具：使用系统默认字体（替代 customtkinter 默认的 Roboto）。

customtkinter 默认字体族是 Roboto（Windows 上通常未安装），中文界面会回退到
系统字体但西文/数字渲染不一致。这里读取 TkDefaultFont 的实际字体族
（Windows 上为 Segoe UI / 微软雅黑）统一用于所有控件。
"""
from __future__ import annotations

import tkinter.font as tkfont

import customtkinter as ctk

_SYSTEM_FAMILY: str = ""


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    """创建使用系统默认字体族的 CTkFont。

    首次调用时（此时 Tk root 已创建）读取系统默认字体的实际 family 并缓存；
    读取失败则退回 customtkinter 默认行为。
    """
    global _SYSTEM_FAMILY
    if not _SYSTEM_FAMILY:
        try:
            _SYSTEM_FAMILY = tkfont.nametofont("TkDefaultFont").actual("family")
        except Exception:  # noqa: BLE001
            _SYSTEM_FAMILY = ""
    kwargs: dict = {"size": size, "weight": weight}
    if _SYSTEM_FAMILY:
        kwargs["family"] = _SYSTEM_FAMILY
    return ctk.CTkFont(**kwargs)
