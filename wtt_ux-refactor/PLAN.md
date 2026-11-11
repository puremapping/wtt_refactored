<!-- 格式：PMS 文档集格式 v1.0 -->

# wtt_ux-refactor 计划

> 状态来源：本文件是**计划**的唯一真相源。
> 父项目：wtt_refactored（共用其 git 与代码，不单独 git init）

## 分期

### P1 调研与方向确定  ✅ 2026-10-29

**为什么**：不确定「怎样让用户想留下」之前，不该动手改界面。先搞清设计依据。

- [x] 调研留人机制（engagement-and-progression.md）：对话长度不是留人指标，真杠杆在会话之间
- [x] 调研动机挖掘方法论（conversational-motivation-research.md）
- [x] 盘点 AI 旅游竞品（ai-travel-competitive-landscape.md）：动机挖掘全是 slogan，无验证过的留存价值
- [x] 调研等待过程与流程可见性（waiting-and-process-visibility.md）：显示真实工作步骤让人愿多等 50 秒
- [x] 调研 SSE 方案（sse-streaming-design.md + spike_sse_stream/）：原型 15/15 断言通过

**验收判据**
```
git log --oneline | grep research   → 至少 5 条 research 提交
spike_sse_stream/ 存在且可导入
```

### P2 有效推荐优先  ⬜ 未开始

**为什么**：信任数据显示 55% 用户遇过错误推荐、16% 被推荐过不存在的地方；推荐不准，体验再好用户也不会回来。阿哲 2026-10-29 定「有效推荐 > 使用体验」。

- [ ] 跨画像 Top-5 Jaccard 重合度诊断（验证「等级塌缩」是否导致推荐对动机不敏感）
- [ ] 用官方名录外的身份稀缺性（世界遗产/国家级风景名胜区）补价值主分
- [ ] 高德在线评分做阈值否决（协议 3.5 禁存储，只在线读）
- [ ] 行程可行性改为带时间窗模型（TOPTW 而非 TSP）

## 待议（未排期）

- [ ] 记忆用「改写+有功能」引用（N=169 实验：逐字引用提升隐私顾虑）
- [ ] 行程生成后留一个具体缺口（洗车实验：预填 2 格 34% vs 空卡 19%）
- [ ] 动机问题当场见效（回答后第一个推荐明确因它不同）