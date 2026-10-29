# 对话式引导的产品设计模式调研

面向：AI 旅游决策平台（对话为主入口 + 右侧行程卡片）
调研日期：2026-10-29
证据分级：**[实证]** 有量化数据/受控实验；**[案例]** 真实产品已验证；**[实践共识]** 大厂规范/资深设计师规范；**[观点]** 本文推断

---

## 0. 先说结论：当前问题不是"关键词漏词"，是架构错位

现在的链路是：LLM 抽画像 → LLM 生成回复（可调工具）→ 服务端校验工具调用。

问题出在第三段：**"该不该调工具"这个决策交给了模型自然语言意图，然后又用关键词白名单去补模型的行为。**

关键词白名单的三个结构性局限（[实践共识]，逻辑必然）：

1. **无限集合不可枚举**。「排一天的行程」「帮我凑个一天」「这天怎么过」「上午下午怎么分」「一天能逛完吗」「给我个方案吧」——中文里同一意图的表达是开放集合，词表永远差一个。每漏一个就是一次线上事故。
2. **误报同样致命**。「这个行程排得太赶了」含「排」+「行程」，属于**修改/抱怨**，不是生成。词表法只能靠更长的词表去排除，复杂度指数上升。
3. **无法表达"条件性"**。真正决定该不该调工具的是**上下文状态**（已经生成过吗？画像够不够？用户要改还是新建？），这不是关键词能编码的。同一个「排一天」在第 3 轮和第 8 轮该有不同行为。

而学术上有明确命名的问题：**under-clarification bias / ask-vs-answer 决策**，并且有独立的评测基准。

---

## 1. "该调工具"这件事，漏是常态，不是意外

### 1.1 有验证的定量证据

| 来源 | 结论 |
|---|---|
| **When2Call**（Ross et al., NAACL 2025, NVIDIA） | 现有基准几乎只测"调得对不对"，不测**"该不该调"**。作者构造基准后结论是：SOTA 工具调用模型在 when-to-call 决策上**"significant room for improvement"**。决策类别被分成三种：生成工具调用 / 追问用户 / 承认工具无法回答。三种收益显著不同，用偏好优化（DPO 风格）比传统微调提升大得多。**[实证]** |
| **ClarifyMT-Bench**（Luo et al., 2025, HKU + 中国移动九天地） | 评了 10 个模型，观察到**"consistent under-clarification bias: LLMs prefer to answer prematurely rather than engage in sufficient clarification"**，且**对话越深越差**。6120 条多轮对话、5 维歧义分类、6 种用户人格。**[实证]** |
| **QuestBench**（Li, Kim, Wang, NeurIPS 2025 D&B） | 在只需要问**一个**澄清问题的任务上，模型在 Logic-Q / Planning-Q 只有 **40–50%** 准确率（Planning-Q 上部分大模型甚至 <30%）。关键发现：**"能解完整规格的问题"≠"能识别该问什么"**——这是两种独立能力。**[实证]** |
| **ClarQ-LLM**（Gan et al., 2024） | 任务型对话中主动提问收集信息，GPT-4o 成功率 **50.8%**，LLaMA3.1-405B **60.5%**，人类 **85%**。作者明确指出：**"LLMs like GPT-4, ChatGPT, AND BARD often skip asking clarification questions"**。**[实证]** |

**结论（[实证] 支撑的判断）**：模型"该不该触发动作"的可靠性天然低于"动作内容执行得对不对"。所以**任何依赖模型自觉的判断都要有确定性兜底**，且兜底不能是关键词表。

### 1.2 业界的正确分层：模型做语言，代码做控制流

三处独立来源说的是同一件事：

- **Google Cloud CX Agent Studio / SCRAPI "Slot Filling Pattern"**：*"Split the problem across two components: Python (the callback) owns state, control flow, task firing, validation, and retry logic. The LLM owns language: parsing user intent, calling the right setters."* ——**Python 拥有状态、控制流、任务触发的权力，LLM 只负责语言。** **[实践共识]**
- **UX/UI Principles「Tool Use and Function Calling UX」**：组织规则是 *"model-controlled invocation, human-approved consequence"*。要注意这条规则针对的是**后果性动作**（写/发/付款/删除）；读操作应自动执行。**"[G]ate[ing] writes"** 是安全机制，不是意图识别机制——这点很容易被误用成"每次都问用户要不要生成"，那是摩擦。**[实践共识]**
- **Anthropic「Writing effective tools for agents」(2025-09)**：与其猜模型会不会调，不如**建评测集**——收集真实用户说法（dozens of prompt/response pairs），跑 `while` 循环做 agentic 评测，指标包括**"工具是否被调用"**（可指定期望调用的工具，但要避免过拟合路径）。关键数据点：*"Even small refinements to tool descriptions can yield dramatic improvements. Claude Sonnet 3.5 achieved SOTA on SWE-bench Verified after we made precise refinements to tool descriptions"*。**[实证]**

---

## 2. 替代方案：把"该不该调工具"改成"引擎决定的显式状态机"

这是本文的核心可执行建议，把模型不可靠的意图判断，换成**服务端可观测的状态转移**。

### 2.1 用显式状态（slot / phase）代替意图分类

**Slot filling** 的成熟做法（Microsoft Copilot Studio 官方指南 [实践共识]）：

- 用户说 "I'd like to order 3 large blue t-shirts" → 系统识别 Topic=Order, Qty=3, Color=Blue, Item=T-Shirt，**跳过这些提问**，只问缺的 Size。
- 官方原文：*"Slot filling lets your agent acquire and use information more easily and reduces the number of questions you need to ask."*
- 反例（官方不建议）：*"Don't ask for information already provided or data that can be retrieved automatically through APIs."*

**映射到本项目**：行程生成需要的最小槽位是 `date/duration` + `city` + （可选）`pace/companions/interests`。这些**已经从第 2 步的画像抽取里拿到了**。

那就不要问"用户是不是想生成行程"，而是问：

```
if 已有画像.时长 >= 1天 and 画像.目的地 is not None and not 本轮行程已生成:
    → 触发工具
```

**关键洞察**：用户说「帮我排一天的行程」，这句话的**信息增量**其实只是 `duration=1天`。其余全部来自已有画像。所以这个触发不该依赖句子里有没有「排」字，而该依赖**槽位是否齐了 + 用户是否在问时间安排**。而"在问时间安排"本身可以用更稳的办法判断：**这一轮是否引入了此前没有的行程参数**。

### 2.2 推荐的三层兜底（按确定性从高到低）

1. **确定性硬触发**（最高优先级，规则，零 LLM）：本轮抽取出了新的行程约束（时长/日期/节奏/地点），或用户点了推荐按钮 → 直接调工具。
2. **LLM 结构化决策 + 强制枚举**（不是自由生成）：一次轻量分类调用，**只输出 JSON**：`{"action": "generate_itinerary" | "modify_itinerary" | "answer" | "clarify", "confidence": 0-1}`。这是 When2Call/ClarifyAgent 的路子——把 ask-or-act 变成多选而不是自由文本。
3. **自检/重试**（Anthropic 路线）：如果模型返回 `answer`，但**回复正文里出现了 3 个以上带时间/地点标记的行程条目**（可用正则：`\d{1,2}[:：]\d{2}`、`第[一二三]天`、`上午|下午|傍晚` + 地点名），判定"描述型行程已经发生"，服务端**补一次工具调用并替换卡片**，而不是把文字留在那里。

第 3 条特别值得做：它把"漏调"从**用户可见的失败**变成**不可见的自愈**。Anthropic 的实践原则里有对应表述——不要指望一次到位，要建立**可测量的 eval 循环**。

### 2.3 关键词白名单还能不能留

能，但降级为**特征而非判据**：作为第 2 层分类器的提示词里的 few-shot 示例来源，或者作为第 3 层正则的一部分。不要让它单独决定是否调工具。

---

## 3. 建议问句（suggested prompts）：证据充分，但要分清三种用途

NN/G 把 prompt suggestions 明确分成三类（**[实证]**，2025-06-27「Designing Use-Case Prompt Suggestions」/ 2026-04-24「10 Guidelines for AI Chatbots」）：

| 类型 | 用途 | 出现时机 |
|---|---|---|
| **Use-case suggestions** | 教学：让用户知道系统能干什么 | 空状态、首次打开 |
| **Follow-up suggestions** | 继续对话：基于当前回答给下一步 | 每条回答之后 |
| **Autocomplete** | 补全当前输入 | 输入中 |

### 3.1 关键实证要点

- **必须是按钮，不是文字**。NN/G 2026：*"present them as clickable buttons, rather than text. This approach avoids unnecessary typing"*。反例：Williams Sonoma 的追问质量很高但**是纯文本**，用户想用还得自己打一遍。正例：Home Depot Magic Apron 每次回答后都给可点击、且**随对话上下文更新**的选项。**[实证]**
- **不要只在开头给，之后就不给**。NN/G 发现 Scouting America 的 Scoutly 对话开始后就停了推荐，用户原话：*"it doesn't have the option for secondary questions, which I feel like is a very helpful thing"*。**[实证]**
- **"push revelation" 的风险**：预先设定、不看用户上下文的推荐有明确记录的可用性问题——*"intrusive, easily ignored, and quickly forgotten"*；必须**容易忽略、视觉不打扰、明确绑定常见目标**。**[实证]**
- **推荐要跟上下文绑定**：Amazon Rufus 在首页给宽泛个性化建议，进入商品页立刻换成该商品相关问题——"立即表明它知道你在看什么"。反例：Home Depot 的 bot 其实能读页面上下文，但界面没说，用户就手动复制粘贴商品名。**[实证]**
- **别承诺做不到的**：Turo 开场说"anything you need"，用户真去问了车源，直接翻车。开场要列**覆盖范围**（Williams Sonoma 的 AI Sous Chef 列了找厨具/厨房好物/找菜谱）。**[实证]**
- **顺序偏差**：分析推荐点击率时必须考虑位置偏差（首屏/靠近输入框的必然高），**建议随机化顺序**才能分离内容效果和位置效果。**[实证]**

### 3.2 会不会限制用户表达？会，但要分清"限制"和"引导"

- Google Conversation Design（**[实践共识]**）给出 wide-focus vs narrow-focus 的权衡表：
  - **宽焦点**：鼓励自然表达、用户有掌控感、能拿到真实需求；但可能让用户**"deer in the headlights"**，也可能**过度承诺**。
  - **窄焦点**：边界清晰、好回答、少困惑；但**可能让用户觉得被限制**，像自动电话系统一样机械。
  - 原文金句：*"The magic and art of good conversation design is that users feel like they're in control and that they can say anything at anytime, but in reality, the dialog directs them along pre-scripted paths."*
- **实操结论**：推荐的形态必须是「**可点的捷径 + 不消失的自由输入框**」。Cloudscape 的规范说得最清楚：*"When structured options don't meet the user's needs, ensure they can always access the prompt input to provide open-ended context in their own words."* **[实践共识]**
- NN/G 的单边证据：复杂的宽泛示例（如 Claude 登录前的轮播）为了讲清能力**牺牲了真实性**——展示的是「一句话 → 完整产出」，而实际做不到。这是「限制表达」之外的另一种失真风险。**[实证]**

### 3.3 对旅游场景的具体设计

用 **AI 填半句** 而不是给整句。NN/G 记录的 ChatGPT 做法：点 pill → 弹出 autocomplete → 选中后把 prompt 改成问句并补充细节。**用户仍然在"说自己的话"，但省掉了组织语言的成本。**

对行程卡片后面：不要给「再排一天吧」这种死句，而是给**参数化追问**，例如「节奏慢一点」「换掉第 2 天的户外」「加上吃饭的地方」——这些是**直接对应修改工具入参**的，点了就调 `modify_itinerary`，是纯确定性触发（见 §2.2 第 1 层）。

---

## 4. 多轮对话：什么时候追问，什么时候给答案

### 4.1 有验证的决策框架

**Cloudscape（AWS 设计系统，[实践共识]，2025-07-16）给的判据最干净：**

> *"Decide whether to gather information before showing output or during the interaction. **For high-impact decisions or when confidence is low, collect details first.** When multiple questions are needed, collecting them sequentially reduces cognitive load and keeps each decision focused. **For other scenarios, start with an initial response and ask follow-up questions to refine results.**"*

配套硬规则：
- **先给答案，再精修**——大多数场景属于"other scenarios"。
- **一次问一个**（Google：*"Prompt the user with only a single question at a time"*）。
- **追问 ≤ 5 个/流程**（Cloudscape：*"limit follow-up questions to 5 or fewer per workflow"*），按相关性排序，最可能的在前。
- **不要为能自动获取的信息提问**（Cloudscape + Copilot Studio 一致）。
- 每一步都要有 **proceed / skip / exit**（Cloudscape：*"Provide clear options for users to proceed, skip, or exit at each step"*）。

**Google Conversation Design（[实践共识]）的补充**：
- *"Don't keep speaking after asking a question"* —— 提问后必须停下来等回答，不能自问自答。
- 追问的**三个正当理由**：错误处理、消歧（disambiguation）、**显式确认**。确认只在两种情况下必要：**误解代价高**（名字、地址、代他人发布的内容），或**动作难以撤销**（删除数据、完成交易）。
- **错误发生后要收窄问题**（narrow the focus），而不是把所有细节前置给所有人。

### 4.2 与本项目的对应判据

对旅游行程这个场景，我给出（**[观点]**，但由上面证据推出）：

| 情况 | 动作 | 依据 |
|---|---|---|
| 槽位基本齐（有目的地+时长） | **直接生成**，不要问"要我帮你排吗" | Cloudscape "other scenarios start with an initial response"；用户体验上是纯摩擦 |
| 缺关键槽（无目的地 / 无时长） | **问一个问题**，且用**窄焦点选项**（1天/2天/3天+） | Google：错误后/信息缺时收窄；Cloudscape：结构化输入优于开放文本 |
| 用户没说节奏/兴趣但已有画像 | **生成后用卡片让用户改**，而不是先问 | 行程卡片本身就是"可编辑的输出"，追问的价值被侧边面板替代 |
| 用户明显在改（"太赶了""换掉这天"） | **不问，直接调 modify** | 意图无歧义，问就是多余摩擦 |
| 行程涉及价格/预订等不可撤销动作 | 此时才上显式确认 | Google 的 explicit confirmation 判据 |

**一条容易忽略的实证**：NN/G 分析 425 段真实对话发现，**对话长度不是成功指标**，且用户常常**在拿到不合格回答之后才知道自己需要说清什么**（funneling conversation）。这意味着：**不要指望用户第一句就把约束说全**——画像抽取 + 后续修改，本来就是正确的分工。你的架构方向是对的。

---

## 5. "用户不知道能干什么"：这是文献里研究得最透的一题

### 5.1 三条有实验支撑的结论

**（1）引导的"内容"和"时机"是两个独立变量，且各有优劣**
CHI '22「How to Guide Task-oriented Chatbot Users, and When」（Yeh et al.）用**组间实验**比较了 2 种引导类型（**example-based** 范例式 vs **rule-based** 规则式）× 4 个时机（**服务引导期 / 任务介绍期 / 失败后 / 用户主动请求时**），共 8 种组合，测量任务表现、**后续任务上的学习提升**、主观体验。
核心结论：*"each guidance type and timing has particular strengths and weaknesses... each type/timing combination has a unique impact"*。**没有一种组合全面最优。** **[实证]**

→ 实践含义：不要只在空状态给一次推荐就完事。**"失败后"和"用户主动请求时"是必须补齐的两个时机**——而这正好对应"用户说了中文自然表达但没触发工具"那一刻。

**（2）选项（choices）应该主要用在对话破裂时**
HICSS 2024「When and How to Implement Choices on Customer Service Chatbots」：*"choice provision is more likely to benefit service outcomes **when conversational breakdowns occur**, because providing choices can guide customers back to a structured conversation."* **[实证]**

→ 实践含义：行程没生成、用户困惑的时候给选项，比一开始就给 5 个选项更有效，也更不打断表达。

**（3）引导频率过高会反噬**
ACM 上已有「Guidance Frequency in Task-Oriented Chatbots」的专门研究（90 名被试、随机分配三种引导频率）。另 NN/G 的 push-revelation 证据也指向同一方向：**过度设计的推荐会从帮助变成干扰**。**[实证]**

### 5.2 长期效应：前 5 次会话决定后面 5 个月

[观点/行业观察，非同行评审] falkster.com 的「Five Sessions, Then the Prompting Habit Sets」提出：模板会很快失效，用户大约 **5 次会话内收敛到 2–4 个模板**，而**第一批会话里试过的说法，在之后的使用中复现频率高 5–50 倍**。

→ 即使把它当弱证据看待，方向也与 NN/G 的"教学"定位一致：**建议问句的真正价值在头几次会话，之后价值递减**。所以：不要只给 3 个死句子，要给**会随画像更新、随对话推进而变化的动态问句**——否则第 6 次会话用户就无视它们了（NN/G 的"已被证明会被快速遗忘"）。

### 5.3 硬性设计清单（综合 NN/G 10 条 + Microsoft HAX）

Microsoft HAX「Guidelines for Human-AI Interaction」(Amershi et al., CHI 2019，18 条，经 heuristic evaluation 验证) 中最相关的四条：

- **G1 Make clear what the system can do**（初始期）
- **G2 Make clear how well the system can do what it can do**（初始期，讲清不可靠性）
- **G7 Support efficient invocation**（出错时：让调用 AI/功能变容易）
- **G8 Support efficient dismissal** / **G9 Support efficient correction**（出错时：容易忽略、容易修正）
- **G11 Scope services when in doubt**（出错时：不确定时收窄服务范围）——**这条直接对应 §4 的"少追问、窄焦点"**

NN/G 10 条里对双栏布局最直接的三条（**[实证]**，均为真实用户测试结论）：
- **G6 Use progressive disclosure to keep the chat short**——聊天窗里不要塞完整行程文字，用卡片承接。
- **G7 Don't autoscroll users to the end of a response**——*"keep the user's scroll position at the top of the new message rather than jumping to the bottom"*。
- **G8 Allow users to resize the chat window**——*"Most chatbot windows are quite small by default"*，有地图/丰富内容时必须有放大可能。Scoutly 放地图在默认窗口里"难以探索"。
- **G9 Allow users to save or share**——*"A useful conversation that disappears after the user exits the page is lost value."*（用户原话：想 email 给自己/分享给女儿，但没这个功能）

---

## 6. 「对话 + 侧边结果面板」：成熟案例与注意力分配

### 6.1 真实产品案例（旅游域最贴的一个）

**Thomas Cook India 的 Tacy（TravBridge），2025-01 上线生产，thomascook.in，每日数千用户**。由 Atirath 设计，案例公开在设计师个人站（[案例]，非同行评审，但是生产系统）。

其设计与本项目高度同构，值得逐条对照：

- **三栏布局**：左=导航 + My Chats/Packages；中=对话，主画布；右=**持久右侧面板**，放 packages、筛选器、**可编辑的行程**。原文 01 图注：*"the conversation is the canvas, with the package pane opening beside it."*
- **动态行程面板在对话旁"自己长出来"**：*"a persistent right-hand pane opens with an editable itinerary shell. Customers edit the key properties of that package directly in the pane while the conversation continues alongside."* ——**用户可以在面板里直接改，不必用嘴描述修改。**
- **为解决"如果→如果→如果"的生成分支，用了 block-based 行程系统**：每天由 block 组成，每种 block 自带约束。Arrival（第一天首块，**不可删**）、Departure（末块）、Accommodation（每晚一个，无缝）、Activity、Food（要按交通时间排序，否则"physically impossible"）、Transport（计入实际耗时）。原文：*"The itinerary rules and non-deletable structural blocks turned 'AI magic' into reliable, bookable trips instead of plausible-sounding suggestions."*
- **两种模式共存**：全定制（动态包）+ 一键固定包。**并且明确告诉用户取舍**——*"These itineraries can't be modified — **the trade is flexibility for speed, and it is made explicit.**"*
- **连续性即产品**：*"Trip planning happens over days, not minutes... Every conversation is stored... Reopening a chat restores the full message history and every package discussed in that thread."* 原文总结：*"The system remembers you — and that memory is the product."*

**本项目的直接借鉴点**：
1. **行程 block 约束**比"让模型排得合理"可靠得多——这是**确定性兜底**在内容层的应用，和 §1.2 同构。你的"服务端校验工具调用"应该扩展到校验**行程结构本身**（首末块、住宿无缝、交通耗时），而不只是校验"有没有调工具"。
2. 面板里**直接可编辑**，等于把大量"修改请求"从对话层转移走，同时降低对工具调用的依赖。这是**降低关键路径依赖**的最有效手段。
3. 固定/宽松两种模式混在一起会搞晕用户——**必须显式说明取舍**。

其他双栏案例：
- **Microsoft Copilot Pages**：左聊天、右文档画布，*"easy to switch between prompting the AI and making direct edits"*。[案例]
- **Cursor Canvases**：*"interactive artifacts that render next to the chat. Instead of scrolling through a long markdown table or code block, you get a standalone view"*。[案例] GitHub Copilot 的 canvas extensions 是同一思路（"shared, agent-driven artifacts"）。
- **Wayfarer**（Vercel 上的 AI travel guide 模板）：*"Chat directs the AI; the canvas is where it works. One prompt fills a live map, day-by-day itinerary, and budget."* ——表述精准：**对话是输入渠道，画布是工作区**。[案例，模板产品]

### 6.2 双栏的已知失败模式（必读）

**Luke Wroblewski「An Alternative Chat UI Layout」(2025-11)** [实践共识，资深设计师观点 + Augment Code/VS Code 实观察]：

问题描述：agentic 循环让 chat 变成*"a long internal monologue"*；在**侧边栏这种窄空间**里尤其糟糕。VS Code 里的 Augment Code：*"By the time a task is complete, the initial user message that kicked it off is long off screen and people are left scrolling up and down to get context."*

他的结论（**对本项目很重要**）：
- **"chat + canvas"分离过程与结果的思路听起来好，但实践中很难干净划线**——*"How 'final' does the output need to be before it's considered 'the result'?"*，且有后续问题、中间步骤的情况更难。
- 他提出的替代：**双滚动面板**——用户指令/思考/工具调用在**一栏**，结果在**另一栏**；模型完成思考后**过程折叠成摘要**，结果在结果栏**持久且可滚动**。目的是让"指令和产物"始终同时可见。

→ **对项目的具体含义**：右侧行程卡片是"结果栏"，千万不要往卡片里塞思考过程和每次工具调用的细节。而**左侧对话区也只放摘要**，详细过程折叠。两侧各自独立滚动，互不驱动。

### 6.3 注意力怎么分配：可执行的几条

综合 NN/G 与 agentic 模式资料（**[实践共识]**，部分为 **[观点]**）：

1. **侧栏变化必须被"宣告"**。NN/G：用户不会假设 bot 知道你正在看什么，**除非你明确说出来**。→ 卡片生成时，对话里必须有一句简短的话指过去（"右侧更新了一版，你看看第 2 天"），而不是静默替换。
2. **不要把自动滚动当成通知**。NN/G G7 明确反对 autoscroll；Streaming Results 模式同样列了*"Anchored Scrolling and Focus — Avoid automatically scrolling to the bottom"*。
3. **能用"就地修改"就别用"重新生成"**。Streaming Results 的 pattern 要求：*"Refinements and follow-ups either update the current block predictably or create clearly labeled new versions."* ——**新建版本要明确标注**，否则用户不知道哪版是最新的。
4. **部分结果要标"部分"**。若行程卡片是流式出现的，要显示"还在补第 3 天"。原文：*"Partial results are visibly labeled, with counts or progress indicators where possible."*
5. **错误要局部化**。*"If a tool call fails, the affected block shows a localized error with clear scope"* + 提供 retry / 改参数 / 用部分结果。**不要整页报错。**
6. **卡片上每一条都要有入口**。*"Provide 'Ask about this' entry points on rows/cards to initiate focused conversations"* —— 点某个景点可以追问。这是**让用户"知道能干什么"的第二种手段**（第一种是建议问句）。

---

## 7. 汇总：对本项目的 5 条改动建议（按 ROI 排序）

| # | 改动 | 依据 | 成本 |
|---|---|---|---|
| 1 | **删掉关键词白名单判据**，改成：本轮回填了新的行程槽位（时长/地点/节奏/日期）→ 确定性直接调工具 | Copilot Studio slot filling；CX Agent Studio "Python owns control flow" **[实践共识]** | 低 |
| 2 | **加"描述型行程自愈"**：模型返回 answer 但正文含 ≥3 个时间/地点条目 → 服务端补调工具、覆盖卡片 | Anthropic eval 循环思路；把漏调从用户可见失败改为不可见自愈 **[观点+实证]** | 低 |
| 3 | **行程结构校验**：不只校验"调没调工具"，校验首末块/住宿无缝/交通耗时，不合格重排 | Thomas Cook Tacy 的 block-based itinerary **[案例]** | 中 |
| 4 | **卡片每项给"就地修改"入口** + 生成后在对话里指过去一句；固定模式/自由模式的取舍显式写出 | Streaming Results pattern；NN/G G7/G8/G9；Tacy "made explicit" **[实证/案例]** | 中 |
| 5 | **建一个 30–50 条真实说法的 eval 集**（含「排一天的行程」「这天怎么过」「太赶了」这类），每次改提示词跑一遍，看"该调未调"率 | Anthropic "Writing effective tools"：*"Even small refinements to tool descriptions can yield dramatic improvements"* **[实证]** | 低（但必须持续） |

**额外建议（不影响闭环但值得排期）**：建议问句做成**参数化 + 上下文相关**（对应用户当前画像），而不是固定 3 条；并在对话开始后**继续提供**（NN/G 发现停掉是个常见错误）。

---

## 8. 证据强度自查

**较强（有实验/生产验证）**：When2Call / ClarifyMT-Bench / QuestBench / ClarQ-LLM 的 under-clarification 与 ask-vs-act 弱点；NN/G 的 button-vs-text、follow-up 持续性、autoscroll、resize、save/share；CHI'22 引导类型×时机；HICSS'24 选项用于破裂修复；Cloudscape/Google/Copilot Studio 的追问规则；Anthropic 的 tool description + eval 方法；Thomas Cook Tacy 的生产形态。

**中等（资深从业者观察/单案例）**：Luke W 的双栏观察（来自 Augment Code/VS Code 实际使用）；falkster 的"前 5 次会话"数据（博客，未同行评审，**建议只当方向参考，不要当数字引用**）。

**本文推断（明确标注为观点）**：§2.2 三层兜底的具体实现；§4.2 的判据表；§6.3 的注意力条目中第 1、3 条的具体措辞。
