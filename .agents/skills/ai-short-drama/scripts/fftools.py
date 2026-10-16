# -*- coding: utf-8 -*-
"""ffmpeg/ffprobe 路径解析(所有脚本共用): PATH 优先, 数据根 tools/ffmpeg/ 兜底
配合 ensure_ffmpeg.py 使用(缺失时自动下载静态版到 tools/)。
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root

FF_DIR = os.path.join(ws_root(), "tools", "ffmpeg")


def _local(name):
    return os.path.join(FF_DIR, name + (".exe" if sys.platform == "win32" else ""))


def resolve(name):
    """'ffmpeg'/'ffprobe' → 可执行文件路径(优先 PATH, 其次本地 tools)"""
    found = shutil.which(name)
    if found:
        return found
    return _local(name)


def available():
    return shutil.which("ffmpeg") is not None or (os.path.exists(_local("ffmpeg")) and os.path.exists(_local("ffprobe")))


def ffmpeg_bin():
    return resolve("ffmpeg")


def ffprobe_bin():
    return resolve("ffprobe")
