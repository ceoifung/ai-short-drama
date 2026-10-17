# -*- coding: utf-8 -*-
"""解说模式 Stage 5(MVP): plan.json → 切片拼接 + 烧字幕 → 07_final/recap_v1.mp4
MVP 约定(无声链路): 无 TTS, 保留原声; 解说词以大字幕烧录, 时长按 est_seconds(4.5字/秒)
用法: python render_recap.py --project projects/<名>_recap
stdout 末行 JSON: {ok, final, segments, seconds, subtitle}
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fftools import ffmpeg_bin, ffprobe_bin

sys.stdout.reconfigure(encoding="utf-8")
FPS = 30


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", cwd=cwd)
    if r.returncode != 0:
        print(json.dumps({"ok": False, "issues": ["ffmpeg 失败: %s\n%s" % (" ".join(cmd[:6]), (r.stderr or "")[-400:])]}, ensure_ascii=False))
        sys.exit(1)
    return r


def ass_time(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    plan_path = os.path.join(a.project, "02_plan", "plan.json")
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    segs = plan.get("segments", [])

    # 剧集源路径
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

    timeline = []
    for s in segs:
        sid = int(s["id"])
        epdir = "ep%02d" % int(s["ep"])
        src = sources[epdir]["source"]
        t0 = float(s["t_start"])
        if s["audio_mode"] == "voiceover":
            dur = float(s["est_seconds"])
        else:
            dur = float(s["t_end"]) - t0
        cut = os.path.join(cuts_dir, "cut_%02d.mp4" % sid)
        vf = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d" % (W, H, W, H, FPS)
        run([ffmpeg_bin(), "-y", "-v", "error", "-ss", "%.3f" % t0, "-t", "%.3f" % dur, "-i", src,
             "-vf", vf, "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", cut])
        text = (s.get("narration_text") or "").strip() or (s.get("原声台词") or "").strip() or "【原声】"
        timeline.append({"start": sum(t["dur"] for t in timeline), "dur": dur, "text": text,
                         "mode": s["audio_mode"]})

    lst = os.path.abspath(os.path.join(cuts_dir, "list.txt"))
    with open(lst, "w", encoding="utf-8") as f:
        for i in range(1, len(segs) + 1):
            f.write("file 'cut_%02d.mp4'\n" % i)
    joined = os.path.abspath(os.path.join(cuts_dir, "joined.mp4"))
    run([ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])

    # ASS 字幕(时间轴 = 成片累计时间)
    ass_path = os.path.join(a.project, "02_plan", "subtitle.ass")
    events = []
    for t in timeline:
        events.append("Dialogue: 0,%s,%s,Big,,0,0,0,,%s" % (
            ass_time(t["start"] + 0.15), ass_time(t["start"] + t["dur"] - 0.05), ass_escape(t["text"])))
    ass = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W, "PlayResY: %d" % H, "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Big,Microsoft YaHei,%d,&H00FFFFFF,&H00FFFFFF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,70,1" % (H // 24),
        "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events, "",
    ])
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass)

    final = os.path.abspath(os.path.join(final_dir, "recap_v1.mp4"))
    # ass 滤镜用相对路径(免 Windows 盘符转义问题), 故 cwd=项目目录; 输出用绝对路径
    run([ffmpeg_bin(), "-y", "-v", "error", "-i", joined,
         "-vf", "ass=02_plan/subtitle.ass", "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
         "-c:a", "copy", final], cwd=a.project)

    dur_r = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", final], capture_output=True, text=True)
    total = float(dur_r.stdout.strip() or 0)
    print(json.dumps({"ok": True, "final": final.replace("\\", "/"), "segments": len(segs),
                      "seconds": round(total, 1), "subtitle": ass_path.replace("\\", "/"),
                      "resolution": "%dx%d" % (W, H),
                      "note": "MVP无声版: 保留原声, 解说词为字幕; TTS版将替换解说段音频"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
