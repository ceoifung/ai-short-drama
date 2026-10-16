// AI 短剧自动化工作流（P1: full=素材→生产包 / qa=质检+自动剪辑）
interface SourceInfo {
  /** 归一化后的来源类型 */
  type: "novel" | "idea" | "script" | "video" | "audio";
  /** 源文本字符数 */
  chars: number;
  /** 入库摘要 */
  summary: string;
}

interface Draft {
  /** 剧本文件的 workspace 相对路径 */
  path: string;
  /** 一句话内容概括 */
  summary: string;
  /** 出场人物名 */
  characters: string[];
}

interface Issue {
  /** high=会导致废片或平台不过审; medium=明显缺陷; low=可改可不改 */
  severity: "low" | "medium" | "high";
  /** 问题位置(镜头/段落/章节) */
  where: string;
  /** 一句话: 什么问题 */
  problem: string;
  /** 具体修改建议 */
  suggestion: string;
}

interface Verdict {
  /** 是否通过 */
  pass: boolean;
  /** 0-100 综合分 */
  score: number;
  /** 问题清单 */
  issues: Issue[];
}

interface SegmentInfo {
  /** 选段文件路径 */
  path: string;
  /** 选段一句话概括 */
  summary: string;
  /** 全书分集大纲(每集一句话+结尾钩子) */
  episodes_hint: string;
}

interface BoardInfo {
  /** storyboard.json 路径 */
  path: string;
  /** 镜头数 */
  shots: number;
  /** 总秒数 */
  total_seconds: number;
}

interface PackInfo {
  /** 生产包目录 */
  dir: string;
  /** 节点数 */
  nodes: number;
  /** 执行清单路径 */
  checklist: string;
}

interface Approval {
  /** 是否批准进入资产/分镜阶段 */
  approved: boolean;
  /** 修改意见(不批准时给出) */
  notes: string;
}

interface AssetFiles {
  /** 主文件路径(characters.json 或 scenes.json) */
  path: string;
  /** 主文件登记的名字 */
  names: string[];
  /** 附带文件路径(props.json, 可为空) */
  extra_path?: string;
  /** 附带文件登记的名字 */
  extra_names?: string[];
}

interface QaClip {
  /** 片段文件名 */
  clip: string;
  /** 对应分镜 id */
  shot_id: number;
  /** ok=可用; redo=建议重生成 */
  verdict: "ok" | "redo";
  /** 问题列表(空=无问题) */
  problems: string[];
}

interface ImgCheck {
  /** 图片文件名(含扩展名) */
  name: string;
  /** ok=可用; redo=需重生成 */
  verdict: "ok" | "redo";
  /** 问题说明(redo 时给原因) */
  problems: string[];
}

interface Finding {
  /** 位置: 文件或镜头 */
  where: string;
  /** 发现了什么 */
  what: string;
  /** 依据 */
  evidence: string;
  /** verified=独立复核或机检确认; unconfirmed=单方判断 */
  status: "verified" | "unconfirmed";
  /** high=影响成片或过审 */
  severity: "low" | "medium" | "high";
}

interface WorkflowReport {
  /** 两三句话回答用户要什么 */
  conclusion: string;
  findings: Finding[];
  /** 本次跑过并起决定作用的检查 */
  verified: string[];
  /** 没查什么/查不了什么, 为什么 */
  notCovered: string[];
}

const title = String(args.title ?? "暮色餐厅");
const source = String(args.source ?? "测试素材_小说.txt");
const mode = String(args.mode ?? "full");
const stypeArg = String(args.source_type ?? "auto");
const ep = Number(args.episode ?? 1);
const shotSeconds = Number(args.shot_seconds ?? 15);
const shotCount = Number(args.shot_count ?? 0);
const style = String(args.style ?? "真人现代短剧");


const SK = ".agents/skills/ai-short-drama";
const PROJ = "projects/" + title;
const draftPath = PROJ + "/01_script/ep" + ep + ".novel.md";
const rewrittenPath = PROJ + "/01_script/ep" + ep + ".rewritten.md";
const boardPath = PROJ + "/03_storyboard/ep" + ep + ".storyboard.json";
const sizeHint = shotCount > 0 ? "恰好 " + shotCount + " 个镜头" : "4-8 个镜头(按剧情密度定)";

function lastJson(s: string): unknown {
  const lines = s.trim().split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const t = lines[i].trim();
    if (t.startsWith("{")) {
      try {
        return JSON.parse(t);
      } catch {
        // 继续往前找
      }
    }
  }
  return undefined;
}

function failRun(conclusion: string, evidence: string): WorkflowReport {
  return {
    conclusion,
    findings: [{ where: "-", what: conclusion, evidence, status: "unconfirmed", severity: "high" }],
    verified: [],
    notCovered: ["失败于前置阶段, 后续环节未执行"],
  };
}

if (mode === "qa") {
  phase("逐条质检片段");
  const clips = await files.glob(PROJ + "/05_footage/ep" + ep + "/*.mp4");
  if (clips.length === 0) {
    return failRun("05_footage/ep" + ep + " 里没有片段", "把 updream 批量下载解压后的 mp4 按镜头编号(01.mp4, 02.mp4…)放入后重跑 mode=qa");
  }
  let shotsCount = 0;
  try {
    shotsCount = (JSON.parse(await files.read(boardPath)) as { shots: unknown[] }).shots.length;
  } catch {
    return failRun("找不到或读不了分镜文件 " + boardPath, "先跑 mode=full 生成分镜后再质检");
  }
  log("待质检 " + clips.length + " 个片段, 分镜共 " + shotsCount + " 个镜头");
  const qas = await Promise.all(
    clips.map((c) => {
      const m = c.match(/(\d+)\.mp4$/);
      const sid = Number(m?.[1] ?? 0);
      return agent("片场质检员·镜头" + sid).ask<QaClip>(
        "用 Read 工具观看片段 " + c + " (视频文件可直接读), 对照分镜 " + boardPath + " 里 id=" + sid + " 的镜头与角色表 " + PROJ + "/02_assets/characters.json 核查: 1 画面与该镜头的【画面】【镜头】是否相符 2 出场人物长相/服装与设定是否一致 3 该有台词的镜头有没有出台词 4 是否明显废镜头(画面崩坏/长时间空镜/黑屏)。把结论写入 " + PROJ + "/06_review/qa_ep" + ep + "_shot" + sid + ".json (UTF-8 JSON, 字段 clip/shot_id/verdict/problems) 并返回结果对象。拿不准就 verdict=redo 并说明原因。",
      );
    }),
  );
  qas.forEach((q) => report(q));

  phase("自动剪辑并导出成片");
  const edit = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/auto_edit.py", "--project", PROJ, "--episode", String(ep)], { timeoutMs: 600000 });
  if (edit.exitCode !== 0) {
    return failRun("自动剪辑失败", (edit.stdout + edit.stderr).slice(0, 500));
  }
  const editInfo = lastJson(edit.stdout) as { final: string; clips: number; trims: { clip: string; seconds: number }[]; final_seconds: number } | undefined;
  if (editInfo === undefined) {
    return failRun("剪辑输出解析失败", edit.stdout.slice(0, 500));
  }
  log("成片 " + editInfo.final + " (" + editInfo.final_seconds + " 秒, 裁掉 " + editInfo.trims.length + " 段长静音)");
  try {
    await artifact.file("final", editInfo.final, { title: "《" + title + "》第 " + ep + " 集成片" });
  } catch {
    await artifact.markdown("final-note", "成片已生成: " + editInfo.final + " (文件超出发布上限, 请在本地打开)", { title: "《" + title + "》第 " + ep + " 集成片" });
  }
  const redo = qas.filter((q) => q.verdict === "redo");
  await artifact.markdown(
    "qa-report",
    [
      "# 第 " + ep + " 集质检报告",
      "",
      "- 片段 " + editInfo.clips + " 条, 通过 " + (qas.length - redo.length) + " 条, 建议重生成 " + redo.length + " 条",
      "- 静音裁剪 " + editInfo.trims.length + " 段: " + editInfo.trims.map((t) => t.clip + " 移除 " + t.seconds + "s").join("; "),
      "- 成片: " + editInfo.final + " (" + editInfo.final_seconds + " 秒)",
      "",
      "## 建议重生成的镜头",
      ...(redo.length === 0 ? ["(无)"] : redo.map((r) => "- 镜头" + r.shot_id + " (" + r.clip + "): " + r.problems.join("; "))),
    ].join("\n"),
    { title: "第 " + ep + " 集质检报告" },
  );
  return {
    conclusion: "第 " + ep + " 集成片已导出: " + editInfo.final + ", " + editInfo.final_seconds + " 秒。逐条质检 " + qas.length + " 条片段, " + (redo.length === 0 ? "全部可用" : redo.length + " 条建议重生成(见质检报告)") + "。",
    findings: redo.map((r) => ({
      where: r.clip,
      what: r.problems.join("; "),
      evidence: "质检员对照分镜 id=" + r.shot_id + " 审看结论: " + PROJ + "/06_review/",
      status: "unconfirmed" as const,
      severity: "medium" as const,
    })),
    verified: [
      "逐片段由独立质检员对照分镜与角色设定审看 (" + qas.length + " 条)",
      "静音由 ffmpeg silencedetect 机检 (<=-35dB 且 >=2.8s) 并自动裁剪, 拼接后统一 1080x1920/30fps",
    ],
    notCovered: ["跨镜头人物一致性为逐条独立判断, 未做全局比对", "成片发布效果(抖音端)未验证"],
  };
}

// ---------------- mode = full ----------------

phase("素材入库与来源识别");
log("归一化素材: " + source);
const ing = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/ingest.py", "--project", PROJ, "--source", source, "--type", stypeArg, "--episode", String(ep)], { timeoutMs: 600000 });
if (ing.exitCode !== 0) {
  return failRun("素材入库失败", (ing.stdout + ing.stderr).slice(0, 500));
}
const meta = lastJson(ing.stdout) as SourceInfo | undefined;
if (meta === undefined) {
  return failRun("入库输出无法解析", ing.stdout.slice(0, 500));
}
log("来源类型 " + meta.type + ", " + meta.chars + " 字: " + meta.summary);

phase("创作剧本初稿");
let draft: Draft;
if (meta.type === "novel") {
  const seg = await agent("选段师", { system: "你是短剧选段编辑, 擅长从长文里挑出冲突完整、适合单集竖屏短剧的段落。把文件写到指定路径。素材不适合或要求无法满足时直接说明, 不要编造。" }).ask<SegmentInfo>(
    "读取小说 " + PROJ + "/00_source/raw.txt (约 " + meta.chars + " 字)。为第 " + ep + " 集选出冲突最完整、最适合做一集短剧的段落(600-1200字), 原文摘出写入 " + PROJ + "/01_script/ep" + ep + ".selected.md; 文件末尾加「# 分集大纲」小节: 全书可拆分的每一集一句话梗概+结尾钩子。只返回结果对象。",
  );
  draft = await agent("改编师", { system: "你是短剧编剧, 擅长把小说改编成画面感强的分镜剧本。把文件写到指定路径。无法满足要求时直接说明, 不要编造。" }).ask<Draft>(
    "读取选段 " + seg.path + " 和提示词 " + SK + "/prompts/p3_adapt_novel.txt, 把小说段落改编成「小说化正文+逐镜头说明」的短剧剧本初稿, 写入 " + draftPath + "。每镜头约 " + shotSeconds + " 秒容量, 共 " + sizeHint + "。只返回结果对象。",
  );
} else if (meta.type === "idea") {
  draft = await agent("原创编剧", { system: "你是短剧编剧, 擅长从一句话创意扩写成强冲突的家庭情感短剧。把文件写到指定路径。无法满足要求时直接说明, 不要编造。" }).ask<Draft>(
    "读取创意原文 " + PROJ + "/00_source/raw.txt, 以此为题材写竖屏短剧剧本初稿: 家庭情感向、多角色、强冲突、情绪递进, 格式「小说化正文+逐镜头说明」, 写入 " + draftPath + "。每镜头约 " + shotSeconds + " 秒容量, 共 " + sizeHint + "。只返回结果对象。",
  );
} else if (meta.type === "script") {
  draft = await agent("剧本整理师", { system: "你是短剧剧本整理编辑。把文件写到指定路径。无法满足要求时直接说明, 不要编造。" }).ask<Draft>(
    "读取已有剧本 " + PROJ + "/00_source/raw.txt, 整理成统一格式「小说化正文+逐镜头说明」(每个镜头: 场景/景别/人物/动作/台词), 不改剧情只做规范化, 写入 " + draftPath + "。只返回结果对象。",
  );
} else {
  draft = await agent("小说化编剧", { system: "你是短剧编剧, 擅长把台词转写稿还原成画面感强的小说化分镜剧本, 一句台词都不丢。把文件写到指定路径。无法满足要求时直接说明, 不要编造。" }).ask<Draft>(
    "读取转写稿 " + PROJ + "/00_source/raw.txt 和提示词 " + SK + "/prompts/p1_novelize.txt, 严格按提示词把台词稿还原成「小说化正文+逐镜头说明」的剧本初稿, 写入 " + draftPath + "。只返回结果对象。",
  );
}
log("初稿完成: " + draft.path + " - " + draft.summary);

phase("爆款改写与审核");
const rewriter = agent("爆款改写师", { system: "你是爆款短剧改写手, 严格执行提示词里的创作规则与合规红线。把文件写到指定路径。规则之间冲突或无法满足时直接上报, 不要硬编。" });
const scriptReviewer = agent("剧本审核官", { system: "你是短剧平台的严苛审稿人, 按 rubric 逐条核查, 宁可挑刺不放水; 判 high 必须给确凿依据。把审核报告写到指定路径。" });
let feedback = "无(第一轮)";
let verdict: Verdict = { pass: false, score: 0, issues: [] };
for (let round = 1; round <= 2 && !verdict.pass; round++) {
  await rewriter.ask(
    "第 " + round + " 轮改写。读取初稿 " + draft.path + " 和提示词 " + SK + "/prompts/p2_rewrite.txt: 先在文首逐条复述确认规则, 再执行爆款改写, 写入 " + rewrittenPath + " (覆盖旧稿)。单集体量 " + sizeHint + "。上一轮审核意见(逐条解决): " + feedback,
  );
  verdict = await scriptReviewer.ask<Verdict>(
    "审核剧本 " + rewrittenPath + " (判断改写是否跑偏可对照初稿 " + draft.path + "): 1 合规(抖音创作者中心: 无暴力细节特写/无脏话/无违规元素) 2 爆款三要素(黄金三秒强冲突开场/冲突升级递进/结尾互动钩子) 3 质量(角色名前后一致/台词口语化/逻辑贴近现实)。审核报告写入 " + PROJ + "/01_script/ep" + ep + ".review.md (覆盖), 返回结构化结论。",
  );
  report({ stage: "剧本审核", round, score: verdict.score, pass: verdict.pass });
  feedback = JSON.stringify(verdict.issues);
}
if (verdict.pass) {
  const fresh = await agent("独立终审员", { system: "你是没看过任何前期讨论的独立审稿人, 只凭文本本身挑毛病。把报告写到指定路径。挑不出毛病就如实通过。" }).ask<Verdict>(
    "只读剧本 " + rewrittenPath + " (不提供初稿和往期意见), 从「观众会不会三秒划走」「台词像不像真人说的」「有没有过不了平台审核的内容」三个角度独立挑毛病。报告写入 " + PROJ + "/01_script/ep" + ep + ".final_read.md, 返回结论。",
  );
  report({ stage: "独立终审", score: fresh.score, pass: fresh.pass });
  if (!fresh.pass && fresh.issues.length > 0) {
    await rewriter.ask("独立终审意见(逐条解决, 其余不动): " + JSON.stringify(fresh.issues) + "。修订 " + rewrittenPath);
    verdict = await scriptReviewer.ask<Verdict>("复审 " + rewrittenPath + ", 重点核查终审意见是否已解决。更新 " + PROJ + "/01_script/ep" + ep + ".review.md, 返回结论。");
    report({ stage: "终审复审", score: verdict.score, pass: verdict.pass });
  }
}

const approval = await hole<Approval>(
  "剧本定稿确认",
  "《" + title + "》第 " + ep + " 集剧本已生成: " + rewrittenPath + " 。审核结论: " + (verdict.pass ? "通过 (" + verdict.score + " 分)" : "两轮未全过 (" + verdict.score + " 分), 遗留问题: " + JSON.stringify(verdict.issues.slice(0, 3))) + " 。批准进入角色/分镜设计吗? 不批准请在 notes 里给修改意见。", async () => {
  return { approved: true, notes: "" };
},
);
if (!approval.approved && approval.notes.trim().length > 0) {
  await rewriter.ask("用户对剧本的修改意见(逐条落实): " + approval.notes + "。修订 " + rewrittenPath);
  verdict = await scriptReviewer.ask<Verdict>("按用户意见修订后的复审 " + rewrittenPath + ", 更新 " + PROJ + "/01_script/ep" + ep + ".review.md, 返回结论。");
  report({ stage: "用户意见复审", score: verdict.score, pass: verdict.pass });
}

phase("设定角色与场景资产");
const assetsDir = PROJ + "/02_assets";
// join: 分镜阶段需要角色与场景两份资产都齐
const charDesigner = agent("角色设定师", { system: "你是短剧角色设计师, 输出的设定要具体到能直接生成三视图立绘。把文件写到指定路径。无法满足要求时直接说明, 不要编造。" });
const sceneDesigner = agent("场景道具师", { system: "你是短剧美术设定师, 场景与道具描述要具体到能直接出图。把文件写到指定路径。无法满足要求时直接说明, 不要编造。" });
const [charRes, sceneRes] = await Promise.all([
  charDesigner.ask<AssetFiles>(
    "读取定稿剧本 " + rewrittenPath + ", 提取全部出场角色, 写入 " + assetsDir + "/characters.json (UTF-8 JSON 数组): 每项 {name, gender, age, appearance, costume, voice}。name 用 2-4 字中文名且与剧本用词完全一致; appearance/costume 具体到发型/脸型/体型/上下装颜色材质/鞋。只返回结果对象(path=文件路径, names=角色名列表)。",
  ),
  sceneDesigner.ask<AssetFiles>(
    "读取定稿剧本 " + rewrittenPath + ", 提取全部场景与关键道具, 分别写入 " + assetsDir + "/scenes.json (数组 [{name, description}]) 和 " + assetsDir + "/props.json (数组 [{name, description}])。name 简短(如「老式厨房餐厅」)且与剧本用词一致。返回 {path: scenes.json 路径, names: 场景名, extra_path: props.json 路径, extra_names: 道具名}。",
  ),
]);
const assetReviewer = agent("资产审核官", { system: "你是设定集审核员, 专查遗漏与命名不一致。把报告写到指定路径。挑不出问题就如实通过。" });
let assetVerdict = await assetReviewer.ask<Verdict>(
  "对照剧本 " + rewrittenPath + " 核查 " + assetsDir + "/ 下 characters.json / scenes.json / props.json: 1 剧本中每个出场角色、每处场景、每个关键道具都已登记 2 名字与剧本用词完全一致 3 描述可直接出图。报告写入 " + assetsDir + "/review.md, 返回结论。",
);
if (!assetVerdict.pass) {
  await Promise.all([
    charDesigner.ask("资产审核意见(涉及角色的逐条修复): " + JSON.stringify(assetVerdict.issues) + "。更新 " + assetsDir + "/characters.json, 返回新的 {path, names}。"),
    sceneDesigner.ask("资产审核意见(涉及场景/道具的逐条修复): " + JSON.stringify(assetVerdict.issues) + "。更新 scenes.json / props.json, 返回新的 {path, names, extra_path, extra_names}。"),
  ]);
  assetVerdict = await assetReviewer.ask<Verdict>("修复后复审 " + assetsDir + "/ 三个 json, 更新 " + assetsDir + "/review.md, 返回结论。");
  report({ stage: "资产复审", pass: assetVerdict.pass, score: assetVerdict.score });
}
log("资产: 角色 " + charRes.names.length + " / 场景 " + sceneRes.names.length + " / 道具 " + (sceneRes.extra_names?.length ?? 0));

phase("生成参考图并抽检");
let imagesGenerated = false;
const imgGen = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/gen_assets.py", "--project", PROJ], { timeoutMs: 900000 });
if (imgGen.exitCode === 3) {
  log("未配置图片 API key, 跳过参考图生成 (照 checklist 人工出图)");
} else if (imgGen.exitCode !== 0) {
  return failRun("参考图生成失败 (检查 config.json 的 key/额度)", (imgGen.stdout + imgGen.stderr).slice(0, 500));
} else {
  imagesGenerated = true;
  const imgs = await files.glob(PROJ + "/02_assets/images/*.png");
  if (imgs.length > 0) {
    const checks = await Promise.all(
      imgs.map((p) => {
        const name = p.split("/").pop() ?? p;
        return agent("参考图抽检员·" + name).ask<ImgCheck>(
          "用 Read 工具查看图片 " + p + " , 并在 " + assetsDir + "/ 下三个 json 里按去扩展名的名字找到它的设定(角色看 appearance/costume, 场景道具看 description), 核查: 1 图与设定是否一致 2 角色类是否三视图齐全(正/侧/背)且为同一人物 3 有无明显崩坏(畸形/文字/水印)。返回 {name: 文件名, verdict, problems}; 拿不准就 redo 并说明。",
        );
      }),
    );
    const bad = checks.filter((c) => c.verdict === "redo");
    report({ stage: "参考图抽检", total: imgs.length, redo: bad.length });
    if (bad.length > 0) {
      const extras = bad.map((b) => b.name + ": " + b.problems.join("; ")).join(" | ");
      const regen = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/gen_assets.py", "--project", PROJ, "--only", bad.map((b) => b.name.replace(/\.[a-z]+$/, "")).join(","), "--extra", "重点修正: " + extras], { timeoutMs: 900000 });
      log(bad.length + " 张抽检不过, 已带反馈重生成 (退出码 " + regen.exitCode + ")");
    }
  }
}

phase("撰写分镜并通过校验");
const boardWriter = agent("总分镜师", { system: "你是分镜师, 只引用资产表里存在的名字, 输出严格合法 JSON。把文件写到指定路径。要求无法满足时直接说明, 不要编造。" });
const boardReviewer = agent("分镜审核官", { system: "你是连戏审核员, 专查镜头衔接、人物出场逻辑与节奏。宁可挑刺; 判 high 要有确凿依据。把报告写到指定路径。" });
let pack: PackInfo | undefined;
let boardFeedback = "无(第一轮)";
for (let round = 1; round <= 3 && pack === undefined; round++) {
  await boardWriter.ask<BoardInfo>(
    "读取剧本 " + rewrittenPath + "、角色表 " + assetsDir + "/characters.json、场景表 " + assetsDir + "/scenes.json、道具表 " + assetsDir + "/props.json。为第 " + ep + " 集撰写分镜, 写入 " + boardPath + " (UTF-8 JSON): {\"style\": \"" + style + "\", \"shot_seconds\": " + shotSeconds + ", \"shots\": [{\"id\": 1, \"seconds\": " + shotSeconds + ", \"scene\": \"必须取自 scenes.json\", \"characters\": [\"必须取自 characters.json\"], \"props\": [\"取自 props.json 或留空数组\"], \"prompt\": \"【画面】…【动作】…【镜头】…【台词】…\"}]}。共 " + sizeHint + "; 镜头 id 从 1 连续递增; 每条 prompt 不超过 1000 字且必须包含【画面】【动作】【镜头】三个标记。机检与审核意见(逐条解决): " + boardFeedback,
  );
  const gate = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/render_pack.py", "--project", PROJ, "--episode", String(ep)]);
  if (gate.exitCode !== 0) {
    boardFeedback = "机检未过: " + gate.stdout.trim();
    continue;
  }
  const semantic = await boardReviewer.ask<Verdict>(
    "对照剧本 " + rewrittenPath + " 与角色设定, 审核 " + boardPath + ": 相邻镜头场景/人物衔接是否连戏、出场人物与剧情是否对应、情绪节奏是否递进、每镜头信息量是否匹配 " + shotSeconds + " 秒、黄金三秒是否落在镜头 1。报告写入 " + PROJ + "/03_storyboard/ep" + ep + ".review.md (覆盖), 返回结论。",
  );
  report({ stage: "分镜审核", round, score: semantic.score, pass: semantic.pass });
  if (semantic.pass) {
    const parsed = lastJson(gate.stdout) as PackInfo | undefined;
    if (parsed !== undefined) {
      pack = parsed;
    } else {
      boardFeedback = "机检输出解析失败: " + gate.stdout;
    }
  } else {
    boardFeedback = JSON.stringify(semantic.issues);
  }
}
if (pack === undefined) {
  return failRun("分镜 3 轮未过校验, 已停止 (生产包未生成)", boardFeedback.slice(0, 500));
}

phase("生成交付包");
const render = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/render_pack.py", "--project", PROJ, "--episode", String(ep)]);
if (render.exitCode !== 0) {
  return failRun("生产包渲染失败", render.stdout.slice(0, 500));
}
const finalPack = lastJson(render.stdout) as PackInfo;
let charCount = 0;
let sceneCount = 0;
let propCount = 0;
try {
  charCount = (JSON.parse(await files.read(assetsDir + "/characters.json")) as unknown[]).length;
  sceneCount = (JSON.parse(await files.read(assetsDir + "/scenes.json")) as unknown[]).length;
  propCount = (JSON.parse(await files.read(assetsDir + "/props.json")) as unknown[]).length;
} catch {
  // 计数仅用于摘要, 失败不影响交付
}
log("生产包就绪: " + finalPack.dir + " (" + finalPack.nodes + " 个节点)");
await artifact.file("script", rewrittenPath, { title: "《" + title + "》第 " + ep + " 集剧本终稿" });
await artifact.file("checklist", finalPack.checklist, { title: "生产执行清单(照此在即刻AI/updream 操作)" });
await artifact.markdown(
  "pack",
  [
    "# 《" + title + "》第 " + ep + " 集生产包就绪",
    "",
    "- 来源: " + meta.type + " (" + meta.chars + " 字) → 剧本审核 " + verdict.score + " 分",
    "- 资产: 角色 " + charCount + " / 场景 " + sceneCount + " / 道具 " + propCount,
    "- 参考图: " + (imagesGenerated ? "已本地生成于 02_assets/images/, 上传即用" : "未生成, 按清单在即刻AI人工出图"),
    "- 分镜: " + finalPack.nodes + " 个镜头 x " + shotSeconds + " 秒, 风格「" + style + "」",
    "",
    "## 下一步",
    "1. " + (imagesGenerated ? "把 02_assets/images/ 的全部图片上传 updream 通用角色库(先清空旧素材)" : "照 " + finalPack.checklist + " 在即刻AI 生成角色/场景图(webp 按名字保存)"),
    "2. 在 updream 按 node_01.md ~ node_" + String(finalPack.nodes).padStart(2, "0") + ".md 逐镜生成, 批量下载",
    "3. 片段按 01.mp4… 放入 " + PROJ + "/05_footage/ep" + ep + "/, 再对我说「质检剪辑」(mode=qa)",
  ].join("\n"),
  { title: "《" + title + "》第 " + ep + " 集生产包", description: "剧本已定稿, 分镜已过双重校验, 照清单去平台生成即可", primary: true },
);
const verifiedLines = [
  "分镜机检(render_pack): 引用完整性/提示词<=1000字/时长范围, 退出码 0",
  "剧本经审核官 " + (verdict.pass ? "通过" : "两轮审核") + (verdict.pass ? " + 独立终审" : ""),
  "资产经审核官核查(角色/场景/道具与剧本一致)",
  "分镜经连戏审核员人工级审核",
];
if (imagesGenerated) {
  verifiedLines.push("参考图经图片API生成并逐张视觉抽检");
}
return {
  conclusion: "《" + title + "》第 " + ep + " 集生产包已生成: " + finalPack.dir + " (" + finalPack.nodes + " 个镜头节点)。剧本审核 " + verdict.score + " 分, 分镜通过机检+连戏审核; 参考图" + (imagesGenerated ? "已生成并抽检" : "未配置API key, 需人工出图") + "。照 checklist.md 完成平台生成后, 跑 mode=qa 自动质检剪辑。",
  findings: verdict.issues
    .filter((i) => i.severity !== "low")
    .map((i) => ({ where: i.where, what: i.problem + " → " + i.suggestion, evidence: "剧本审核报告 " + PROJ + "/01_script/ep" + ep + ".review.md", status: "unconfirmed" as const, severity: i.severity })),
  verified: verifiedLines,
  notCovered: [
    "视频生成与成片质检未执行(需平台生成后跑 mode=qa)",
    imagesGenerated ? "平台(updream)实际生成效果未验证" : "图片API未接入(config.json 无 key), 参考图走人工通道",
  ],
};
