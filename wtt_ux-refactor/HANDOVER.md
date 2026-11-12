<!-- 格式：PMS 文档集格式 v1.0 -->

# HANDOVER — wtt_ux-refactor 交互设计重构线交接

**交接日期：** 2026-11-12
**交接方：** 小霁（session `20261029_104842_8aae3c`，本线发起人）
**接收方：** 后续负责 ux-refactor 线的 session
**交接类型：** 项目管理权转移（不是临时接管）

---

## 一、最重要的一件事：这条线没有「可以照做的结论」，只有「已经排除掉的路」

老师给的命题是「探索生成式 UI 与交互式视频」。调研做完了，**结论是两条方向里只有一条能做、且要做对的事很反直觉**。

⚠️ **不要重新调研**。四份报告共 140KB、来源 ledger 齐全：

| 报告 | 位置 | 回答什么 |
|---|---|---|
| 生成式 UI 全景 | `docs/research/generative-ui-landscape.md` | 12 个产品逐个拆、三条技术路线对比 |
| 交互式视频 | `docs/research/interactive-video-concept-and-feasibility.md` | 四个概念方向、可达性判定 |
| **落地约束诊断** | `wtt_ux-refactor/generative-ui-interactive-video-diagnosis.md` | **本项目能做什么、代价多少** |
| 推荐评估方法 | `docs/research/eval-methods.md` | K=5 时 Precision/MAP/MRR 全失效 |
| 推荐质量可行性 | `docs/research/quality-and-feasibility-evaluation.md` | 高德数据能读不能存、5A 是便利性认证 |

---

## 二、已经排除掉的路（别再走）

| 排除项 | 排除理由 | 证据位置 |
|---|---|---|
| LLM 现场写 HTML | 1–2 分钟延迟；模型错误率断崖（Gemini 3 是 0%，Flash-Lite **60%**）；a11y 最差 | generative-ui-landscape §5 |
| 流式填充正文 | 工具轮 content 为空，没有正文可流 | sse-streaming-design §6.3 |
| 世界模型/可玩视频 | 无公开 API；官方自认「无法精确模拟真实地点」——对旅游决策是致命伤 | interactive-video §3 |
| 分支叙事互动剧 | Netflix 2024-12 下架 24 个中的 20 个，Bandersnatch 也清零 | interactive-video §3 |
| 实时数字人 | 玉龙雪山中标 **307.65 万 / 40 项交付 / 120 天**；且「涨参与不涨信息质量」 | interactive-video §3 |
| 把「平均对话轮次」当指标 | Chai 论文自述会话长度服从幂律（50% ≤10 条），均值无意义 | engagement-and-progression §5.2 |

---

## 三、唯一可行的生成式 UI 形态（反直觉，必须理解）

**不是「模型生成界面」，是「服务端确定性组件编排」。**

```
预定义原生 JS 组件库（行程卡 / 地图 / 对比表…）
        +
纯 Python manifest（决定这一轮用哪些组件、放什么数据）
        =
LLM 零调用的「生成式界面」
```

**为什么必须这样**：Google 论文里 Gemini 3 输出错误率 0%，但 Flash-Lite 是 60%。我们用的是 GLM-4-Flash，**不能赌它写对界面**。

**Google 论文的最大漏洞**：82.8% 偏好是**把速度拿掉、给评审看预缓存结果**得到的。生成一次要 1–2 分钟。

---

## 四、⚠️ 下一任最容易踩的三个坑

### 坑 1：分数算出来了但没留下 —— 这是「分数压缩」的真根因

诊断报告读 `recommend.py` 发现的，**不是公式问题，是数据契约问题**：

- `score` 与分项在 `build_candidates()` 压成 9 元组时**全部丢失**
- `to_dict()` 第 118 行还 `round(..., 3)`

这解释了 Jaccard 诊断里看到的怪象：top5 分数 `[0.490, 0.490, 0.489, 0.485, 0.485]`，差距 0.005。

**`Scored` 缺 5 个字段**（纯加法，零 LLM 零迁移）：
`score_breakdown` / 结构化 `match_reasons(code)` / `penalties`+`exclusion_reason` / `poi_type` / `data_confidence`

### 坑 2：排除项会一刀切误伤，靠名称猜类型不可靠

实测复现：**故宫在「恢复/逃离」下得分 0.099、reasons 为空。**

根因链：`INDOOR_HINTS` 含「馆」→ 故宫被判为「室内博物馆」→ 被扣光 → 而且 `score_one` 在 `:224` **主动把 reasons 撤掉**。

**故宫其实是露天的。** 想「逃离加班」的用户因此一个故宫都看不到，拿到的是黄芩仙谷、爨柏景区这类冷门地方。

同类问题：「博物」这个词同时命中室内和文化两个维度，语义冲突。

### 坑 3：两条线共用一个 git —— 别用 `git add -A`

本线曾因此把 `wtt_miniapp/mvp/` 整批提交进自己的 commit（commit `683c8b3`，留痕在 `efdb5b4`）。

**正确做法**：`git add <明确路径>`。父项目任何一条线提交前先看 `git status`。

---

## 五、下一任的第一步（按这个顺序，不要跳）

```
第 1 步：修数据契约（Scored 补 5 字段）        ← 纯加法，两条线都受益
第 2 步：修推荐三项
        · 分数压缩 → 等级降为「闸门」而非主分
        · 排除项误伤 → 改软降权；类型判定不能只靠名字
        · 规则表缺 → 「美食/感官」复用 culture_hint，与「文化/沉浸」完全相同
第 3 步：才谈生成式 UI
```

⚠️ **第 3 步之前必须先做完 1、2**。诊断报告 §6 红线第 11 条写得很直白：

> 推荐三项修复前上花哨组件

**理由**：界面变精致、推荐仍错，比界面朴素、推荐错**更伤信任**——「界面这么好看，推荐却这么离谱」。

---

## 六、待接收方决策的问题（我给建议，不替你定）

### 问题 1：老师说「交互式视频」，到底指哪个方向？

材料**无法判定**。四个方向成本差三个数量级：

| 方向 | 结论 |
|---|---|
| (a) 世界模型/可玩视频 | 直接放弃，且要向老师说明 |
| (c) 可点击/可问答交互层 | **能做**，且可与生成式 UI 合并 |
| (d) 实时数字人 | 能接但不划算 |

**建议：当面确认。** 这决定下一步是「做」还是「回绝」。

### 问题 2：生成式 UI 的 A 档（零 LLM 调用）是不是太保守？

诊断建议「把 LLM 从界面生成链上整个拿掉」。好处是确定性、可测、零延迟；代价是界面不会「因人而异」。

**建议：先做 A 档验证形态，B 档（LLM 选组件）留到推荐修完后再评估。**

---

## 七、可复现的验收判据

```
# 1. 测试基线
.venv/Scripts/python.exe -m pytest tests/        → 275 passed

# 2. Jaccard 诊断（可复现）
.venv/Scripts/python.exe wtt_ux-refactor/jaccard_diag.py
  → 7 动机 Top-5 矩阵；首个推荐去重 5 个；全部选中去重 19/35
  → 「美食/感官」与「文化/沉浸」两行完全相同

# 3. 复现故宫误伤
.venv/Scripts/python.exe -c "
import os
for k in ('SECRET_KEY','GLM_API_KEY','ADMIN_TOKEN'): os.environ.setdefault(k,'x')
from app.services.recommend import load_candidates, score_one
items = load_candidates(city='北京')
g = [i for i in items if i.name=='故宫博物院'][0]
s = score_one(g, '恢复/逃离', 3)
print(s.score, s.reasons)   # → 0.0993 []
"

# 4. 数据契约
grep -n "score_breakdown\|match_reasons\|poi_type" app/services/recommend.py
  → 若仍无输出，说明第 1 步尚未做
```

---

## 八、弦外之音：谁是主干

```
D:\fs\workspace\projects\
├── wtt_refactored\      ← 父项目，唯一 git 仓库，两条线共用代码
│   ├── wtt_ux-refactor\  ← 本线（交互设计重构）
│   └── wtt_miniapp\      ← 另一条线（平台接入小程序），另一 session 推进
```

- **不要向旧库 `where_to_travel` 提交任何代码** —— 它已冻结
- **两条线共用 `app/` 代码**，改动会互相影响；提交前先看 status
- `wtt_miniapp/mvp/` 下的代码**不是本线的**，不要改

---

## 九、环境坑（都踩过）

| 坑 | 症状 | 解法 |
|---|---|---|
| 临时脚本放 `D:\fs\tmp` | `inspect.py` 遮蔽标准库 → `ModuleNotFoundError: PIL` | 脚本放项目目录内跑 |
| Windows curl 传中文 | GBK 编码 → 400 | 用 Python + `json.dumps(ensure_ascii=False).encode()` |
| `import recommend` 撞名 | `'module' object is not callable` | `from app.services.recommend import recommend as recommend_fn` |
| 高德数据入库 | 协议 3.5 禁存储缓存、3.4 禁训练 | **只在线读**，存自算派生量 |
| 服务未重启 | 改完代码看到旧行为 | 杀旧进程 → 起新 → 拉只存在于新代码的东西验证 |

---

## 十、接收方确认

> 读完本文件后请确认：
>
> - [ ] 知道「生成式 UI」唯一可行形态是服务端确定性组件编排，不是模型写 HTML
> - [ ] 知道为什么推荐三项必须先修（诊断报告 §6 红线 11）
> - [ ] 知道两条线共用 git，提交前必须看 status
> - [ ] 知道「交互式视频」的方向待与老师当面确认
> - [ ] 已知悉 `wtt_miniapp/` 的代码不是本线的
>
> 确认人：__________  时间：__________
