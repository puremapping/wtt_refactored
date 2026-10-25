# 可复用性评估：analysis.md 中的开源原型与论文

**评估日期：** 2026-09-17
**评估目的：** 判断哪些能直接借鉴/复用，避免重复造轮子
**评估方法：** 拉取仓库源码树 + 阅读核心文件 + 检查依赖可用性

---

## 一、结论速览

| 资源 | 内容实质 | 可复用度 | 建议 |
| --- | --- | --- | --- |
| **ETKG 海南** (`xcwujie123/Hainan_KG`) | 46 文件，含模型+训练+4个基线+QA系统 | ⭐⭐⭐⭐ **模型与数据建模可借鉴** | 抄 SPARQL 数据模型，不抄 TF1 代码 |
| **携程游记图谱** (`fangjiataizi/Tourist_KG`) | 73 文件，含爬虫+事件抽取+图谱构建 | ⭐⭐⭐ **方法论可借鉴** | 抄顺承事件提取思路，代码需重写 |
| **Nomad** (`hossamasr/MLH-HacksForHackers`) | 单文件 `Nomad.py` (3.4KB) | ⭐ **仅思路参考** | 看 Prompt 设计即可 |

**核心判断：三个仓库的思路都有价值，但没有一个可以「直接拿来跑」——依赖均已过时。**

---

## 二、ETKG 海南（`xcwujie123/Hainan_KG`）

### 2.1 它做了什么

```
ETKGCN/              —— POI 推荐框架（核心）
baseline/            —— 4 个对比基线
  ├─ GCN/
  ├─ transE/
  ├─ LightFM/
  └─ SVDpp/
task-oriented conversational system/  —— Rasa 问答系统
data/                —— 部分示例数据
```

**ETKG 的定位（README 原文）：**

> "Traditional tourism knowledge Graph a knowledge base which focuses on the static facts about entities, such as hotels, attractions, while **ignoring events or activities of tourists' trips and temporal relations**."

> "The graph is **centered on the activities that tourists have participated in** during the trips and regard **tourists' trajectories as carriers**."

**这与本项目 PRD 第 13 章的 Travelling 事件思路高度一致。**

### 2.2 ⭐ 可借鉴之处：事件驱动的 SPARQL 查询模型

README 给了两个真实查询示例，**这就是"动机+约束"的数据建模样板：**

```sparql
-- 按活动类型查地点
SELECT ?location WHERE {
  ?e rdf:type:Event.
  ?e :hasActivity "diving".
  ?e :hasLocation ?location
}

-- 按「同伴+时长+出行方式」查旅程
SELECT ?Journey WHERE {
  ?Journey rdf:type: Journey.
  ?Journey :hasCompanion "parents".
  ?Journey :hasDuration "7".
  ?Journey :TravelType "self driving"
}
```

**对本项目的直接价值：** 第二个查询的谓词集合
（`:hasCompanion` / `:hasDuration` / `:TravelType`）
**就是 PRD「本次需求采集（同伴/时间/预算/目的地）」的 RDF 表达**。
可以直接借鉴这套本体设计，而不必从零设计。

### 2.3 ⚠️ 不可直接复用的原因

| 文件 | 依赖 | 问题 |
| --- | --- | --- |
| `ETKGCN/model.py` | `tensorflow` (1.x API) | 用 `tf.placeholder`、`tf.contrib.layers.xavier_initializer` —— **TF 1.x 已停止维护，Python 3.13 无法运行** |
| `task-oriented conversational system/*` | `Rasa` | Rasa 版本迭代巨大，旧代码不兼容新版 |
| 图谱本体 | RDF/SPARQL | 图数据「因空间限制只上传了部分示例」——**完整图谱没有** |

**结论：模型架构（KGCN + 事件权重）值得理解，实现需用 PyTorch 重写。**

---

## 三、携程游记图谱（`fangjiataizi/Tourist_KG`）

### 3.1 它做了什么

```
news_spider/travelspider/     —— Scrapy 爬虫
BeijingAttractions/           —— 北京景点爬虫
HarbinAttractions/            —— 哈尔滨景点爬虫
event_graph/
  ├─ event_extract.py    (3.3KB)  —— 顺承事件抽取
  ├─ event_graph.py      (4.0KB)  —— 图谱构建
  └─ sentence_parser.py  (7.0KB)  —— LTP 依存句法
```

**完整覆盖了 PRD 13.2「从游记提取 Travelling 事件」的全流程。**

### 3.2 ⭐ 可借鉴之处：规则法的具体实现

**顺承触发词（`event_extract.py` 实测源码）：**

```python
self.pattern = re.compile(r'(.*)(其次|然后|接着|随后|接下来)(.*)')
```

**长句切分：**
```python
re.split(r'[？?！!。；;：:\n\r….·]', content)
```

**短句切分：**
```python
re.split(r'[,、，和与及且跟（）~▲．]', content)
```

**事件提取路径：**
```
长句切分 → 顺承连词匹配 → 前后子句切分
  → jieba 分词 → LTP 依存句法分析
  → 提取 VOB（动宾）关系
  → 仅保留 (动词, 名词) / (动词, 习语) 组合
  → 输出 "词#词" 格式短语
```

**关键设计：以「顺承连词」为切分锚点，而非全篇解析。**
这是低成本高收益的做法——`其次/然后/接着/随后/接下来` 五个词就能定位行程顺序。

### 3.3 ⚠️ 不可直接复用的原因

| 依赖 | 问题 |
| --- | --- |
| **`pyltp`**（哈工大 LTP Python 绑定） | **2020 年后基本停止维护，Python 3.13 装不上** |
| `ltp_data/`（cws/pos/parser/ner 模型） | **不在仓库里**，需自行下载 |
| `pymongo` + MongoDB | 硬编码直连本地 MongoDB |
| Scrapy 爬虫 | 目标站（携程）结构多变，爬虫大概率已失效 |

**替代方案：** LTP 官方现在提供 **`ltp` (新的 PyPI 包，基于 Rust)** 或改用 **LAC / HanLP / jieba+Stanford**。

**结论：触发词表、切分正则、VOB 提取思路都能直接搬，实现要用现代 NLP 库重写。**

---

## 四、Nomad（`hossamasr/MLH-HacksForHackers`）

### 4.1 实质内容

**仅 4 个文件，1 个 Python 脚本（3.4KB）+ README。**

**定位（仓库描述原文）：**
> "Describe your life, not a destination. Nomad uses Gemini to reason about constraints and decide the best trip for you."

### 4.2 价值与局限

| 项 | 说明 |
| --- | --- |
| ✅ 可借鉴 | **"描述生活而非目的地"的 Prompt 设计思路** —— 与 PRD 的 Travel for What 同源 |
| ❌ 不可复用 | 只是 Gemini API 调用 demo，无推荐算法、无数据模型 |
| ⚠️ 提示 | 建仓与最后更新**仅差 2 分钟**（2026-01-03），是黑客松一次性上传，无维护 |

**结论：可作「思路同源」的佐证，但不构成参考实现。**

---

## 五、论文线索的可落地部分

**注意：本次未能读取论文原文**（出版社站点 sciencedirect/wiley 返回 403 反爬），以下基于 analysis.md 的描述与仓库实证推断。

| 论文方向 | analysis 声称 | 可落地性评估 |
| --- | --- | --- |
| 清华 TEKG | 以游记为实体，推荐准确率 +2% | 与 ETKG 海南同源；**+2% 提升幅度较小，需评估投入产出** |
| 规则行程链提取 | 1.7万篇蚂蜂窝游记，相似度 86.14% | **直接对应携程图谱的实现**；该方法无需标注数据，**适合课程作业** |
| TIME-UIE | 事件三元组抽取 +11.1% | LLM 抽取方向；**可用 GLM-4 替代其专用模型** |
| CRS 可解释性 | 可理解性/自然性 → 认知信任 | **直接支撑 PRD 的可解释推荐设计** |
| 可解释景点推荐 | 知识图谱+协同过滤，准确率 93.8% | 需验证；**93.8% 的数据口径不明** |
| 预期怀旧 | 支撑旅程预演功能 | 理论支撑，非技术方案 |

### 待办

**需要补做：** 这 6 篇论文的**具体方法**（而非引用格式）。
建议路径：
1. 用论文标题检索 arXiv / Semantic Scholar / 谷歌学术摘要
2. 优先找**开放获取版本**（arXiv preprint）绕过出版社 403
3. 重点读「方法」章节，判断能否用现有技术栈复现

⚠️ analysis.md 给出的 6 个学术链接**全部指向出版社首页，无法定位到具体论文**。

---

## 六、对本项目的行动建议

### 可直接借鉴（低成本高收益）

1. **ETKG 的事件本体设计** —— `:hasCompanion` / `:hasDuration` / `:TravelType` 等谓词，
   直接对应 PRD 的「本次需求采集」，**省去本体设计工作**
2. **携程图谱的顺承触发词表** —— 5 个连词 + 2 条切分正则，
   立即可用于 PRD 13.2 的游记事件提取

### 需要改造后使用（中成本）

3. **VOB 依存句法提取** —— 思路可用，把 `pyltp` 换成 `ltp` 或 `HanLP`
4. **KGCN 推荐模型** —— 架构可参考，用 PyTorch 重写

### 不必做（避免重复造轮子）

5. ~~从零设计事件数据结构~~ —— 参考 ETKG 的本体
6. ~~从零研究游记事件提取~~ —— 规则法已被验证可行

### 需要进一步调研

7. **6 篇论文的具体方法** —— 当前只有标题与结论，缺方法细节
8. **+2% / 86.14% / 93.8% 这些数字的实验条件** —— 需确认是否适用于北京 212 个景区的规模

---

## 附：评估方法

- 仓库结构：GitHub REST API `git/trees?recursive=1`
- 源码阅读：`raw.githubusercontent.com` 直取核心文件
- 依赖判断：基于源码中的 import 与已知的库生命周期
- **局限：** 未实际安装运行这些仓库；「不可用」结论基于依赖过时推断，未逐项实测
