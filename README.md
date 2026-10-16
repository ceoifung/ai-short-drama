# AI 短剧自动生产流水线

把一条"对标改写"短剧打法全流程自动化：**任意形态素材（对标视频 / 小说 / 一句话创意）→ AI 编剧与爆款改写 → 多级审核 → 角色/场景设定 → 参考图生成 → 分镜与机检 → updream 生产包 → AI 质检 + 自动剪辑成片**。

支持 ZCode 全自动编排（编译型工作流引擎：审核门禁/并行审片/断点续跑），也支持 Codex / Claude Code / Gemini CLI 等任何能跑 shell 的 coding agent 按跨工具手册执行（门禁靠脚本退出码保证）。

## 流程总览

```
素材(视频/音频/小说/创意) ──► 00_source 归一化(本地whisper转写)
  ──► 01_script  剧本初稿 → 爆款改写 → 审核循环(黄金三秒/冲突升级/互动钩子/平台合规)
  ──► ⏸ 剧本定稿确认(你拍板)
  ──► 02_assets  角色三视图设定/场景/道具(JSON) + 审核官核查
  ──► 参考图生成(图片API, 可选) + 视觉抽检 + 不合格自动重生成
  ──► 03_storyboard 分镜 → 机检(引用完整性/字数/时长) + 连戏审核 → 不过自动打回重写
  ──► 04_production 生产包: 每镜头一张"提示词+参考图清单"卡 + 平台操作清单
  ──► (你在即刻AI/updream 照卡点击生成, 片段放回 05_footage)
  ──► AI 逐条审片 + ffmpeg 自动剪静音/拼接/9:16 ──► 07_final 成片
```

## 安装

前置：任意 Python 3.9+，ffmpeg 已加入 PATH。

### 方式一：克隆仓库当工作区（推荐，ZCode 用户必选）

```bash
git clone https://github.com/<你的用户名>/ai-short-drama.git
cd ai-short-drama
python .agents/skills/ai-short-drama/scripts/setup_env.py
```

克隆下来的目录就是工作区：剧本、资产、生产包都会在 `projects/<剧名>/` 下。ZCode 用户还能直接运行保存的工作流 `ai-short-drama`（全自动编排）。

### 方式二：全局安装（在你任何项目里都能用）

```bash
git clone https://github.com/<你的用户名>/ai-short-drama.git
python ai-short-drama/.agents/skills/ai-short-drama/scripts/install.py
```

技能装到 `~/.agents/skills/`（跨工具标准全局位），数据（venv/config/模型/项目产物）集中在 `~/.ai-short-drama/`。装完在任何项目里对你的 AI 说"做短剧"即可。

### 首次配置

第一次使用时 AI 会自动引导你选图片 API（智谱 CogView / 火山 Seedream）并粘贴 key（自动验证后存本机）。不配也能用——参考图环节自动退回即刻AI人工通道。终端党可以自己跑：

```bash
python .agents/skills/ai-short-drama/scripts/configure.py   # 交互向导
```

## 使用

对你的 AI 说人话即可，例如：

- "用 D:\素材\爆款短剧.mp4 当对标，做一部短剧"（视频对标模式）
- "拿这篇小说做短剧：xxx.txt"（小说改编模式，自动分集选段）
- "一句话创意：婆媳争一个碗，碗里有外婆的遗言"（原创模式）
- "质检剪辑《暮色餐厅》第1集"（片段放好后收尾出片）

ZCode 用户由技能自动路由到工作流；其他工具按 `AGENTS.md → PLAYBOOK.md` 手动流程执行。

## 目录结构

```
AGENTS.md                     # 所有 coding agent 的入口路由
agents 资产: .agents/skills/ai-short-drama/
  PLAYBOOK.md                 # 跨工具流程手册(阶段/角色/提示词/门禁/审核标准)
  SKILL.md                    # ZCode 侧规程(触发词/首次配置协议)
  prompts/                    # p1小说化 p2爆款改写 p3小说改编(可自行调优)
  scripts/                    # setup_env/install/ingest/gen_assets/render_pack/auto_edit/configure
  workflow.dwf.ts             # ZCode 全自动编排源码(正式定义在 .zcode/workflows/)
examples/暮色餐厅/            # 一次真实全自动试跑的样例产物(小说→剧本→分镜→生产包)
docs/                         # 设计文档
projects/<剧名>/              # 你的每部剧(00_source ~ 07_final, git 忽略)
```

## 两种运行模式的差别

| | ZCode + 本仓库 | 其他 agent(全局安装或手动) |
|---|---|---|
| 流程执行 | 编译型工作流引擎全自动 | 按 PLAYBOOK 手动流程, 尽力而为 |
| 审核门禁 | 引擎强制(不过不放行) | 脚本退出码强制 + 程序约束 |
| 并行审片/断点续跑 | ✅ | ❌ |
| 参考图API/机检/自动剪辑 | ✅(脚本层, 全模式相同) | ✅(脚本层, 全模式相同) |

## 已知边界

- 视频生成环节目前在 updream 平台人工执行（照生产包点击，约30分钟/集）；生产包已把思考全部前置
- whisper 模型首次转写若无本地缓存会自动从 hf-mirror 下载（约1.6GB）
- 工作流的 venv 路径字面量当前为 Windows 写法，Linux/macOS 的 ZCode 用户需把 `.venv/Scripts/python.exe` 改为 `.venv/bin/python`

## 样例

`examples/暮色餐厅/` 是一次真实全自动试跑的产物：895字小说输入 → 84分过审剧本（7镜头含黄金三秒设计）→ 通过机检+连戏审核的分镜 → 可直接照做的生产包。
