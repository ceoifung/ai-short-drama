# -*- coding: utf-8 -*-
"""解说 TTS 配音: plan.json 的每个解说段 → 02_plan/audio_NN.mp3, 时长回写 plan
用法: python tts.py --project projects/<名>_recap [--force]
provider(config.json 的 tts.provider):
  edge — 免费微软接口(默认)。音色 tts.voice 默认 zh-CN-YunjianNeural(激情解说男声);
         语速 tts.rate 默认 +12%; 音调 tts.pitch 默认 +6Hz(更抓耳)
  volc — 火山豆包TTS(商业级情感音色, 实验性): 需 tts.appid + tts.token + tts.voice_type
退出码: 0=完成  3=TTS 不可用(渲染时回退字幕版)
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root  # noqa: F401
from fftools import ffprobe_bin

sys.stdout.reconfigure(encoding="utf-8")


def clean_for_speech(text):
    """去掉会导致 TTS 念出来的标记与括注"""
    text = re.sub(r"[（(【\[][^）)】\]]*[）)】\]]", "", text)  # 括注
    text = re.sub(r"【原声】", "", text)
    return text.strip()


def volc_tts(appid, token, voice_type, text, out):
    r = json.loads("{}")
    req = urllib.request.Request(
        "https://openspeech.bytedance.com/api/v1/tts",
        data=json.dumps({
            "app": {"appid": appid, "token": token, "cluster": "volcano_tts"},
            "user": {"uid": "ai-short-drama"},
            "audio": {"voice_type": voice_type, "encoding": "mp3", "speed_ratio": 1.12},
            "request": {"reqid": "%d" % int(time.time() * 1000), "text": text,
                        "text_cmd": "{\"ssml\": false}", "operation": "query"},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        r = json.loads(resp.read().decode("utf-8"))
    if r.get("code") != 3000 or not r.get("data"):
        raise RuntimeError("volc tts: %s" % json.dumps(r, ensure_ascii=False)[:200])
    with open(out, "wb") as f:
        f.write(base64.b64decode(r["data"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--force", action="store_true", help="无视已有音频全部重配")
    a = ap.parse_args()

    cfg = {}
    cfgp = os.path.join(ws_root(), "config.json")
    if os.path.exists(cfgp):
        try:
            with open(cfgp, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    tcfg = cfg.get("tts") or {}
    provider = tcfg.get("provider", "edge")

    plan_path = os.path.join(a.project, "02_plan", "plan.json")
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    segs = [s for s in plan.get("segments", []) if s.get("audio_mode") == "voiceover" and (s.get("narration_text") or "").strip()]
    if not segs:
        print(json.dumps({"ok": True, "voiced": 0, "note": "没有解说段"}))
        return

    if provider == "volc":
        appid, token = tcfg.get("appid", ""), tcfg.get("token", "")
        voice_type = tcfg.get("voice_type", "BV700_V2_streaming")
        if not appid or not token:
            print(json.dumps({"ok": False, "reason": "no_key",
                              "hint": "config.json 的 tts 需 appid+token(火山语音控制台获取); 本次回退请把 tts.provider 改回 edge"}, ensure_ascii=False))
            sys.exit(3)
        synth = None  # volc 走函数
    else:
        try:
            import edge_tts
        except ImportError:
            print(json.dumps({"ok": False, "reason": "no_edge_tts",
                              "hint": ".venv 未装 edge-tts: .venv/Scripts/python.exe -m pip install edge-tts"}, ensure_ascii=False))
            sys.exit(3)
        voice = tcfg.get("voice", "zh-CN-YunjianNeural")  # 激情解说男声
        rate = tcfg.get("rate", "+12%")
        pitch = tcfg.get("pitch", "+6Hz")

        import asyncio

        def synth(text, out):
            asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out))

    voiced, failed = 0, []
    for s in segs:
        sid = int(s["id"])
        out = os.path.join(a.project, "02_plan", "audio_%02d.mp3" % sid)
        text = clean_for_speech(s["narration_text"])
        if not text:
            continue
        if a.force or not (os.path.exists(out) and os.path.getsize(out) > 1024):
            ok = False
            for attempt in (1, 2):
                try:
                    if provider == "volc":
                        volc_tts(appid, token, voice_type, text, out)
                    else:
                        synth(text, out)
                    ok = True
                    break
                except Exception:
                    time.sleep(2 * attempt)
            if not ok:
                failed.append(sid)
                continue
        dur_r = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", out], capture_output=True, text=True)
        try:
            dur = float(dur_r.stdout.strip())
        except ValueError:
            failed.append(sid)
            continue
        s["tts_file"] = "02_plan/audio_%02d.mp3" % sid
        s["tts_duration"] = round(dur, 3)
        voiced += 1

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    total_tts = sum(float(s.get("tts_duration", 0)) for s in segs)
    out = {"ok": True, "voiced": voiced, "failed": failed, "provider": provider,
           "tts_total_seconds": round(total_tts, 1)}
    if provider == "volc":
        out["voice_type"] = voice_type
    else:
        out["voice"] = voice
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()

