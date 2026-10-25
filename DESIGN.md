# DESIGN.md — Where to Travel 设计文档

**版本：** v0.2（多轮对话版）
**更新：** 2026-09-18

---

## 一、产品定位

以 AI 对话为核心入口的旅游决策平台。**先搞清楚「为什么去」，再回答「去哪」。**

与竞品的核心差异：**动机驱动**而非标签匹配——同样说"想放松"，一个要恢复元气的人和一个要陪家人的人，会得到完全不同的行程。

---

## 二、MVP 边界

| 做 | 不做（v0.2） |
|---|---|
| 北京（真实数据 212 景区） | 其他省份真实数据 |
| 单日行程 | 多日行程 |
| 动机多轮对话 | 用户系统 / 历史记录 |
| 可解释推荐 + 一日行程 | B 端文旅局后台 |
| Leaflet 地图展示 | 支付 / 票务 |

---

## 三、架构

```
┌─ 前端（Jinja2 + 原生 JS + Leaflet，无构建链）─┐
│  左：多轮对话      右：画像面板 + 行程结果      │
└───────────────────┬──────────────────────────┘
                    │ REST
┌───────────────────▼──────────────────────────┐
│  FastAPI (app/main.py)                        │
│  POST /api/chat        多轮对话                │
│  POST /api/itinerary   生成行程                │
│  GET  /api/session/{id} 取回会话               │
│  POST /api/recommend   推荐（调试用）           │
└───┬────────────┬─────────────┬────────────────┘
    │            │             │
┌───▼────┐ ┌─────▼──────┐ ┌───▼──────────┐
│conversa│ │ recommend  │ │  itinerary   │
│  tion  │ │  动机→评分  │ │ 聚类+TSP+剪枝 │
│动机对话 │ │   +场所气质 │ │              │
└───┬────┘ └─────┬──────┘ └───┬──────────┘
    │            │             │
    │      ┌─────▼─────────────▼───┐
    │      │  SQLite (data/wtt.db) │
    │      │  attractions 212      │
    │      │  transport   216      │
    │      │  crowd_index 217      │
    └──────┤  sessions             │
           └───────────────────────┘
    │
┌───▼──────────────────────┐
│ LLM 服务（app/services/）  │
│  llm.py   GLM-4 Flash 封装 │
│  narrative.py 叙述+评估    │
└──────────────────────────┘
```

---

## 四、核心流程

```
用户开口
   │
   ▼
[每轮对话] conversation.chat(session_id, text)
   │
   ├─ ① 抽取调用  ── 只给用户原话（不带 assistant 消息）→ 更新画像
   ├─ ② 回复调用  ── 带完整历史 → 自然语言回复
   └─ ③ 证据校验  ── 拦掉模型瞎补的字段
   │
   ▼
画像（存 sessions 表）
   ├─ 结构化字段：primary / intensity / hours / companions / ...
   └─ 判断 ready：动机明确 +（时长或同伴）有一个，且 ≥2 轮
   │
   ▼ 用户点「看行程」
[推荐] recommend(motivation, intensity)
   │  评分 = 等级×0.10 + 画像×0.15 + 动机偏好 − 拥挤惩罚
   │  动机偏好含：场所气质匹配（自然/严肃/室内）
   ▼
[编排] itinerary.build_itinerary(candidates, motivation, hours)
   │  距离聚类 → 簇内 TSP(最近邻+2-opt) → 区收敛 → 时间预算剪枝
   ▼
[叙述] narrative.narrate() + assess()
   │
   ▼
时间线 + Leaflet 地图 + 评估
```

---

## 五、数据

### 5.1 来源

| 数据 | 来源 | 状态 |
|---|---|---|
| 景区名录/门票/交通/人流 | [北京市公共数据开放平台](https://data.beijing.gov.cn) | 12 数据集 119,518 行 |
| 景区坐标 | 高德地理编码 | 212 条已补（GCJ-02） |
| 天气 | 和风（未接入） | 公共域名将停服，需专属 Host |

**其他省份**：PRD 规划用占位数据（`data_source: "placeholder"`），**v0.2 未实现**。

### 5.2 表结构

```
attractions   id, name, level, district, address, phone, postcode,
              lon, lat, ticket_free, price_high, price_low, context, embedding
transport     attraction_name, district, level, metro, bus, highway,
              branch_road, airport, railway, town
crowd_index   name, saturation, ts          ← 重点景区饱和指数（实时人流）
sessions      id, created_at, profile(JSON), motivations(JSON), itinerary(JSON)
```

---

## 六、关键设计决策

| 决策 | 理由 |
|---|---|
| **不做前后端分离** | 无构建链，单服务部署；评估过 Chainlit，其地图需自写组件且依赖重（50+ opentelemetry） |
| **SQLite** | 零配置，MVP 够用 |
| **抽取与回复拆两次调用** | 实测：带 assistant 消息的抽取调用会让模型「续写对话」而非抽取，`response_format` 也救不了 |
| **代码层证据校验** | 小模型无视 prompt 里「不要推测」，会瞎补 `companions` |
| **行程不依赖 LLM 排序** | 纯 numpy 聚类+TSP，LLM 只负责叙述 |
| **动机七分类 + 判据词表** | 只给类别名会让模型抓字面（"人少"→探索），给判据词才准 |

---

## 七、已知问题（待修）

| # | 问题 | 影响 | 设计上的修法 |
|---|---|---|---|
| 1 | **画像只能 append，列表字段无法删除/替换** | 说"不要博物馆了"删不掉 | 合并策略改为「支持显式否定」：抽取器识别 `remove` 指令；或列表改为带时间戳的增删记录 |
| 2 | **没有「出发地/目的地」概念** | 给北京以外的用户推错城市 | 画像加 `origin` / `destination` 字段；或在首轮对话主动确认 |
| 3 | **行程只能生成一版** | 用户点第二次得到同样结果 | 支持"换一批"：传入排除列表；或基于反馈重算 |
| 4 | **叙述可能幻觉景点** | 出现"杭州西湖"这类不存在的站 | prompt 里强约束「只能用给定景点」+ 输出后校验站名 |
| 5 | 画像过于粗糙 | 只有结构化字段，无自然语言描述 | 加 `summary` 自由文本字段，保留用户的原始表达 |
| 6 | 行程距离是直线估算 | 与实际驾车差距大 | 接高德路径规划 API（配额 5000/日） |

---

## 八、技术栈

| 层 | 选型 |
|---|---|
| Web | FastAPI + Uvicorn |
| 模板 | Jinja2 |
| 前端 | 原生 JS + Leaflet（无构建链） |
| 数据库 | SQLite |
| 大模型 | GLM-4 Flash（智谱 OpenAI 兼容端点） |
| Embedding | 阿里云百炼 `text-embedding-v3`（1024 维）⚠️ 必须用 Workspace 专属端点 |
| 地图 | 高德 Web 服务 API（地理编码/路径规划） |

---

## 九、运行

```bash
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
cp .env.example .env            # 填 key
python -m app.scripts.import_data    # 导入数据
python -m app.scripts.geocode_all    # 补坐标（约 212 次高德配额）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

**凭证**：全部走 `.env`（已 gitignore），仓库只提供 `.env.example`。

---

## 十、调研文档索引

| 文档 | 内容 |
|---|---|
| `docs/reference/PRD.md` | 产品需求文档 V1.2 |
| `docs/reference/analysis.md` | 竞品与学术支撑 |
| `docs/research/data-sources-report.md` | 四个数据源实测 |
| `docs/research/analysis-verification.md` | 竞品/论文逐条核实 |
| `docs/research/reusable-assets.md` | 开源仓库可复用性评估 |
| `docs/research/arxiv-findings.md` | arXiv 技术方案（ITINERA 等） |
| `docs/research/itinera-verification.md` | ITINERA 实跑验证 |
