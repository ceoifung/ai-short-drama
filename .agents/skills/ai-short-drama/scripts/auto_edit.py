# -*- coding: utf-8 -*-
"""Stage 6 自动剪辑: 05_footage/ep<N>/*.mp4 → 检测长静音并裁剪 → 拼接 → 9:16 → 07_final
用法: python auto_edit.py --project projects/<剧名> --episode 1
输出: stdout 最后一行 JSON {ok, final, clips, trims:[...]} ; 无片段时退出码 1
依赖: ffmpeg(PATH 优先, tools/ 兜底)
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

SILENCE_DB = -35       # 低于此视为静音
SILENCE_MIN_D = 2.8    # 静音超过该秒数才裁
MARGIN = 0.3           # 裁剪时前后各保留的余量
W, H, FPS = 1080, 1920, 30


def fail(msgs):
    print(json.dumps({"ok": False, "issues": msgs}, ensure_ascii=False))
    sys.exit(1)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")


def detect_silences(path):
    r = run([ffmpeg_bin(), "-i", path, "-af", "silencedetect=noise=%ddB:d=%.2f" % (SILENCE_DB, SILENCE_MIN_D), "-f", "null", "-"])
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", r.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", r.stderr)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else s + SILENCE_MIN_D
        if e - s >= SILENCE_MIN_D:
            out.append((s, e))
    return out


def probe_duration(path):
    r = run([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def trim_clip(src, dst, silences, dur):
    """把静音区间(加边距)从 [0,dur] 里挖掉, 同时归一到 1080x1920/30fps"""
    keep = []
    cur = 0.0
    for s, e in silences:
        s2, e2 = max(0.0, s - MARGIN), min(dur, e + MARGIN)
        if s2 - cur > 0.5:
            keep.append((cur, s2))
        cur = max(cur, e2)
    if dur - cur > 0.5:
        keep.append((cur, dur))
    if not keep:
        return False  # 全静音, 交给上层报错

    vf, af = [], []
    for i, (s, e) in enumerate(keep):
        vf.append("[0:v]trim=%.3f:%.3f,setpts=PTS-STARTPTS[v%d]" % (s, e, i))
        af.append("[0:a]atrim=%.3f:%.3f,asetpts=PTS-STARTPTS[a%d]" % (s, e, i))
    n = len(keep)
    vf.append("%sconcat=n=%d:v=1:a=0[s]" % ("".join("[v%d]" % i for i in range(n)), n))
    af.append("%sconcat=n=%d:v=0:a=1[a]" % ("".join("[a%d]" % i for i in range(n)), n))
    scale = "[s]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1,fps=%d[v]" % (W, H, W, H, FPS)
    filter_complex = ";".join(vf + af + [scale]) + ";[v]format=yuv420p[vout]"
    cmd = [ffmpeg_bin(), "-y", "-v", "error", "-i", src, "-filter_complex", filter_complex,
           "-map", "[vout]", "-map", "[a]", "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
           "-c:a", "aac", "-b:a", "128k", "-r", str(FPS), dst]
    r = run(cmd)
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", type=int, default=1)
    a = ap.parse_args()
    ep = a.episode

    footdir = os.path.join(a.project, "05_footage", "ep%d" % ep)
    if not os.path.isdir(footdir):
        fail(["片段目录不存在: %s" % footdir.replace("\\", "/")])
    clips = [f for f in os.listdir(footdir) if f.lower().endswith(".mp4")]
    clips.sort(key=lambda f: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", f)])
    if not clips:
        fail(["%s 里没有 mp4 片段（把 updream 批量下载解压后按 01.mp4、02.mp4… 放入）" % footdir.replace("\\", "/")])

    tmpdir = os.path.join(footdir, "_normalized")
    os.makedirs(tmpdir, exist_ok=True)
    trims, kept = [], []
    for c in clips:
        src = os.path.join(footdir, c)
        dur = probe_duration(src)
        sil = detect_silences(src)
        norm = os.path.join(tmpdir, "n_" + c)
        target = norm if sil else norm  # 统一归一化(裁剪+缩放), 有静音才 trim
        if sil:
            ok = trim_clip(src, target, sil, dur)
        else:
            ok = trim_clip(src, target, [(dur + 10, dur + 20)], dur)  # 空静音表→只走归一化路径
        if not ok:
            fail(["处理片段失败: %s" % c])
        kept.append(norm)
        for s, e in sil:
            trims.append({"clip": c, "silence_start": round(s, 2), "silence_end": round(e, 2), "seconds": round(e - s, 2)})

    finaldir = os.path.join(a.project, "07_final")
    os.makedirs(finaldir, exist_ok=True)
    os.makedirs(os.path.join(a.project, "06_review"), exist_ok=True)
    final = os.path.join(finaldir, "ep%d_final.mp4" % ep)
    lst = os.path.join(tmpdir, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for k in kept:
            f.write("file '%s'\n" % os.path.abspath(k).replace("\\", "/").replace("'", "'\\''"))
    r = run([ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", final])
    if r.returncode != 0:
        fail(["拼接失败: %s" % (r.stderr[-500:])])

    with open(os.path.join(a.project, "06_review", "ep%d_silences.json" % ep), "w", encoding="utf-8") as f:
        json.dump(trims, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "ok": True,
        "final": os.path.join(a.project, "07_final", "ep%d_final.mp4" % ep).replace("\\", "/"),
        "clips": len(clips),
        "trims": trims,
        "final_seconds": round(probe_duration(final), 1),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
