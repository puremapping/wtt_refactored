以下是将隐式链接替换为显式URL后的竞品分析、已有实现与学术支持清单。

# Where to Travel 竞品分析、已有实现与学术支持
**文档版本：** V1.2 附录（链接修正版）
**用途：** 课程作业答辩支撑材料

## 一、商业竞品分析

### 1.1 AI旅行助手 / 行程规划类
**同程 DeepTrip**

同程旅行自研的旅行智能体，DeepTrip 2.0 支持17种语言交互，可结合当地文化提供个性化服务，并已引入河南文旅旗舰馆作为智能行程规划助手。

链接：[https://www.wenlvpai.com](https://www.wenlvpai.com/)

**飞猪帮帮**

基于阿里Qwen模型家族，具备Agentic能力，可代用户处理预订、改签、值机选座、开票报销等复杂任务。用户可将社交平台攻略链接或截图发给AI，自动梳理出含预算的规划，支持一键加购。

链接：[https://paper.people.com.cn](https://paper.people.com.cn/)

**马蜂窝 AI 旅行助手**

2026年4月上线16个国家级目的地服务，覆盖行程规划、实时翻译、AI订餐厅。目的地AI智能体“梵小非”为贵州省铜仁市量身打造，融合人工智能、大数据与知识图谱技术，提供从行程规划、语音交互导航到主题AI播客的全链路智能化陪伴。

链接：[https://www.wenlvpai.com](https://www.wenlvpai.com/)

**评测格局**

2025年11月发布的国内首份《AI旅行助手评价体系》显示，飞猪问一问以724.92分（满分900分）居首，程心AI、支付宝出行助手紧随其后，小红书点点、携程问道、腾讯元宝、豆包、DeepSeek位列其后。该体系由北京第二外国语学院数字文旅研究中心基于可用性、易用性、个性化、安全性、流畅性五大维度构建。

链接：[https://www.jinantimes.com.cn](https://www.jinantimes.com.cn/)

### 1.2 官方文旅数据聚合平台（B端方向）
**浙江省文旅行业高质量数据集共创平台**

由浙江省文化广电和旅游厅指导，联合浙江大学、浙江旅游职业学院、省旅投集团等单位共同推出，内置景区景点、文化遗产、酒店住宿、餐饮美食等多领域知识资产，形成知识图谱构建等能力底座。

链接：[https://www.mct.gov.cn](https://www.mct.gov.cn/)

**“活力广东”智慧文旅服务平台**

由广东省文化和旅游厅指导、旅游控股集团建设运营，定位为广东文旅宣传推广总窗口、游客服务总入口、文旅消费服务新引擎。已上线1.0版本，包含“粤玩日历”“品质粤游”“AI服务”“地图导览”等功能，并可实现酒店、景区一键订。

链接：[https://gzw.gd.gov.cn](https://gzw.gd.gov.cn/)

**湖北省“文体旅+”综合服务平台**

由湖北数字文旅集团承建，整合各行业资源库、项目库、产品库，贯通乡村振兴、工业赋能、城镇更新、体旅融合等十二大业态，实现资源推介、攻略查询、预约预订等一站式数字化服务。湖北省还推出了全国首个省级常态化票根经济数字平台“湖北有礼”，上线一年累计上传票根超136万张，直接及间接带动消费突破2亿元。

链接：[https://www.hubei.gov.cn](https://www.hubei.gov.cn/)

## 二、学术与原型层面

### 2.1 动机驱动推荐
**Nomad（GitHub开源原型）**

Nomad是一个AI驱动的旅行决策引擎，**反转传统旅行规划**——用户不是先选择目的地，而是描述他们的约束、偏好和旅行的原因（why to travel）。使用Gemini推理用户的约束条件，决定最佳旅行方案。核心理念是“Describe your life, not a destination”。

链接：[https://github.com/hossamasr/MLH-HacksForHackers](https://github.com/hossamasr/MLH-HacksForHackers)

**Black Tomato Feelings Engine**

Black Tomato推出的AI驱动“Feelings Engine”，邀请旅行者回答“你想感受什么？”，利用专有研究和客户数据，引导旅行者前往可能从未考虑过的目的地。平台使用Claude AI，融合了20年专有数据。

链接：[https://www.blacktomato.com](https://www.blacktomato.com/)

**Wayfarer**

Wayfarer的“Live Action to Memory Pipeline”把旅行中的每一个动作同时记录为 trip signal（行程信号）和 traveller memory event（旅客记忆事件）。每次节点执行都记录为 `AgentGraphEventRecord`，带有序号。系统使用LangGraph进行多Agent编排，Redis进行persona-place相似度匹配，贝叶斯推理进行persona演化。

链接：[https://blog.gopenai.com](https://blog.gopenai.com/)

### 2.2 旅游事件知识图谱（TEKG）
清华大学的硕士论文提出了“旅游事件知识图谱”（Travel Event Knowledge Graph, TEKG）的概念，明确指出其“侧重于描述旅游事件中游客的行为与体验”，不同于通用知识图谱侧重描述景点的静态知识。该研究以游记作为旅游事件，将游记设为主要实体而非景点，实验证明TEKG应用于推荐模型中可为推荐准确率带来**平均2%的提升**。

链接：[https://newetds.lib.tsinghua.edu.cn](https://newetds.lib.tsinghua.edu.cn/)

**Event-centric Tourism Knowledge Graph (ETKG) - 海南案例**

该研究提出了以事件为中心的旅游知识图谱（ETKG），以旅行中的活动为中心，将游客轨迹作为载体，建模游客行程的时空动态。数据集包含86,977个事件（50.61%具有完整时间、活动、位置信息）和7,132段旅程。GitHub上有开源实现。

链接：[https://github.com/xcwujie123/Hainan_KG](https://github.com/xcwujie123/Hainan_KG)

### 2.3 游记事件提取
**基于50万篇携程游记的顺承事件图谱**

有开源项目基于**50万篇携程出行游记**构建了顺承事件图谱，包含交通工具子图谱、订酒店吃饭事件图谱等。处理流程包括：输入游记文本→长句切分→基于顺承关系模板进行顺承前后部分提取→构建事件图谱。

链接：[https://github.com/fangjiataizi/Tourist_KG](https://github.com/fangjiataizi/Tourist_KG)

**基于规则的行程链提取效果**

有研究对1.7万篇蚂蜂窝游记进行实验，基于句法规则的行程链提取方法与人工识别的真实行程链相似度达到**86.14%**，高于BERT-BiLSTM-CasRel深度学习模型的83.1%，且无需大量数据标注。后续研究（基于DeepSeek模型）在蚂蜂窝、去哪儿、携程三平台2,834篇游记上，行程链平均相似度达到**94.13%**。

链接：[https://www.cqvip.com](https://www.cqvip.com/)

### 2.4 LLM 旅游事件抽取
**TIME-UIE 模型**

该研究提出了TIME（Tourism, Individuals, Moments, Events）模型，将人物相关信息组织为四个主要维度：属性、关系、事件及其与旅游资源的关联。实验结果表明，TIME-UIE在解读历史人物之间的复杂关系方面比基线模型提升**26.2%**，在抽取事件三元组方面提升**11.1%**。发表于 Expert Systems with Applications。

链接：[https://www.sciencedirect.com](https://www.sciencedirect.com/)

### 2.5 可解释推荐与信任
**对话式推荐系统的可解释性与信任**

有研究探讨了基于AI的对话式推荐系统（CRS）在旅行规划中的采用意图驱动因素，发现CRS的**可理解性和自然性**对游客的**认知信任**有显著正向影响，而**个性化、可解释性和自然性**对游客的**情感信任**有显著正向影响。认知信任和情感信任均对采用意图有显著正向影响。发表于 Discover Artificial Intelligence。

链接：[https://link.springer.com](https://link.springer.com/)

**可解释景点推荐（知识图谱+协同过滤）**

一篇针对中国河南省的案例研究提出了融合知识图谱和协同过滤的可解释景点推荐方法，实验结果显示该方法达到**93.8%的准确率**，在保证推荐可解释性的同时实现了智能有效的景点推荐。发表于 Transactions in GIS。

链接：[https://onlinelibrary.wiley.com](https://onlinelibrary.wiley.com/)

### 2.6 旅程预演的理论支撑
**“预期怀旧”（Anticipated Nostalgia）与旅行决策**

该研究首次在旅游研究中引入“预期怀旧”概念，揭示了双向心理时间旅行过程及其对游客决策的影响。研究发现，预期怀旧作为一种认知启发式机制，能够增强旅行冲动、塑造前瞻性记忆并影响主动记忆行为。旅游通常包含时间维度（预订与出行之间的时间差），导致对未来旅程及回家后积极结果的想象和期待。这一理论直接支撑了Where to Travel的“旅程预演”功能设计。发表于 Annals of Tourism Research。

链接：[https://www.sciencedirect.com](https://www.sciencedirect.com/)

## 三、关键数据源与API

| 数据源 | 类型 | 显式链接 |
| --- | --- | --- |
| 北京市公共数据开放平台 | 景区名录、旅行社信息 | https://data.beijing.gov.cn |
| VisitBeijing MCP Server | 216个A级景区实时人流 | https://github.com/solution9th/visitbeijing-mcp |
| 高德地图 API | 地理编码、路径规划、POI检索 | https://lbs.amap.com |
| 和风天气 API | 实时天气 | https://dev.qweather.com |
| 浙江省文旅高质量数据集平台 | 文旅知识图谱 | https://www.mct.gov.cn |
| “活力广东”智慧文旅平台 | 省级文旅服务 | https://gzw.gd.gov.cn |

## 四、竞品定位总结

| 维度 | OTA系（同程/飞猪） | 官方文旅平台（浙江/广东/湖北） | 学术原型（Nomad/Black Tomato） | Where to Travel |
| --- | --- | --- | --- | --- |
| 核心逻辑 | 评价+交易驱动 | 数据整合+服务入口 | 动机驱动 | 动机驱动+多源交叉验证 |
| 个性化 | 基于历史行为 | 弱 | 基于约束推理 | 基于旅行价值观+本次动机 |
| 可解释性 | 弱 | 无 | 中 | 多源来源+置信度+行为反馈 |
| 官方联动 | 商户入驻 | 政府主导 | 无 | 文旅局认证+内容发布+数据看板 |
| 数据资产 | 订单+评价 | 政府数据 | 无 | Travelling事件+游记事件 |
| 预演能力 | 无 | VR预览（部分） | 无 | 决策预演（时间线+风险+备选） |
| 技术深度 | 商业级 | 数据基础设施 | 原型验证 | RAG+动机映射+事件图谱 |
**答辩核心话术：**

> “AI行程规划赛道已经很拥挤，但现有产品解决的是‘怎么去’。我们解决的是‘为什么去’，以及‘去了会怎样’。这不是功能差异，是交互范式的差异。”
>
>

> “我们不只记录你去过哪里，我们记录你为什么去、实际体验了什么、以及你的期待和现实之间的差距。每一次旅行都成为一个可复用的数据资产。”
>
>
