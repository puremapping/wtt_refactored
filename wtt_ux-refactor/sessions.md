<!-- 格式：PMS 文档集格式 v1.0 -->

# wtt_ux-refactor — session 台账

> 维护规则：接手即登记、收工即更新、按时间倒序

## 20261029_104842_8aae3c

- **时间**：2026-10-29 10:48 → 2026-10-29 （持续中）
- **模型 / 来源**：group/economy-ctxl / tui

### 做了什么

**1. 建子项目 wtt_ux-refactor**

双线并行（阿哲 2026-10-29 定）：本线负责交互设计重构；另开 wtt_miniapp 线负责平台接入小程序。按 PMS 子项目规范：建在 wtt_refactored 内部、共用父仓库 git、只放文档。

**2. P1 调研完成**

- 留人机制：对话长度不是留人指标（ChatGPT 中位 3 条、旅游 2-3 轮）；真杠杆在会话之间（Mental 回访 92.6%）；记忆要「改写+有功能」引用
- 动机挖掘：选择过载（阿里 160 万人：2 个最优）、提问轮数控 5-8 轮、无「以搞清需求为核心」的旅游产品先例
- 竞品：交互天花板=对话+可编辑行程卡；动机挖掘全是 slogan；生成完即断头是普遍失败模式
- 等待过程：显示真实工作步骤让人愿多等 50 秒（Buell & Norton 2011，旅游场景）
- SSE 方案：SSE 优于 WebSocket（绕开限流/鉴权会重复 BUG-7）；已验证原型

**3. 推荐评估两项补充调研**

- eval-methods.md：K=5 时 Precision/MAP/MRR 全失效（实测复现，仅 NDCG 区分）；Booking 离线与业务 r=-0.1
- quality-and-feasibility：高德可在线读评分但禁存储（协议 3.5）；5A 是便利性认证非价值认证；正解是 TOPTW 非 TSP

**4. P2 诊断：跨画像 Top-5 Jaccard**

原假设「等级塌缩导致推荐对动机不敏感」**被推翻**（大部分组合 Jaccard=0.0）。但发现三个更实际的问题，详见 PLAN.md：
① 分数压缩到 0.005 级 ② 排除项一刀切误伤（故宫「恢复/逃离」下 0.099）
③ 「美食/感官」与「文化/沉浸」完全相同（规则表缺美食信号）。
脚本 `jaccard_diag.py` 已入库，可复现。

**5. 优先级澄清（阿哲 2026-10-29 晚）**

「有效推荐」与「优化使用体验」是**两条并行都要抓的线**，优先只在冲突时裁决，不是串行。此前我误读为「先做完推荐再做体验」，已改正 PLAN.md 措辞。

**6. 老师建议（阿哲转述）**：AI 交互设计可探索「生成式 UI」与「交互式视频」，参考成型产品。已派 3 个子代理调研（成型产品 / 概念边界可达性 / 本项目落地约束诊断）。此前查过 Google Research《Generative UI》与 Gemini dynamic view，材料在 waiting-and-process-visibility.md。

### 留下的

- wtt_ux-refactor/：.pms.yml / PLAN.md / timeline.md / sessions.md
- 父项目 docs/research/ 下 7 份调研报告
- spike_sse_stream/ 可运行原型
- 待办：P2 有效推荐优先（跨画像 Jaccard 诊断是第一步）

### 状态

进行中