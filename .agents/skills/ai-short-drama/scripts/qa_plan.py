# -*- coding: utf-8 -*-
"""解说画面匹配抽检: 抽取每个解说段原片时间范围的中点帧 → 02_plan/qa_frames/seg_NN.jpg
配合视觉 agent 对照 narration_text 判断画面是否对位。
用法: python qa_plan.py --project projects/<名>_recap [--mode original|final]
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fftools import ffmpeg_bin

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--crop-bottom", type=float, default=0.13, help="与渲染一致的裁切, 便于看到成片真实画面")
    a = ap.parse_args()
    with open(os.path.join(a.project, "02_plan", "plan.json"), encoding="utf-8") as f:
        plan = json.load(f)

    sources = {}
    eps_dir = os.path.join(a.project, "00_episodes")
    for d in sorted(os.listdir(eps_dir)) if os.path.isdir(eps_dir) else []:
        mp = os.path.join(eps_dir, d, "meta.json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                sources[d] = json.load(f)

    outdir = os.path.join(a.project, "02_plan", "qa_frames")
    os.makedirs(outdir, exist_ok=True)
    tasks = []
    for s in plan.get("segments", []):
        if s.get("audio_mode") != "voiceover":
            continue
        sid = int(s["id"])
        epdir = "ep%02d" % int(s["ep"])
        meta = sources[epdir]
        mid = (float(s["t_start"]) + float(s["t_end"])) / 2
        jpg = os.path.abspath(os.path.join(outdir, "seg_%02d.jpg" % sid))
        crop = "crop=iw:%d:0:0," % int(meta.get("height", 1080) * (1 - a.crop_bottom))
        vf = crop + "scale=960:-2"
        r = subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-ss", "%.3f" % mid, "-i", meta["source"],
                            "-frames:v", "1", "-vf", vf, "-q:v", "4", jpg], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(jpg):
            continue
        tasks.append({"id": sid, "ep": int(s["ep"]), "mid_t": round(mid, 1),
                      "narration": s.get("narration_text", ""), "frame": jpg.replace("\\", "/")})
    with open(os.path.join(outdir, "qa_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "frames": len(tasks), "dir": outdir.replace("\\", "/")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
