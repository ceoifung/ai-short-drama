# -*- coding: utf-8 -*-
"""Stage 0 素材入库: 任意形态素材归一化为 00_source/raw.txt + source_meta.json
用法: python ingest.py --project projects/<剧名> --source <路径或内联文本> [--type auto] [--episode 1]
输出: stdout 最后一行 JSON {ok, type, chars, summary, ...}
"""
import argparse
import json
import os
import re
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root

sys.stdout.reconfigure(encoding="utf-8")

MEDIA_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts", ".webm", ".m4a", ".mp3", ".wav", ".aac", ".flac"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


def resolve_whisper_model():
    """优先级: config.json 的 whisper_model > 工作区 models/whisper-turbo
    > E:\\ai-subtitle 老安装 > 模型名(首次转写自动从 hf-mirror 下载)"""
    ws = ws_root()
    for cfg_path in (os.path.join(ws, "config.json"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")):
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    m = json.load(f).get("whisper_model", "")
                if m and (m == "large-v3-turbo" or os.path.exists(m)):
                    return m
            except Exception:
                pass
            break
    for cand in (os.path.join(ws, "models", "whisper-turbo"),
                 r"E:\ai-subtitle\models\whisper-turbo"):
        if os.path.exists(cand):
            return cand
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    return "large-v3-turbo"


def fail(msgs):
    print(json.dumps({"ok": False, "issues": msgs}, ensure_ascii=False))
    sys.exit(1)


def read_text(src):
    if os.path.exists(src):
        with open(src, encoding="utf-8", errors="ignore") as f:
            return f.read()
    return src  # 内联文本（一句话创意等）


def clean(text):
    text = text.replace("\r\n", "\n")
    lines = [l.strip() for l in text.split("\n")]
    return "\n".join(l for l in lines if l).strip()


def detect(src, forced):
    if forced and forced != "auto":
        return forced
    ext = os.path.splitext(src)[1].lower() if os.path.exists(src) else ""
    if ext in MEDIA_EXT:
        return "audio" if ext in AUDIO_EXT else "video"
    text = read_text(src)
    if len(re.findall(r"镜头\s*\d|【镜头", text)) >= 3:
        return "script"
    if len(text) <= 200:
        return "idea"
    return "novel"


def ts(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return "%02d:%02d:%02d" % (h, m, s)


def transcribe(media, outdir):
    wav = os.path.join(outdir, "_tmp_audio.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", media, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav],
        check=True,
    )
    import numpy as np
    from faster_whisper import WhisperModel

    with wave.open(wav, "rb") as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    # 本地模型优先 GPU, 失败降 CPU; 自动下载的模型首次会拉取约1.6GB
    wm = resolve_whisper_model()
    try:
        model = WhisperModel(wm, device="cuda", compute_type="float16")
    except Exception:
        model = WhisperModel(wm, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio, language="zh", vad_filter=True)
    plain, timed = [], []
    for seg in segments:
        t = seg.text.strip()
        if t:
            plain.append(t)
            timed.append("[%s -> %s] %s" % (ts(seg.start), ts(seg.end), t))
    os.remove(wav)
    return "\n".join(plain), "\n".join(timed), float(info.duration)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="项目目录, 如 projects/剧名")
    ap.add_argument("--source", required=True, help="素材路径(视频/音频/文本)或内联文本")
    ap.add_argument("--type", default="auto", help="auto|video|audio|novel|idea|script")
    ap.add_argument("--episode", type=int, default=1)
    a = ap.parse_args()

    for d in ["00_source", "01_script", "02_assets", "03_storyboard", "04_production", "05_footage", "06_review", "07_final"]:
        os.makedirs(os.path.join(a.project, d), exist_ok=True)

    stype = detect(a.source, a.type)
    if stype not in ("video", "audio", "novel", "idea", "script"):
        fail(["未知来源类型: %s" % stype])

    outdir = os.path.join(a.project, "00_source")
    if stype in ("video", "audio"):
        if not os.path.exists(a.source):
            fail(["媒体文件不存在: %s" % a.source])
        try:
            text, timed, dur = transcribe(a.source, outdir)
        except Exception as e:
            fail(["转写失败: %s" % e])
        with open(os.path.join(outdir, "transcript_timed.txt"), "w", encoding="utf-8") as f:
            f.write(timed)
        summary = "媒体转写完成, 时长约 %d 秒" % dur
    else:
        text = clean(read_text(a.source))
        summary = {"novel": "小说/长文本", "idea": "一句话创意", "script": "已有剧本"}[stype]

    with open(os.path.join(outdir, "raw.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    meta = {
        "ok": True,
        "project": a.project.replace("\\", "/"),
        "type": stype,
        "source": a.source if os.path.exists(a.source) else "(内联文本)",
        "chars": len(text),
        "episode": a.episode,
        "summary": summary,
    }
    with open(os.path.join(outdir, "source_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
