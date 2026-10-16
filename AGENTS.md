# AGENTS.md — AI 短剧自动化工作区

本仓库是 AI 短剧生产流水线的工作区：任何遵循本文件的 coding agent（Codex / Claude Code / Gemini CLI / ZCode 等）都能按统一流程产出短剧。

## 用户找你做短剧时（"做短剧 / AI短剧 / 短剧工作流 / 质检剪辑"）

**先读流程手册**：`.agents/skills/ai-short-drama/PLAYBOOK.md`——所有阶段、提示词、脚本调用、审核标准、门禁规则都在里面，严格照做。

**ZCode 快速通道**：如果你是 ZCode 且有动态 workflow 能力，不要手动走流程，直接运行保存的工作流 `ai-short-drama`（CreateWorkflow saved 方式，参数见 PLAYBOOK 末尾）。手动流程是给其他工具的降级路径。

## 硬规则（先记住这几条）

1. **门禁靠脚本退出码，不靠自觉**：机检脚本（render_pack / gen_assets / auto_edit）退出码非 0 就是没过，把 stdout 里的 issues 逐条修掉再重跑，最多 3 轮，仍不过就停下来把问题报给用户，不要自欺欺人地说"通过了"。
2. **产物只写进 `projects/<剧名>/` 的固定目录**（00_source ~ 07_final，见 PLAYBOOK），别的地方不要动。
3. **分镜/提示词只能引用资产 JSON 里登记过的名字**，机器会查。
4. 花钱之前（参考图 API、用户去平台生成）先让用户确认剧本。

## 首次使用（新环境必做）

两种安装方式，数据位置不同（以 `configure.py --check` 的输出为准）：
- **克隆仓库当工作区**（推荐，ZCode 全自动编排用这种）：数据就在仓库内 `.venv/`、`config.json`、`projects/`
- **全局安装**（`python .agents/skills/ai-short-drama/scripts/install.py`，适合在其他项目里随时用）：数据在 `~/.ai-short-drama/` 下

```
1. python .agents/skills/ai-short-drama/scripts/setup_env.py   # 建 .venv、装依赖、定位模型、生成 config.json
2. python .agents/skills/ai-short-drama/scripts/configure.py --check  # 检查配置状态(含 venv 实际路径)
```

若 `need_setup: true`：在对话里问用户选哪家图片 API（智谱 CogView / 火山 Seedream / 暂不配置），拿到 key 后代存：

```
.venv/Scripts/python.exe .agents/skills/ai-short-drama/scripts/configure.py --provider <zhipu|ark> --key <key>
```

（上面这条里的 python 路径换成 `--check` 输出的 `venv_python`；Linux/macOS 是 `.venv/bin/python`。）不要让用户手动编辑配置文件。
