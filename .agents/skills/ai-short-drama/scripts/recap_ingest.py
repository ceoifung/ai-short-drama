# -*- coding: utf-8 -*-
"""解说模式 Stage 0: 剧集文件夹批量入库
用法: python recap_ingest.py --project projects/<名>_recap --source <剧集文件夹>
每集产出 00_episodes/epNN/{meta.json, transcript.txt, transcript_timed.txt, frames/}
stdout 末行 JSON: {ok, episodes, total_seconds, outdir}
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wsroot import ws_root  # noqa: F401 (锚定数据根, 顺带校验安装)
from fftools import ffmpeg_bin, ffprobe_bin
from ingest import transcribe

sys.stdout.reconfigure(encoding="utf-8")
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".ts", ".webm"}


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def probe(path):
    def ff(args):
        r = subprocess.run([ffprobe_bin(), "-v", "error", *args, path], capture_output=True, text=True)
        return r.stdout.strip()
    dur = ff(["-show_entries", "format=duration", "-of", "csv=p=0"])
    wh = ff(["-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0"])
    w, h = (wh.split(",") + ["?", "?"])[:2]
    try:
        return float(dur), int(w), int(h)
    except (TypeError, ValueError):
        return 0.0, 0, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--source", required=True, help="剧集文件夹(文件名排序=剧集顺序)")
    ap.add_argument("--fps", type=float, default=0.1, help="抽帧率, 默认1张/10秒")
    a = ap.parse_args()

    if not os.path.isdir(a.source):
        print(json.dumps({"ok": False, "issues": ["剧集文件夹不存在: %s" % a.source]}, ensure_ascii=False))
        sys.exit(1)
    eps = sorted(
        [f for f in os.listdir(a.source) if os.path.splitext(f)[1].lower() in VIDEO_EXT],
        key=natural_key,
    )
    if not eps:
        print(json.dumps({"ok": False, "issues": ["文件夹里没有视频文件"]}, ensure_ascii=False))
        sys.exit(1)

    base = os.path.join(a.project, "00_episodes")
    os.makedirs(base, exist_ok=True)
    total, chars = 0.0, 0
    for i, f in enumerate(eps, 1):
        src = os.path.join(a.source, f)
        epdir = os.path.join(base, "ep%02d" % i)
        os.makedirs(epdir, exist_ok=True)
        dur, w, h = probe(src)
        if dur <= 0:
            print(json.dumps({"ok": False, "issues": ["第%d集无法读取时长: %s" % (i, f)]}, ensure_ascii=False))
            sys.exit(1)
        plain, timed, _ = transcribe(src, epdir)
        with open(os.path.join(epdir, "transcript.txt"), "w", encoding="utf-8") as fo:
            fo.write(plain)
        with open(os.path.join(epdir, "transcript_timed.txt"), "w", encoding="utf-8") as fo:
            fo.write(timed)
        frames = os.path.join(epdir, "frames")
        os.makedirs(frames, exist_ok=True)
        subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", src, "-vf", "fps=%.3f" % a.fps,
                        "-q:v", "4", os.path.join(frames, "%05d.jpg")], check=False)
        meta = {"ep": i, "file": f, "source": os.path.abspath(src), "duration": round(dur, 2),
                "width": w, "height": h, "chars": len(plain), "frames": len(os.listdir(frames))}
        with open(os.path.join(epdir, "meta.json"), "w", encoding="utf-8") as fo:
            json.dump(meta, fo, ensure_ascii=False, indent=2)
        total += dur
        chars += len(plain)
        print("ep%02d  %6.1fs  %5d字  %s" % (i, dur, len(plain), f))

    print(json.dumps({"ok": True, "episodes": len(eps), "total_seconds": round(total, 1),
                      "chars": chars, "outdir": base.replace("\\", "/")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
