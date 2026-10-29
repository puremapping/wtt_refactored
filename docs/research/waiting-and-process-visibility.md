# 对话产品的「等待期」与「过程可见性」设计参考

**日期：** 2026-10-29
**用途：** 为对话页改版（loading 态、工具调用表达、引导继续对话）提供带证据的设计依据
**证据分级：**
- **[A] 实验数据** —— 有对照组、样本量、统计检验的论文或 A/B 测试
- **[B] 大厂设计规范 / 产品自述** —— 一手来源，但是原则声明而非测量
- **[C] 产品实测拆解** —— 第三方系统盘点现有产品的实际交互
- **[D] 设计师观点** —— 无数据，仅供参考

> 先读结论：证据最强的两条是「显示真实工作步骤能提高感知价值，即使总时长变长」和「过短反而显得不认真」。**但两者都有边界条件**，照抄会翻车。下文逐条说边界。

---

## 一、Loading 态：转圈 vs 步骤提示 vs 流式 token

### 1.1 基础阈值（老但仍是行业默认）

NN/G 的响应时间三档 **[B]**：0.1s = 瞬时感；1s = 思路不断；10s = 注意力漂移。规范建议：

- 2–9 秒 → 循环动画（spinner）
- ≥10 秒 → 明确百分比进度
- 无法给出准确进度时 → **列出已完成/待完成步骤**，并标注当前步骤
- 来源：[NN/g Progress Indicators](https://www.nngroup.com/articles/progress-indicators/)、[NN/g Designing for Long Waits](https://www.nngroup.com/articles/designing-for-waits-and-interruptions/)

这条 10 秒线对 LLM 产品基本失效——推理模型常见 20s+ TTFT，且无法预估百分比。所以下面的实测更关键。

### 1.2 显示真实工作步骤：感知价值上升，即使更慢 [A]

**Buell & Norton (2011), *The Labor Illusion*, Management Science 57(9)** —— 被引用最多的证据。
- 在线旅游搜索场景，5 个实验。对照组只看进度条，实验组额外看到滚动列表「正在搜索 Lufthansa / 正在比较 United 价格 / 正在查余位」
- 结果：同一份结果，**看到工作过程的一组感知价值高 8.1%**；等待被设成 10–60s 随机区间后，人们**愿意为相同结果多等最多 50 秒**
- 机制：感知到的"付出"触发互惠感（reciprocity），进而抬高价值判断
- 二手转述的两个数字（"感知等待短 15%"、658 人 / 45 秒）来自 [ux-strategy.ch 的综述](https://www.ux-strategy.ch/en/effects/operational-transparency.html)，**我未在原论文中逐字核到这两个数字**，引用时建议只用「8.1% 提升 + 愿意多等」，这两个是原摘要与原文明确写的
- 来源：[HBS 全文 PDF](https://www.hbs.edu/ris/Publication%20Files/Norton_Michael_The%20labor%20illusion%20How%20operational_f4269b70-3732-4fc4-8113-72d0c47533e0.pdf)
- **场景契合度：高。** 原论文的领域就是"在线旅游 + 在线dating"，和本产品几乎同构

**Tsekouras, Li & Benbasat (2022), Information & Management** —— 复现了同一方向：只是 7 秒 spinner 配「calculating results」文字，用户对推荐质量的评价就显著高于即时返回（N=306 汽车搜索 / N=294 约会匹配）。转述来源：[HubSpot 综述](https://blog.hubspot.com/marketing/why-ai-shows-loadtime)（**我未读原文，标为二手**）

### 1.3 过短反而显得不认真 [A]

**Tan, Messerschmidt, Nov et al. (2026), CHI'26** —— 这篇最直接回答"我们的场景该怎么等"。
- N=240，控制 TTFT = 2s / 9s / 20s，首 token 之后统一 25 tok/s；任务分 Creation / Advice 两类
- **2 秒的回复被评为「更不深思熟虑」（thoughtfulness 5.76 vs 6.09/6.11）**；usefulness 在 9 秒时最高（6.44 vs 2 秒的 6.19）
- 有趣的是：**用户的交互行为（发问次数、复制、重开）对延迟完全不敏感**；只有主观评价变了
- 注意延迟的比率：2s→26.6%，9s→66.3%，20s→81.5%
- 定性主题（N=140 自述注意到延迟的人）：45% 说没影响 / 31% 推断"AI 在思考"从而期待更高质量 / 14% 怀疑系统坏了 / 7% 负面情绪
- 来源：全文 [arXiv:2604.06183](https://arxiv.org/pdf/2604.06183)（另见 ACM DOI 10.1145/3772318.3790716）
- **对我们的含义：** 如果行程生成刻意压到 1–2 秒出结果，用户可能反而觉得"没认真想我的情况"。但要小心下面 1.5 的反例

### 1.4 反例：什么情况下"过程透明"变成负担 [A]

**Hong, Hess & Hardin (2013), MIS Quarterly, "When Filling the Wait Makes it Feel Longer"** —— 与劳动幻觉方向相反的证据。核心发现：当等待信息**与用户的认知任务层面不匹配**（例如正在做需要专注的判断时，屏幕上的动态内容会抢占注意力），填充式反馈会让等待**感觉更长**。标题本身就是论点。DOI: 10.25300/misq/2013/37.2.04（我只读到摘要，未读全文）

**Aaldijk et al. (2024)** —— 零结果，必须知道。
- N=40，组内设计，总延迟统一 2 秒，对比「什么都不显示 / 三点动画 / 逐字打字」
- **三者感知可用性无显著差异**（p = 0.148）；与用户原有 chatbot 经验也无交互
- 作者自陈局限：延迟只有 2 秒、任务过于简单，可能不足以显现差异
- 解读：**在 2 秒这个量级上，做什么 loading 都可能无所谓。**这是一个"没有证据支持差异"的结果，不能反推"任何时长都一样"
- 来源：[原文 PDF](https://userexperience.org/wp-content/uploads/2025/01/Study-on-Chatbot-repsonse-delay.pdf)

**Arunkumar et al. 2026, "Wait for It" (VR, N=18)** —— 明确的反例：在拟人化对话场景（VR 化身）里，**显式 spinner 反而降低了拟人感、破坏了沉浸**，把用户从"社交心智模型"切到"技术心智模型"；具身化的"思考动作"表现最好。
- **边界：** 这是 VR/具身场景，不能直接搬到文字聊天界面。但它给出一个重要提醒：**当 AI 被包装成一个"人"时，暴露机器细节是有代价的**
- 来源：[arXiv:2610.23336](https://arxiv.org/html/2610.23336)

### 1.5 流式 token：证据比想象中弱

- 我**没有找到**"流式 vs 阻塞式"在 LLM 场景下的直接对照实验（同等总时长、只差异呈现方式）。网上广泛流传的 "TrackAI n=200，3s 阻塞 vs 5s 流式" 表格找不到可核验出处，**不要引用**
- 能核到的相关事实：[Andes (arXiv:2404.16283)](https://arxiv.org/html/2404.16283v1) 把文本流式的 QoE 形式化为 TTFT + 最小 token 交付速度（TDS）两个门槛，指出用户的阅读速度本身是上限——**服务端再快也没用，人会读不过来**。这是工程论文，不是用户实验
- 推理：[CHI'26 那篇](https://arxiv.org/pdf/2604.06183)固定了 25 tok/s 只变 TTFT，说明社区默认"首 token 何时到"比"总时长"更关键
- **[找不到]** 一篇能说"流式比转圈感知等待短 X%"的可信实验。**如果团队里有人说"有研究表明流式更好"，请对方给论文。**

---

## 二、过程透明：什么时候涨信任，什么时候涨焦虑

### 2.1 关键结论：透明不是越多越好，是"刚刚好" [A]

**Pareek et al. (2026), CHI'26, *Sensemaking in Multi-Agent LLM Interfaces*** —— **和本产品最像的一篇**（多智能体、要看内部过程）。
- 定性比较观察研究，被试使用 5 个透明度不同的界面变体，任务分"信息查询"和"逻辑推理"两类
- 结论：不存在统一的"最优透明度"。**理想水平由三者共同决定：任务需求 × 界面能力 × 用户特征（领域专长、对 AI 的先天信任度）**，论文称之为 "Goldilocks（刚刚好）" 透明度
- 明确指出的张力：**过程可见性 vs 信息充分性 vs 认知成本**，三者互相拉扯
- 来源：[ACM DOI 10.1145/3772318.3791157](https://doi.org/10.1145/3772318.3791157)（只读到摘要，未读全文）

### 2.2 展开大量 reasoning 有副作用：过度依赖 + 虚假理解感 [A]

**Fernandes, Kosch, Buschek, Welsch (2026), CHI'26 Workshop *Explaining Too Much?***
- 预注册，N=569，LSAT 型推理任务，三组：仅答案 / 完整推理链 / 推理摘要
- 引用的既有结论：高冗余度的解释会诱发 "illusion of understanding"，流畅的论证会推动用户**即使结论错误也过度依赖**；且 CoT **并不总是忠实**反映模型的真实计算过程
- 来源：[全文 PDF](https://ai-tools-for-thought.github.io/workshop/documents/chi26/Fernandes_et_al_Explaining_Too_Much_TfT_CHI26.pdf)
- ⚠️ 这是 workshop 短论文（6 页），正文写着 "provide preliminary evidence"，**数字结论我不引用**，只引用其框架与文献综述部分

### 2.3 反向证据：结构化展示 CoT 确实帮到用户 [A]

**Schelhorn, Gnewuch & Maedche (2024, SIGHCI)** N=84：展示 CoT（显示了"找到哪些数据集 / 选了哪个 / 怎么查的 / 怎么得出结论"）**显著提高了 representational fidelity**，并间接正向影响任务有效性。**注意情境：数据分析任务，用户需要理解结论怎么来的**。来源：[AISeL](https://aisel.aisnet.org/cgi/viewcontent.cgi?article=1014&context=sighci2014 的 sighci2024 卷)

**Zhou et al. (IUI'26)** N=125：把 CoT 改成**可交互**的形态（可导航、高亮、图结构）比纯文本 CoT 明显更好——错误检出率 85.6%(iGraph) / 82.5% / 80.6% vs 73.5%(纯文本)，验证速度也更快（57.9s / 60s vs 64.7s）。来源：[arXiv:2510.22922](https://arxiv.org/html/2510.22922v4)
- **可迁移的启示：** 过程信息"可点开、可导航"比"平铺一大段"有效得多

### 2.4 汇总：判断表

| 情境 | 透明度策略 | 依据 |
|---|---|---|
| 用户在等待、还没看到结果 | 显示**真实**的工作步骤（查了什么、在算什么） | [A] 劳动幻觉 +8.1% 价值 |
| 用户需要判断结果可不可信（查数据、推荐理由） | 给可展开的结构化过程，支持核对 | [A] Schelhorn +84人 / Zhou +125人 |
| 用户只想快点拿到行程 | 默认折叠过程，一句话结论在前 | [A] Fernandes: 冗余诱发过度依赖；[B] Intuit 规范 |
| AI 被包装成"同伴/顾问"的人格 | 少暴露技术细节，用"任务语言"而非"系统语言" | [A] VR 反例（弱外推） |
| 步骤是**假的**（编造进度） | 绝对禁止 | [B] Intuit 明令 "Avoid fake progress indicators" |

---

## 三、「思考过程」面板：多少人真的会展开？

### 3.1 找不到公开数据

我**没有找到**任何产品公开的"thinking 面板展开率"。OpenAI / Anthropic / Google 都没发过这类遥测。任何声称 "只有 X% 用户会展开" 的说法都是编的。**明确说：此项无数据。**

### 3.2 能找到的：各家产品选了完全不同的默认值 [C]

**Northbase 系统盘点（130 个实例，9 个产品）** 是目前最具体的一份实测拆解：
- 推理展示呈"四极"分布，互不兼容：
  - **DeepSeek**：原始思维链，**默认展开**，带「Thought for 93 seconds」
  - **Claude**：给内容摘要，从**不给时长**
  - **ChatGPT**：只给时长 chip「Thought for 26 seconds」，**从不给内容**
  - **Gemini**：什么都不显示（6 张截图核实为空）
- 9 个系统里只有 1 个（DeepSeek）默认展开原始 CoT
- 9 个系统里只有 3 个（ChatGPT / DeepSeek / v0）报告**实际**耗时；Copilot 只给运行前预估
- 来源：[Northbase: The Agentic Interface](https://www.northbase.design/patterns/agentic-interface)
- **解读（[D] 我的推论）：** 头部厂商的分歧说明这是个**还在被 A/B 检验、没有定论**的设计点，不是"业界共识"。抄谁都行，但要有自己的埋点

### 3.3 Anthropic 自己给的展开与否的理由 [B]

Claude 3.7 发布文明确列了「可见思维过程」的利弊：
- 利：信任（可观察、可核对）、对齐研究、有趣
- 弊：**思维过程没有做角色训练，语气冷淡且可能含错误/半成品的想法**，部分用户会觉得烦躁；**faithfulness 无法保证**（模型很多决策根本没在思维链里说）；安全风险（可被用来构造越狱）
- 来源：[Anthropic, Claude's extended thinking](https://www.anthropic.com/news/visible-extended-thinking)
- **对我们的直接含义：** 我们的"智能体身份标签"和思考展示如果没有约束，用户会看到「画像抽取 agent」吐槽他的原话，这比不显示更糟

---

## 四、工具调用怎么表达：「正在生成行程…」vs 直接出中间结果

### 4.1 有实验支持的：中间结果要"真"且有结构 [A]

- [Zhou et al. IUI'26]：结构化/可交互的中间结果 > 一段文字。迁移到行程：**边生成边把站点卡片一个个地"落"到右侧，比一句"正在生成行程…"强**，因为用户能核对"第一站为什么是这个"
- [Buell & Norton 2011]：但要保证中间显示的**是真的在发生的事**。行程生成的真实步骤可以是「在候选池里筛 64 个景点 → 按动机剔除不匹配的 → 算路线 → 排时间线」——这些是真步骤，可以显示；"正在深度思考中"就不是
- [B] Intuit 内容设计规范给了可直接抄的三段式公式：**planning → doing → done**
  1. 说明将要做什么：「Generating your day plan」
  2. 显示真实进展：「Filtering 64 spots by your motive」「Solving the route」「Balancing your 4h window」
  3. 收尾：「Your plan will be ready in a moment」
  - 并明确 **"Avoid fake progress indicators"**
  - 来源：[Intuit Content Design – UX patterns](https://contentdesign.intuit.com/ai/ux-patterns/)

### 4.2 反例：只有"进行中"没有"完成了"会更焦虑 [C]

- Northbase 盘点里的 anti-pattern：**「With no visible progress, a two-minute task feels frozen at 40 seconds. Users refresh the page or start a duplicate task.」** → 用户的典型反应是刷新或发起重复任务（会双花 token、产生两条行程）
- 另一个：**6/9 个产品在任务跑在后台时，任何地方都不显示状态**——如果用户切到别的标签，回来发现"什么也没发生"
- ChatGPT 的 stop 行为：**静默丢弃已生成的部分**；Perplexity 反而把中止重标成「Completed 14 steps」带同样的 ✓。→ 停止/失败必须**命名状态并保留已生成的部分**
- 来源：同上 Northbase

### 4.3 结论（我的建议，标注为推论 [D]）

对「生成一天行程」这个动作，最优表达是**二段式**：

1. **0–1s 内**：不转圈，直接给**结构化的占位骨架**（右侧出现 4 张空的行程卡片，带时间轴槽位）+ 一行真实步骤文案。骨架不是假进度，是"答案的形状"
2. **每个站点生成完就落一张真卡片**，同时对话气泡里说一句「第 3 站换了，捧河湾的人流比天门山低」
3. **结束后**折叠步骤，留「用时 12 秒 · 查了 64 个景点」的可点开账本

理由链：骨架给"形状预期"（NN/G 的步骤剩余感）→ 真卡片给"进展可信"（劳动幻觉）→ 折叠账本给"可核对但不吵"（Fernandes / Intuit）

⚠️ **没有直接实验证明这个组合更好**。最接近的支撑是上面几条各自独立的证据拼起来。上线要自己做 A/B。

---

## 五、引导用户继续对话：哪些有数据

### 5.1 有 A/B 数据的一条 [A]

**Qwen App, "What to Edit Next"（阿里）** —— 图生图场景的追问建议（follow-up edit suggestions）
- **14 天用户随机化 A/B，百万级用户**，对比已上线的 prompt-engineered 方案
- 结果：推荐点击率 **+32.70%**、图片带走率 **+16.32%**、**人均对话轮次 +39.90%**（均 p<0.05）
- 附加：视觉不一致率 3.7% → 0.9%
- 来源：[arXiv:2608.07565](https://arxiv.org/pdf/2608.07565)
- **能外推什么：** 「AI 主动给出**具体、可执行、且与当前上下文强相关**的下一步建议」能显著拉高轮次。注意它靠的是**用真实点击数据训一个策略**，不是随手写几个 chip。**不能外推：**不能说明"任何 suggested prompts 都 +40%"

### 5.2 有 A/B 数据的一条（但方向不同）[A]

**alby（AI 购物，1500 万消费者 A/B）**
- 传统聊天气泡机器人：仅 **0.3%** 流量会点开；CSAT 55%
- 改成"Click-to-Prompt"按钮（点按钮 = 直接问一个具体问题）：搜索页顶部 **参与率翻倍到 0.7%**、产品页 **转化率 +30%**（但参与率降到 0.2%）
- 最终形态"嵌在商品页里的生成式问答"：**参与率是传统 chatbot 的 14 倍、转化 2 倍、CSAT 86%**
- 来源：[alby blog](https://blog.alby.com/we-tested-ai-powered-shopping-experiences-with-15m-consumers)
- **对我们的含义：** **入口/提问的位置和形态**比"话术"重要一个量级。在对话页里，"AI 主动问 + 给两个具体选项" 比"请随意输入"有效

### 5.3 反驳：suggested prompts 也可能是噪音

- 有些研究显示 prompt scaffold / nudge 改变了用户行为但**没有改善结果**（如 [K-12 学生 ChatGPT 研究](https://www.aied.hk/en/news/k12-chatgpt-adaptation-prompt-scaffolds)：106 名九年级学生，脚手架改变了使用方式但未提升知识增益）。这提示：**建议问句提升的是"互动量"，不等于"决策质量"**。对于一个旅游决策产品，如果用户被引导点了一堆 chip 但画像没变深，那是虚假繁荣
- **[D] 我的判断：** suggested prompts 应**由画像缺口驱动**，而不是装饰。画像缺"预算"就建议「预算大概多少？」，缺"同伴"就建议「一个人还是带人？」，缺"动机"就建议「你更想要哪种感觉？」

### 5.4 卡片式回答 vs 纯文本

- **[A] Google Research《Generative UI: LLMs are Effective UI Generators》**：人类评审对生成式 UI 的偏好**显著高于**标准文本/markdown 输出，仅次于人类专家手写网站；**但其自述"未计入生成速度"**，且当前实现**可能要一分钟以上**才能生成
  - 来源：[Google Research blog](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/)、[Jakob Nielsen 的解读（90% 偏好）](https://jakobnielsenphd.substack.com/p/generative-ui-google)
  - ⚠️ 偏好研究（preference），不是任务完成率研究。而且这项研究没算速度成本——**它恰恰承认了生成慢是主要风险**
- 对本产品的含义：**右侧行程卡片本身已经是"卡片式回答"**，方向是对的；缺的是把卡片和对话气泡做成"一个动作的两个面"，而不是两个脱节的窗口

---

## 六、产品案例（具体到交互细节）

### 案例 1：Perplexity —— 步骤账本 + 来源 chip + 追问行
- **进行中**：Pro Search 先给出结构化研究计划（子问题列表），随流式更新；步骤行（`Reading raw/canva.md · Now`）**只在对该行 hover 时显示时长**（Northbase 实测：时长渲染 opacity 0）
- **完成后**：答案上方一行 favicon 堆叠 + 「10 sources」，旁边是分享/复制/改写
- **追问**：答案下方给出若干具体追问
- **多智能体**：显示「Awaiting 1 subagent」，并把子代理名（snake_case，如 `wide_search_research`）和它的完整活动日志缩进一级展开
- **缺点**：hover 才见时长 ≈ 没给时长；中止会被重标成「Completed N steps」✓，与真成功同形
- 来源：[Northbase](https://www.northbase.design/patterns/agentic-interface)、[Perplexity 引用拆解](https://aiuxplayground.com/teardowns/perplexity/citations)、[Perplexity Pro 架构](https://www.langchain.com/breakoutagents/perplexity)

### 案例 2：Claude —— 折叠 thinking + Artifacts 侧栏
- **thinking**：以「Thought for Ns」式折叠块置于答案上方（Claude 主体给内容摘要，不给时长；Claude Code 给「thought for Xs」+ 可展开）——两者口径不同，说明内部还未统一
- **Artifacts**：检测到"可交付物"（文档/代码/组件）时**自动在右侧开分栏**，左侧对话、右侧产出物，产出物可迭代编辑并带版本历史
- **为什么对我们重要**：Artifacts 解决的问题和我们"右侧行程卡片"是同一个——**对话是过程，产出物要装在一个能反复操作的地方**。案例的失败模式也值得记：侧栏一旦和对话脱节，用户就以为功能坏了（正是当前问题 2）
- 来源：[Anthropic 官方](https://www.anthropic.com/news/visible-extended-thinking)、[Artifacts 帮助中心](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them)、[Interface Lineage 分析](https://interfacelineage.com/claude-artifacts-side-panel)

### 案例 3：ChatGPT —— 时长 chip + 停止即丢弃 + 后台无状态
- **thinking**：只有时长 chip「Thought for 26 seconds」，没有内容；这是"用时长做预期管理"的极简派
- **Agent 模式**：先展示步骤/计划，再执行；「Worked for 4m 10s」给实际耗时
- **缺陷（Northbase 实测）**：任务在后台跑时，界面**任何位置都没有徽标/toast/列表状态**；点 stop 会**静默丢掉部分回复**
- 来源：[Northbase](https://www.northbase.design/patterns/agentic-interface)

### 案例 4：DeepSeek —— 唯一默认展开原始思维链的产品
- 原始、碎片化、未修饰的思维链**默认展开**，顶部「Thought for 93 seconds」；搜索模式下的推理还会**不随提示语言切换，一路中文输出**
- 测评评价："这是差异化声明，不是可照抄的 UX 默认值——它取信技术受众，劝退其他人"
- 另一处独有设计：中止后**保留部分思维链**并提供「Continue」按钮
- 来源：[Northbase](https://www.northbase.design/patterns/agentic-interface)

### 案例 5：Gemini（Google）—— Generative UI，把"回答"直接变成"界面"
- 模型不仅生成内容，还**现场写出一个完整交互界面**（网页/游戏/工具/模拟器）来回答这一个问题
- 明确举了旅游的例子：「为即将到来的旅行做计划」会得到完全不同的界面形态
- Google 自己的数字：评审偏好**显著高于**文本/markdown，仅次于人类专家手做网站；**但生成可能需一分钟以上**
- 已作为 `dynamic view` 与 Search AI Mode 的实验上线
- 来源：[Google Research](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/)

### 案例 6：Intuit —— 唯一写明"禁止假进度"的大厂内容规范
- 三段式：planning → doing → done；示例文案给到句子级
- 明令「Avoid fake progress indicators」，并且说明理由（劳动幻觉会被假步骤反噬）
- 还给了 **front door response**（开放式问「你想用工资单做什么？」）vs **disambiguation response**（给 2–3 个选项，当模型确信用户会选其中一个时用）——**这正是引导对话的官方分级做法**
- 来源：[Intuit UX patterns](https://contentdesign.intuit.com/ai/ux-patterns/)

---

## 七、对本产品的直接建议（标注为推论 [D]，非证据）

| 当前问题 | 建议做法 | 支撑证据 |
|---|---|---|
| 1. 只有转圈，不知道在等什么 | 换成**真实步骤行**（筛选候选 → 匹配动机 → 解路线 → 排时间线），每完成一步打勾 | [A] Buell&Norton；[B] Intuit；[C] Northbase anti-pattern |
| 2. 说"排一天行程"但不调工具 | **不靠 UI 救，靠工具描述救**：把 `generate_itinerary` 的 description 写成"用户提到「排/看看/安排一天」等**任何**行程意愿时**必须**调用，禁止用文字描述替代"。UI 侧加"兜底"：检测到回复里出现时间点+地名但没 tool_call，自动触发一次生成 | 无直接研究；这是工具设计问题，不是交互问题。可参考 `propose_` 前缀约束的既有做法（本项目 DESIGN v0.3 §3.2） |
| 3. 看不出是哪个智能体说的 | 身份标签保留，但**只显示角色，不显示内部昵称**；思考面板里**不要**暴露画像抽取 agent 的原始吐槽 | [A] Fernandes（冗余诱发误解）+ [B] Anthropic（思维未做角色训练，语气会伤人） |
| 4. 没有流式 | 做**两段式**：先骨架 + 真步骤，站点逐个落卡片 | [A] Zhou（结构化中间结果）+ [B] Intuit 三段式；**流式本身无直接实验证据** |
| 引导继续对话 | suggested prompts **由画像缺口生成**（缺预算/同伴/时长就给对应问题），不用装饰性 chip | [A] Qwen A/B +39.9% 轮次；[A] alby 位置效应 14× |

### 需要警惕的坑
1. **不要造假进度**。假步骤一旦被识破，劳动幻觉会反噬成"这产品在骗我"
2. **不要把 20s+ 的等待美化成"深度思考"**。CHI'26 显示 20s 时 83% 的人注意到延迟，14% 开始怀疑系统坏了
3. **不要默认展开思考过程**。9 个产品里只有 DeepSeek 这么做，且它是差异化而非最优解
4. **不要用"提升轮次"当唯一成功指标**。轮次上去了但画像没变深 = 虚假繁荣（§5.3）

---

## 八、我明确没找到的数据

- thinking / 推理面板的**展开率**（无任何产品公开遥测）
- **流式 vs 阻塞**在 LLM 场景的对照实验（只找到工程侧的 QoE 建模，无用户实验）
- suggested prompts 在**旅游决策**场景的效果（只有电商/图像编辑场景的 A/B）
- 卡片式回答 vs 纯文本在**决策质量**上的差异（Google 测的是偏好，且明确排除生成速度）
- "步骤提示 vs 转圈"在 **LLM 长等待（>10s）** 下的直接对照实验——最接近的是 Buell&Norton（非 LLM）与 Aaldijk（2 秒、零结果）
