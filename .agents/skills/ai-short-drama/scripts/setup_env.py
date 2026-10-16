# -*- coding: utf-8 -*-
r"""一键环境装配: 新机器上用任意 Python3.9+ 跑一次即可
用法(在工作区根目录): python .agents/skills/ai-short-drama/scripts/setup_env.py [--no-mirror]

做什么:
1. 在工作区创建 .venv 并安装 faster-whisper + numpy (workflow 只认 .venv/Scripts/python.exe)
2. 自检 ffmpeg / ffprobe 是否在 PATH
3. 定位 whisper 模型: config.json 的 whisper_model > 工作区 models/whisper-turbo
   > E:\ai-subtitle\models\whisper-turbo(老机器) > 留空(首次转写自动从 hf-mirror 下载)
4. 生成/更新 config.json (只补缺, 不覆盖已有 key)
仅标准库。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root

sys.stdout.reconfigure(encoding="utf-8")
WS = ws_root()
VENV_PY = os.path.join(WS, ".venv",
                       "Scripts/python.exe" if sys.platform == "win32" else "bin/python")
DEFAULT_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"


def find_model(cfg):
    if cfg.get("whisper_model"):
        return cfg["whisper_model"], "config 指定"
    for cand in [
        os.path.join(WS, "models", "whisper-turbo"),
        r"E:\ai-subtitle\models\whisper-turbo",
    ]:
        if os.path.exists(cand):
            return cand, "本机已有"
    return "", "(首次转写时自动下载 large-v3-turbo, 约1.6GB, 走 hf-mirror)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mirror", action="store_true", help="pip 不走清华镜像")
    a = ap.parse_args()

    report = {"workspace": WS, "steps": [], "issues": []}

    # 1. venv
    if not os.path.exists(VENV_PY):
        r = subprocess.run([sys.executable, "-m", "venv", os.path.join(WS, ".venv")])
        if r.returncode != 0 or not os.path.exists(VENV_PY):
            report["issues"].append("创建 .venv 失败(需要任意 Python 3.9+)")
            print(json.dumps(report, ensure_ascii=False))
            sys.exit(1)
        report["steps"].append("已创建 .venv")
    else:
        report["steps"].append(".venv 已存在")

    # 2. 依赖
    pkgs = ["faster-whisper", "numpy"]
    cmd = [VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "--quiet"] + pkgs
    if not a.no_mirror:
        cmd += ["-i", DEFAULT_MIRROR]
    r = subprocess.run(cmd)
    if r.returncode != 0 and not a.no_mirror:
        r = subprocess.run([VENV_PY, "-m", "pip", "install", "--disable-pip-version-check", "--quiet"] + pkgs)
    if r.returncode != 0:
        report["issues"].append("pip 安装 faster-whisper/numpy 失败(检查网络)")
    else:
        report["steps"].append("依赖已安装: " + ", ".join(pkgs))
        ver = subprocess.run([VENV_PY, "-c", "import faster_whisper;print(faster_whisper.__version__)"],
                             capture_output=True, text=True)
        report["faster_whisper"] = (ver.stdout or "").strip() or "?"
        try:
            import ctranslate2  # noqa: F401  (仅探测, .venv 里一定有)
        except Exception:
            pass
        cuda = subprocess.run([VENV_PY, "-c", "import ctranslate2;print(ctranslate2.get_cuda_device_count())"],
                              capture_output=True, text=True)
        n = (cuda.stdout or "").strip()
        report["cuda_devices"] = int(n) if n.isdigit() else 0

    # 3. ffmpeg
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool):
            report["steps"].append(tool + " OK")
        else:
            report["issues"].append(tool + " 不在 PATH (自动剪辑/媒体转写需要, 装好后重跑本脚本验证)")

    # 4. config.json
    cfg_path = os.path.join(WS, "config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    model, src = find_model(cfg)
    changed = False
    if model and cfg.get("whisper_model") != model:
        cfg["whisper_model"] = model
        changed = True
    if "provider" not in cfg:
        cfg["provider"] = "zhipu"
        changed = True
    if changed:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        report["steps"].append("config.json 已更新")
    report["whisper_model"] = model or "(自动下载)"
    report["whisper_model_source"] = src
    report["venv_python"] = ".venv/Scripts/python.exe"
    report["ok"] = not report["issues"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0 if not report["issues"] else 1)


if __name__ == "__main__":
    main()
