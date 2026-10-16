# -*- coding: utf-8 -*-
r"""安装器: 把本技能装到用户主目录, 实现"任何项目里说'做短剧'都能用"

用法(任意 python, 在仓库根或技能目录均可):
    python .agents/skills/ai-short-drama/scripts/install.py            # 全局安装
    python .agents/skills/ai-short-drama/scripts/install.py --uninstall  # 卸载

做什么:
1. 复制技能目录到 ~/.agents/skills/ai-short-drama (跨工具标准全局位, ZCode/Claude Code 等都能发现)
2. 立即用新位置跑 setup_env.py: 在 ~/.ai-short-drama/ 建 .venv、装依赖、定位模型、写 config
   (config/models/projects 以后都在 ~/.ai-short-drama/ 下, 不污染任何项目)
注意:
- ZCode 的全自动 workflow 是项目级的, 全局安装只有"手动流程"(PLAYBOOK) + 全部门禁脚本。
  要全自动编排请用"克隆仓库当工作区"的方式安装。
- 已存在同名全局技能会被覆盖(先删除再复制)。
仅标准库。
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_SKILL = os.path.abspath(os.path.join(HERE, os.pardir))  # .../ai-short-drama
HOME = os.path.expanduser("~")
DST_SKILL = os.path.join(HOME, ".agents", "skills", "ai-short-drama")
DATA_ROOT = os.path.join(HOME, ".ai-short-drama")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()

    if a.uninstall:
        if os.path.isdir(DST_SKILL):
            shutil.rmtree(DST_SKILL)
            print("已卸载全局技能: " + DST_SKILL)
        if os.path.isdir(DATA_ROOT):
            print("数据目录保留(内有你的 config/模型/项目): " + DATA_ROOT + "  确认不要可手动删除")
        return

    if os.path.abspath(SRC_SKILL) == os.path.abspath(DST_SKILL):
        print("已经在全局位置, 无需安装。")
        return

    os.makedirs(os.path.dirname(DST_SKILL), exist_ok=True)
    if os.path.isdir(DST_SKILL):
        shutil.rmtree(DST_SKILL)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(SRC_SKILL, DST_SKILL, ignore=ignore)
    print("已复制技能到: " + DST_SKILL)

    setup = os.path.join(DST_SKILL, "scripts", "setup_env.py")
    print("\n开始装配数据目录 " + DATA_ROOT + " (建 .venv / 装依赖 / 定位模型)...\n")
    r = subprocess.run([sys.executable, setup])
    venv_py = os.path.join(DATA_ROOT, ".venv",
                           "Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    print("\n" + "=" * 50)
    print("安装完成!")
    print("  全局技能:   " + DST_SKILL)
    print("  数据根:     " + DATA_ROOT + "  (config.json / models / projects 都在这里)")
    print("  python:     " + venv_py)
    print("  下一步:     对你的 AI 说「做短剧」, 或先跑")
    print("              " + venv_py + " " + os.path.join(DST_SKILL, "scripts", "configure.py") + " --check")
    print("  提示:       ZCode 用户要全自动编排请改为克隆整个仓库作工作区")
    sys.exit(0 if r.returncode == 0 else 1)


if __name__ == "__main__":
    main()
