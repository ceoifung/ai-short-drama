---
name: ai-short-drama
description: AI短剧全自动制作工作流（对标改写打法）。用户说"做短剧 / AI短剧 / 短剧工作流 / 跑短剧流水线 / 质检剪辑第X集"时触发。流程：素材入库（视频whisper转写/小说/创意归一化）→ 编剧改写（提示词驱动）→ AI审核 → 角色/场景资产 → 参考图生成（图片API+视觉抽检）→ 分镜（机检门禁）→ updream 生产包 →（人工平台生成后）AI质检+ffmpeg自动剪辑。环境自包含：setup_env.py 自建 .venv（faster-whisper）并自动供给 ffmpeg（缺失时下载静态版到 tools/）。
---

# AI 短剧工作流

把"对标改写"短剧打法自动化：AI 负责编剧、审核、分镜、参考图、质检与剪辑，人只做剧本/成片两次拍板和 updream 上的生成点击。

> 跨工具：仓库根 `AGENTS.md` 把 Codex/Claude Code/Gemini CLI 路由到本目录 `PLAYBOOK.md`（手动流程手册）；ZCode 优先走保存的 workflow，本文件是 ZCode 侧规程。

## 首次使用协议（AI 必须先执行，不要让用户手动改配置文件）

用户第一次触发本技能时，先跑状态检查（`.venv` 不存在则先引导跑 setup_env.py）：

```
.venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/configure.py --check
```

若 `need_setup: true`，**用 AskUserQuestion 引导配置，不要提"编辑 config.json"这类要求**：

1. 问题1（单选）："图片生成 API 用哪家？"
   - 智谱 CogView（推荐：已有智谱账号可直接用，open.bigmodel.cn 控制台领 key）
   - 火山方舟 Seedream（即梦同源；这把 key 以后还能接 Seedance 视频 API）
   - 暂不配置（参考图退回即刻AI人工通道，随时可再配）
2. 问题2（选了商家才问，提示用户在 Other/自定义里粘贴）："请粘贴 API key"
3. 代用户执行保存+验证（脚本会发一张测试图验证 key，约几分钱）：

```
.venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/configure.py --provider <zhipu|ark> --key <用户输入>
```

4. 把验证结果告诉用户（key 只保存在本机 config.json），然后正常启动工作流。
   验证失败时把脚本报的 HTTP 错误原样转述，让用户检查 key/余额后重试。
   用户不想验证可加 `--no-validate`。

终端用户也可以自己跑 `python .agents/skills/ai-short-drama/scripts/configure.py` 进交互向导。

## 调用方式

两个保存的动态 workflow：

1. **`ai-short-drama`**（制作流水线）——用 CreateWorkflow 的 `saved` 方式启动：

```
CreateWorkflow: saved = { name: "ai-short-drama", args: { title, source, mode, ... } }
```

2. **`ai-drama-recap`**（解说样片）——输入一个剧集文件夹（文件名排序=集数顺序），产出 5-10 分钟"一口气看完"式解说片（TTS口播+原声压低+逐短语解说字幕）：

```
CreateWorkflow: saved = { name: "ai-drama-recap", args: { title: "XX剧解说", source: <剧集文件夹>, target_minutes: 8 } }
```

流程：批量转写+抽帧 → 剧情分析师(每批5-6集, beat timeline) → 全剧梳理(十大爆点) → 解说文案+审核 → ⏸文案定稿 → 素材规划+机检(素材时长≥解说/原声单次≤5s且总占比<15%/总时长5-10分钟) → TTS口播(edge-tts, 语速+12%, 原声压12%) → ffmpeg 切片拼接+逐短语字幕 → `07_final/recap_v2.mp4`(TTS不可用自动降级无声字幕版)。设计文档见 docs/解说方案.md。

## 参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| title | string | 必填 | 剧名（=项目目录名 projects/&lt;title&gt;） |
| source | string | 必填 | 素材路径（视频/音频/txt小说）或一句话创意文本 |
| mode | string | full | full=入库→生产包；qa=质检+自动剪辑（素材就绪后跑） |
| source_type | string | auto | auto/novel/idea/script/video/audio，一般不用指定 |
| episode | number | 1 | 集号（多集=改集号重跑） |
| shot_seconds | number | 15 | 每镜头时长（5-20秒） |
| shot_count | number | 0 | 0=按剧本自定（4-8镜头） |
| style | string | 真人现代短剧 | 画面风格 |

## 两次运行的节奏

1. **mode=full**：跑到"生产包"为止，中途有一个"剧本定稿确认"检查点。产物在 `04_production/ep<N>/`。
2. 人照 `checklist.md` 在即刻AI出角色图、updream 逐镜生成（照 node_NN.md 复制粘贴），批量下载后把 mp4 按镜头编号（01.mp4…）放进 `05_footage/ep<N>/`。
3. **mode=qa**：AI 逐条看片质检 + ffmpeg 自动剪静音/拼接/9:16，成片落 `07_final/`。

## 项目目录约定（projects/&lt;剧名&gt;/）

```
00_source/   raw.txt + source_meta.json（来源类型/字数）
01_script/   ep{N}.novel.md 初稿 → ep{N}.rewritten.md 终稿 → ep{N}.review.md 审核
02_assets/   characters.json / scenes.json / props.json（+ 平台生成的图片）
03_storyboard/ ep{N}.storyboard.json（机检：引用完整性/字数/时长）
04_production/ep{N}/  node_NN.md（提示词+参考图清单）+ manifest.json + checklist.md
05_footage/  ep{N}/01.mp4…（人工放入）
06_review/   qa_*.json + ep{N}_silences.json
07_final/    ep{N}_final.mp4
```

## 提示词可调

`prompts/` 下的 p1（小说化）、p2（爆款改写，核心规则来自用户《提示词.doc》原文）、p3（小说改编）都是纯文本，改文件即生效，不用动 workflow。

## 新环境部署（发给新客户机器时）

1. 整个 `E:\AI短剧` 目录（含 `.zcode/`）拷过去，装好任意 **Python 3.9+**（ffmpeg 缺失会自动下载）
2. 在工作区根目录跑一次：`python .agents/skills/ai-short-drama/scripts/setup_env.py`
   - 自动创建工作区 `.venv` 并安装 faster-whisper/numpy（workflow 只认 `.venv/Scripts/python.exe`，不依赖任何机器上的绝对路径）
   - 自动定位 whisper 模型：config 指定 > 工作区 `models/whisper-turbo` > 本机 `E:\ai-subtitle` 老安装 > 留空则首次转写自动从 hf-mirror 下载（约1.6GB）
   - 自检 ffmpeg(缺失自动下载)/GPU 可用性，生成 `config.json`
3. 首次对 AI 说"做短剧"时，会自动弹出服务商选择和 key 输入引导（见下方"首次使用协议"），用户不用手动碰任何配置文件

## 图片 API 接入（无人值守出参考图）

1. 配置走首次使用引导（AI 弹选项代填），或终端跑 `scripts/configure.py` 交互向导；key 存本机 config.json
2. full 模式自动多跑"生成参考图并抽检"：API 出图 → 视觉抽检 → 不合格带反馈重生成
3. 不配 key 自动降级为即刻AI人工通道

## 脚本（确定性部分）

- `scripts/setup_env.py` — 一键装配（venv/依赖/ffmpeg自动下载/模型定位/config）
- `scripts/ensure_ffmpeg.py` — ffmpeg 自动供给（检测→下载静态版→抽取→验证, --check/--force）
- `scripts/configure.py` — 配置向导（--check 查状态 / --provider --key 代填+验证 / 无参交互式）
- `scripts/ingest.py` — Stage 0 归一化；媒体走 faster-whisper（GPU 优先 CPU 兜底；模型路径四级解析；传 numpy 绕过旧 PyAV 兼容问题）
- `scripts/render_pack.py` — Stage 4 机检 + 生产包渲染（退出码=门禁）；自动感知已生成参考图切换人工/API通道
- `scripts/gen_assets.py` — Stage 4.5 参考图生成（图片API通道，断点续跑，退出码 3=未配key自动降级）
- `scripts/auto_edit.py` — Stage 6 静音裁剪 + 拼接 + 1080x1920/30fps 导出

运行环境：工作区 `.venv`（setup_env.py 创建）；ffmpeg PATH 优先、tools/ 本地兜底（ensure_ffmpeg.py 自动下载）。
