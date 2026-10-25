# arXiv 调研：可落地的技术方案

**调研日期：** 2026-09-17
**起因：** analysis.md 引的 6 篇论文全部读不到（出版社 403，链接只到首页）。
**方法：** 改从 arXiv 检索，按「能否落地实现」筛选。

---

## 一、核心结论

**arXiv 上找不到 analysis 引的那 6 篇**（旅游/酒店管理领域主要发期刊，不发预印本）。
**但找到了更好的替代：一批 2024-2026 年的旅行规划工作，其中一篇有可直接复用的开源实现。**

> **最重要发现：ITINERA —— 67 star、GPL-3.0、现代依赖、且代码里原生支持 `beijing`。**

---

## 二、⭐ ITINERA：可直接复用的实现

| 项 | 值 |
| --- | --- |
| 论文 | EMNLP 2024 Industry Track + **KDD UrbComp 2024 最佳论文** |
| 仓库 | `github.com/YihongT/ITINERA` |
| Star | **67**（对比：analysis 提到的三个仓库是 0/0/6） |
| License | **GPL-3.0**（明确开源，可商用需注意传染性） |
| 语言 | Python |
| 最后推送 | 2025-05-22 |

### 2.1 它做的事 = PRD 的核心链路

> "decomposing user requests, selecting candidate points of interest (POIs), **ordering the POIs based on cluster-aware spatial optimization**, and generating the itinerary."

对照 PRD：

| PRD 模块 | ITINERA 对应 |
| --- | --- |
| 需求采集 | `user_reqs` 自然语言请求 |
| 推荐引擎 | POI 候选筛选 |
| 行程编排 | **聚类感知空间优化（TSP）** |
| 推荐输出 | LLM 生成带叙事的行程 |

### 2.2 依赖健康（关键 vs 前三个仓库）

```txt
folium==0.18.0        geopandas==1.0.1      networkx==2.8.8
numpy==2.0.2          openai==1.54.3        pandas==2.2.3
PuLP==2.9.0           python_tsp==0.5.0     scipy==1.13.1
shapely==2.0.6        requests==2.32.3      thefuzz==0.22.1
```

**全部是现代库、全部可安装。** 对比：
- ETKG 海南 → TensorFlow 1.x（已停维护）
- 携程图谱 → pyltp（已停维护）
- **ITINERA → 无历史包袱** ✅

### 2.3 原生支持北京

```python
parser.add_argument('--city', default='shanghai',
    choices=["hangzhou", "qingdao", "shenzhen", "shanghai",
             "beijing", "changsha", "wuhan"])
```

**并且有中文版**：`itinera_zh.py` + `all_prompts.py`（中文 Prompt）+ `shanghai_zh.csv`。

### 2.4 代码结构

| 文件 | 大小 | 作用 |
| --- | --- | --- |
| `model/itinera.py` | 27.9 KB | 主流程（中文） |
| `model/spatial.py` | 15.6 KB | **空间优化：聚类 + TSP** |
| `model/search.py` | 5.6 KB | POI 检索 |
| `model/utils/all_prompts.py` | 22 KB | **中文 Prompt 模板集** |
| `model/utils/funcs.py` | 12.5 KB | 工具函数 |
| `model/data/shanghai_zh.csv` | 7 KB | 上海 POI 数据（含 x/y 坐标） |

**产出物**：`model/output/*.html`（folium 地图可视化）+ `result_zh.json`（结构化行程）。

### 2.5 空间优化算法（`spatial.py` 实测源码要点）

**1) 距离阈值聚类** —— 用 scipy 距离矩阵 + networkx 连通图：
```python
dist_matrix = scipy.spatial.distance.cdist(coords, coords)
np.fill_diagonal(dist_matrix, thresh + 100)
G = nx.Graph()
for i in range(N):
    for j in range(i+1, N):
        if dist_matrix[i, j] < thresh:   # 默认 thresh=5000 米
            G.add_edge(i, j)
```

**2) 离群点剔除** —— 1.5 倍标准差：
```python
mean_distance = np.mean(distances)
std_distance = np.std(distances)
non_outliers = [poi for i, poi in enumerate(poi_candidates)
                if abs(distances[i] - mean_distance) <= 1.5 * std_distance]
```

**3) 路径排序** —— 模拟退火解 TSP：
```python
from python_tsp.heuristics import solve_tsp_simulated_annealing
from pulp import LpVariable, LpProblem, LpMinimize, lpSum, LpBinary, PULP_CBC_CMD
```

**4) citywalk 模式** —— 5000 米阈值内的步行范围优化。

### 2.6 中文 Prompt 设计（可直接借鉴）

**角色设定：**
```
您好ChatGPT, 请扮演一个旅行大师，精通各种精致旅行体验。
你的任务是从给出的'潜在兴趣点'列表中，制定完美的一日行程。
你的特点？通过编织生动的故事和唤起一种如此强烈的漫游欲望，
以至于仅仅通过听到你的故事就感觉如身临其境。
```

**行程时长推断**（把自然语言需求转为小时数）：
```
用户需求: ["黄浦江", "豫园逛逛", "五小时左右"]  →  输出: ["5"]
用户需求: ["博物馆", "地道美食", "夜生活"]      →  输出: ["8"]
```

**起点选择规则**（含领域知识）：
```
1. 确保所选点符合用户需求
2. 起点应靠近其相邻点
3. 优先考虑像博物馆或艺术画廊这样的地方，这些地方通常需要更多的探索时间
4. 避免从酒吧或俱乐部开始
```

**工程细节：** 所有 Prompt 都强制返回**纯 JSON list**，并写明「不需要编写任何代码」「确保可以被 json.loads 解析」——这是可用的 Prompt 工程范式。

---

## 三、其他值得看的 arXiv 工作

| 论文 | arXiv | 价值 |
| --- | --- | --- |
| **ATLAS** 约束感知多智能体 | `2509.25586` | ⭐⭐⭐ **动态约束管理 + 迭代式计划批判**，把 TravelPlanner 通过率从 23.3% → **44.4%** |
| **iTIMO** 行程修改数据集 | `2601.10609` | ⭐⭐⭐ **REPLACE/ADD/DELETE 三种修改操作**，对应 PRD 的「用户反馈调整」环节 |
| **TripCraft** 时空细粒度基准 | `2502.20508` | ⭐⭐ 5 个连续评估指标（时间/空间/顺序/画像） |
| **TravelAgent** | `2409.08069` | ⭐⭐ 四模块架构：Tool-usage / Recommendation / Planning / Memory |
| **TripTailor** | `2508.01432` | ⭐⭐ 真实世界个性化基准（2025-08） |
| Collab-REC | `2508.15030` | 多智能体推荐平衡 |
| RETAIL | `2508.15335` | 真实世界旅行规划 |

### 3.1 ATLAS 的约束分类（对本项目最有启发）

> "constraints that are **explicit, implicit, and even evolving**"

| 约束类型 | 例子 | PRD 对应 |
| --- | --- | --- |
| **显式** | 时间、预算、目的地 | 本次需求采集 |
| **隐式** | 体力、偏好、忌讳 | 偏好深挖 |
| **演化** | 用户反馈后变化的 | 行后反馈闭环 |

**ATLAS 的三个机制：**
1. 动态约束管理
2. 迭代式计划批判（iterative plan critique）
3. 自适应交错搜索（adaptive interleaved search）

**这三个恰好补的正是 PRD「旅程预演」和「用户反馈调整」环节的算法空白。**

### 3.2 iTIMO 的修改操作（对应 PRD 的调整环节）

```
三种操作：REPLACE / ADD / DELETE
三种扰动意图：
  · disruptions of popularity   （热度扰动）
  · spatial distance            （空间距离）
  · category diversity          （类别多样性）
```

**这就是「换掉/太赶/加景点」的算法化表达。**

---

## 四、与 analysis.md 的对比

| analysis 引用的 | arXiv 上的实际情况 |
| --- | --- |
| 清华 TEKG（期刊） | 未找到预印本 |
| ETKG 海南 | 有 GitHub 仓库（`xcwujie123/Hainan_KG`），无 arXiv |
| 规则行程链提取（cqvip） | 未找到，方法已在携程仓库中复现 |
| TIME-UIE（Expert Systems with Applications） | 未找到预印本 |
| CRS 可解释性（Discover AI） | 未找到 |
| 可解释推荐（Transactions in GIS） | 未找到 |
| 预期怀旧（Annals of Tourism Research） | 未找到 |

**结论：analysis 的学术引用基本无法从 arXiv 获得，但方向（事件驱动、可解释、约束感知）在 arXiv 上有更实用的近期替代。**

---

## 五、行动建议

### 立即可做

1. **跑通 ITINERA** —— `pip install -r requirements.txt` → `python main.py --city beijing --type zh`
   - 它的 POI 数据只含上海，**北京数据需替换**（我们已有 212 个景区 + 高德地理编码能力）
   - 这是验证「动机驱动行程生成」最快的路径

2. **搬它的 Prompt 范式** —— 角色设定 + 少样本 + 强制 JSON 输出

### 借鉴改造

3. **空间优化算法** —— 聚类阈值 + 离群剔除 + TSP 模拟退火，可直接用于本项目的一日游编排
4. **ATLAS 的约束三分法** —— 显式/隐式/演化，用于设计画像模型
5. **iTIMO 的修改操作集** —— REPLACE/ADD/DELETE，用于「用户反馈调整」

### 注意事项

- ⚠️ **GPL-3.0**：若直接复用 ITINERA 代码，衍生作品需同样开源
- ⚠️ ITINERA 用 OpenAI API；本项目计划用 GLM-4 Flash，需改 `proxy_call.py`
- ⚠️ 其 POI 数据是上海，**要换成我们的北京数据**

---

## 附：调研方法

- arXiv API（`export.arxiv.org/api/query`）按关键词检索
- 论文摘要：arXiv abs 页面解析
- 源码：GitHub REST API `contents` 端点（`raw.githubusercontent.com` 取不到，该仓库需走 API）
- **局限：** 未阅读论文全文（仅摘要 + 仓库源码）；未实际安装运行 ITINERA
