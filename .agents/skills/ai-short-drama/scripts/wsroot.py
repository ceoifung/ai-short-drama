# -*- coding: utf-8 -*-
"""工作区根目录解析(所有脚本共用)。两种安装模式都支持:
- 项目模式: 技能在 <工作区>/.agents/skills/ai-short-drama (或 .zcode/skills/) → 工作区即数据根
- 全局模式: 技能在 <用户主目录>/.agents/skills/ai-short-drama → 数据根为 ~/.ai-short-drama/
  (.venv / config.json / models / projects 都放这里, 自动创建)
锚定顺序:
1. 当前目录是工作区(其 .zcode 或 .agents 下存在本技能) → 当前目录
2. 脚本位置反推: 上四级若是用户主目录 → 全局模式数据根; 否则视为工作区
3. 都不中则报错退出。
"""
import os

SKILL_DIRS = (".zcode", ".agents")


def _looks_like_ws(d):
    for marker in SKILL_DIRS:
        if os.path.isdir(os.path.join(d, marker, "skills", "ai-short-drama")):
            return True
    return False


def global_data_root():
    """全局模式的数据根目录"""
    home = os.path.expanduser("~")
    return os.path.join(home, ".ai-short-drama")


def is_global_install():
    """本技能是否装在用户主目录(全局模式)"""
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir, os.pardir))
    home = os.path.expanduser("~")
    return os.path.normcase(cand) == os.path.normcase(home)


def ws_root():
    home = os.path.expanduser("~")
    cwd = os.getcwd()
    if os.path.normcase(cwd) != os.path.normcase(home) and _looks_like_ws(cwd):
        return cwd
    if is_global_install():
        root = global_data_root()
        os.makedirs(root, exist_ok=True)
        return root
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.abspath(os.path.join(here, os.pardir, os.pardir, os.pardir, os.pardir))
    if _looks_like_ws(cand):
        return cand
    raise SystemExit(
        "找不到数据根目录。项目模式请在工作区根目录运行(技能须在 <工作区>/.agents/skills/ 下); "
        "全局模式请用 install.py 安装到 ~/.agents/skills/。"
    )
