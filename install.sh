#!/usr/bin/env bash
# Bootstrap: use existing Python to build the venv. Never installs Python.
set -e
cd "${0%/*}" 2>/dev/null || true
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[x] 未检测到 Python。本脚本不会替你安装 Python, 请先装好再重跑:"
  echo "    Debian/Ubuntu: sudo apt install python3 python3-venv"
  echo "    macOS:         brew install python"
  exit 1
fi
exec "$PY" .agents/skills/ai-short-drama/scripts/setup_env.py "$@"
