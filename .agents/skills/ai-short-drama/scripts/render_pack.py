# -*- coding: utf-8 -*-
"""Stage 4 生产包: 校验 storyboard.json 并渲染 updream 节点卡/manifest/checklist
用法: python render_pack.py --project projects/<剧名> --episode 1
- 机检: 引用完整性(角色/场景/道具必须在资产表中)、提示词<=1000字且含【画面】【动作】【镜头】
- 通过: 写 04_production/ep<N>/node_NN.md + manifest.json + checklist.md
输出: stdout 最后一行 JSON {ok, dir, nodes, checklist} 或 {ok:false, issues:[...]}
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


def load(path, issues, label):
    if not os.path.exists(path):
        issues.append("缺少%s: %s" % (label, path))
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        issues.append("%s 不是合法 JSON: %s" % (label, e))
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--episode", type=int, default=1)
    a = ap.parse_args()
    ep = a.episode
    issues = []

    def fail():
        print(json.dumps({"ok": False, "issues": issues}, ensure_ascii=False))
        sys.exit(1)

    sb = load(os.path.join(a.project, "03_storyboard", "ep%d.storyboard.json" % ep), issues, "分镜文件")
    chars = load(os.path.join(a.project, "02_assets", "characters.json"), issues, "characters.json")
    scenes = load(os.path.join(a.project, "02_assets", "scenes.json"), issues, "scenes.json")
    props = load(os.path.join(a.project, "02_assets", "props.json"), issues, "props.json")
    if issues:
        fail()

    cnames = [c.get("name", "") for c in chars]
    snames = [s.get("name", "") for s in scenes]
    pnames = [p.get("name", "") for p in props]
    shots = sb.get("shots", [])
    if not shots:
        issues.append("分镜文件里没有任何镜头")
        fail()

    default_secs = sb.get("shot_seconds", 15)
    for s in shots:
        sid = s.get("id", "?")
        for ref in s.get("characters", []):
            if ref not in cnames:
                issues.append("镜头%s: 角色『%s』不在 characters.json 里" % (sid, ref))
        for ref in s.get("props", []):
            if ref not in pnames:
                issues.append("镜头%s: 道具『%s』不在 props.json 里" % (sid, ref))
        sc = s.get("scene", "")
        if sc not in snames:
            issues.append("镜头%s: 场景『%s』不在 scenes.json 里" % (sid, sc))
        p = s.get("prompt", "")
        if len(p) > 1000:
            issues.append("镜头%s: 提示词 %d 字超过 1000 字上限" % (sid, len(p)))
        for kw in ("【画面】", "【动作】", "【镜头】"):
            if kw not in p:
                issues.append("镜头%s: 提示词缺少 %s 标记" % (sid, kw))
        try:
            secs = int(s.get("seconds", default_secs))
            if not (5 <= secs <= 20):
                issues.append("镜头%s: 时长 %d 秒不在 5-20 秒范围内" % (sid, secs))
        except (TypeError, ValueError):
            issues.append("镜头%s: seconds 字段不是数字" % sid)
        if not str(sid).isdigit() or int(sid) < 1:
            issues.append("镜头 id 必须是从 1 开始的正整数, 当前: %r" % sid)
    if issues:
        fail()

    # ---- 扫描已生成的参考图(API 通道产物), stem -> 实际文件名 ----
    img_dir = os.path.join(a.project, "02_assets", "images")
    have_imgs = {}
    if os.path.isdir(img_dir):
        for f in os.listdir(img_dir):
            stem, ext = os.path.splitext(f)
            if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                have_imgs[stem] = "images/" + f

    def ref_img(name):
        """有真图用真图路径, 没有给命名约定"""
        return have_imgs.get(name, name + ".webp")

    # ---- 校验通过, 渲染生产包 ----
    outdir = os.path.join(a.project, "04_production", "ep%d" % ep)
    os.makedirs(outdir, exist_ok=True)
    style = sb.get("style", "真人现代短剧")
    ids = sorted(int(s["id"]) for s in shots)
    manifest = {
        "episode": ep,
        "style": style,
        "model": "Seedance 2.0 Mini",
        "ratio": "9:16",
        "quality": "480P",
        "audio": True,
        "shots": [],
    }
    for s in sorted(shots, key=lambda x: int(x["id"])):
        sid = int(s["id"])
        secs = int(s.get("seconds", default_secs))
        refs = []
        for c in s.get("characters", []):
            refs.append("- [ ] 角色 **%s**（图: %s）" % (c, ref_img(c)))
        refs.append("- [ ] 场景 **%s**（图: %s）" % (s["scene"], ref_img(s["scene"])))
        for pr in s.get("props", []):
            refs.append("- [ ] 道具 **%s**（图: %s）" % (pr, ref_img(pr)))
        md = "\n".join([
            "# 镜头 %d / %d" % (sid, ids[-1]),
            "",
            "## 节点参数（updream 视频节点）",
            "- 模型: **Seedance 2.0 Mini**（便宜档）",
            "- 比例: **9:16**  画质: **480P**  时长: **%d 秒**  音频: **开启**" % secs,
            "",
            "## 提示词（整段复制粘贴）",
            "",
            "```",
            s.get("prompt", ""),
            "```",
            "",
            "## 参考图（从通用角色库勾选）",
            *refs,
            "",
            "> 做一次删一次：上传前先清空通用角色库旧素材，再把 02_assets 的图全部上传（按角色名命名）。",
        ])
        with open(os.path.join(outdir, "node_%02d.md" % sid), "w", encoding="utf-8") as f:
            f.write(md)
        manifest["shots"].append({
            "id": sid, "seconds": secs, "scene": s.get("scene", ""),
            "characters": s.get("characters", []), "props": s.get("props", []),
            "prompt": s.get("prompt", ""),
        })

    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    used_names = set()
    for s in shots:
        used_names.update(x for x in s.get("characters", []) if x)
        used_names.add(s.get("scene", ""))
        used_names.update(x for x in s.get("props", []) if x)
    covered = [n for n in used_names if n and n in have_imgs]
    missing = [n for n in used_names if n and n not in have_imgs]
    all_covered = not missing

    if all_covered:
        section_one = [
            "## 一、参考图已就绪（API 已生成, 无需即刻AI）",
            "- 全部 %d 张参考图在 02_assets/images/ 下, 文件名=资产名" % len(covered),
            "- 直接把整个文件夹的图片上传 updream 通用角色库（记得先清空旧素材）",
        ]
    else:
        section_one = [
            "## 一、即刻AI（jikeai.cc）出角色/场景图" + ("（%d/%d 张已由 API 生成, 只补缺）" % (len(covered), len(covered) + len(missing)) if covered else ""),
            "1. 创建项目: 创作模式=多视角参考生成视频; 图片模型=GPT image 2.0; 分辨率 1K; 宽高比 **竖屏9:16**; 视频模型=Seedance 2.0 Mini",
            "2. 新建分集, 进入第1步脚本改写: **去掉「从项目角色库中搜索」的对勾**, 粘贴 %s" % os.path.join("01_script", "ep%d.rewritten.md" % ep).replace("\\", "/"),
            "3. 风格选「%s」→ 点「识别角色场景」→ 核对角色/场景/物品与 02_assets 三个 json 一致" % style,
            "4. 生成全部图片, 逐张右键另存, **文件名=角色/场景/道具名.webp**（与生产包引用对应）" + ("; 本次还缺: %s" % ", ".join(missing) if covered else ""),
        ]

    checklist = "\n".join([
        "# 第 %d 集生产执行清单（P1 手动通道）" % ep,
        "",
        *section_one,
        "",
        "## 二、updream（updream.cn）逐镜生成",
        "5. 新建项目 → 画布「分镜制作」节点右键 → 添加视频节点, 按 node_XX.md 设参数",
        "6. **先删后传**: 清空通用角色库旧图 → 上传全部角色/场景/道具图（已生成的直接传 02_assets/images/ 里的文件）",
        "7. 逐节点: 粘贴提示词 → 从通用角色库勾选该镜头的参考图 → 生成（共 %d 个节点）" % len(shots),
        "8. 下载中心 → 批量下载 zip → 解压, **按镜头编号重命名 01.mp4 ~ %02d.mp4**" % ids[-1],
        "        放入 projects 目录的 05_footage/ep%d/" % ep,
        "",
        "## 三、回到 ZCode 质检剪辑",
        "9. 对我说「质检剪辑 %s 第%d集」或运行 workflow mode=qa → AI 逐条审片 + 自动剪静音/拼接/9:16 → 07_final 出成片" % (a.project.replace("\\", "/"), ep),
    ])
    with open(os.path.join(outdir, "checklist.md"), "w", encoding="utf-8") as f:
        f.write(checklist)

    rel = os.path.join(a.project, "04_production", "ep%d" % ep).replace("\\", "/")
    print(json.dumps({
        "ok": True, "dir": rel, "nodes": len(shots),
        "checklist": rel + "/checklist.md", "manifest": rel + "/manifest.json",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
