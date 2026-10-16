# PLAYBOOK.md — AI 短剧跨工具流程手册

> 本手册是流水线的唯一权威流程。任何 agent（Codex / Claude Code / Gemini CLI / 无编排引擎的 ZCode 会话）按此执行。
> 有并行子代理能力的工具（Claude Code subagents 等）可以把"角色"映射为子代理；没有的就由主对话依次扮演，但**角色间必须互不迁就：审核就是挑刺，过就是过，不过就是不过**。
> Python 一律用流水线自带的 venv——先跑 `configure.py --check`，用输出里的 `venv_python` 路径执行后续命令（克隆仓库=仓库内 `.venv`；全局安装=`~/.ai-short-drama/.venv`）。ffmpeg 用 PATH 里的, 没有则跑 setup_env/ensure_ffmpeg 自动下载到 tools/。

## 产物目录约定（projects/<剧名>/）

```
00_source/      raw.txt + source_meta.json        # 归一化素材
01_script/      ep{N}.novel.md 初稿 → ep{N}.rewritten.md 终稿 → ep{N}.review.md 审核
02_assets/      characters.json / scenes.json / props.json (+ images/ 参考图 + review.md)
03_storyboard/  ep{N}.storyboard.json (+ ep{N}.review.md)
04_production/  ep{N}/node_NN.md + manifest.json + checklist.md   # 给人照着点击的生产包
05_footage/     ep{N}/01.mp4, 02.mp4…             # 人工放入平台生成的片段
06_review/      qa_*.json + ep{N}_silences.json
07_final/       ep{N}_final.mp4                   # 成片
```

---

## 模式一：full（素材 → 生产包）

### Stage 0 素材入库（脚本，无 AI）

```
.venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/ingest.py \
  --project projects/<剧名> --source <素材路径或一句话创意> --episode <N>
```

- 自动识别来源类型：video/audio（本地 whisper 转写）/ novel / idea / script
- 退出码非 0 → 停下报错；成功则读 stdout 最后一行 JSON 的 `type` 字段决定 Stage 1 走哪条分支

### Stage 1 剧本初稿（按来源选一个角色扮演）

| 来源 | 角色 | 做法 |
|---|---|---|
| video/audio | 小说化编剧 | 读 `00_source/raw.txt` + `prompts/p1_novelize.txt`，产出「小说化正文+逐镜头说明」写入 `01_script/ep{N}.novel.md` |
| novel | 选段师→改编师 | 选段师先从 raw.txt 选 600-1200 字冲突完整段落存 `ep{N}.selected.md`（文末附全书分集大纲）；改编师读选段 + `prompts/p3_adapt_novel.txt` 产出初稿 |
| idea | 原创编剧 | 以创意为题材写家庭情感向强冲突初稿（同格式） |
| script | 剧本整理师 | 不改剧情，只规范化成统一格式 |

### Stage 2 爆款改写 + 审核（循环，最多 2 轮）

1. **爆款改写师**：读初稿 + `prompts/p2_rewrite.txt`（先在文首逐条复述确认规则再改写），写入 `ep{N}.rewritten.md`
2. **剧本审核官**按 L1 rubric 审核并写 `ep{N}.review.md`：
   - 合规（抖音创作者中心：无暴力细节特写/无脏话/无违规元素）
   - 爆款三要素（黄金三秒强冲突开场 / 冲突升级递进 / 结尾互动钩子）
   - 质量（角色名前后一致 / 台词口语化 / 逻辑贴近现实）
   - 输出结论：通过 or 问题清单（每条：位置/问题/建议）
3. 不通过 → 把问题清单原样发给改写师修订，重审；两轮仍不过 → 带问题进入检查点让用户裁决
4. 通过后加一轮**独立终审**（换一个没看过初稿的视角，只读终稿挑毛病），有问题再修一轮

### ⏸ 检查点①（必须问用户）

把 `ep{N}.rewritten.md` 路径和审核结论告诉用户，问"批准进入角色/分镜设计吗？"用户给修改意见就落实后复审再继续。

### Stage 3 资产设定（两个角色可并行）

- **角色设定师** → `02_assets/characters.json`，每项：
  `{"name": "2-4字中文名(与剧本一致)", "gender": "", "age": "", "appearance": "发型/脸型/体型/肤色…", "costume": "上下装颜色材质/鞋…", "voice": ""}`
  （appearance/costume 必须具体到能直接生成三视图立绘）
- **场景道具师** → `scenes.json` 和 `props.json`，每项 `{"name": "简短名", "description": "具体到能直接出图"}`
- **资产审核官**（L2 rubric）：剧本里每个出场角色/场景/关键道具都已登记、名字与剧本用词一致、描述可出图。不过 → 发回对应设定师修一轮。

### Stage 3.5 参考图生成（脚本门禁 + 视觉抽检）

```
.venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/gen_assets.py --project projects/<剧名>
```

- 退出码 **3** = 未配 API key → 跳过本阶段（生产包自动走人工通道）
- 退出码 **1** = 生成失败 → 把 stdout 的错误（key 无效/额度不足）报给用户
- 退出码 **0** → 逐张看 `02_assets/images/*.png`（**参考图抽检员**）：图与设定一致？角色三视图齐全且同一人物？无崩坏/文字/水印？不合格的带反馈重生成：
  ```
  gen_assets.py --project … --only 名1,名2 --extra "重点修正: <问题>"
  ```

### Stage 4 分镜 + 双重门禁（循环，最多 3 轮）

1. **总分镜师**读剧本 + 三个资产 JSON，写 `03_storyboard/ep{N}.storyboard.json`：
   ```json
   {"style": "真人现代短剧", "shot_seconds": 15,
    "shots": [{"id": 1, "seconds": 15, "scene": "必须取自scenes.json",
               "characters": ["必须取自characters.json"], "props": ["取自props.json"],
               "prompt": "【画面】…【动作】…【镜头】…【台词】…"}]}
   ```
   约束：4-8 个镜头（或用户指定数）；prompt ≤1000 字且必含【画面】【动作】【镜头】；id 从 1 连续递增。
2. **机检（必须跑，不许跳）**：
   ```
   .venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/render_pack.py --project projects/<剧名> --episode <N>
   ```
   退出码 1 → stdout 有 issues JSON，逐条修分镜重跑；退出码 0 → 同时已渲染生产包到 `04_production/ep{N}/`。
3. **分镜审核官**（L3 rubric，写 `ep{N}.review.md`）：相邻镜头连戏、出场人物与剧情对应、情绪节奏递进、每镜头信息量配得上时长、黄金三秒落在镜头1。不过 → 意见发回分镜师重写，机检+审核重来。

### Stage 5 交付

最后跑一次 render_pack（幂等），然后把交付物告诉用户：
- `04_production/ep{N}/checklist.md`：用户照此去即刻AI/updream 操作（参考图已生成则第一节自动消失）
- `node_NN.md`：每镜的提示词（整段复制）+ 参考图勾选清单
- 提醒：片段下载后按 01.mp4… 放进 `05_footage/ep{N}/`，回来喊"质检剪辑"

---

## 模式二：qa（质检 + 自动剪辑）

1. 找 `05_footage/ep{N}/*.mp4`（没有 → 提示用户先去平台生成）；读 `03_storyboard/ep{N}.storyboard.json`
2. **片场质检员**逐条（可并行）：读视频片段（文件名数字=分镜 id），对照分镜卡与角色设定查：画面相符？人物服装长相一致？该有台词的有没有？是否废镜头（崩坏/黑屏/空镜过长）？结论写 `06_review/qa_ep{N}_shot{id}.json`，拿不准标 redo。
3. 剪辑（脚本）：
   ```
   .venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/auto_edit.py --project projects/<剧名> --episode <N>
   ```
   自动：检测长静音(≤-35dB 且 ≥2.8s)并裁掉 → 按编号拼接 → 1080x1920/30fps → `07_final/ep{N}_final.mp4`
4. 向用户报：成片路径、建议重生成的镜头清单（有的话）、静音裁剪明细

---

## ZCode 专用：保存的 workflow 参数

`CreateWorkflow saved: { name: "ai-short-drama", args: {...} }`，参数：
`title`(必填剧名) / `source`(必填素材) / `mode`(full|qa) / `episode`(默认1) / `shot_seconds`(15) / `shot_count`(0=自定) / `style`(真人现代短剧) / `source_type`(auto)
