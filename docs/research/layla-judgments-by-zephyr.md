<!-- 格式：PMS 文档集格式 v1.0 -->
# 阿哲亲测 Layla 的设计判断

> 记录日期：2026-11-21
> 来源：**阿哲本人亲自体验 layla.ai 后的判断**（不是子代理实抓，不是小霁推导）
> 性质：产品判断与结论。与本目录 `competitor-interaction-review.md`（子代理实抓的客观交互拆解）分开存——
> 那份记「Layla 是什么样」，这份记「阿哲认为其中什么值得抄、背后的道理是什么」。
> 署名约定：每条下「判断」= 阿哲原话要点；「依据 / 推论」= 文中明确标出，不混进判断。

---

## 一、并列提问的信息收集 + 右侧栏动态进度清单

### 判断（阿哲）

**观察到的事实**：生成行程这个动作前，Layla 在右侧栏列了**清晰的必要信息收集清单，动态更新**，用户能实时查看自己的信息完善进度。对比我们主项目现在的状态：用户不知道自己还要被提问多久。

**并列提问机制**：
- Layla 假设需要收集五个问题的信息，会先把**逻辑上靠前的三个问题**在一条消息里用三行问句并列提出。
- 「靠前」的判断依据是**大前提与小前提的先后关系**——问「你去哪」一定排在问「你什么时候去」前面。
- 为什么一次问三个（而不是只问一个）：因为**一些问题在逻辑上没有明确先后关系**。例：「你和谁一起去」与「你从哪里出发」，先问哪个都可以。
- 用户可以**每轮只回答一个问题**；未回答的问题会被 Layla 保留，继续进入下一轮的并列提问中。

**并列提问的设计用意**：避免固定、模板化的提问流程，给用户更自由的思路组织顺序。有的人就是喜欢先考虑「跟谁一起去」，定下来之后才考虑「从哪里出发」——因为两个人可能要先碰面再出发。如果一轮只问一个问题，就等于**定死了事项决定的先后顺序**，没有给用户自由。

**选项提示的配套设计**：因为是并列提问，Layla 的选项提示也做了三个，分别对应三个问题各一个推荐答案。用意是——如果每个问题都给三个预设答案，用户会面临九个选项，**达到米勒定律的上限**。

**结论（阿哲原话要点）**：用并列提问来实现「决定顺序自由」，与用多选项来实现「问题选项自由」，之间存在**需要平衡的矛盾**。

### 依据 / 推论（小霁标注，非阿哲原话）

- 米勒定律（Miller 1956）：工作记忆一次约能处理 7±2 个组块。阿哲说的「九个选项达到上限」指此。此处三个问题 × 各一推荐 = 3 个选项，规避了 3×3=9 的过载。
- 待核（未验证）：Layla 实际是否严格按「三个」并列、三个未答如何保留进下一轮——这是阿哲体验所见，未做逐轮截图留证。若要落到本项目设计，需再实测确认交互细节。

---

## 二、trip 卡片的元素级细分与独立评价

### 判断（阿哲）

**观察到的事实**：Layla 最后的行程卡生成在**右侧栏**，与我们主项目设计一致，但功能明显更完善。

**trip 卡片的结构**：分为若干细分板块——
- Itinerary（时间顺序的行程安排）
- Routes（基于地图的路线图）
- Transport（交通表）
- Stays（住宿）
- Activities（活动，即有什么好玩的）

**交互细节**：
- 每个条目点击后打开**详情页**，看完可点 **change** 去替换。
- 因为层级很多，trip 做了**面包屑导航**。

**细分的好处（阿哲的判断）**：
1. 用户在**评价**时，不需要对着整块的大 trip 做整体评价，而可以对里面元素**独立评价**——比如「哪个航班经常晚点」「哪个宾馆卫生很好」「哪个活动很好玩」。
2. trip 的**组合多样性**因此提高——因为它的组合材料是一些**有独立评分的元素**，而不是只照着一个高分 trip 抄过来。

### 依据 / 推论（小霁标注，非阿哲原话）

- 待落地映射：本项目刚做的「先选点、后串线」中，SpotCandidate 是单个景点卡、ItineraryCard 是串线结果。阿哲这条判断指向的是——**每个被选中的点应该保留为可独立评价/可替换的元素**，而不是串线后被吸收进一张整体卡片就失去个体性。这是对现有探针设计的直接启示，但这条映射是小霁推的，不是阿哲说的。
- 待核（未验证）：Layla 各板块的详情页字段、change 的替换逻辑、面包屑的具体层级——阿哲体验所见，未逐项截图。

---

## 三、补充调研：行程开始后的调整与导览（子代理实抓，非阿哲判断）

> 来源：2026-11-21 子代理 web_search + web_extract 实抓。**这一节是事实调研，不是阿哲的判断，也不是小霁的推论。**
> 证据分层：`【官方】`layla.ai 自有页面 / 官方应用商店描述与版本记录；`【第三方】`独立媒体实测、竞品对比。查不到一律标注。

### 问题 A：到目的地后临时改 trip

**结论：部分支持，但形态是「App 内手动编辑 + 出问题找人工」，不是「到了当地 AI 自动实时改」。**

【官方】
- App 内有「就地编辑行程各部件」：Google Play 官方描述（更新 2026-11-19）"CHANGE ANYTHING — Swap a hotel, move a day, add a safari or a cooking class. Layla reworks the rest of the trip around it."；Apple App Store 版本记录 1.0.36「Edit your trip in place: transport, hotels, activities, car rental, airport transfer」、1.0.41「Edit any part of a trip from the trip page」。**但官方没标注为「旅途中专用」，也没承诺实时重订已确认的供应商订单。**
- 官网七步流程第 5 步「Make it yours — Change anything until it feels right」在第 6 步「We book it」**之前**，属预订前阶段。
- 行程真正开始后的改动走**人工**：FAQ「24/7 support throughout your travels if something unexpected happens… contact our team… including WhatsApp, for help with unexpected changes or problems」。
- 《Travel Advisor Service Terms》（更新 2026-10-09）§11：旅客可请求更改已确认预订，Layla 评估可行性，可能受供应商可用性、改期费、价差、行政费约束，实施前披露费用；不可行/供应商禁止时无义务执行。§18「Urgent in-trip matters will be prioritised for operational support」。
- 官方博客自述 AI 在实时中断（罢工、台风、临时闭馆）上"often a beat behind"，建议用户自己查航司 App / 旅游局 / 新闻。

【第三方】
- **未查到**任何「到目的地后按 GPS 位置自动重排当天行程」「实时交通/闭馆感知」的独立实测或官方承诺。Mashable 2024 实测的自动定位到 Austin 推荐 "near me" 属**规划期**位置推荐，不是旅途中实时更新。
- Zenvoya（竞品自产、明确非实测、有偏向）称改已预订项目需回第三方供应商网站，与官方 §11 口径不一致，**未独立验证，不采信为事实**。

### 问题 B：是否提供旅游导览 / 陪伴

**结论：不是导览/陪伴产品。** 24/7 WhatsApp 是**真人旅行顾问的售后与应急通道**，不是 AI 导游。

【官方】
- WhatsApp 上由**真人旅行顾问**对接：官网首页摆出具名顾问 Carla/Aleks/Erol，文案 "Your travel advisor … stays with you on WhatsApp"；FAQ "real people to guide and support you"。
- 底层是混合的（条款 §2：AI + 真人顾问 + 供应商系统；§29：AI 用于研究、行程开发、推荐），但**对客承诺的关系是「你的旅行顾问」这个人**。**官方没有公布一个 WhatsApp 号码/AI bot 让你随便问当地问题。**
- 具体做什么：处理意外变更/问题、协助改单（§11）、服务差错补救（§15）、困难时信息协助（§16：健康服务/当地政府/领事/替代交通/远程通信）、接收投诉并升级（§18）。
- **不是什么**：官方 nowhere 把它描述成逐站讲解/语音导览/现场 step-by-step 陪伴。about 页「What I do」四项（实时比价、会变的计划、交互地图、16 语言聊天）全是**规划期**能力。App Store v1.0.36「Book a call with a travel advisor from the chat」是出发前通话预约。

【第三方】
- 多篇第三方把「落地后随问随答」的角色归给 **GuideGeek**，不是 Layla：Just Gone Wandering 实测用 WhatsApp 向 GuideGeek 问「where can I find the schedules for buses and trains」，称其适合 "on-the-trip questions"；NewzV 评测（明确非实测）把 GuideGeek 列为 "Best AI Trip Planner for When You're Already There"（cheap dinner near me right now / how do I get to Sintra from here / is this neighbourhood safe at 11pm）。对 Layla 的实测均仅限**行程生成**。
- **未查到** Layla 任何官方或第三方关于目的地导览、逐站讲解、当地实时推荐、AI 导游、WhatsApp 现场问答机器人的产品描述或实测。

### 来源

【官方】https://layla.ai/about · https://layla.ai/faq · https://layla.ai/ · https://layla.ai/terms/human-expert · https://play.google.com/store/apps/details?hl=en_US&id=ai.layla.android.app · https://apps.apple.com/us/app/layla-ai-trip-planner/id6758730467 · https://layla.ai/blog/news-and-tips/how-to-plan-a-trip-with-ai-2026 · https://layla.ai/plan/ai-travel-agent

【第三方】https://justgonewandering.com/ai-travel-planning-chatgpt-layla-guidegeek/ · https://monkeyeatingmango.com/blog/layla-alternatives-2026/ · https://zenvoya.ai/blog/best-ai-travel-planners-2026 · https://newzv.com/productivity-ai/best-free-ai-trip-planner/ · https://me.mashable.com/tech/42988/4-ai-travel-concierge-services-thatll-help-plan-your-next-vacation

**说明**：搜索 help.layla.ai 帮助中心直接命中为空，相关内容以 layla.ai/faq 与 about 页为准。竞品主张与官方条款冲突处已逐条标明，未把营销措辞当实测结论。
