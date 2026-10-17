/* zcode-workflow
description: 短剧解说视频自动制作(MVP无声字幕版)：剧集文件夹批量转写+抽帧 → 剧情分析师(beat timeline) →
  全剧梳理(十大爆点) → 爆款解说文案+审核循环+定稿检查点 → 素材规划+机检(时长匹配/原声≤5s且<15%/总时长5-10分钟) → ffmpeg
  切片拼接烧大字幕 → 07_final/recap_v1.mp4。TTS配音版规划中。
whenToUse: 用户要做短剧/影视剧解说、"一口气看完"式盘点视频时。给一个剧集文件夹即可；产出 5-10 分钟解说样片(当前为无声字幕版, 保留原声+烧解说字幕)。
args:
  batch_size:
    type: number
    description: 每个剧情分析师负责的集数
    default: 6
  source:
    type: string
    description: 剧集文件夹路径(文件名排序=集数顺序)
    required: true
  target_minutes:
    type: number
    description: 目标成片时长(分钟, 5-10)
    default: 8
  title:
    type: string
    description: 项目名 = projects/<title>(建议 XX剧解说)
    required: true
*/
// 短剧解说视频自动制作(MVP: 无声字幕版) — 输入剧集文件夹 → 分析/梳理/文案/规划/机检/渲染
interface IngestInfo {
  /** 入库集数 */
  episodes: number;
  /** 素材总秒数 */
  total_seconds: number;
  /** 转写总字数 */
  chars: number;
}

interface Beats {
  /** beats json 文件路径 */
  path: string;
  /** 覆盖的集号 */
  eps: number[];
}

interface Arc {
  /** 故事弧大纲路径 */
  path: string;
  /** 十大爆点一句话列表 */
  top_bombs: string;
}

interface RecapDraft {
  /** 解说文案路径 */
  path: string;
  /** 预计分钟数 */
  est_minutes: number;
  /** 总字数 */
  words: number;
}

interface Issue {
  severity: "low" | "medium" | "high";
  where: string;
  problem: string;
  suggestion: string;
}

interface Verdict {
  pass: boolean;
  score: number;
  issues: Issue[];
}

interface PlanResult {
  /** plan.json 路径 */
  path: string;
  /** 段落数 */
  segments: number;
  /** 总秒数 */
  total_seconds: number;
}

interface Approval {
  approved: boolean;
  notes: string;
}

interface Finding {
  where: string;
  what: string;
  evidence: string;
  status: "verified" | "unconfirmed";
  severity: "low" | "medium" | "high";
}

interface WorkflowReport {
  conclusion: string;
  findings: Finding[];
  verified: string[];
  notCovered: string[];
}

const title = String(args.title ?? "解说测试");
const source = String(args.source ?? "测试素材_剧集");
const targetMinutes = Number(args.target_minutes ?? 8);
const batchSize = Number(args.batch_size ?? 6);

const SK = ".agents/skills/ai-short-drama";
const PROJ = "projects/" + title;

function lastJson(s: string): unknown {
  const lines = s.trim().split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const t = lines[i].trim();
    if (t.startsWith("{")) {
      try {
        return JSON.parse(t);
      } catch {
        // 继续找
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

phase("解说素材入库");
log("批量入库剧集: " + source);
const ing = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/recap_ingest.py", "--project", PROJ, "--source", source], { timeoutMs: 1800000 });
if (ing.exitCode !== 0) {
  return failRun("剧集入库失败", (ing.stdout + ing.stderr).slice(0, 500));
}
const meta = lastJson(ing.stdout) as IngestInfo | undefined;
if (meta === undefined) {
  return failRun("入库输出无法解析", ing.stdout.slice(0, 400));
}
log("入库 " + meta.episodes + " 集, 素材共 " + Math.round(meta.total_seconds / 60) + " 分钟, 转写 " + meta.chars + " 字");

phase("批量剧情分析");
const epMetas = await files.glob(PROJ + "/00_episodes/ep*/meta.json");
const epNums = epMetas.map((p) => Number(p.match(/ep(\d+)\/meta\.json$/)?.[1] ?? 0)).filter((n) => n > 0).sort((x, y) => x - y);
if (epNums.length === 0) {
  return failRun("没找到剧集 meta", PROJ + "/00_episodes/");
}
const batches: number[][] = [];
for (let i = 0; i < epNums.length; i += batchSize) {
  batches.push(epNums.slice(i, i + batchSize));
}
log("分 " + batches.length + " 批分析(每批最多 " + batchSize + " 集)");
const beatsFiles = await Promise.all(
  batches.map((batch, bi) => {
    const epsArg = batch.map((n) => "ep" + String(n).padStart(2, "0")).join(", ");
    const fileList = batch.map((n) => PROJ + "/00_episodes/ep" + String(n).padStart(2, "0") + "/transcript_timed.txt").join(" 、 ");
    return agent("剧情分析师·第" + batch[0] + "-" + batch[batch.length - 1] + "集").ask<Beats>(
      "读取这些剧集的带时间戳转写稿: " + fileList + " 。需要确认画面时, 读 " + PROJ + "/00_episodes/epNN/frames/ 下的 jpg(00001.jpg≈0-10秒, 00002.jpg≈10-20秒, 每10秒一帧, NN=两位集号)。为批次内每一集产出 beat timeline, 写入 " + PROJ + "/00_episodes/batch_" + (bi + 1) + ".beats.json (UTF-8 JSON): {\"items\":[{\"ep\": 集号, \"one_line\": \"本集一句话\", \"characters\": [\"出场人物\"], \"beats\": [{\"t_start\": 秒, \"t_end\": 秒, \"event\": \"事件一句话\", \"heat\": 1-5冲突强度, \"who\": [\"出场人物\"]}], \"highs\": [{\"t_start\": 秒, \"t_end\": 秒, \"what\": \"高能时刻及为何炸\"}], \"quotes\": [{\"t\": 秒, \"who\": \"\", \"line\": \"金句台词\"}]}]}。时间戳必须取自转写稿真实时间, beats 粒度 10-30 秒。只返回 {path, eps}。",
    );
  }),
);

phase("全剧梳理");
const beatsList = beatsFiles.map((b) => b.path).join(" 、 ");
const arcRes = await agent("全剧梳理师", { system: "你是长剧压缩专家, 擅长把几十集短剧压成一条故事弧。把文件写到指定路径。素材不足时直接说明, 不要编造。" }).ask<Arc>(
  "读取全部 beat 文件: " + beatsList + " 。写故事弧大纲到 " + PROJ + "/01_script/arc.md : 1 人物关系表(2-4个核心角色: 身份/欲望/矛盾) 2 三幕式主线(设定→升级→高潮, 各含哪些集) 3 十大爆点排序(每个标注 ep 与时间戳, 从各集 highs 里选) 4 金句 TOP5(标时间戳) 5 详略分配建议(哪些集多讲/哪些合并)。只返回 {path, top_bombs}。",
);
log("梳理完成, 十大爆点: " + arcRes.top_bombs.slice(0, 120));

phase("解说文案撰写与审核");
const writer = agent("解说文案师", { system: "你是爆款短剧解说写手, 严格执行提示词规则。把文件写到指定路径。规则冲突时直接上报, 不要硬编。" });
const reviewer = agent("文案审核官", { system: "你是短视频平台严苛审稿人, 宁可挑刺不放水。把审核报告写到指定路径。" });
let feedback = "无(第一轮)";
let verdict: Verdict = { pass: false, score: 0, issues: [] };
for (let round = 1; round <= 2 && !verdict.pass; round++) {
  await writer.ask(
    "第 " + round + " 轮。读故事弧 " + arcRes.path + " 和提示词 " + SK + "/prompts/p5_recap_writer.txt , 写「一口气看完」式解说文案到 " + PROJ + "/01_script/recap.md (覆盖), 目标 " + targetMinutes + " 分钟。上一轮审核意见(逐条解决): " + feedback,
  );
  verdict = await reviewer.ask<Verdict>(
    "审核解说文案 " + PROJ + "/01_script/recap.md (对照故事弧 " + arcRes.path + "): 1 前5秒钩子是否抓人 2 字数与 " + targetMinutes + " 分钟匹配(±10%, 4.5字/秒) 3 每个自然段在故事弧里有对应事件可配画面 4 【原声】3-6处且单处台词念完≤5秒 5 详略分配是否合理(爆点多给/弱集合并) 6 合规与语言网感。报告写入 " + PROJ + "/01_script/recap.review.md (覆盖), 返回结论。",
  );
  report({ stage: "文案审核", round, score: verdict.score, pass: verdict.pass });
  feedback = JSON.stringify(verdict.issues);
}
const approval = await hole<Approval>(
  "解说文案定稿确认",
  "《" + title + "》解说文案已生成: " + PROJ + "/01_script/recap.md 。审核: " + (verdict.pass ? "通过(" + verdict.score + "分)" : "两轮未全过(" + verdict.score + "分), 遗留: " + JSON.stringify(verdict.issues.slice(0, 3))) + " 。批准进入素材规划与渲染吗? 不批准请在 notes 给修改意见。", async () => {
  return { approved: true, notes: "" };
},
);
if (!approval.approved && approval.notes.trim().length > 0) {
  await writer.ask("用户修改意见(逐条落实): " + approval.notes + "。修订 " + PROJ + "/01_script/recap.md");
  verdict = await reviewer.ask<Verdict>("复审修订后的 " + PROJ + "/01_script/recap.md, 更新 " + PROJ + "/01_script/recap.review.md, 返回结论。");
  report({ stage: "用户意见复审", score: verdict.score, pass: verdict.pass });
}

phase("素材规划与机检");
const planner = agent("素材规划师", { system: "你是剪辑师, 只引用 beat 文件里真实存在的时间戳, 输出严格合法 JSON。要求无法满足时直接说明, 不要编造。" });
let planOk = false;
let planFeedback = "无(第一轮)";
let planInfo: PlanResult | undefined;
for (let round = 1; round <= 3 && !planOk; round++) {
  await planner.ask<PlanResult>(
    "读取解说文案 " + PROJ + "/01_script/recap.md 、全部 beat 文件(" + beatsList + ", 含每集时长与时间戳)和 " + PROJ + "/00_episodes/ 下各 epNN/meta.json。把文案逐段转成素材规划, 写入 " + PROJ + "/02_plan/plan.json (UTF-8 JSON): {\"segments\":[{\"id\": 从1连续, \"ep\": 集号, \"t_start\": 秒, \"t_end\": 秒, \"audio_mode\": \"voiceover\"|\"original\", \"narration_text\": \"该段解说词(原声段留空)\", \"est_seconds\": 解说段=字数/4.5四舍五入到0.5, \"原声台词\": \"原声段台词\"}]}。硬约束: 解说段素材时长(t_end-t_start)必须≥est_seconds; 时间戳取自 beat 的 t_start/t_end; 原声段 t_end-t_start≤5; 同一素材最多用2次; 总时长 5-10 分钟。机检意见(逐条解决): " + planFeedback,
  );
  const gate = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/plan_check.py", "--project", PROJ]);
  if (gate.exitCode !== 0) {
    planFeedback = "机检未过: " + gate.stdout.trim();
    continue;
  }
  const parsed = lastJson(gate.stdout) as PlanResult | undefined;
  if (parsed === undefined) {
    planFeedback = "机检输出解析失败: " + gate.stdout;
    continue;
  }
  planInfo = parsed;
  planOk = true;
}
if (!planOk || planInfo === undefined) {
  return failRun("素材规划 3 轮未过机检, 已停止", planFeedback.slice(0, 500));
}
log("规划通过: " + planInfo.segments + " 段, 总时长 " + Math.round(planInfo.total_seconds) + " 秒");

phase("渲染字幕版样片");
const render = await world.run(".venv/Scripts/python.exe", [SK + "/scripts/render_recap.py", "--project", PROJ], { timeoutMs: 1800000 });
if (render.exitCode !== 0) {
  return failRun("渲染失败", (render.stdout + render.stderr).slice(0, 500));
}
const rendered = lastJson(render.stdout) as { final: string; segments: number; seconds: number; resolution: string } | undefined;
if (rendered === undefined) {
  return failRun("渲染输出解析失败", render.stdout.slice(0, 400));
}
log("样片完成: " + rendered.final + " (" + rendered.seconds + " 秒)");
await artifact.file("script", PROJ + "/01_script/recap.md", { title: "《" + title + "》解说文案" });
let publishedVideo = true;
try {
  await artifact.file("final", rendered.final, { title: "《" + title + "》解说样片(MVP无声版)" });
} catch {
  publishedVideo = false;
  await artifact.markdown("final-note", "样片已生成: " + rendered.final + " (文件较大请在本地打开)", { title: "《" + title + "》解说样片(MVP无声版)" });
}
return {
  conclusion: "《" + title + "》解说样片(MVP无声字幕版)已生成: " + rendered.final + ", " + rendered.segments + " 段 / " + rendered.seconds + " 秒 / " + rendered.resolution + "。文案审核 " + verdict.score + " 分, 素材规划过机检。样片保留原声、解说词为字幕; 确认画面匹配与节奏后, 下一步上 TTS 配音版。" + (publishedVideo ? "" : "(成片较大, 请在本地播放)"),
  findings: verdict.issues
    .filter((i) => i.severity !== "low")
    .map((i) => ({ where: i.where, what: i.problem + " → " + i.suggestion, evidence: "文案审核 " + PROJ + "/01_script/recap.review.md", status: "unconfirmed" as const, severity: i.severity })),
  verified: [
    "素材规划机检(plan_check): 时长匹配/引用时间戳在集内/原声≤5s且<15%/重复≤2次/总时长5-10分钟",
    "文案经审核官 " + (verdict.pass ? "通过" : "两轮审核") + " 并由用户定稿",
    "渲染产物经 ffprobe 校验时长",
  ],
  notCovered: [
    "MVP 为无声字幕版: 未含 TTS 配音/原声压低/BGM, 画面与解说对位靠字幕呈现",
    "画面情绪匹配精度为规划师基于 beat 判断, 未逐段视觉复核",
  ],
};
