# -*- coding: utf-8 -*-
"""Stage 4.5 参考图生成: 02_assets/*.json --图片API--> 02_assets/images/{name}.png
用法: python gen_assets.py --project projects/<剧名> [--provider zhipu|ark] [--only 名1,名2] [--extra "修正要求"] [--dry-run]

key 优先级: --key > 环境变量 ZHIPU_API_KEY / ARK_API_KEY > 工作区根目录 config.json
退出码: 0=全部成功(或dry-run)  1=有生成失败  3=未配置 key(调用方应跳过本阶段)
特性: 已存在的同名图默认跳过(断点续跑); 每条重试3次; manifest 记录全量状态
仅用标准库, 不需要装任何包。
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
WS_CONFIG = os.path.join(ws_root(), "config.json")


def out(d):
    print(json.dumps(d, ensure_ascii=False))


def load_config(provider_arg, key_arg):
    cfg = {}
    for p in [WS_CONFIG, os.path.join(HERE, "config.json")]:
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception:
                pass
            break
    provider = provider_arg or cfg.get("provider", "zhipu")
    env_key = os.environ.get("ZHIPU_API_KEY" if provider == "zhipu" else "ARK_API_KEY", "")
    cfg_key = cfg.get("zhipu_key" if provider == "zhipu" else "ark_key", "")
    key = key_arg or env_key or cfg_key
    return provider, key, cfg


def char_prompt(c, style, extra):
    return (
        "%s风格角色三视图立绘: 同一人物的正面、侧面、背面全身像水平并排, 站姿自然, 纯白背景, 写实摄影质感。"
        "%s, %s。外貌: %s。服装: %s。三个视角的长相、发型、服装必须完全一致。画面无文字、无水印。%s"
        % (style, c.get("gender", ""), c.get("age", ""), c.get("appearance", ""), c.get("costume", ""), extra or "")
    )


def scene_prompt(s, style, extra):
    return (
        "%s风格场景参考图: %s。写实、生活化、光线自然, 画面里无人物, 构图完整。无文字、无水印。%s"
        % (style, s.get("description", ""), extra or "")
    )


def prop_prompt(p, _style, extra):
    return "物品特写参考图: %s。纯白背景, 写实, 细节清晰。无文字、无水印。%s" % (p.get("description", ""), extra or "")


def call_api(provider, key, cfg, prompt, size):
    if provider == "zhipu":
        url = "https://open.bigmodel.cn/api/paas/v4/images/generations"
        body = {"model": cfg.get("zhipu_model", "cogview-4"), "prompt": prompt, "size": size}
    else:
        url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
        body = {"model": cfg.get("ark_model", "doubao-seedream-4-0-250828"), "prompt": prompt, "size": size}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode("utf-8"))
    item = (data.get("data") or [{}])[0]
    if item.get("url"):
        rq = urllib.request.Request(item["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(rq, timeout=180) as r:
            return r.read()
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    raise RuntimeError("响应里没有图片: " + json.dumps(data, ensure_ascii=False)[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--provider", default="", help="zhipu|ark, 默认读 config")
    ap.add_argument("--key", default="")
    ap.add_argument("--only", default="", help="只生成这些名字(逗号分隔), 用于失败重生成")
    ap.add_argument("--extra", default="", help="追加到提示词末尾的修正要求(抽检反馈)")
    ap.add_argument("--dry-run", action="store_true", help="只组提示词不调API, 不花钱")
    a = ap.parse_args()

    provider, key, cfg = load_config(a.provider, a.key)
    style = cfg.get("style", "真人现代短剧")
    assets_dir = os.path.join(a.project, "02_assets")
    img_dir = os.path.join(assets_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    tasks = []
    for kind, fname, size_key, mk in [
        ("character", "characters.json", "size_character", char_prompt),
        ("scene", "scenes.json", "size_scene", scene_prompt),
        ("prop", "props.json", "size_prop", prop_prompt),
    ]:
        p = os.path.join(assets_dir, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for item in json.load(f):
                name = item.get("name", "").strip()
                if not name:
                    continue
                if a.only and name not in [x.strip() for x in a.only.split(",")]:
                    continue
                size = cfg.get(size_key, "1440x720" if kind == "character" else "1024x1024")
                tasks.append({
                    "kind": kind, "name": name,
                    "file": os.path.join(img_dir, name + ".png"),
                    "prompt": mk(item, style, a.extra),
                    "size": size,
                })
    if not tasks:
        out({"ok": False, "issues": ["没有待生成的资产(检查 02_assets/*.json 或 --only 名单)"]})
        sys.exit(1)

    if a.dry_run:
        out({"ok": True, "dry_run": True, "count": len(tasks),
             "tasks": [{"name": t["name"], "kind": t["kind"], "size": t["size"], "prompt": t["prompt"]} for t in tasks]})
        sys.exit(0)

    if not key:
        out({"ok": False, "reason": "no_key",
             "hint": "在 E:\\AI短剧\\config.json 配 provider/zhipu_key(或 ark_key), 或设环境变量后重跑; 本次跳过参考图生成"})
        sys.exit(3)

    manifest_path = os.path.join(img_dir, "manifest.json")
    manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []
    done = {m.get("name"): m for m in manifest}

    failed = []
    for t in tasks:
        if os.path.exists(t["file"]) and not a.extra:
            entry = {"name": t["name"], "kind": t["kind"], "file": t["file"].replace("\\", "/"), "status": "ok", "note": "已存在, 跳过"}
            done[t["name"]] = entry
            continue
        ok = False
        err = ""
        for attempt in range(1, 4):
            try:
                blob = call_api(provider, key, cfg, t["prompt"], t["size"])
                with open(t["file"], "wb") as f:
                    f.write(blob)
                ok = True
                break
            except urllib.error.HTTPError as e:
                err = "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:200])
                if e.code in (401, 403):
                    break  # key 无效, 重试无意义
            except Exception as e:
                err = str(e)[:200]
            time.sleep(2 * attempt)
        entry = {"name": t["name"], "kind": t["kind"], "file": t["file"].replace("\\", "/"),
                 "status": "ok" if ok else "failed", "error": "" if ok else err, "provider": provider}
        done[t["name"]] = entry
        if not ok:
            failed.append(t["name"])

    result = list(done.values())
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    out({"ok": len(failed) == 0, "generated": len(tasks) - len(failed), "failed": failed,
         "dir": img_dir.replace("\\", "/")})
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
