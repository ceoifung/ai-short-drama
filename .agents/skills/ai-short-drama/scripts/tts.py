# -*- coding: utf-8 -*-
"""解说 TTS 配音: plan.json 的每个解说段 → 02_plan/audio_NN.mp3, 时长回写 plan
用法: python tts.py --project projects/<名>_recap
- 断点续跑(已存在的音频直接测时长); 每段重试2次
- 音色/语速: config.json 的 tts.voice(默认 zh-CN-XiaoxiaoNeural) / tts.rate(默认 "+0%")
退出码: 0=完成(部分失败也算, 失败段无 tts_duration 渲染时自动回退字幕)  3=edge-tts 不可用(静音字幕版)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root  # noqa: F401
from fftools import ffprobe_bin

sys.stdout.reconfigure(encoding="utf-8")


def clean_for_speech(text):
    """去掉会导致 TTS 念出来的标记与括注"""
    text = re.sub(r"[（(【\[][^）)】\]]*[）)】\]]", "", text)  # 括注
    text = re.sub(r"【原声】", "", text)
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()

    try:
        import edge_tts
    except ImportError:
        print(json.dumps({"ok": False, "reason": "no_edge_tts",
                          "hint": ".venv 未装 edge-tts: .venv/Scripts/python.exe -m pip install edge-tts"}, ensure_ascii=False))
        sys.exit(3)

    cfg = {}
    cfgp = os.path.join(ws_root(), "config.json")
    if os.path.exists(cfgp):
        try:
            with open(cfgp, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    voice = (cfg.get("tts") or {}).get("voice", "zh-CN-XiaoxiaoNeural")
    rate = (cfg.get("tts") or {}).get("rate", "+12%")  # 解说节奏偏快; 慢了会被渲染端 atempo 硬拉

    plan_path = os.path.join(a.project, "02_plan", "plan.json")
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    segs = [s for s in plan.get("segments", []) if s.get("audio_mode") == "voiceover" and (s.get("narration_text") or "").strip()]
    if not segs:
        print(json.dumps({"ok": True, "voiced": 0, "note": "没有解说段"}))
        return

    async def synth(text, out):
        c = edge_tts.Communicate(text, voice, rate=rate)
        await c.save(out)

    import asyncio
    voiced, failed = 0, []
    for s in segs:
        sid = int(s["id"])
        out = os.path.join(a.project, "02_plan", "audio_%02d.mp3" % sid)
        text = clean_for_speech(s["narration_text"])
        if not text:
            continue
        if not (os.path.exists(out) and os.path.getsize(out) > 1024):
            ok = False
            for attempt in (1, 2):
                try:
                    asyncio.run(synth(text, out))
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
    print(json.dumps({"ok": True, "voiced": voiced, "failed": failed,
                      "voice": voice, "tts_total_seconds": round(total_tts, 1),
                      "note": "失败段渲染时自动回退为纯字幕"} if not failed else {"ok": True, "voiced": voiced, "failed": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
