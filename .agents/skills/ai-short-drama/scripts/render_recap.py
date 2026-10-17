# -*- coding: utf-8 -*-
"""解说渲染: plan.json → 切片 + (可选TTS混音) + 逐短语字幕 → 07_final/recap_vN.mp4
有 tts_duration 的段: 口播+原声压低(12%), 视频时长=max(est, tts+0.35), 素材不够则顺延时间戳、再不够微加速(≤1.25x)
无 tts 的段: 保留原声, 纯字幕
字幕: 按标点切短语(每条≤14字), 按字数占比分配显示时长, 逐条显示
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fftools import ffmpeg_bin, ffprobe_bin

sys.stdout.reconfigure(encoding="utf-8")
FPS = 30
MAX_CHUNK = 14


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", cwd=cwd)
    if r.returncode != 0:
        print(json.dumps({"ok": False, "issues": ["ffmpeg 失败: %s\n%s" % (" ".join(cmd[:6]), (r.stderr or "")[-400:])]}, ensure_ascii=False))
        sys.exit(1)


def split_chunks(text, maxlen=MAX_CHUNK):
    """按句末标点→句中标点两级切短语, 超长硬切"""
    parts = re.split(r"(?<=[。！？；!?;])", text.strip())
    chunks, buf = [], ""
    for p in parts:
        for s in filter(None, (x.strip() for x in re.split(r"(?<=[，、：,:…—])", p))):
            if len(buf) + len(s) <= maxlen:
                buf += s
            else:
                if buf:
                    chunks.append(buf)
                while len(s) > maxlen:
                    chunks.append(s[:maxlen])
                    s = s[maxlen:]
                buf = s
    if buf:
        chunks.append(buf)
    return chunks


def ass_time(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        cs, s = 0, s + 1
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    with open(os.path.join(a.project, "02_plan", "plan.json"), encoding="utf-8") as f:
        plan = json.load(f)
    segs = plan.get("segments", [])
    if not segs:
        print(json.dumps({"ok": False, "issues": ["plan.json 没有段落"]}, ensure_ascii=False))
        sys.exit(1)

    sources = {}
    eps_dir = os.path.join(a.project, "00_episodes")
    for d in sorted(os.listdir(eps_dir)) if os.path.isdir(eps_dir) else []:
        mp = os.path.join(eps_dir, d, "meta.json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                sources[d] = json.load(f)
    first = sources.get("ep%02d" % int(segs[0]["ep"]), {})
    portrait = first.get("height", 1920) >= first.get("width", 1080)
    W, H = (1080, 1920) if portrait else (1920, 1080)

    cuts_dir = os.path.join(a.project, "03_cuts")
    os.makedirs(cuts_dir, exist_ok=True)
    final_dir = os.path.join(a.project, "07_final")
    os.makedirs(final_dir, exist_ok=True)

    voiced_n = sum(1 for s in segs if s.get("tts_duration"))
    version = "v2" if voiced_n else "v1"
    final = os.path.abspath(os.path.join(final_dir, "recap_%s.mp4" % version))
    timeline = []

    for s in segs:
        sid = int(s["id"])
        epdir = "ep%02d" % int(s["ep"])
        meta = sources[epdir]
        t0 = float(s["t_start"])
        t1 = float(s["t_end"])
        tts_dur = float(s.get("tts_duration", 0))
        cut = os.path.abspath(os.path.join(cuts_dir, "cut_%02d.mp4" % sid))
        af = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
        vf = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (W, H, W, H, FPS)

        if s["audio_mode"] == "voiceover":
            est = float(s.get("est_seconds", 3))
            clip = t1 - t0
            dur, atempo = clip, None
            if tts_dur:
                # 口播时长封顶: 最多比文案预算多30%, 超出部分靠微加速消化(防成片超时)
                want = max(est, min(tts_dur + 0.35, est * 1.3))
                dur = want
                if dur > clip:  # 素材不够 → 先顺延时间戳(不超集长)
                    t1 = min(float(meta["duration"]), t0 + dur)
                    dur = t1 - t0
                if tts_dur > dur - 0.45:  # 口播仍装不下 → 微加速
                    atempo = min(1.25, round(tts_dur / max(0.6, dur - 0.45), 3))
            run([ffmpeg_bin(), "-y", "-v", "error", "-ss", "%.3f" % t0, "-t", "%.3f" % dur, "-i", meta["source"],
                 "-vf", vf, "-c:v", "libx264", "-crf", "23", "-preset", "veryfast"] + af + [cut])
            if tts_dur:
                audio = os.path.abspath(os.path.join(a.project, s["tts_file"]))
                nar = "[1:a]" + ("atempo=%.3f," % atempo if atempo else "") + "adelay=250|250[nar]"
                # apad 必须限长(whole_dur), 否则无限填充 + duration=first 永不结束
                fc = ("[0:a]volume=0.12,apad=whole_dur=%.3f[bg];" % dur + nar +
                      ";[bg][nar]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
                run([ffmpeg_bin(), "-y", "-v", "error", "-i", cut, "-i", audio,
                     "-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-t", "%.3f" % dur,
                     "-c:v", "copy"] + af + [cut + ".t.mp4"])
                os.replace(cut + ".t.mp4", cut)
        else:
            dur = t1 - t0
            run([ffmpeg_bin(), "-y", "-v", "error", "-ss", "%.3f" % t0, "-t", "%.3f" % dur, "-i", meta["source"],
                 "-vf", vf, "-c:v", "libx264", "-crf", "23", "-preset", "veryfast"] + af + [cut])

        text = (s.get("narration_text") or "").strip() or (s.get("原声台词") or "").strip() or "【原声】"
        timeline.append({"start": sum(t["dur"] for t in timeline), "dur": dur,
                         "chunks": split_chunks(text), "mode": s["audio_mode"]})

    lst = os.path.abspath(os.path.join(cuts_dir, "list.txt"))
    with open(lst, "w", encoding="utf-8") as f:
        for i in range(1, len(segs) + 1):
            f.write("file 'cut_%02d.mp4'\n" % i)
    joined = os.path.abspath(os.path.join(cuts_dir, "joined.mp4"))
    run([ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    # 字幕: 每段内按字数占比把时间分给各短语
    ass_path = os.path.abspath(os.path.join(a.project, "02_plan", "subtitle.ass"))
    events = []
    for t in timeline:
        if not t["chunks"]:
            continue
        total_chars = sum(len(c) for c in t["chunks"])
        span = max(0.8, t["dur"] - 0.35)
        cur = t["start"] + 0.2
        for c in t["chunks"]:
            d = span * len(c) / total_chars
            events.append("Dialogue: 0,%s,%s,Big,,0,0,0,,%s" % (
                ass_time(cur), ass_time(min(cur + d, t["start"] + t["dur"] - 0.05)), ass_escape(c)))
            cur += d
    ass = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W, "PlayResY: %d" % H, "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Big,Microsoft YaHei,%d,&H00FFFFFF,&H00FFFFFF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,90,1" % (H // 22),
        "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, "",
    ])
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass)

    # ass 滤镜用相对路径(免盘符转义), cwd=项目目录
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", joined,
         "-vf", "ass=02_plan/subtitle.ass", "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
         "-c:a", "copy", final], cwd=a.project)

    dur_r = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", final], capture_output=True, text=True)
    print(json.dumps({"ok": True, "final": final.replace("\\", "/"), "segments": len(segs),
                      "voiced_segments": voiced_n, "mode": "tts+原声压低" if voiced_n else "无声字幕版",
                      "seconds": round(float(dur_r.stdout.strip() or 0), 1),
                      "resolution": "%dx%d" % (W, H)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
