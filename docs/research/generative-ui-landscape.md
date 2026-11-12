# 生成式 UI 方向调研：成型产品、技术形态与可参考案例

**日期：** 2026-11-12
**用途：** 老师建议「AI 交互的设计，可以尝试探索生成式 UI」。为判断「生成式 UI」是否、以及以何种形态能落地到 wtt_refactored（FastAPI + SQLite + Jinja2 + 原生 JS，**刻意不做前端构建链**；对话为主入口 + 右侧行程卡片）提供带来源的依据。
**证据分级（沿用 `waiting-and-process-visibility.md`）：**
- **[A] 实验数据** —— 有对照组/样本量/量化测量的论文或评测
- **[B] 大厂一手声明 / 官方文档** —— 一手来源，但是原则或产品自述，非独立测量
- **[C] 产品实测拆解** —— 第三方上手实测、开源实现、技术逆向
- **[D] 设计观点** —— 无数据，仅供参考
- **[厂商]** 供应商自报数字，方法公开但未经独立复现

> **先读结论：** 老师的建议在方向上有强证据支持（Google 的偏好实验），但**该证据的适用条件和我们产品的形态正好错开**。Google 拿到 82.8% 偏好的实现是「LLM 现写整页 HTML，1–2 分钟，评测时把生成速度拿掉、给评审看预生成结果」；我们是多轮对话式决策，等待发生在每一轮。真正可落地的是另外两条路：**结构化 JSON 由前端渲染**、**预定义组件库 + LLM 选组件填参数**。后者恰好就是 GPT-6 Intelligent UI 的真实做法，也恰好能接进仓库已有的 SSE 事件流。

---

## 一、概念边界：五个词，工业界没有共识定义

**结论：`Generative UI` 没有统一的工业界定义**，只有 NN/g 提出的一个被广泛转述的工作定义，加上 Google 论文里的一个具体实现定义。这四个词常被混用，但分属不同层次。

| 词 | 出处与含义 | 关键点 |
|---|---|---|
| **Adaptive UI (AUI)** | HCI 老概念，Jameson 2003 / Gajos et al. 2008。系统根据行为/能力对**既有屏幕**重排、个性化、智能默认值 | 布局集合有限且预定义；十年前就有 [A] |
| **Intelligent UI (IUI)** | HCI 学术概念（Horvitz 1999、Jameson 2003）：系统**推断意图并主动发起**界面变化，mixed-initiative | 2025 ACM DIS 论文把它列为 GUI → CUI → AUI → IUI → GenUI 演进链上的一环 [A] |
| **Generative UI (GenUI)** | NN/g（Kate Moran & Sarah Gibbons, 2024-03-22）：「由 AI 实时动态生成、按用户当下需求与语境定制的界面」；2026-03-27 补充判据：**由 AI 决定要生成界面，而不是用户要求生成** | 这是目前被引用最多的工作定义；NN/g 明确区分 genUI / AI-assisted design / vibe coding [D] |
| **Generative Interfaces** | Google 研究博客把 generative UI「also referred to as generative interfaces」——**同义词**，不是另一个概念 [B] |
| **Server-driven UI / Adaptive Cards** | 服务端返回屏幕描述，客户端用已发布的组件库渲染。Microsoft Adaptive Cards 起于 2016、v1.0 于 2018，**纯声明式 JSON、无 code-behind、host 拥有样式** | 生成式 UI 的「传输机制」祖先；「内容归作者，外观归宿主」这条原则 2016 年就定下来了 [B] |

### ⚠️ GPT-6 的 "Intelligent UI" 到底是什么（重点澄清）

**它和 Google 的生成式 UI 不是一类东西，而且名字和 HCI 学术术语撞车。**

OpenAI 2026-10-07 官方公告 [B]：

> "We built a **library of native, streamable components**, along with a **compiler** that processes the interface as the model generates it. The library gives each response a familiar design foundation while leaving the model room to decide how the pieces fit together. The compiler allows the interface to appear progressively as the model generates it."

拆开看：

- **生成物**：不是 HTML，不是 React 代码，是**对一组预先做好的原生组件的调用/组合**。模型被训练成「会用这个组件库、会判断何时该交互、何时纯文本就够」。
- **约束方式**：组件库本身即约束（模型不能凭空造组件）+ 训练时评估「clarity / usefulness / completeness」。OpenAI 承认「still work ahead to improve the model's design judgment」。
- **延迟设计**：streamable 组件 + 增量编译 = **边生成边出现**，不等整段生成完。这是它和 Google 实现最本质的差别。
- **产品边界**（官方帮助中心 [B]）：只在 ChatGPT **Chat** tab；Work tab、Voice、Pro reasoning（GPT-6 Astra）都**不支持**；部分组件（如 checklist）刷新后状态可留，**跨 thread 不留**；无完全关闭开关，只有 `Personalization → Layout and Visuals → Simple` 这个「调光器」（官方明说 some may still appear）。
- **没有公开开发者 API** 能把这个组件库用在自己的产品里（第三方设计评论也这么提醒）[C]。
- 公告里唯一的量化数字：「需联网搜索的问题，GPT-6 Instant 比 GPT-5.6 Instant 平均**早 44% 开始回答**」——这是「边想边答」的收益，**不是组件渲染延迟**，别误读 [B]。

> 归纳：OpenAI 借用了 IUI 这个学术名词，实际交付的是**「预定义组件库 + LLM 编排 + 流式编译」**（本文 §四 的第 3 条路）。Google 的 Generative UI 是**「LLM 现写整页代码」**（第 1 条路）。两者同名不同物，混为一谈会导致技术选型整个走偏。

### 术语上还有两处必须切开的混淆 [D]

1. **设计期生成 ≠ 运行期生成**。Vercel v0 / Lovable / Bolt 生成代码进仓库、人工 review 后发布，所有用户看到同一份产物；这是 AI 辅助开发，**不是** NN/g 定义的 genUI。判据：「输出是 PR 就是设计期；输出是某个人此刻看到的屏幕才是生成式 UI」。
2. **NN/g 的判据是「谁决定」**：用户说「帮我做个伦敦行程规划 App」= vibe coding（AI 负责执行保真度）；用户说「帮我规划行程」而系统自己决定弹一个交互工具 = genUI（AI 负责**设计判断**，失败模式也变成「不该生成却生成了」）[D]。

---

## 二、成型产品逐个拆

| 产品 | 生成的是什么 | 怎么约束 | 延迟 | 公开用户反馈 |
|---|---|---|---|---|
| **Gemini dynamic view** / **Google AI Mode 生成式界面** | **整页 HTML/CSS/JS（Tailwind），原样在浏览器渲染** + 生成图片等资产 [A][B] | ① 长 system prompt（目标/规划/示例/技术规格/避错提示）② 工具（图像生成、搜索）③ **9 个 post-processor** 修常见错 | 论文：「一分钟到两分钟」，流式渲染**减半**；博客「a minute or more」[A][B] | 有，见 §五、§六 |
| **Gemini visual layout** | 杂志式版面 + 照片 + 模块 + **滑块/筛选器**，非整页自由编码 [B] | 预置版面模板，比 dynamic view 紧 | 未见公开数字 | 「plan a 3-day trip to Rome」是官方示例 [B] |
| **GPT-6 Intelligent UI** | **原生可流式组件库的组合**（按钮/表单/图表/交互图），非 HTML [B] | 组件库 + 编译器 + 训练期设计评估 | 设计上以「渐进出现」压感知等待；**组件级实测延迟未公开** | 有，见 §六 |
| **Claude Artifacts** | 单文件 HTML / React JSX / SVG / Mermaid / Markdown，装在 `<antArtifact>` XML 标签里，MIME 类型区分 [C] | 独立 iframe（`claudeusercontent.com`），`sandbox="allow-scripts"` 且**不给 `allow-same-origin`**；仅允许 cdnjs 外链；禁 localStorage/sessionStorage；React 仅开放 recharts / lucide / shadcn 等白名单库 | 小应用约 10s 量级 [C] | 版本树可回退；可发布/分享/iframe 嵌入；实测反馈多为「渲染好用但生成偶发失败」 |
| **ChatGPT Canvas** | 文档/代码协作编辑器；2025-01 起能渲染 HTML & React（有隐含 JSX 编译步骤）[C] | 与 Artifacts 类似的沙箱 | 未公开 | Simon Willison 实测遇到 `Build failed ... Expected "}"` 且自带的 "fix this bug" 也修不好，**几乎无文档** [C]。有二手来源称 Canvas 于 2026-05-28 被移除，**未与 OpenAI 一手来源核实** |
| **Microsoft Copilot Pages** | **不是生成式 UI**：Loop 驱动的可持久化文档画布，块类型（表格/清单/日期/标注/Mermaid）由用户或 `/` 菜单插入 [B] | 固定组件菜单 | 微软自承大页面响应变慢 [B] | 微软支持页明列限制：「deep customization (e.g. layout changes, advanced formatting) may be limited」[B] |
| **Vercel v0** | React + Tailwind + shadcn/ui **源码**，交付到仓库 [B][C] | 约定即约束（Tailwind theme / shadcn 规范） | 设计期，无运行期等待 | 常见工程反馈：生成的组件偏单体、状态放错层、数据获取是 mock，接真实 API 要重做；「成熟代码库里集成成本可能超过收益」[C] |
| **Vercel AI SDK (RSC / UI)** | 工具调用 → **React 组件**；`streamUI` / `createStreamableUI` 从服务端流式推组件 [B] | Zod `inputSchema` 约束工具入参；组件由开发者写好 | 依赖模型 tool-call 延迟 | **官方已标记 experimental，明确「不建议用于稳定生产」**：无法 abort 流、`.done()` 时组件重挂载闪烁、多 suspense 边界崩溃、`createStreamableUI` 造成二次方数据传输 [B]。这条对我们「不引入 React/构建链」是直接佐证 |
| **Thesys C1 / OpenUI** | OpenAI 兼容 API 返回 **UI spec**：早期是 `{"component":..., "props":...}` 的 JSON 组件树；自 API 版本 `v-20260331` 起**破坏性**改为 **OpenUI Lang**（逐行 DSL，如 `root = Stack([header, chart])`），React SDK（Crayon）渲染 [B][C] | 组件目录 + 由目录自动生成 system prompt；解析器做流式 autocloser | 厂商实测见下 | Thesys 自述「一年生产流量、10,000+ 开发者」，JSON 在 demo 里行、复杂后 token 高 / 延迟随 token 线性涨 / malformed output 逼重试，所以换 DSL [厂商] |
| **OpenAI Apps SDK / MCP Apps** | **预写好的 HTML5 文档**，挂在 `ui://` URI（`text/html;profile=mcp-app`），工具通过 `_meta.ui.resourceUri` 关联，宿主丢进沙箱 iframe；数据走 `structuredContent` + `outputSchema`，`postMessage` JSON-RPC 通信 [B] | 开发者拥有 widget 代码；模型只**选工具**、不写 UI。官方推荐「data tools / render tools 解耦」避免过度重渲染 | 无生成延迟（widget 是静态资产） | GitHub issue #179：`structuredContent` 未传到 `window.openai.toolOutput`，始终为 null [C]——实际集成有坑 |
| **Google A2UI** | **声明式 JSON**：扁平的组件列表 + ID 引用 + 数据模型，客户端用自己的目录渲染；`application/a2ui+json` [B] | 「safe like data, expressive like code」：agent **只能请求客户端已批准的 catalog 里的组件**，无 HTML/CSS/JS 过线。扁平面非树是**刻意迁就 LLM 增量生成** | 为流式增量更新设计 | Apache 2.0，v0.9.1 / v1.0 RC；渲染器 Lit / Angular / Flutter / React；已用于 Opal、Gemini Enterprise、Flutter GenUI SDK [B] |
| **Microsoft Adaptive Cards（前身）** | 纯声明式 JSON 卡片，无 code-behind，宿主控制外观 [B] | Schema + 渲染 SDK；提交类动作由宿主裁决 | 无生成延迟 | 2016 起、2018 v1.0，至今仍是「安全渲染外部 UI」的教科书参照 |

### 一句话归位

上表里 **只有三家是「LLM 在运行时生成界面」**：Google dynamic view / AI Mode（生成代码）、GPT-6 Intelligent UI（生成组件组合）、Thesys C1 / OpenUI（生成 spec）。Artifacts、v0、Apps SDK、A2UI 各自是「沙箱执行」「设计期生成」「预写 widget」「声明式协议」——**都常被列进"生成式 UI 产品清单"，但机制完全不同**。

---

## 三、Google 那篇论文到底证明了什么（[A]，逐条）

来源：`arxiv.org/abs/2604.09577`《Generative UI: LLMs are Effective UI Generators》，Google Research；配套博客 `research.google/blog/generative-ui-...`；交互样例 `generativeui.github.io`。

**实现**：Gemini 3 Pro，输出「单个完整生成的网页 + 配套资产」，**原样在用户浏览器渲染**（论文 §2）。三件套：工具服务（图像生成/搜索，结果可给模型也可直送浏览器）、长 system prompt、**post-processors**。

**评测设计**：从 LMArena 随机取 100 条 prompt（排除 8 条），另建 information-seeking 集；两两偏好对比，每结果 2 名评审，三点量表（左偏好/中立/右偏好）。**关键：给评审看的是 pre-cached 结果，生成时间不计入**。

| 格式 | ELO（LMArena） |
|---|---|
| 人类专家手写网站 | 1800.3 |
| **Generative UI** | **1736.2** |
| Markdown | 1437.7 |
| 搜索结果第一名网页 | 1352.2 |
| 纯文本 | 1173.7 |

- vs Markdown：**82.8% 偏好**；information-seeking 集 **90.5%**
- vs 人类专家：Generative UI 赢 35.3%，专家赢 50.0% → 摘要表述「约 50% 案例至少可与人工作品相比」
- information-seeking 集 ELO：专家 1821.5 / GenUI 1727.3 / 搜索结果 1424.3 / Markdown 1385.5 / 文本 1141.4
- **Prompt ablation**：Full 1553.23 / Minimal 1496.00 / No Philosophy 1450.77 → 精心写的 system prompt 确实有贡献，但模型够强时 minimal 也「reasonable」
- **模型 ablation（最有价值的失败数据）**：Gemini 3 / 2.5 Pro / 2.5 Flash 输出错误率 **0%**；**Gemini 2.0 Flash 29%、2.0 Flash-Lite 60%**（LMArena 集）。作者据此称 GenUI 是最新模型的**涌现能力**

**必须标注的边界**（否则会误用这个结论）：
1. **测的是偏好，不是学习效果、不是任务完成率、不是理解度**。有第三方研究笔记直指这点 [C]。
2. **把速度拿掉了**，而作者自己说生成要一分钟到两分钟——「a minute of waiting changes the experience」。
3. 每页都是全新代码，**除了 post-processing 没有正确性校验**；模型读不回用户在页面上做了什么。
4. 论文 §5 明确把「LLM 调用预定义 widget 填充」称为 **"Templated UI"** 并说自己的工作是「paradigm shift away from ... constrained templates」。也就是说：**Google 把我们下面推荐的路明确划为「旧范式」**。这个判断在「任意 prompt 生成任意体验」的目标下成立；在「多轮行程决策」的目标下不成立。

**PAGEN**：论文承诺公开专家手写网站数据集；本次检索**未找到已发布的数据集链接**（第三方研究笔记同样标注「didn't find it」）。

---

## 四、技术形态分类：三条路，以及哪条能进无构建链项目

| | ① LLM 直吐 HTML/CSS/JS | ② LLM 吐结构化 JSON，前端渲染 | ③ 预定义组件库 + LLM 选组件填参数 |
|---|---|---|---|
| 代表 | Google dynamic view / AI Mode、Claude Artifacts（人触发） | A2UI、OpenUI / C1、Adaptive Cards、Vercel AI SDK 的 tool-result 路线 | GPT-6 Intelligent UI、Vercel AI SDK `streamUI`、CopilotKit |
| 表达力 | 最高（游戏/仿真/任意可视化） | 中（受 catalog 上限约束） | 低—中 |
| **可靠性** | 最差。需 9 个 post-processor；旧模型 29–60% 输出错误；Google 承认偶发 JS/CSS/HTML 错误 | 好。Schema 可校验（`additionalProperties: false`）、未知组件直接拒 | 最好。组件是你自己写、自己测过的 |
| **延迟** | **60–120s**（流式减半仍 30–60s） | 随 token 线性：厂商 benchmark 下一个 dashboard 的 JSON 约 37s @60 tok/s，DSL 约 20s | 最快。只生成少量参数，可秒级出首帧 |
| **安全性** | 需 iframe + 独立源 + CSP + `postMessage` 白名单；即便如此仍有幻觉资产、外链、注入面 | 不执行代码；**但组件可触发的动作仍需服务端鉴权** | 同 ②，且动作集合可枚举 |
| **无障碍** | 最差。界面每次不同，无法审计/回归；设计期工具已有 72% 违规率数据 | 好。语义化组件一次做对，全局受益 | 好，同 ② |
| **可测试性** | 几乎无法写确定性 E2E（同 prompt 不同结果） | 可测：断言 JSON / 断言组件树 | 可测：有限状态机 |
| **与既有状态联动** | 差。生成页是「一次性答案」，只能通过 postMessage 桥接宿主状态 | 好。props 直接来自 SQLite 的行程对象 | 最好。直接读写现有 session / itinerary |
| **需要构建链吗** | **不需要**（就是裸 HTML，可走 CDN Tailwind） | **不需要**（vanilla JS 一个 dispatcher 即可） | **不需要** |

### ⚠️ 一个反直觉但必须说清的点

「不做构建链」这个约束**并不能**排除第 ① 条路——iframe 里塞一段 HTML 恰恰是最不需要构建链的做法。真正把它排除掉的是另外四件事：

1. **延迟落在每一轮对话上**。Google 的偏好实验是单轮、预生成；我们是多轮「先搞清楚为什么去，再回答去哪」，一轮等 60–90 秒会直接毁掉对话节奏。仓库已有的 `docs/research/waiting-and-process-visibility.md` 对等待期有完整证据梳理。
2. **状态割裂**。右侧行程卡片是本产品的核心资产，生成页读不回用户点了什么（Google 论文自承「no agent loop：页面是答案，不是 agent 能继续操作/读回的屏幕」）。
3. **不可测试 / 不可回归**。同 prompt 每次不同（a11y 研究里明确记录「regenerating with the same prompt produced notably different designs」）。
4. **无障碍与幻觉界面**。见 §六。

### 对本项目的可行形态（[D]，我的建议，未验证）

**主选 ③，以 ② 作为线格式；把 ① 留作可选的「富视图」，且永不放在关键路径上。**

理由还包括一个现成的架构契合点：仓库 `docs/sse-streaming-design.md` 已经实测过并定下方案——**业务层 yield dict 事件，SSE 只在 ASGI 边界拼一次**；且实测发现「工具轮 `content` 为空，正文流式对工具轮天然无内容，过程面板才是主要实时性来源」。生成式 UI 的第 ③ 条路正好就是**工具轮/事件驱动的组件派发**，可以直接长在既有事件流上，不需要新链路。

建议形状：

```
LLM (tool call / structured output)
  → FastAPI 侧 Pydantic 校验 + 组件白名单
  → SSE 事件：{"type":"ui", "op":"upsert", "component":"ItineraryCard", "id":"...", "props":{...}}
  → 原生 JS ~100 行 dispatcher：switch(component) → render 到你自己的 DOM
  → 后续事件 {"type":"ui","op":"patch","id":"...","props":{...}} 增量补数据
```

要点（这些是各路公开实现里反复被验证过的做法）：

- **组件白名单先定，格式是推论**：大约 8–12 个语义组件即可覆盖本产品（画像卡、动机选项、候选地点卡、日程时间线、地图路线、成本拆解、对比表、偏好 chips、确认条、空态/错误态）。别让模型发明组件。
- **把视觉属性从线格式里删干净** [D]：不给 `color` / `font` / `padding`，只给语义枚举（`tone: "warning"`）。设计 token 留在你自己的 CSS 里。这正是 Adaptive Cards 2016 年定下的「card authors own content, host apps own look and feel」。
- **Schema 关闭** [D]：每个对象 `additionalProperties: false`，模型编出来的 key 直接校验失败而不是悄悄到达前端。Google 用 post-processor 修错误，我们用 schema 校验替代——这是「post-processors 是个信号」的读法。
- **先出骨架再补 props**：这是 OpenAI "streamable components + compiler" 的核心思路，也是把「time-to-first-useful-frame」从分钟压到秒的关键。评测时**要量这个数**，Google 恰好没量。
- **动作与外观分离**：生成的按钮可以请求「换一个候选」，但**鉴权、数据写入、行程修改全部照旧走服务端**，绝不因为按钮是模型生成的就绕过权限检查（Thesys 文档、A2UI 文档都把这条写成硬规则）。
- **保留降级**：模型不确定 / schema 校验失败 / 超时 → 回落到纯文本 + 既有行程卡片。NN/g 的 genUI 判据提醒我们「不该生成却生成了」本身就是一种失败，所以**允许系统选择不生成**。
- **如果要试 ①**：只在用户显式点「生成完整页面/分享」时触发，沙箱 iframe + 独立源 + 无 `allow-same-origin` + CSP + `postMessage` 白名单，且不承载行程状态。这样能拿到 Google 那种「漂亮的一次性交付物」的好处，而不污染对话主链路。

---

## 五、旅游 / 行程规划域：谁真的做过

**先说缺口：没有找到「生成式 UI 用于行程规划」的对照实验、任务完成率研究或独立用户调研。** 下面是产品案例 + 实测拆解，证据级别 [B]/[C]，不是 [A]。

### 5.1 Google 自己把旅行当头号示例

- 研究博客原文 [B]：「explaining the microbiome to a 5 year old requires different content ... just as creating a gallery of social media posts for a business requires **a completely different interface to generating a plan for an upcoming trip**」——老师举的例子来自这里，是**一手来源**。
- Gemini 3 发布博客 [B]：「Ask Gemini to **'plan a 3-day trip to Rome next summer'**, and you'll get a **visual itinerary you can actually explore**」。注意：这个罗马例子归 **visual layout**（杂志式 + 可交互模块），不是 dynamic view 的整页编码。
- 2026 I/O 的 Search 公告 [B]：用 Gemini 3.5 Flash + Antigravity 在 Search 里实时组装「interactive visuals, tables, graphs or simulations」，并规划**可反复回来的 custom dashboards / trackers / mini apps**（明确举了婚礼筹划、搬家、健身追踪）。「mini apps 是否已发货」本次**未确认**。
- AI Mode 的 **Canvas 作为持久行程工作区**（汇总实时航班/酒店/地图/评价、可编辑）+ agentic booking：来自 Google I/O 2026 博客与二手汇总 [B][C]，**未找到独立评测**。

### 5.2 最有价值的真实评测：Android Authority 的 Gran Canaria 七日行程 [C]

2025-11-26，Mitja Rutnik 用真实 prompt 测 dynamic view（「我要去 Gran Canaria 待一周，喜欢海滩/户外/公路旅行/美食/古迹/晚上泡吧，帮我做 itinerary」）。生成结果：**多 tab 小网站**——整周行程 tab（含景点与驾车时长）、地图 tab、餐厅/酒吧/户外活动 tab。

作者的原话结论，对我们极有参考价值：

- 「看起来很棒，比纯文本答案不那么让人不知所措」
- **但**：点某个地点按钮**不会缩放/高亮**，只显示全岛多 pin 的通用地图，分不清是哪个点；**没有画出公路旅行的实际路线**；没给租车、没给住宿推荐；目的地信息只有人口/货币/平均气温，很单薄；餐厅只列 3 家且**看不出在哪个城市、地图上也没有**。
- 健身计划那次：**没有在第一屏就问饮食限制/可用器械**（作者是素食者，被推了肉菜），要靠额外四五轮 prompt 补救。作者的判词：「更好的首次生成 = 更少的追加 prompt，我不想为了拿到信息再写五个 prompt」。
- 总体判词：「对 planning 和 learning 有价值，但我自己暂时还是用文本」。
- **延迟**：简单问题用 dynamic view「要等**最多 90 秒，有时更久**」，而且塞一堆不关心的额外信息；结论是「不要每个 prompt 都用」。
- 同页投票 **2,215 票，87% 从未用过 Dynamic View** —— 这是本次调研里最硬的一条产品侧量化反馈（虽是自助样本，非随机抽样）。另有第三方汇总给「30–90 秒」区间 [C]。

> 把这条和 Google 的 82.8% 并排看很有意思：**偏好实验里赢的是「一次性、预生成、不看等待」的界面；真实产品里输的是「多轮、要等、要和状态联动」的体验。** 我们的产品属于后者。

### 5.3 其他旅游域案例

- **Google 论文作者本人的用例** [C]：Danny Lumen（论文作者之一）把夫妻俩用表格做的既有行程丢给 dynamic view，生成了一个网站，「以后旅行都这么干」——真实但属开发者自述，非独立评测。
- **A2UI 官方 quickstart 就是个行程规划器** [B]：`samples/travel-a2ui`，一个 Python agent + React（web）/ Flutter（mobile）双客户端。catalog 里除基础组件外有 `FlightOption` / `DateRangePicker` / `PriceSummary`，还有客户端函数 `calcNights`、`formatCurrency`。**Web 客户端专门做了 `Catalog` tab（列出模型被允许用的全部组件）和 `Wire` tab（把模型写的 JSON 摆在消息旁边）**，并演示「卡片标题先出现，再一块块补」的流式效果。这是本项目最可直接照抄的参考实现。官方标明「sample for learning, not meant for production use」。
- **Atlas / trip-architect-a2ui** [C]：和我们的「对话 → 行程卡片」闭环几乎同构。用户描述目的地 → agent 每轮**只提一个地点**、渲染成 `StopCard`（名称/理由/建议时长/Approve / Skip）→ 点 Approve 落到真实地理编码的地图 pin 并画路线 → 再提下一个；行程完成出 completion card。技术栈 A2UI + AG-UI + FastAPI + LangGraph + **开源权重模型（Nebius）**。关键设计：「agent 决定展示什么，我的设计系统决定长什么样，agent 从不碰样式/CSS，每个推荐都要人工确认」。**无用户研究，是 demo。**
- **Flutter GenUI SDK 的 travel 示例** [B][C]：alpha SDK，catalog 驱动，官方举例「用户问 plan a trip → 生成含滑块、日期选择器、文本框的完整表单」；社区实现做了预算滑块 + 兴趣 picker + 逐日行程 + 重生成按钮。组件交互（滑块变化）可作为 `UiInteractionPart` 回传给模型。
- **CopilotKit Trip Planner demo** [C]：`useCopilotReadable` 把行程状态暴露给 AI、`useCopilotAction` 注册可调用动作。这更接近「**可交互组件**（AI 改已有界面）」而非「生成新界面」，但对本项目的「右侧行程卡片可被对话修改」这一半需求是直接参照。
- 其余多为教程/短视频（"Gemini Can Plan Your Entire Vacation"、Visual Layout 旅行行程教程），宣传性质，无评测数据，**不作为证据**。

---

## 六、失败模式：哪些有量化数据，哪些没有

| 失败模式 | 量化证据 | 级别 / 边界 |
|---|---|---|
| **慢** | Google 论文：「a minute or two」，流式减半；博客「a minute or more」。Android Authority 实测「up to 90 seconds, sometimes more」；第三方汇总 30–90s | [A] + [C]。**评测时把速度移除，是这份证据最大的洞** |
| **输出错误率随模型断崖** | Gemini 3 / 2.5 Pro / 2.5 Flash **0%**；2.0 Flash **29%**；2.0 Flash-Lite **60%**（LMArena 集，论文 Table 3） | [A]。本次能找到的**最硬的可靠性数字**。论文未进一步定义 "output errors" 的判定细则 |
| **幻觉资产 / 幻觉界面** | Google 的 post-processor #9 明写「Fix common issues with **hallucinated assets (e.g. icons)**」；另有修 JS/CSS/属性转义/循环 Tailwind 依赖/API 调用等共 9 项 [A]。KTH AdaptFit 论文（6 人、42 次迭代）：**24/42 成功生成的 UI 仍有可用性问题**（图标 URL 无效、不存在的字体、占位 URL、布局被新元素挤坏、承诺的动画没实现），仅 1/42 完全部署失败 | [A]。注意 AdaptFit 是 Android 个性化 UI，非网页；但「模型承诺了却没实现」这个失效模式和 GPT-6 实测一致 |
| **内容错误藏进漂亮界面** | Google 博客承认 "occasional inaccuracies" [B]。GPT-6 Intelligent UI 的 11 例上手：6 例成功、2 例仅展示、**3 例出问题**——月销售分析里图表数字对而说明文字算错（应为 -25 万写成 -35 万）；旅行 checklist 刷新后状态归零；日光自驾地图里「详情面板」与「行程选择」不联动、且酒店分级来源无法核实 [C] | [C]，样本 11、单次探索、作者自承未测可复现性 |
| **无障碍** | CHI/DOI `10.1145/3708557.3716347`：**200 个 AI 生成界面（5 个工具）中 144 个有 WCAG 违规 = 72%**，平均严重度 1.2/4（较轻）；在 prompt 里写满 5 条 WCAG 准则**几乎没用**（严重度差 Δ=0.2）；需中位数 **3 轮**对话式修正才达标；同 prompt 重新生成会得到明显不同的设计（不可复现）[A]。另一综述：88 个 GPT-3.5 生成的网站中 **84%** 至少有一处违规；模型能修自身约 70% 的违规 [A] | [A]，**但范围是设计期工具（Uizard/Banani/Visily 类）与代码生成，不是运行期 genUI 产品**。**没有找到对 Gemini dynamic view / GPT-6 Intelligent UI 的公开无障碍审计**——这是明确的数据缺口，不能把 72% 直接套到运行期产品上 |
| **无法测试 / 无法 A/B** | NN/g 指出：AI 输出的固有随机性大幅抬高统计噪声，小样本 A/B 里界面改动效应会被 AI 表现波动淹没，应以质性研究为主 [D]；a11y 研究里「同 prompt 重生成明显不同」是直接观察 [A] | **没有找到「生成式 UI 测试成本」的量化数据** |
| **不可预测 / 用户想关掉** | OpenAI 社区有「加个完全关闭 Intelligent UI 的开关」的功能请求，理由是「overwhelming and overly directive，像老师盘问学生」；官方只有 Simple「调光器」，无纯文本模式 [B][C]。NN/g：genUI 独有的失败是**「不该生成却生成了」，即使技术完美也是设计失败** [D] | 无百分比 |
| **发现率 / 采纳率** | Android Authority 投票 2,215 票：**87% 从未用过 Dynamic View** [C] | 自助样本，非随机；但量级值得警惕 |
| **框架自身不成熟** | Vercel 官方把 AI SDK RSC 标为 experimental 且「不建议用于稳定生产」，列出 4 类具体缺陷（无法 abort、`.done()` 重挂载闪烁、多 suspense 边界崩溃、`createStreamableUI` 二次方数据传输） | [B]。对「要不要为了生成式 UI 引入 React/RSC」是很强的反面证据 |

**明确没找到数据的项**（不编）：
- GPT-6 Intelligent UI **组件级的实测延迟**（44% 那个数字是「边想边答 + 联网搜索」，不是 UI 渲染）
- 生成式 UI 在**旅行/行程规划**场景的任务完成率、理解度、留存、满意度对照实验
- 任何运行期生成式 UI 产品的公开无障碍审计
- 生成式 UI 的维护成本 / 回归测试成本的量化研究
- Thesys 官网「**Preferred by 83% of users** vs text-in/text-out」的方法学：本次**未找到**样本量、题目、对照组描述。该数字与 Google 论文的 82.8% 高度接近，建议当作营销口径而非证据
- Google 承诺公开的 **PAGEN** 数据集链接

### 供应商 benchmark（[厂商]，方法公开但未经独立复现）

Thesys / OpenUI 的 token 与延迟对比（`openui.com/docs/openui-lang/benchmarks`，GPT-5.2、temperature 0、tiktoken、60 tok/s 线性外推，7 个场景）：

| 场景 | YAML | Vercel JSON-Render | C1 JSON | OpenUI Lang |
|---|---|---|---|---|
| 7 场景总 token | 9,122 | 10,180 | 9,948 | **4,800**（比 C1 JSON -51.7%） |
| contact-form 估算延迟 | 12.70s | 14.88s | 14.15s | **4.90s** |
| dashboard 估算延迟 | 35.47s | 37.45s | 37.68s | **20.43s** |

官网另称「跨 46 个界面平均 1,362 output tokens/屏，比 json-render 少 58%、比 A2UI 少 52%」「3x faster、67% fewer tokens」「Preferred by 83% of users」。**全部是 Thesys 自报**；方法、场景、仓库都公开可复跑，但本次未见第三方复现。Thesys 工程博客还给了流式解析器从 O(N²) 改 O(N) 后总解析开销 2.6–3.3x 的实测——这是**工程实现**数据，不是「生成式 UI 好不好」的证据，别混用。

> 这张表对我们真正有用的信息不是「DSL 更快」，而是：**即使是最紧凑的 JSON 方案，一个复杂 dashboard 也要 ~20–38 秒纯生成时间**（60 tok/s 理想外推，未计 TTFT 与网络）。所以「换 JSON 就快了」是错的；快的来源是**少生成东西**（只出组件名 + 少量参数），不是格式本身。这正是第 ③ 条路的优势。

---

## 七、给本项目的判断（[D]，建议，未验证）

1. **老师的建议值得采纳，但要采纳的是「界面按语境适配」这个产品思想，不是 Google 的实现路径。** 现有「右侧行程卡片」其实已经是半个生成式界面；可做的增量是**让对话能决定此刻该出现哪种卡片/控件**（动机选项 chips → 候选对比表 → 日程时间线 → 成本滑块 → 确认条），而不是让模型写整页 HTML。
2. **线格式选结构化 JSON + 组件白名单（②+③）**，接进 `docs/sse-streaming-design.md` 已定的 dict 事件流。零构建链、零新依赖、可测、可降级、无障碍一次做对。
3. **不要为这个方向引入 React / RSC / v0 / Thesys 托管服务**：前者 Vercel 自己标了不适合生产，后者是 React-first 且把渲染与 spec 绑在供应商上（第三方评测明确列为 vendor coupling 风险）。
4. **把「允许不生成」写成显式规则**。GenUI 的特有失败是判断失误，不是渲染失败。
5. **评测别照抄 Google**。可以复用它的「两两偏好 + 预缓存结果」这个廉价方法，但必须补两项：① **把真实等待计入**（量 time-to-first-useful-frame，Google 恰好没量）② 加**任务完成/理解度**题（偏好 ≠ 有用）。仓库 `docs/research/eval-methods.md` 已有可复用的指标体系。
6. **可选实验**：用户显式点「生成可分享的完整行程页」时，用 ① 走沙箱 iframe 出一次性交付物。这是唯一能让 60–90 秒等待变得合理的位置，且不影响对话主链路。

---

## 八、来源清单

**一手 / 官方（[B]）**
- OpenAI, *GPT-6 and Intelligent UI for everyone*, 2026-10-07 — https://openai.com/index/gpt-6-for-everyone/
- OpenAI Help Center, *Intelligent UI in ChatGPT* — https://help.openai.com/en/articles/20001598-intelligent-ui-in-chatgpt
- Google Research, *Generative UI: A rich, custom, visual interactive user experience for any prompt* — https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/
- Google, *See new Gemini app updates with the Gemini 3 AI model*（罗马行程 / visual layout）— https://blog.google/products-and-platforms/products/gemini/gemini-3-gemini-app/
- Google, *A new era for AI Search*, I/O 2026 — https://blog.google/products-and-platforms/products/search/search-io-2026/
- Google Support, *Get AI-powered responses with AI Mode in Google Search*（交互视觉需显式要求）— https://support.google.com/websearch/answer/16011537
- Google Developers Blog, *Introducing A2UI* — https://developers.googleblog.com/introducing-a2ui-an-open-project-for-agent-driven-interfaces/
- A2UI 官方文档（对比表、quickstart、travel-a2ui）— https://a2ui.org/introduction/agent-ui-ecosystem/ , https://a2ui.org/quickstart/ , https://a2ui.org/quickstart/agent.md
- OpenAI Developers, *Add UI to your MCP server* / *Reference* — https://developers.openai.com/plugins/build/chatgpt-ui , https://developers.openai.com/plugins/reference
- Model Context Protocol Blog, *MCP Apps*, 2026-01-26 — https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/
- Vercel AI SDK, *Rendering UI with Language Models* / *Migrating from RSC to UI* / *AI SDK RSC overview* — https://ai-sdk.dev/docs/advanced/rendering-ui-with-language-models , https://ai-sdk.dev/docs/ai-sdk-rsc/migrating-to-ui
- Microsoft, *How Microsoft 365 Copilot Pages works* / *Get started* / *Adaptive Cards: Motivations and Principles* / *Adaptive Cards Overview* — support.microsoft.com , https://learn.microsoft.com/en-us/adaptive-cards/resources/principles
- Thesys / OpenUI 官网与 benchmarks — https://www.thesys.dev/ , https://www.openui.com/ , https://www.openui.com/docs/openui-lang/benchmarks , https://www.openui.com/blog/rust-wasm-parser

**论文 / 实验（[A]）**
- Leviathan et al., *Generative UI: LLMs are Effective UI Generators*, arXiv:2604.09577（全文 HTML + PAGEN + post-processor 附录）— https://arxiv.org/abs/2604.09577 , https://arxiv.org/html/2604.09577
- *Understanding and Improving Accessibility in AI-Generated Interfaces through Interactive Prompt Engineering Methods*, DOI 10.1145/3708557.3716347（200 界面 / 72% / 3 轮）
- *Towards a Working Definition of Designing Generative User Interfaces*, ACM DIS, DOI 10.1145/3715668.3736365（127 篇文献 + 18 访谈 + 12 案例，5 要素；GUI→CUI→AUI→IUI→GenUI 演进框架）
- *AI-Assisted Accessible Web Interface Generation and WCAG Validation: A Review*（35 研究综述；84% / 70% 修复率）— ijsrem.com
- *Enhancing Generative User Interfaces with LLMs*（KTH, AdaptFit，6 人 / 42 迭代 / 24 有可用性问题）— https://kth.diva-portal.org/smash/get/diva2:2018717/FULLTEXT01.pdf

**设计观点（[D]）**
- NN/g, *Generative UI and Outcome-Oriented Design*, 2024-03-22 — https://www.nngroup.com/articles/generative-ui/
- NN/g, *GenUI vs. Vibe Coding: Who's Designing?*, 2026-03-27 — https://www.nngroup.com/articles/genui-vs-vibe/
- Julia Díez, *The Interface That Writes Itself*（adaptive → generative → intent-based 三段谱系、本地化失效）— https://juliadiez.substack.com/p/the-interface-that-writes-itself
- generativeui.guide（design-time vs runtime / server-driven UI 区分）— https://generativeui.guide/vs , https://generativeui.guide/ecosystem

**第三方实测 / 拆解（[C]）**
- Android Authority, *Gemini's Dynamic View is great, just don't use it for every prompt*, 2025-11-26 — https://www.androidauthority.com/gemini-dynamic-view-3619662/
- 池田朋弘, *[What is Intelligent UI?] Hands-on verification of 11 new GPT-6 features* — https://note.com/popinsight_ikeda/n/necf695947536
- 日本語 hands-on（Visual Layout / Dynamic View 3 例，约 15 秒、显示溢出）— https://note.com/doerstokyo_kb/n/nac7b87432e1d
- Reid Barber, *Reverse engineering Claude Artifacts*（`<antArtifact>` 格式与 MIME 类型全文）— https://www.reidbarber.com/blog/reverse-engineering-claude-artifacts
- Simon Willison, *OpenAI Canvas gets a huge upgrade*（JSX 编译错误、文档缺失）— https://simonwillison.net/2025/jan/25/openai-canvas-gets-a-huge-upgrade/
- AI/TLDR, *What Is Thesys C1?*（调用形态、风险清单）— https://ai-tldr.dev/learn/building-ai-apps/ai-ux-patterns/thesys-c1-generative-ui/
- genui-field-notes, *OpenUI and Thesys C1*（JSON → OpenUI 破坏性变更）— https://genui-field-notes.2bab.com/03-openui-thesys-c1
- fictty research notes（对 Google 论文方法学的批评、时间线）— https://fictty.com/research/html/gemini-generative-ui/ , https://fictty.com/research/ideas/google-generative-ui/
- `github.com/dsouzavijeth/trip-architect-a2ui`（Atlas）、`github.com/rondagdag/ai-ui-demos`（5 种 AI-UI 模式 + Trip Planner）、`a2ui-project/labs/samples/travel-a2ui`
- OpenAI 社区功能请求（关闭 Intelligent UI）— https://community.openai.com/t/feature-request-add-a-toggle-to-disable-intelligent-ui-interactive-buttons/1408083

**仓库内部**
- `docs/sse-streaming-design.md`（SSE 选型、dict 事件、工具轮 content 为空的实测）
- `docs/research/waiting-and-process-visibility.md`（等待期证据分级与边界）
- `docs/research/eval-methods.md`（可复用的评估指标体系）
- `DESIGN.md` / `docs/DESIGN-conversation-itinerary-loop.md`（现有架构与对话-行程闭环）

---

## 九、诚实清单：本次没能确认的事

1. **PAGEN 数据集**是否真的公开、在哪下载——论文说会公开，未找到链接。
2. **GPT-6 Intelligent UI 组件渲染延迟**——无公开测量；44% 是另一件事。
3. **旅行场景生成式 UI 的效果数据**——无任何对照实验 / 任务完成率 / 独立用户调研。所有旅游案例都是产品演示、官方示例或单人上手。
4. **运行期生成式 UI 产品的无障碍审计**——零。72% / 84% 是设计期代码生成，外推需谨慎。
5. **Thesys「83% 用户偏好」**的方法学——未找到；与 Google 82.8% 数值巧合，按营销口径处理。
6. **ChatGPT Canvas 于 2026-05-28 被移除**——仅见二手汇总，未与 OpenAI 一手公告核实。
7. **Google Search 的 persistent mini apps / dashboards 是否已发货**——I/O 2026 说 "in the coming months"，未确认。
8. **Google 论文 "Output Errors" 的判定细则**——Table 3/4 给了百分比，正文未进一步定义什么叫一个 output error。
9. **各产品的公开用户反馈量级差异极大**：Gemini dynamic view 有 2,215 人投票 + 详细长文实测；Claude Artifacts / v0 / A2UI / C1 的反馈主要是开发者博客与技术评测，**没有可比口径的满意度数据**。本报告未把它们并列成「谁更受欢迎」。
