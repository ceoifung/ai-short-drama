# -*- coding: utf-8 -*-
r"""配置向导: 把图片API等配置保存到工作区 config.json (供 AI 代填或终端自填)

- AI 代填:   python configure.py --provider zhipu --key sk-xxx [--no-validate]
- 终端自填:  python configure.py            (交互式, 需要真实终端)
- 查状态:    python configure.py --check    (输出 JSON, 供 AI 判断是否需要引导配置)

默认会用 key 生成一张 1024x1024 测试图验证有效性(约几分钱); --no-validate 跳过。
仅标准库。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root, is_global_install

sys.stdout.reconfigure(encoding="utf-8")
WS = ws_root()
CFG = os.path.join(WS, "config.json")

PROVIDERS = {
    "zhipu": {
        "name": "智谱 CogView-4",
        "url": "https://open.bigmodel.cn/api/paas/v4/images/generations",
        "model": "cogview-4", "model_field": "zhipu_model",
        "key_field": "zhipu_key", "env": "ZHIPU_API_KEY",
        "where": "open.bigmodel.cn 右上角控制台 → API Keys",
    },
    "ark": {
        "name": "火山方舟 Seedream",
        "url": "https://ark.cn-beijing.volces.com/api/v3/images/generations",
        "model": "doubao-seedream-4-0-250828", "model_field": "ark_model",
        "key_field": "ark_key", "env": "ARK_API_KEY",
        "where": "console.volcengine.com/ark → API Key 管理",
    },
}


def load():
    if os.path.exists(CFG):
        try:
            with open(CFG, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save(cfg):
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def mask(k):
    return (k[:6] + "..." + k[-4:]) if len(k) > 12 else "***"


def validate(provider, key, cfg):
    """发一张测试图验证 key, 返回 (ok, msg)。约几分钱。"""
    p = PROVIDERS[provider]
    body = {"model": cfg.get(p["model_field"], p["model"]), "prompt": "一只线描小猫", "size": "1024x1024"}
    req = urllib.request.Request(
        p["url"], data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            json.loads(r.read().decode("utf-8"))
        return True, "key 有效(已用一张测试图验证)"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        return False, "HTTP %s: %s" % (e.code, detail)
    except Exception as e:
        return False, str(e)[:200]


def current_status():
    cfg = load()
    provider = cfg.get("provider", "")
    key = cfg.get(PROVIDERS[provider]["key_field"], "") if provider in PROVIDERS else ""
    venv_py = os.path.join(WS, ".venv",
                           "Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return {
        "mode": "global" if is_global_install() else "workspace",
        "data_root": WS,
        "config_file": CFG,
        "provider": provider or "(未设置)",
        "provider_name": PROVIDERS[provider]["name"] if provider in PROVIDERS else "",
        "key_set": bool(key),
        "key_masked": mask(key) if key else "",
        "whisper_model": cfg.get("whisper_model", "(自动解析)"),
        "venv_python": venv_py,
        "venv_ok": os.path.exists(venv_py),
        "projects_dir": os.path.join(WS, "projects"),
        "need_setup": not bool(key),
    }


def do_configure(provider, key, no_validate):
    if provider not in PROVIDERS:
        print(json.dumps({"ok": False, "error": "provider 必须是 " + "/".join(PROVIDERS)}, ensure_ascii=False))
        sys.exit(1)
    cfg = load()
    cfg["provider"] = provider
    cfg[PROVIDERS[provider]["key_field"]] = key
    save(cfg)
    if no_validate:
        print(json.dumps({"ok": True, "saved": CFG, "provider": provider, "validated": False}, ensure_ascii=False))
        return 0
    ok, msg = validate(provider, key, cfg)
    print(json.dumps({"ok": ok, "saved": CFG, "provider": provider, "validated": ok, "message": msg}, ensure_ascii=False))
    return 0 if ok else 1


def interactive():
    if not sys.stdin.isatty():
        print(json.dumps({"ok": False, "error": "非交互终端; AI 请用 --provider/--key 代填, 或先 --check"}, ensure_ascii=False))
        sys.exit(2)
    print("== AI短剧 配置向导 ==")
    print("1) 智谱 CogView-4   (open.bigmodel.cn)")
    print("2) 火山方舟 Seedream (console.volcengine.com/ark)")
    print("3) 暂不配置 (参考图走人工通道)")
    choice = input("选择 1/2/3: ").strip()
    if choice == "3":
        print("已跳过。之后随时运行本脚本重新配置。")
        return 0
    provider = {"1": "zhipu", "2": "ark"}.get(choice)
    if not provider:
        print("无效选择")
        return 1
    p = PROVIDERS[provider]
    print("获取 key: " + p["where"])
    key = input("粘贴 API key: ").strip()
    if not key:
        print("key 为空, 未保存")
        return 1
    return do_configure(provider, key, no_validate=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="", help="zhipu|ark")
    ap.add_argument("--key", default="")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        print(json.dumps(current_status(), ensure_ascii=False, indent=2))
        return
    if a.provider and a.key:
        sys.exit(do_configure(a.provider, a.key, a.no_validate))
    sys.exit(interactive())


if __name__ == "__main__":
    main()
