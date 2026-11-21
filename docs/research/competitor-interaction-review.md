<!-- 格式：PMS 文档集格式 v1.0 -->
# 竞品交互与产品设计逐产品拆解

> 调研日期：2026-11-21（子代理实抓）
> 指派：阿哲 2026-11-12，`wtt_ux-refactor/PLAN.md` §竞品调研任务
> 视角：**交互与产品设计**（不是赛道盘点）。赛道全景见 `ai-travel-competitive-landscape.md`，本文不重复。
> 证据标注：`【官方】`厂商自述 / `【第三方实测】`记者博主亲自上手 / `【第三方报道】`媒体转述 / `【推断】`基于证据的推测，非原文结论。

---

## 0. 查证前提（影响结论怎么用，先看）

1. **两个 URL 性质不对等**。`easywithai.com/.../tripnotes-ai/` 是 AI 工具目录站的聚合页，正文只有一段话，不是产品官网；`tripplanner.ai` 是产品官网本身。证据权重不同。[S1][S2]
2. **TripNotes 名实分离，且原产品已停运**。目录页描述的 "Tripnotes.ai" 是极简工具（输入目的地 → 5 个推荐景点）；第三方评测和创始人作品集里那个被广泛报道的 Tripnotes.ai 功能丰富得多（地图+笔记+对话 Concierge），2022-07 至 2023-08 运营，2023 年底被 Dorsia 收购后关闭。**两者是否同一产品，材料无法确认，下文分开标注，不混为一谈。**[S1][S3][S4][S6][S8]
3. **TripPlanner.ai 实质是 Layla.ai 的导流前端**。官网多处把用户导向 Layla（"watch the magic happen on Layla.ai"）；宣传的"对话即时重算行程"发生在 Layla，不是 tripplanner.ai 本体。[S2]
4. **Klarna 是支付公司，不是旅游产品**。它被列入旅游竞品清单有两条有据可查的理由：① 2021-10 收购 AI 行程规划器 Inspirock（实体业务布局）；② 它的对话式购物助手/AI concierge 成为"对话式商务"范式。清单作者的具体意图无法确认，不还原。[S9][S10][S18]

---

## 一、TripNotes AI

### 交互流程
- **目录页所述版本（唯一指定 URL 的一手描述）**：进入 → 输入目的地 → 点 "Next" → 得该地 **5 个最推荐景点/建筑**。全程 3 步，页面未提地图、对话、登录等后续环节。再多的细节查不到，不脑补。【官方目录页】[S1]
- **第三方评测所述的 Tripnotes.ai（是否同一产品存疑）**：无需注册即可开始 → ①输入目的地点 Continue → ②在 Concierge 输入自然语言问题（做完整行程/推荐活动/推荐餐厅）并点 Generate，或粘贴笔记/文章 URL/TikTok 链接/邮件短信 → ③几秒内出完整行程（景点、餐厅、住宿、购物，含描述与路线地图）→ ④点条目看详情（导航、官网、社媒、评论）→ ⑤点 Share 生成链接发送。到结果约 4–5 步。【第三方实测】[S3][S5][S6][S7]

### 输入形态
- 目录页版本：**单字段表单**（一个目的地输入框 + Next 按钮）。[S1]
- 评测版本：**混合**——目的地表单 + 自然语言对话（Concierge）+ **粘贴式非结构化文本/URL**（TikTok、YouTube、Apple Notes、推文）。粘贴内容自动抽取地名并高亮。【第三方实测】[S3][S5][S6][S7]

### 输出形态
- 目录页版本：仅"5 个推荐景点"列表，**未提可编辑**。[S1]
- 评测版本：地图 + 分类清单 + 图文详情 + 社交内容关联（每个地点挂 TikTok/Instagram/评论/专家点评摘要）。Uproxx 实测首页是旋转地球、选中城市后地图打点展示推荐。【第三方实测】[S3][S5][S6]
- **就地编辑存疑**：TravelAI Hub 称"生成后无法修改/无法保存"[S3]；Wonderplan 称可通过 chat 增删活动[S4]；Show HN 官方帖称 full version 可编辑文本、自动高亮[S7]。**无法判定哪个为准，标注存疑。**

### 对话与结果面板关系
**查不到确切布局。** 第三方描述显示地图是主界面、Concierge 以对话接收问题[S5][S7]，但对话与结果（地图/笔记）是同屏分栏还是分离页面，文字材料未明确，不下结论。

### 个性化机制
- **外部数据为主**：自报 1600 万地点、3.5 亿数据点，第三方数据+自建爬虫，考虑偏好/时段/交通/地理位置。[S6][S7]
- **当前对话/粘贴内容**：Concierge 理解自然语言意图、从粘贴文本/网页/视频字幕抽地名。[S6][S7]
- **无登录画像**：公开版无需注册；full version 有 waitlist、维护笔记历史。[S7]
- "从历史交互学习"只见于第三方宣传性评测[S3]，与官方帖口径不完全一致，可信度较低。

### 可抄 / 不可抄
- **可抄 ①：粘贴即结构化。** 把用户散落的笔记、链接、TikTok 粘进来，自动抽地名、高亮、落到地图并保留原文上下文——把"用户已有的碎片"变成行程起点，比从空表单填起门槛低得多。[S6][S7]
- **可抄 ②：地点社交内容关联。** 每个地点挂 TikTok/Instagram/评论/专家摘要，决策依据不止评分数字，适合做"为什么推荐这里"的可信度层。[S3][S6]
- **不可抄：把建议做成不可改的一次性输出**（"生成后无法定制/无法保存"[S3]）。行程是反复调整的产物，一次性结果逼用户推倒重来——TripPlanner 的"可管理活动、可改期"[S9] 是反面参照。

**来源**：[S1] 目录页 · [S3] TravelAI Hub 评测 · [S4] Wonderplan 评测（2023-11）· [S5] Uproxx 实测（2023-04）· [S6] 创始人作品集 · [S7] Show HN 官方帖（2023-03）· [S8] Skift 收购/停运报道。完整清单见文末。

---

## 二、TripPlanner.ai

### 交互流程
- **官网自述（宣传）**：输入日期+目的地 → 得完整计划（航班、酒店、活动，含时间/路线/预算一屏查看）；后续在 Layla.ai 用对话持续微调。[S2]
- **第三方实测（9 步版，更新 2025-11）**：① Google 账号注册（作者强调**别跳过**，否则从头规划）→ ② Dashboard 点 "Create My First Trip" → ③选目的地和日期（可加多个，单地≤10天）→ ④选活动类型（Kid Friendly/Museums/Shopping/Historical/Outdoor Adventures/Art & Cultural/Amusement Parks，至少选1）、人数（≤10）、同行关系（friends/family/couple）→ ⑤选预算档（Cheap/Mid/High）和餐食 → ⑥（可选）先选酒店 → ⑦出结果，分 About/Itinerary/Explore Sights 三个 tab → ⑧（可选）AI Hotels Finder，可下载 PDF、分享链接。[S9]
- **另一实测入口不同**：无需登录，直接点 "New Trip"，选城市/日期/活动/人数 → 餐饮预算页（显示四口之家每天约 $700）→ 选酒店 → "Build my trip" → 出结果。与"必须注册"矛盾，可能随时间/入口变化，如实并列。【第三方实测】[S11]

### 输入形态
**纯表单/卡片式向导，不是自由对话**：多步骤选择器（目的地、日期、活动标签、人数、关系、预算、餐食）。还有"行程忙碌程度"选项。[S9][S10][S11] 对话是后置功能，名为 **Trippy** 的 chatbot[S9]；官网宣传的对话式规划在 Layla.ai。[S2]

### 输出形态
- **地图 + 分日清单 + 详情**：颜色编码地图，含景点到住宿及彼此的距离、简短描述、平均价与门票、建议时间段、每日餐饮/游玩花费估算。结果按 About/Itinerary/Explore Sights 分 tab。[S9][S10]
- **可编辑（实测有时间线差异）**：2025-11 实测称活动完全可管理、可从 Sights tab 添加、可改期、酒店可自挑[S9]；官网称换活动/调交通/升酒店后即时重算成本与路线[S2]；2024-02 实测称"找不到编辑方法，只能重新创建"[S10]。按时间线，较新的评测支持"可编辑"，早期不可编辑，可能是产品迭代。

### 对话与结果面板关系
实测中 **chat（Trippy）是独立聊天入口**，行程结果在独立的 About/Itinerary/Explore Sights tab 页里；餐饮预算、选酒店、编辑活动都在表单/结果页完成，而非在对话里。[S9][S11] 官网宣传的"边聊边改、即时重算"实际在 Layla.ai。tripplanner.ai 本体的 chat 与结果面板是否同屏一体，材料未明确，**无法确认**。[S2]

### 个性化机制
- **登录画像**：Google 账号注册保存行程数据（不注册会丢进度）。[S9]
- **当前对话**：Trippy chatbot 可做调整，但实测反馈一般——问《Suits》相关景点第一次答非所问，问"纽约最好吃的热狗"才给出带评分和官网的有效结果。[S9]
- **表单显式偏好**：活动类型、同行关系、人数、预算档、餐食直接决定推荐。[S9][S10][S11]
- **外部数据**：官网称用实时数据、Skyscanner/Booking.com/GetYourGuide 实时比价预订。[S2] 目录站另称接入 1600+ 社媒来源（Instagram Reels、TikTok）做灵感和多目的地路线优化[S12]——**仅目录站单一来源，未在官网或实测证实，待核。**

### 可抄 / 不可抄
- **可抄 ①：把"同行关系"做成结构化选项**（friends/family/couple + 人数，≤10），并利用它调整推荐强度（家庭自动留休息时间、情侣偏浪漫）——人际上下文用几个按钮就能收，比让人写一大段 prompt 高效。[S2][S9]
- **可抄 ②：可拆可改的活动块 + 即时重算**。换一个活动，费用/交通时间/附近建议同步更新，让行程是"活文档"而非一次性 PDF。[S2][S9]
- **不可抄：把餐食填入行程却落不了地。** 实测者明确填了餐饮预算，结果行程里根本没排餐食（他给 4/10 的主因）；另一实测发现餐厅像按"离得近"而非质量挑的。[S10][S11] 字段填了就必须在结果里兑现，且推荐排序把质量权重放在距离之前。

**来源**：[S2] 官网 · [S9] mspoweruser 实测（2025-11）· [S10] explore.com 实测（2024-02）· [S11] Phil Ranta 实测（4/10）· [S12] browse-ai.tools 目录（待核）。完整清单见文末。

---

## 三、Layla

### 交互流程
- **官方七步**：①聊天说想法/日期/同行人 → ②与顾问通话 → ③策划师按预算做方案 → ④一起审阅 → ⑤随意改到满意 → ⑥团队代订机票/酒店/接送/活动 → ⑦旅途中 24/7 WhatsApp 支持。【官方】[L1]
- **更细漏斗（创始人演示）**：自由描述 → 目的地候选卡（含实时机票价、天气）→ 选城市 → 文字版 rough summary → "trip"动态包（航班/租车/酒店/活动/达人视频）→ 用自然语言逐项替换。【官方演示】[L5]
- 官网另有"不找顾问、自己直接订"的分支，与全流程并行。[L1]

### 输入形态
**混合，以纯对话为主**。支持打字或语音口述（"typed or spoken"）、"brain dump"式自由输入、目的地/预算/日期；第三方实测确认首次交互是 AI 主动问一串简单直选问题，而不是甩一堆选项。【官方】[L1][L4]【第三方实测】[LT4]

### 输出形态
**卡片 + 逐日清单 + 地图 + 视频 + 文字摘要**。官方明列"Interactive maps：多城市路线、自驾路线、达人视频上地图"；航班/酒店/火车/租车实时比价[L1]。第三方实测看到景点卡含照片、FAQ、建议日期时间与详细地图；酒店卡含评分、评论、价格、房型；行程地图标出每日路线和餐厅；App 内是"精美的卡片式界面"。【第三方实测】[LT1][LT4][LT5]
**就地编辑：能**——官方与创始人演示强调"说一句话就改，其余行程自动重排"（例："换成海边有健身房和 spa 的 ins 风酒店"）[L1][L5]；第三方也验证了加站、换酒店后能重新生成。[LT3][LT4]

### 对话与结果面板关系
**对话驱动、结果同屏更新的一体化为主**。对话是唯一入口，改一句话即刷新行程/卡片/地图，不是"聊完再去另一个页面找结果"。【官方演示】[L5]【第三方实测】[LT1][LT5]
**但有一道裂缝**：第三方实测指出桌面端"从 Layla 结果复制粘贴又丑又别扭"，PDF 导出要升级到更贵订阅才给——结果区与可携带文本之间并未打通，别照抄。[LT1]

### 个性化机制
- **当前对话**：日期、预算、同行人、风格靠追问补齐；"改任何一项，其余跟着变"。[L1][L4]
- **外部数据**：接入 Skyscanner 机票、Booking.com 酒店、Viator/GetYourGuide 活动，约 1500 位达人视频；路由/房价预测/酒店推荐是自研模型而非纯 LLM。【官方】[L5][L1]
- **登录画像**：不登录可聊，注册后才能保存行程。[LT3] 顾问通话会了解旅行风格与优先级，属人工采集的长期画像。[L1]
- **外部推断（有争议）**：一位实测者被 AI 直接猜"我猜你来自纽约"，她明确表示不喜欢这种"没给信息却过度个性化"的惊悚感。可能来自 IP 地理定位，原文未证实，**不要当结论**。【第三方实测】[LT4]

### 可抄 / 不可抄
- **可抄 ①："自然语言就地改写整个结构化结果"**。用户说人话改一个酒店，路线、日程、价格一起重算，而不是让用户回到表单——对话产品最该抄的核心交互，Layla 把它做成主流程而非彩蛋。[L1][L5]【第三方实测佐证】[LT4][LT5]
- **可抄 ②：漏斗前置 + 渐进收敛**。先用目的地候选卡（带实时价和天气）帮用户做"去哪个国家"这个第一决策，再逐层收到城市、逐日行程。比一上来要求填完整表单更符合真实决策顺序。[L5]
- **不可抄：把未经核实的细节说得非常确定**。实测中出现"木屋有 spa"（细读才发现没有，AI 自己认错）、teamLab 排了两天且不提醒提前订票、按 day1/day2 而非日历日期排导致南段行程全错、创始人自曝把德国用户叫"Hans"。旅行是履约型消费，错误价格的代价比"聊得开心"高得多——**抄它的人机分工（AI 草稿+人工核验）可以，抄它的自信度不行**。【第三方实测】[LT4][LT1]【官方自曝】[L5]

**补充事实（非 6 项，但与定位相关）**：第三方实测文提到 Expedia 于 2026 年 7 月收购 Layla。**仅见第三方，官方页未见声明，待一手信源再核。**[LT1]
价格口径不一致，别引用错：官网/llms.txt 说"规划免费、无订阅"，官方博客说"$9.99/月或 $49.99/年 + PriceLock"，第三方实测普遍报"$49.95/年"。[L1][L3][L6][LT1]

**来源**：[L1] layla.ai/about · [L3] llms.txt · [L4] Google Play 官方描述 · [L5] 创始人 Demo Day 演示 · [L6] 官方博客 · [LT1] Practical Globetrotters 实测 · [LT3] Just Gone Wandering 实测 · [LT4] cxfoundation 实测 · [LT5] 中文实测。完整清单见文末。

---

## 四、Klarna（支付公司，非旅游产品）

### 为什么被列入旅游竞品清单
先澄清：Klarna 是"先买后付"的支付/购物公司，**不是旅游产品**。有据可查的理由两条：
1. **真实收购过旅游规划产品（最硬的理由）**：2021-10 收购 AI 行程规划器 **Inspirock**——用 AI + 本地专业知识生成个性化行程，官方目标是补上"订完机票酒店之后，用户到底玩什么"的空白，并让用户用 BNPL 买景点门票、把 25 万零售伙伴接到旅行场景。这不是交互形态类比，是实体业务布局。【第三方报道】[K8][K9][K11]
2. **AI assistant 交互形态成为范式**：2024 年起 chat-based 购物助手（对话搜商品、比价、看评论、直接买）和 2026 年 AI concierge（在 WhatsApp/iMessage 上代订餐厅、代处理退货、起草邮件待批准）被反复当作"对话式商务/代理式助手"标杆。【官方】[K7][K9]【第三方报道】[K10]

任务书原猜测"很可能是 AI assistant 交互形态"**对但只说对一半**：交互形态是传播最广的原因，但清单若由旅游行业的人编，2021 年 Inspirock 收购更可能是直接依据。**清单作者的具体意图无法确认**，以上只是有据可查的客观事实。

### 交互流程
- **购物助手**：App 右上角 chat 图标 → 输入框+预置 prompt（"比较 Nike 和 Adidas"）→ 自由描述需求 → AI 追问/点选品牌 → 出商品卡、价格走势图、评论摘要 → App 内直接买。【官方】[K7]【第三方实测】[KT7]
- **客服 bot**：泛问或从某笔具体订单发起 → 约 20 秒出答案 → 答案注入订单价格/商家/购买日期 → 越界话题转人工。【第三方实测】[KT6]
- **2026 concierge**：候补名单 → 收邀请 → 聊天里发第一句话，代办订位/购物/整理收据，付款必须人工授权。【官方】[K9]

### 输入形态
**混合——对话为主 + 卡片/按钮点选 + 并列独立浏览区**。自由文本和预置 prompt，也有"点选相似品牌"的结构化输入；实测明确提到可点 **Shop** 标签在助手旁边浏览比价。【官方】[K7]【第三方实测】[KT7]

### 输出形态
**商品卡/比价清单 + 价格历史折线图 + 评论摘要 + 优缺点总结 + 关键参数**，并能在对话里就地购买（审批后付款）。【官方】[K7][K9]【第三方实测】[KT7]（亲测价格图与 4.7/5、379 条评论，去官网核对无误）

### 对话与结果面板关系
**并列分离**。实测描述是聊天面板与 Shop 浏览区"alongside"（并排）而非同一 pane；但价格图、商品卡又在对话流里就地出现。可概括为"聊天 + 独立浏览区并列，结果卡内联在对话中"。【第三方实测】[KT7]（官方 K7 只说"single chat interface"，与实测口径略有出入，以实测为准）

### 个性化机制
- **登录画像（最强）**：官方明说基于购物偏好推荐——"是否每年同一时间买某类东西？更喜欢白鞋还是彩鞋？"等。【官方】[K7]
- **当前对话**：追问式澄清持续收窄。【第三方实测】[KT7]
- **外部数据**：接入 560 万商品的价格数据库、库存、配送、返现、评论、价格历史。【官方】[K7]
- **一方交易数据注入回答**：客服 bot 会把订单价格、商家、购买日期编织进回复，这是它"像懂我"的关键，而不是靠性格设定。【第三方实测】[KT6]

### 可抄 / 不可抄
- **可抄 ①：把一方数据注入对话上下文**。别做"你好，我是旅行助手，请问想去哪"，而要让助手开口就带着"你上次去的京都、你会员等级、你这张未用的券"。订单上下文注入被实测者评价为"beyond simple search"的关键差异——旅游产品对应的是已有订单/常旅客/历史行程。[KT6]
- **可抄 ②："shared control"审批闸门**。助手可以找、可以订、可以起草，但付款/提交前必须人点确认。【官方】[K9]【第三方报道】[K10] 行业侧佐证：只有 2% 用户愿意让 AI 无人监督全权订旅行，用户偏好"AI 订、人批准"。[LT4]
- **不可抄：为防守而把助手锁进白名单、逐字复述政策**。实测者 15 分钟无法诱出幻觉，但也直言这更像"写得好、路由精准的 L1 客服"，越界即甩人工，不是"颠覆性"。旅游对话产品若照搬这种强约束，会直接杀死"开放式灵感探索"这个旅行场景最需要的部分。【第三方实测】[KT6] 另一别抄的实测 bug：反复推荐缺货商品[KT7]——对应旅游就是"推荐了订不到的酒店"。

### 对旅游对话产品的借鉴意义（归纳）
- **闭环**：灵感 → 比价 → 决策 → 购买在同一会话完成，中间用人工授权做安全阀，这是 Klarna 从支付侧反推出来的路径，正好是旅游对话产品"聊完就走"缺失的一环。[K7][K9]
- **形态载体可以外挂**：2026 年助手直接跑在 WhatsApp/iMessage 上，Layla 的旅途支持也在 WhatsApp——旅行场景的"陪聊+变更"天然适合消息平台，不必都困在自己 App 里。[K9][L1]
- **但边界要学反向教训**：Klarna 的核心护城河是交易数据+比价库，不是人格化闲聊；旅游产品若没有实时库存/价格/订单这类硬数据，抄它的对话壳只会得到一个更会说话的搜索引擎。【基于 KT6/KT7 的对比推断】

**来源**：[K7] Klarna 官方（2024-09）· [K9] Klarna investors（2026-11 AI concierge）· [K8] TechCrunch 收购 Inspirock · [KT6] Pragmatic Engineer 客服 bot 实测 · [KT7] CNET/Yahoo 实拍实测 · [K10] Payments Dive。完整清单见文末。

---

## 五、横向对照与本项目的取舍

| 产品 | 输入形态 | 对话与结果 | 就地编辑 | 个性化主力 |
|---|---|---|---|---|
| TripNotes（目录版） | 单字段表单 | 无对话 | 未提 | — |
| TripNotes（评测版，存疑） | 混合（表单+对话+粘贴） | 地图主界面，布局不明 | 存疑 | 外部数据+粘贴内容 |
| TripPlanner.ai | 表单向导（对话后置） | 分离（chat 独立） | 可编辑（新评测） | 登录画像+表单显式偏好 |
| Layla | 对话为主（含语音） | 一体化同屏 | 可编辑（自然语言改） | 当前对话+外部数据+顾问 |
| Klarna | 对话+卡片+并列浏览 | 并列分离，结果卡内联 | 就地购买需审批 | 登录画像+一方交易数据 |

**对本项目的三点取舍**（结合 `wtt_ux-refactor/PLAN.md` 的裁决规则：冲突时以有效推荐为准）：
1. **Layla 的"自然语言就地改整个结构化结果"最值得抄**，且与我们探针已验的「选点→串线」形态一致：改一个点，路线/时间/理由同步重算。
2. **Klarna 的"一方数据注入对话"是远期方向**，本项目当前只有官方名录+人流数据，没有用户历史订单/常旅客数据——在补数据之前，抄它的对话壳是空架子。
3. **共同的坑：把不确定性说得确定**。Layla 的 spa 幻觉、TripPlanner 的餐食不落地、Klarna 的缺货推荐，都是"字段填了/话说了但结果兑现不了"。本项目刚修的 `sentence 与卡片一致性`、`round(score,3)` 压缩、配图署名，正是同一类纪律——**界面越精美，内容错的伤害越大**。

---

## 来源清单（完整）

### TripNotes AI
- [S1] https://easywithai.com/ai-travel-planners/tripnotes-ai/ — 目录页（指定 URL，仅一段话）
- [S2] https://tripplanner.ai/ — TripPlanner 官网（宣传）
- [S3] https://www.travelaihub.com/tripnotes-ai-review-2023/ — 第三方评测，宣传性强、内部有矛盾
- [S4] https://wonderplan.ai/blog/tripnotes-review-does-it-simplify-travel-planning — 第三方评测，2023-11-08
- [S5] https://uproxx.com/life/how-to-use-ai-to-plan-a-vacation-tripnotes/ — 第三方实测（LA），2023-04-18
- [S6] https://matthewer.com/tripnotes — 创始人作品集页（官方自述+演示视频）
- [S7] https://news.ycombinator.com/item?id=35276431 — Show HN 官方团队帖，2023-03-23
- [S8] https://skift.com/2024/01/02/tripnotes-a-buzzy-chatgpt-based-trip-planner-was-acquired-and-shut-down/ — 收购/停运报道
- [S9] https://mspoweruser.com/trip-planner-ai-review/ — 第三方实测（9 步详解），更新 2025-11-07
- [S10] https://www.explore.com/1512545/let-ai-artificial-intelligence-plan-vacation/ — 第三方实测对比，2024-02-13
- [S11] https://www.linkedin.com/pulse/trip-planner-ai-itineraries-phil-ranta-l0lle — 第三方实测（4/10）
- [S12] https://www.browse-ai.tools/tool/trip-planner-ai — 目录站，2025-07-05（社媒灵感说法待核）

### Layla
- [L1] https://layla.ai/about — 七步流程、实时比价/互动地图/16 语言、FAQ
- [L3] https://layla.ai/llms.txt — 产品与页面索引、human-in-the-loop 自述
- [L4] https://play.google.com/store/apps/details?hl=en_US&id=ai.layla.android.app — 官方应用描述
- [L5] https://www.youtube.com/watch?v=-MPNqgM8b50 — 创始人 Demo Day 演示
- [L6] https://layla.ai/blog/news-and-tips/app-that-plans-trips-and-suggests-hotels — 官方博客（订阅价）
- [LT1] https://practicalglobetrotters.substack.com/p/we-tested-4-ai-travel-services-to — 日本行实测四款
- [LT3] https://justgonewandering.com/ai-travel-planning-chatgpt-layla-guidegeek/ — 英国西南两周实测
- [LT4] https://cxfoundation.com/blog/vacations-by-ai — Layla 实测（spa 幻觉、猜纽约）
- [LT5] https://jindage.com/archives/4773 — 中文实测（卡片式界面）

### Klarna
- [K7] https://www.klarna.com/international/press/shopping-made-smarter-klarna-adds-more-ai-features-to-its-assistant-powered-by-openai/ — 2024-09-19 购物助手
- [K8] https://techcrunch.com/2021/10/22/klarna-travel-inspirock-acquisition/ — 收购 Inspirock
- [K9] https://investors.klarna.com/News--Events/news/news-details/2026/From-returns-to-restaurant-bookings-Klarnas-AI-assistant-finds-the-best-product--price-buys-it-for-you-and-you-dont-pay-until-it-arrives-2026-AsJ__j3bx3/default.aspx — 2026-11-17 AI concierge
- [K10] https://www.paymentsdive.com/news/klarna-launches-ai-concierge/875033/ — AI concierge 报道
- [K11] https://www.crowdfundinsider.com/2021/10/182023-fintech-klarna-acquires-inspirock-bringing-travel-planning-to-its-consumers/ — 收购背景
- [KT6] https://blog.pragmaticengineer.com/klarnas-ai-chatbot/ — 客服 bot 实测
- [KT7] https://tech.yahoo.com/ai/articles/saved-hundreds-dollars-klarnas-ai-130004179.html — CNET 实拍实测

---

## 未查到 / 未采信（明确留白）

- TripNotes 对话与结果面板的确切布局；目录页版本是否支持编辑/保存
- TripNotes 目录版与评测版是否同一产品
- TripPlanner.ai 本体 chat 与结果面板是否一体
- [S12][S14] 的社媒灵感与 Expedia 归属
- Layla 具体 UI 布局的官方截图描述；Klarna Inspirock 技术当前是否仍在服役
- 那份旅游竞品清单作者的具体意图
- Expedia 收购 Layla 仅见第三方 [LT1]，官方页未见声明，待一手信源再核

以上均未用推测填充。
