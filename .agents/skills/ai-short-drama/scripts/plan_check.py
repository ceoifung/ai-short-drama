# -*- coding: utf-8 -*-
"""解说模式 Stage 3 机检: 校验 02_plan/plan.json
门禁规则:
 1 段落 id 从 1 连续; voiceover 段必有 narration_text; est_seconds 与字数匹配(中文≈4.5字/秒, 容差±40%)
 2 素材时长(t_end-t_start) ≥ 该段时长需求; 时间在对应集的 meta.json 时长范围内
 3 总时长落在 5-10 分钟; 原声段: 单条≤5s 且总占比<15%
 4 同一(ep,t_start,t_end)重复使用≤2次; audio_mode 只能是 voiceover|original
退出码: 0 通过 / 1 有问题(stdout 输出 issues JSON)
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
CHARS_PER_SEC = 4.5
MIN_TOTAL, MAX_TOTAL = 295.0, 635.0  # 5-10分钟, 各留5秒容差


def fail(issues):
    print(json.dumps({"ok": False, "issues": issues}, ensure_ascii=False))
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    issues = []
    plan_path = os.path.join(a.project, "02_plan", "plan.json")
    if not os.path.exists(plan_path):
        fail(["缺少 02_plan/plan.json"])
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    segs = plan.get("segments", [])
    if not segs:
        fail(["没有任何段落"])

    # 剧集时长表
    eps_dir = os.path.join(a.project, "00_episodes")
    durations = {}
    if os.path.isdir(eps_dir):
        for d in os.listdir(eps_dir):
            mp = os.path.join(eps_dir, d, "meta.json")
            if os.path.exists(mp):
                with open(mp, encoding="utf-8") as f:
                    durations[d] = json.load(f).get("duration", 0)

    usage = {}
    total = 0.0
    orig_total = 0.0
    for i, s in enumerate(segs):
        sid = s.get("id", "?")
        if s.get("id") != i + 1:
            issues.append("段落%s: id 必须从 1 连续递增" % sid)
        mode = s.get("audio_mode", "")
        if mode not in ("voiceover", "original"):
            issues.append("段落%s: audio_mode 必须是 voiceover|original" % sid)
            continue
        ep = s.get("ep")
        epdir = "ep%02d" % int(ep) if str(ep).isdigit() else None
        if epdir is None or epdir not in durations:
            issues.append("段落%s: 集数 ep=%r 不在入库清单里" % (sid, ep))
            continue
        t0, t1 = float(s.get("t_start", -1)), float(s.get("t_end", -1))
        clip = t1 - t0
        if t0 < 0 or clip <= 0:
            issues.append("段落%s: t_start/t_end 无效" % sid)
            continue
        if t1 > durations[epdir] + 0.5:
            issues.append("段落%s: t_end=%.1f 超出第%s集时长 %.1f" % (sid, t1, epdir, durations[epdir]))
        text = (s.get("narration_text") or "").strip()
        if mode == "voiceover":
            if not text:
                issues.append("段落%s: 解说段缺 narration_text" % sid)
                continue
            est = float(s.get("est_seconds", 0))
            if est <= 0:
                issues.append("段落%s: 缺 est_seconds" % sid)
                continue
            expect = len(text) / CHARS_PER_SEC
            if not (0.6 * expect <= est <= 1.4 * expect):
                issues.append("段落%s: %d字配%.0f秒不匹配(约需%.0f秒, 4.5字/秒)" % (sid, len(text), est, expect))
            if clip < est:
                issues.append("段落%s: 素材仅%.1fs 短于解说%.1fs" % (sid, clip, est))
            total += est
        else:
            if not text and not (s.get("原声台词") or "").strip():
                pass  # 原声段可无解说文字
            if clip > 5.5:
                issues.append("段落%s: 原声段 %.1fs 超过 5s 上限" % (sid, clip))
            total += clip
            orig_total += clip
        key = (ep, round(t0, 1), round(t1, 1))
        usage[key] = usage.get(key, 0) + 1

    for key, n in usage.items():
        if n > 2:
            issues.append("素材 ep%s %.1f-%.1f 被用了 %d 次(上限2)" % (key[0], key[1], key[2], n))
    if not (MIN_TOTAL <= total <= MAX_TOTAL):
        issues.append("总时长 %.1f 秒不在 5-10 分钟范围" % total)
    if total > 0 and orig_total / total >= 0.15:
        issues.append("原声占比 %.0f%% 超过 15%%" % (100 * orig_total / total))

    if issues:
        fail(issues)
    print(json.dumps({"ok": True, "segments": len(segs), "total_seconds": round(total, 1),
                      "original_seconds": round(orig_total, 1)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
