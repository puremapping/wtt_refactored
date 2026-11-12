# 生成式 UI / 交互式视频：本项目落地约束诊断

**日期**：2026-11-12
**对象**：`D:\fs\workspace\projects\wtt_refactored`（FastAPI + SQLite + Jinja2 + 原生 JS + Leaflet + GLM-4-Flash）
**性质**：落地约束诊断，不是技术选型，也不是实现方案。**本文不写代码。**

---

## 0. 判据与证据口径（先说清这份报告按什么被检查）

本报告的官方判据 = 委托任务给的 6 个必答问题 + 4 条硬约束 + 1 条优先级：

| 判据 | 来源 |
|---|---|
| Q1 两方向各能落到什么程度 + 一个具体 demo 规格（看到什么/点什么/后端发生什么） | 委托任务 §1 |
| Q2 行程卡片变「生成式界面」时推荐结果的数据契约；`recommend()` 的 `Scored` 缺哪些字段 | 委托任务 §2（指定读 `app/services/recommend.py`） |
| Q3 GLM-4-Flash 生成结构化 UI 描述的延迟；能否绕过「一分钟以上」风险 | 委托任务 §3 |
| Q4 会不会掩盖推荐不准，怎么避免界面花哨但内容仍错 | 委托任务 §4 |
| Q5 生成式 UI 怎么进 pytest；无构建链下 275 个测试怎么覆盖新界面 | 委托任务 §5 |
| Q6 明确的红线 | 委托任务 §6 |
| 硬约束：不引构建链、不加算力、不换模型 | 委托任务 CONTEXT |
| 冲突时优先保证「有效推荐」 | `wtt_ux-refactor/PLAN.md:30`（阿哲 2026-10-29 定的裁决规则） |

**证据分级**（下文每条结论都带标记，转述不当事实用）：

- **[实读]** 本次亲自打开的文件与行号。
- **[实跑]** 本次在本仓库实际执行的命令/脚本输出。
- **[文档转述]** 项目内已有文档的记载，本诊断未重新验证其原始来源。
- **[未实测]** 仓库里没有该数据，明确标注，不填估算值。

**本次实跑结果**（可直接复现）：

```
./.venv/Scripts/python.exe -m pytest -o addopts='' -q   →  275 passed in 36.80s
data/wtt.db: attractions 315（北京 212 / 成都 103），坐标 315/315，
             transport 216，crowd_index 217
recommend(): 故宫博物院「恢复/逃离」score=0.0993 reasons=[]
             「美食/感官」与「文化/沉浸」top5 完全相同
             （故宫/天坛/大运河/圆明园/明十三陵）
```

> 说明：[实跑] 复现了 `wtt_ux-refactor/PLAN.md:44-46` 记载的两个具体症状（故宫 0.099、美食≡文化）；
> 该文档里的 **7 动机 Top-5 Jaccard 全表矩阵本诊断未重跑**，属 [文档转述]。

---

## 1. 现状：约束到底卡在哪（读盘结论）

| 事实 | 证据 | 对两个方向的约束 |
|---|---|---|
| 「刻意不用前后端分离构建链、Chainlit、bcrypt/passlib、ORM」 | [实读] `README.md:239-240`；`DESIGN.md:132`（理由：无构建链、单服务部署；Chainlit 地图要自写组件且依赖重 50+ opentelemetry） | 不能靠装框架获得「生成式 UI」，组件必须长在现有 `app/static/app.js` + `app/templates/chat.html` 里 |
| 主入口 `/chat` 已是「左对话气泡 + 右持久结果栏」 | [实读] `app/templates/chat.html:25-70`：`#profile` / `#cta-block` / `#result-block`（内 `#narrative` `#assessment` `#timeline` `#map` `#btn-share`） | **右侧行程卡本身就是「卡片式回答」**，方向没错；缺的是卡片与对话的联动，不是缺一个画布 |
| Leaflet 走 CDN，地图实例已在 JS 全局 | [实读] `chat.html:90-91`；`app/static/app.js:9-11, 373-401`（`map` / `mapLayer` / `renderMap()`） | 「交互式」可以零成本复用，不需要新播放器 |
| 前端渲染靠模板字符串拼 `innerHTML` | [实读] `app/static/app.js:334-368`（`renderItinerary()`），`esc()` 只在 :465 定义且部分使用，`stop.name` 直接插值 | **把模型输出接进 innerHTML 是现成的 XSS 面**，这决定了「LLM 现场写界面」是红线 |
| 静态资源版本号 = `static/` 最新 mtime，启动时注入 | [实读] `app/routers/deps.py:13-28`；`README.md:83-86`（改前端需重启） | 新增 JS 文件不需要构建，但要重启服务才生效；测试侧无法靠「热更新」验证 |
| GLM 封装没有流式必需参数 | [实读] `app/services/llm.py:20-50`（`chat_raw` / `chat` / `json_chat` / `parse_json`）；`app/core/config.py:31-35`（`GLM_MODEL=glm-4-flash`，fallback `glm-4.7` 贵 16 倍） | 注释实测：不开 `force_json` 时 glm-4-flash 会无视格式要求直接回自然语言（`llm.py:44-48`） |
| **一轮对话已 ≥2 次 LLM，生成行程再叠 2~4 次** | [实读] `app/services/conversation/orchestrator.py:73-158`（抽取 + 回复 + 工具被拦后逼说话）；`app/services/narrative.py:153/165/187`（narrate、幻觉重写、assess）；`app/routers/itinerary.py:111-117`（修改行程又 narrate+assess） | 一次「看行程」是 **4~6 次串行 GLM 调用**；`README.md:174` 已把「生成行程超时」写进 FAQ。任何新增调用都加在已知超时路径上 |
| 限流按 `/api/chat` 次数计 | [实读] `app/routers/chat.py:19-23, 34` 匿名 20/min、登录 60/min，注释「每次对话真实消耗 GLM 费用」 | 多一次 LLM = 多一倍成本与限流压力 |
| SSE 原型已验证 | [实读] `docs/sse-streaming-design.md`；`spike_sse_stream/`（15/15 断言） | 关键限制：**工具轮 `content` 为空**（:22-31），而行程恰是工具轮产出；同步生成器不能在 LLM 调用内部 yield，正文只能「整段到达 + 前端打字机」（:480-493） |
| 测试底盘 | [实读] `tests/conftest.py:13-39`（`GLM_API_KEY=test-key-not-real`、`tmp_db` 重定向 `DB_PATH`）；`pyproject.toml:28-31`（`testpaths=["tests"]`、dev 依赖仅 pytest、「0 次 LLM 真调用」） | 275 个测试零真 LLM、零真实库；**不能把 node/浏览器变成默认门禁**，那等于变相引构建链 |
| 素材为零 | [实读] `app/core/db.py:14-30`（`attractions` 无 `photo_url`/`media`/`type`/`tags` 列）；`PLAN.md:135-137`（帖子卡片仍是渐变占位图，图片上传未做） | 「视频」没有素材基础，这是硬缺口，不是选型问题 |
| 数据边界 | [实跑] 315 景区、坐标全有；`PLAN.md:128-133` 成都缺 transport/crowd_index | 成都行程退化为「只按等级和距离排」，UI 不能把这种缺数据状态画得跟北京一样确定 |

---

## 2. Q1｜两条方向分别能落到什么程度

### 2.1 生成式 UI：能做「确定性组件编排」，不能做「模型现场写界面」

老师/Google 语境里的 Generative UI = 模型现场写出一个完整交互界面（网页/游戏/工具）来回答问题 [文档转述] `docs/research/waiting-and-process-visibility.md:237-242`，且自述「可能要一分钟以上」[:202, :240]。**这个形态在本项目里做不了，也不该做**：没有构建链承载动态组件、GLM-4-Flash 结构化输出不可靠（`llm.py:44-48`）、`innerHTML` 有 XSS 面（`app.js:346-368`）、且会再加一次串行 LLM。

能落地的形态是**服务端确定性组件清单（component manifest）**：LLM 完全不参与界面生成；`app/static/app.js` 里预定义一组原生 JS 渲染函数（组件库），后端由纯 Python 依据推荐结果决定「这次挂哪几个组件、各自 props 是什么」。这仍然兑现了「界面随回答而变」，只是把「生成」放在数据层而非代码层。

**Demo 规格：行程卡片「布局清单 v1」**

| 项 | 规格 |
|---|---|
| 用户看到什么 | 右栏 `#result-block` 仍是持久行程卡，但卡片头部按动机/风险**换组件组合**而不是换 HTML：用户说「带爸妈、走不快」→ 顶部出现「节奏条」（低强度 + 每站步行分钟）；「恢复/逃离」→ 出现「避开说明」（列出被排除项与原因码）；`risks[]` 含高人流 → 出现「拥挤预警」。时间线、Leaflet 地图、强度评估仍是现有组件，不重画。左栏对话气泡里有一句「右侧按你的节奏换了个看法」（对应 `docs/research/conversational-guidance-patterns.md:239` 的「侧栏变化必须被宣告」） |
| 用户点什么 | 每个组件最多 1 个动作，全部复用**现有后端路由**、不新增 LLM：拥挤预警上的「换掉这站」→ `POST /api/itinerary/modify {action:"replace", target:<站名>}`（`app/routers/itinerary.py:76-135` 已实现，含归属校验）；「看别的候选」→ `POST /api/recommend`（`:23-37`）；时间线点站 → Leaflet `map.flyTo()`（`app.js:373-401` 全局实例可直接用）。**组件点击只发确定性 action，不让模型再生成界面** |
| 后端发生什么 | `app/services/itinerary_flow.py:102-137` 的 `generate_itinerary()` 在 `d = it.to_dict()` 之后，新增一个**纯 Python、无 LLM** 的 `build_ui_manifest(d, profile)`，输出挂在 `d["ui"]`；随 `/api/itinerary`、`/api/chat` 的 `result["itinerary"]`、`GET /api/session/{id}` 的历史行程一起返回。`sessions.itinerary` 本身就是 JSON 列（`app/core/db.py:91`），**零 schema 迁移、零新表**。LLM 调用数增量 = 0，延迟增量 ≈ 0 |
| 硬规则 | manifest 是推荐结果的**投影**，不是第二份真相。所有 props 只能引用 `stops[]` / `risks[]` / `assessment` / `profile` 已有值；`component.type` 必须命中前端白名单，未命中一律回落 `legacy_timeline`；`actions[].endpoint` 必须是已注册路由，禁止模型给 URL |

**能不能绕过「一分钟以上」风险**：能，但不是靠「预定义组件库 + 流式填充」里的流式，而是靠**把 LLM 从界面生成链上整个拿掉**。见 Q3。

### 2.2 交互式视频：只能兑现「交互」，「视频」必须降级

三条硬缺口同时存在：① 315 个景区零图片/视频素材，`attractions` 无 media 列 [实读]；② 不加算力、不换模型 ⇒ 无视频生成/实时渲染/转码能力；③ GLM-4-Flash 是文本模型。**按字面做「交互式视频」在本项目里不成立。**

能落地的**最小可用形态**是把「视频」降级为「行程预演」——这个词 `README.md:6` 的产品定位里已经写了，接入已有叙事，不算新增产品方向。

**Demo 规格：行程预演（地图动画 + 时间轴，明确不是视频）**

| 项 | 规格 |
|---|---|
| 用户看到什么 | `#result-block` 加一个「▶ 预演」按钮。点击后右栏时间轴逐站高亮，Leaflet 依次 `map.flyTo()` 到每站，底部进度条按 `arrive` 时刻推进。所需字段全在现有 `Stop.to_dict()`（`app/services/itinerary.py:69-83`：`order/name/level/district/lon/lat/crowd/metro/arrive/duration_min/reasons`）。无视频文件、无新库、无 CDN 播放器 |
| 用户点什么 | 播放 / 暂停 / 跳到某一站 / 点站卡展开 `reasons[]` / 「换掉这站」（同 2.1，落 `/api/itinerary/modify`）。点站即把该站「为什么推这个」摊开，这是可解释性而非动画炫技 |
| 后端发生什么 | **首版零后端改动**，只在 `app/static/app.js` 加 `previewItinerary(d)`；不发 POST。若要埋点，复用 `app/services/analytics.py` 的 `track()` 范式（`app/routers/itinerary.py:70` 已有调用），不新建事件表 |
| 必须保留的诚实标注 | `app.js:367-368` 现有文案「全程约 X 公里（直线估算）」在动画里不许丢；`itinerary.py:38-41` 的 `STAY_MINUTES=75` 固定停留、`TRAVEL_MINUTES_PER_KM=3.0` 直线换算都是已知粗糙处。顺滑动画最容易把不可行性画成「已安排妥当」 |
| 交付话术 | 若老师要看「视频」，直说这版没有视频文件，只有可交互的时间轴预演。**不要用自动播放的动画冒充交互式视频** |

**为什么这个降级是「务实」而不是「缩水」**：`docs/research/ai-travel-competitive-landscape.md:50-52` [文档转述] 已判定「地图是唯一能一眼识破路线折返/一天排太满的界面」，且「卡片流/滑动是输入偏好最优解，不是输出行程的解」。把预算花在地图时间轴上比花在没有素材的视频上更贴产品判据。

---

## 3. Q2｜数据契约：`Scored` 缺什么字段

### 3.1 现有结构（[实读] `app/services/recommend.py`）

`Scored`（`:92-108`）字段：
`id, name, level, district, address, ticket_free, price_high, price_low, crowd, has_metro, lon, lat, city, score, reasons: list[str]`

`to_dict()`（`:110-119`）把 `score` **`round(self.score, 3)`** 后输出。`recommend()`（`:236-246`）先按 `-score` 再按 `-len(reasons)` 排序，返回 `list[Scored]`；`/api/recommend`（`app/routers/itinerary.py:23-37`）回 `{motivation, city, items:[i.to_dict()]}`。

下游：`itinerary_flow.build_candidates()`（`:48-85`）把 Scored 压成 9 元组 `(name, level, district, address, lon, lat, crowd, metro, reasons)` → `itinerary.build_itinerary()` → `Stop.to_dict()`（`:69-83`）→ `flow.generate_itinerary()` 补 `city / narrative / assessment / profile`。**注意：`score`、`score` 的分项、动机强度、被扣分的原因在这一路上全部丢光了**，界面拿到的只有站名、等级、人流、理由文本。

### 3.2 生成式界面需要的契约形状

界面层不该直接消费 `Scored`（那是候选层），也不该让 `recommend()` 吐组件名。**分两层**：

- **候选层**（`recommend()` / `Scored`）：补「可审计证据」字段，供组件选型和内容闸门使用。
- **界面层**（挂在 itinerary dict 上的 `d["ui"]`）：纯投影，零新增真相。

建议的 `d["ui"]` 形状（规格，非代码）：

```
{
  "schema": "wtt.ui.v1",
  "context": {"motivation": ..., "intensity": ..., "city": ..., "hours": ...},
  "components": [
    {"type": <白名单内的组件名>,
     "props": { ... 只引用 stops/risks/assessment/profile 已有值 ... },
     "actions": [{"label": "换掉这站", "endpoint": "/api/itinerary/modify",
                  "body": {"action": "replace", "target": <站名>}}]}
  ],
  "fallback": "legacy_timeline"
}
```

三条契约纪律：① `type` 白名单外一律 fallback；② `props` 里出现的任何景点名必须 ∈ `{s.name for s in d.stops}`（**精确集合包含**，比 `narrative.py:66-76` 的景点后缀正则可靠，后者自己承认「无后缀幻觉抓不到」`:49-50`）；③ `endpoint` 必须是 `app.main.app.routes` 里已注册的路径。

### 3.3 `Scored` / 推荐结果缺的字段清单

| 缺的字段 | 类型 | 界面为什么需要 | 现有数据能否给 | 落点 |
|---|---|---|---|---|
| `score_breakdown` | `dict[str,float]`（`s_level/s_profile/s_pref/penalty`） | 组件要显示「为什么是它」而非一个被 round 过的 0.34；也是修复 0.005 压缩的前提 | ✅ **立刻**：`score_one()` `:179-231` 每笔都在算，只是没留 | `recommend.py` `Scored` + `to_dict()` |
| `score` 精度 | 不 round，或 round 4~6 | `:118` 的 `round(...,3)` 把 0.489x / 0.485x 压成同值，是 `wtt_ux-refactor/PLAN.md:44` 诊断在 API 层的二次伤害 | ✅ 立刻 | `recommend.py:118` |
| `match_reasons` 结构化 | `list[{code,label,evidence,weight}]` | 组件要按**理由码**分派（`crowd_high` → 拥挤预警）；现在 `reasons` 是自由文本 `list[str]`（`:187/194/198/203/207/211/215/221`），机器判不了 | ✅ 立刻：`reasons.append` 改带 code，旧 `reasons` 字段保留兼容 | `recommend.py` |
| `penalties` / `exclusion_reason` | `list[{code,label}]` | 故宫被扣到 0.0993 且 reasons 被清空（[实跑]；`:224` 主动撤掉含「历史」的理由、`:225-226` 扣分不打标）。界面必须能显示「因名称含『馆』被判室内」，而非静默消失 | ✅ 立刻 | `recommend.py:222-226` |
| `poi_type` / `tags` | `list[str]` | 组件库按自然/文化/美食/室内选型；现在 `_kind()`（`:80-89`）靠名称猜，且前端若重跑一遍必然与后端分叉 | ⚠️ `attractions` 无此列（`db.py:14-30`），需新增列 + 数据补齐；**不该由 LLM 现场生成** | 新列或独立标注表 |
| `data_confidence` / `evidence` | `enum{verified,inferred,missing}` + 来源 | 界面要区分「库里真有的」和「名称猜的」。生成式 UI 最危险的就是把猜的画得像真的 | ✅ 立刻（保守）：`_kind()` 结果标 `inferred`；`crowd`/`metro` 缺失标 `missing` | `recommend.py` |
| `identity_tier` / `value_score` | `enum` / `float` | 有效推荐优先（`wtt_ux-refactor/PLAN.md:33`）要求换主分；「为什么值得去」组件需要它 | ⚠️ 未实现；构造法见 `docs/research/quality-and-feasibility-evaluation.md:72-91` [文档转述]（世界遗产/国家级风景名胜区，Wikidata CC0 可入库） | 新列 |
| `opening_hours` / `visit_minutes` / `bookable_from` | `str/int/str` | 「可行性预警」组件必需；调研 `:147-151` 明确是硬校验 | ❌ 库里没有，且高德协议 3.5 禁落库（`:19-30`），只能在线读 + 进程内短 TTL | 运行时，不入库 |
| `distance_km` / `travel_min`（逐段） | `float/int` | 预演进度条要按段；现在只有全程 `total_distance_km` + 固定 `STAY_MINUTES=75`（`itinerary.py:38-41`） | ⚠️ 直线估算已有，真实路网需在线 API | `itinerary.py` |
| `photo_url` / `media` | `str` | 卡片流/视频组件的素材前提 | ❌ 完全没有，`PLAN.md:135-137` 连图片上传都未做 | 需先补资产，**本次范围外** |
| 查询上下文回显（motivation/intensity/city） | `str/int/str` | UI 要能声明「布局因动机而变」；`flow.generate_itinerary()` `:108-115` 有这些值但没写进 `d` | ✅ 立刻 | `itinerary_flow.py` → `d["ui"]["context"]` |

**关键取舍**：上表前 6 项都是「把已经在算、但没留下来的东西留下来」，零数据补齐、零 LLM、零外部依赖，**这是唯一值得先做的契约改造**。后 5 项涉及补数据/补资产，属于 `wtt_ux-refactor/PLAN.md:33-35` 的有效推荐工作，不该由 UI 需求倒逼着半途上线。

---

## 4. Q3｜延迟预算：仓库里没有实测值，但结构性结论是确定的

### 4.1 诚实边界

**`GLM-4-Flash 生成一段结构化 UI 描述要多久` —— 本仓库没有这个实测值，[未实测]，不填估算秒数。** 现有的相关实数只有：

- `app/core/config.py:31` 注释「实测 2026-09-18：glm-4-flash 可用且最省（12 tokens）」—— 是可用性/成本，**不是延迟** [实读]。
- `app/scripts/test_glm_models.py:39` `timeout=30` —— 是脚本给单调用设的超时上限，**不是实测耗时** [实读]。
- `docs/sse-streaming-design.md:22-31` 真实 GLM 流式探针：`[plain] chunks=7 text_len=7`、`[tool] chunks=2 text_len=0 tool_calls=[generate_itinerary]` —— 给了分块数，**没给墙钟时间** [实读]。
- Google Research「可能一分钟以上」[文档转述] `waiting-and-process-visibility.md:202/240` —— 那是生成**完整交互界面**（写网页/游戏/工具），不是本项目要的短 JSON，量级不可直接类比。

若真要一个数，落地前用 `app/scripts/test_glm_models.py` 的范式加一次计时探针（同 payload 跑 3 次取中位数，打印 `tokens` + 墙钟），把预算建立在实测上。**在那之前写具体秒数就是脑补数据。**

### 4.2 不需实测就能确定的结构性事实

[实读] 一次「看行程」的串行 LLM 链：

```
orchestrator.chat(): 抽取 json_chat (1) + 回复 chat_raw (2)
                     [工具被拦后逼说话 +1] (orchestrator.py:149-158)
→ generate_itinerary(): narrate (3) + assess (4)
                        [叙述幻觉校验失败重写 +1] (narrative.py:158-172)
→ 若用户再点「换掉这站」: narrate + assess 又 2 次 (routers/itinerary.py:111-117)
```

即 **4~6 次串行 GLM 调用**，且 `README.md:174` 已把「生成行程超时」列进 FAQ。`routers/chat.py:34` 明确每次都真烧钱。任何「再加一次 LLM 生成 UI 描述」都是直接恶化一个已登记的已知症状。

### 4.3 能不能绕过「一分钟以上」

**能，但正确解法是「不要让 LLM 生成界面」，不是「流式填充」。** 三档：

| 档 | 做法 | 延迟增量 | 评价 |
|---|---|---|---|
| **A（推荐）** | 预定义组件库 + 服务端**确定性** `build_ui_manifest()`，布局由 `motivation` + `risks[]` + `MOTIVATION_RULES`（`recommend.py:26-61`）查表得出 | **0 次 LLM，≈0ms** | 「一分钟以上」风险根本不出现，因为链上根本没有生成式生成。已兑现「界面随回答变」 |
| B（若一定要让模型选布局） | GLM 只输出**一个 enum**（`layout: low_pace / culture / crowded`），走 `llm.json_chat(force_json=True)`（`llm.py:44-48` 实测这才可靠）；必须**复用或并行**于 narrate/assess，禁止串行再加一次；enum 不在白名单 → 直接 fallback，**不重试**（重试 = 再加一次调用） | ≤1 次，且需与现有调用合并 | 可行但收益低：同一 enum 用 `motivation` 查表就能得到，没必要花一次调用和一份不确定性 |
| C（流式填充） | 用 `spike_sse_stream/` 的 SSE，先出组件壳再逐块填 props | 首字节快，总时长不变 | **不划算**。两处硬限制：工具轮 `content` 为空（`sse-streaming-design.md:22-31`），而行程正是工具轮产出；同步生成器不能在 LLM 调用内部 yield，只能「每步一帧」（`:480-493`）。真要做是 `docs/sse-streaming-design.md:525-539` 的 6 步重构，要改 `orchestrator.chat()` 为生成器、动 `/api/chat` 契约（`:207` 明确 `tests/test_agent_routing.py` 有 8 个用例直接打它）。**为了掩盖延迟而引入更大的重构，且会挤掉 P2 有效推荐** |

一句话：**预定义组件库是对的，流式填充在这个项目里是错的解法**。A 档把「生成式 UI」重新定义成「数据驱动的组件编排」，既守住了无构建链/不换模型/不加算力，也守住了延迟。

---

## 5. Q4｜会不会掩盖推荐不准：会，而且现有形态尤其容易

### 5.1 机制（带实跑证据）

界面组件越「会解释」，越像有依据。但本项目 `reasons[]` 是 `score_one()` 按名称关键词拼出来的（`recommend.py:187-226`），不是证据：

- [实跑] 故宫博物院「恢复/逃离」`score=0.0993`、`reasons=[]`。因为 `INDOOR_HINTS` 含「馆」（`:70`），故宫被判室内扣分（`:225-226`），同时 `:224` 把含「历史」的理由主动撤掉。**结果是「无理由的低分」**——如果生成式 UI 给这种结果套上精美卡片，用户看到的是「一个自信的推荐」，而不是「一个被错误规则排除的景区」。
- [实跑] 「美食/感官」与「文化/沉浸」top5 **完全相同**（故宫/天坛/大运河/圆明园/明十三陵）。根因 `MOTIVATION_RULES:57-60` 美食规则没有任何美食信号，复用了 `prefer_culture_hint`。**同一个错误内容，换 7 种布局也还是错。**
- `to_dict():118` 把分数 round 到 3 位，配上「等级 badge」「彩色标签」这类装饰，会把 0.005 级差异画成看似精确的可视化。
- `docs/research/quality-and-feasibility-evaluation.md:64-70` [文档转述] 论证 5A 是「便利性认证」不是「价值认证」；:199-202 论证旅游由**最坏情况**与 peak-end 规则主导。顺滑的预演动画最容易把「直线估算、每站固定 75 分钟」这个已知粗糙处抹平。

按 `wtt_ux-refactor/PLAN.md:28-30` 的裁决规则，**这些冲突一律以有效推荐优先**。

### 5.2 避免「界面花哨但内容仍错」的四条硬约束（可直接写进验收判据）

1. **UI 是投影，不是第二真相**。`ui.components[].props` 只允许引用 `stops[]` / `risks[]` / `assessment` / `profile` 已有值；禁止 manifest 生成新景点名、票价、时间、理由文案。服务端做集合包含校验（沿用 `narrative.py:17-33` 的防幻觉硬约束与 `README.md:249`「服务端硬拦数据边界」的纪律）。
2. **证据不足必须显式降级**。`data_confidence != verified` 或 `reasons` 为空的站，界面显示「依据不足」灰态，**不许用装饰性徽章填补空白**；`round(score,3)` 的值不许被画成置信度/质量分数条。
3. **先过内容闸门，再谈 UI**。把 `wtt_ux-refactor/PLAN.md:33-35` 三项设为 UI 上线前置。最小可测闸门三条：
   - 故宫在「恢复/逃离」下不再 0.099（且不靠 hardcode 白名单绕过，要修 `_kind()` 的误判）；
   - 「美食/感官」与「文化/沉浸」top5 Jaccard < 1.0；
   - `sum(score_breakdown.values()) == score`（防止界面显示的分项与排序用的分数不是一回事）。
4. **界面不得放大不可行性**。预演里必须显式保留「直线估算 / 未计营业时间 / 固定 75 分钟」标注；`app.js:367-368` 现有那句「全程约 X 公里（直线估算）」在动画里不许丢。

### 5.3 反过来：唯一值得做的生成式 UI 取向

把 `score_breakdown` / `penalties` / `data_confidence` 暴露成人能看懂的组件，正是让「故宫为什么消失」这类 bug **在界面上可见**，而不是只藏在 `wtt_ux-refactor/` 的 Jaccard 脚本里。即：**做「可解释性界面」，不做「装饰性界面」**。这也和 `docs/research/conversational-guidance-patterns.md:207-215` [文档转述] 的结论一致——行程 block 约束比「让模型排得合理」可靠，确定性兜底要延伸到界面层。

---

## 6. Q5｜可测试性：275 个测试怎么覆盖新界面

### 6.1 现有底盘（[实跑] + [实读]）

- `275 passed in 36.80s`；`tests/conftest.py:13-19` 注入 `SECRET_KEY` / `GLM_API_KEY=test-key-not-real`，`:25-39` 的 `tmp_db` 重定向 `app.core.db.DB_PATH`、清 `cities._cache` 与匿名会话；`pyproject.toml:31` 注明「0 次 LLM 真调用，不碰真实 data/wtt.db」。
- 假 LLM 注入范式：`monkeypatch.setattr(orch, "LLM", lambda: fake)`（`docs/sse-streaming-design.md:466-470`；`tests/test_itinerary_endpoint.py:29-45`）。
- 契约回归：`tests/test_itinerary_endpoint.py:64-92` 断言 `/api/chat` 真的生成行程且**每个站名 ∈ 库**；`tests/test_multicity.py:59-60` 断言城市隔离；`tests/test_llm_parse.py` 测 `parse_json`。
- ⚠️ **全等断言存在**：`tests/test_agent_protocols.py:27`、`test_agent_runtime.py:164/202`、`test_api.py:121` 用 `== {...}`。往那些 payload 里加键会当场破。

### 6.2 三层测法（全部 pytest，不把 node 变成门禁）

**第 1 层 · 契约层（必须有，成本最低）** — 新增 `tests/test_ui_manifest.py`，纯 Python 测 `build_ui_manifest(d, profile)`：

- 每个 `component.type` ∈ 白名单常量；
- 每个 `props` 里出现的景点名 ∈ `{s["name"] for s in d["stops"]}`（防幻觉，对应 `narrative.py` 的教训，但用精确集合包含）；
- 每个 `actions[].endpoint` ∈ `app.main.app.routes` 的已注册路径集合（不硬编码 URL）；
- `ui.context.motivation == d["motivation"]`、`ui.context.city == d["city"]`（防 UI 与内容分叉）；
- 同一 `d` 调两次 → manifest 完全相等（**确定性**：无 LLM、无随机、无时间戳）；
- 证据不足样例：`reasons=[]` + 低分站 → 必须产出灰态组件，不许产出「推荐」类组件；
- 用 `seed_beijing` fixture（`conftest.py:42-76`）跑临时库，不碰 `data/wtt.db`。

**第 2 层 · 接口层（保证 275 个不破）** — 在 `tests/test_itinerary_endpoint.py` 加一条 `body["itinerary"]["ui"]["schema"] == "wtt.ui.v1"`，并断言 `ui` 之外原有字段不变。

> **纪律**：新字段只做加法，挂在 `result["itinerary"]["ui"]` 里，**不改 `/api/chat` 顶层 result**（`app/routers/chat.py:81-90`）。这正是避开 6.1 里全等断言的办法。若改成顶层 `ui` 键或新增顶层 API，需逐个核对 `tests/test_agent_protocols.py` 等文件。

**第 3 层 · DOM 层（可选、非门禁）** — `spike_sse_stream/_ui_test.mjs` 已证明本仓库能跑 headless Chrome 做 15/15 断言 [实读 `docs/sse-streaming-design.md:7,581`]，但 `pyproject.toml:24-26` 的 dev 依赖只有 pytest、`testpaths=["tests"]`。因此把 JS 断言留在 `spike_sse_stream/` 那种**显式手动跑**的脚本里；pytest 内只做弱覆盖（用 `TestClient` 取 `/chat`，断言 `#ui-manifest-root` 存在、`ASSET_V` 由 `app/routers/deps.py:13-28` 注入）。**不要把 node/npm/浏览器变成 275 个测试的前置依赖——那等于变相引入构建链。**

**若真做流式**：照 `docs/sse-streaming-design.md:544-568` 的四个必测用例（终止帧 / 上游失败 / 工具轮 / **两套接口逐字段相等**），`TestClient.stream()` 直接读流、不需真起服务；且 `orchestrator.chat()` 签名与返回类型必须不变（`:472-478`），否则 12 个测试文件要改。

### 6.3 判据

> **生成式 UI 的可测试性来自「manifest 是纯函数产物」，不来自「前端有没有跑起来」。**

只要坚持 manifest 由服务端确定性生成、LLM 不参与，275 个测试不但不受影响，还多了一层比原来更强的**内容—界面一致性**回归。反之，一旦让模型输出 HTML/组件代码，这层保证立刻消失，且无法用现有假 LLM 夹具覆盖。

---

## 7. Q6｜明确红线

| # | 不该做 | 理由（带路径） |
|---|---|---|
| 1 | 引入 React/Vue/Vite/Webpack 或任何前端构建链 | `README.md:239-240`、`DESIGN.md:132` 是阿哲刻意决策；已评估 Chainlit（地图需自写组件且依赖重 50+ opentelemetry）。也会撑破 `pyproject.toml:24-26` 的 dev 依赖与 275 测试门禁 |
| 2 | 让 LLM 现场生成 HTML/CSS/JS 并 `innerHTML` 注入 | `llm.py:44-48` 实测 glm-4-flash 不 force_json 就回自然语言；`app.js:346-368` 已用模板字符串拼 innerHTML 且 `stop.name` 未 esc（`esc()` 仅 :465 定义、部分使用）→ 开 XSS + 不可测。也是 Google「一分钟以上」风险的直接来源 [`waiting-and-process-visibility.md:202/240`，文档转述] |
| 3 | 为界面再**串行**加一次 GLM 调用到生成行程链 | 现为 4~6 次串行（`orchestrator.py:73-158` + `narrative.py:153/165/187`）；`README.md:174` 已登记「生成行程超时」；`routers/chat.py:34` 每次真烧钱 |
| 4 | 换模型 / 上 GPU / 引视频生成或扩散模型 | 任务硬约束；且 `quality-and-feasibility-evaluation.md:19-30` 说明外部数据不可落库/训练 [文档转述]，**加算力不解决数据缺口** |
| 5 | 声称做「交互式视频」并交付视频文件 / 引 CDN 视频播放器 | `attractions` 无 media 列（`db.py:14-30`），`PLAN.md:135-137` 连图片上传都没做，315 景区零素材。没有素材的「视频」只能是假动画；诚实叫「行程预演」 |
| 6 | 把高德 `rating` / `opentime_week` / POI 坐标写进 `attractions` 或喂模型当特征 | 协议 3.5/3.4 禁止存储、缓存、用于训练（`quality-and-feasibility-evaluation.md:19-30` [文档转述]）；只能在线读 + 进程内短 TTL |
| 7 | 让 UI 自己产出/补全景点名、票价、时间、理由文案 | 与 `narrative.py:17-33` 防幻觉硬约束、`:36-98` 校验器、`README.md:249`「服务端硬拦数据边界」同一条纪律。UI 只能投影 |
| 8 | 把 `round(score,3)` 或等级 badge 当「置信度/质量」可视化 | `recommend.py:118` + `wtt_ux-refactor/PLAN.md:44` 分数压缩 0.005 级 + `quality-and-feasibility-evaluation.md:64-70` 5A 是便利性认证 [文档转述]。画成分数条是精确的假象 |
| 9 | 改 `/api/chat` 顶层响应结构、或改 `orchestrator.chat()` 签名来适配 UI | `docs/sse-streaming-design.md:207/472-478`：`test_agent_routing.py` 8 个用例直接打它、12 个测试文件依赖签名；`tests/test_agent_protocols.py:27` 等有全等断言。新字段只做加法、塞进 `itinerary.ui` |
| 10 | 用 SSE 流式重构来「掩盖」生成式 UI 的慢，把两者捆成一个大改 | `docs/sse-streaming-design.md:525-539` 是 6 步重构、要动契约；`PLAN.md:117-126` 已把「对话交互整体重设计」列为独立未开始大改。捆一起会挤掉 P2 有效推荐，违反 `wtt_ux-refactor/PLAN.md:30` 的冲突裁决 |
| 11 | 在有效推荐三项修复（身份稀缺性 / 评分阈值否决 / TOPTW 时间窗）落地前先上花哨组件 | `wtt_ux-refactor/PLAN.md:28-35`；[实跑] 故宫 0.0993、美食≡文化 top5 完全相同。界面会把这两个 bug 包装得更好看 |
| 12 | 动 `data/wtt.db`、或让测试碰真实库 | `tests/conftest.py:25-39` tmp_db 重定向、`pyproject.toml:31`「不碰真实 data/wtt.db」、`README.md:46` 数据随仓库提供 |

---

## 8. 可执行结论（按优先级排序，不含代码实现）

**裁决：先做有效推荐，UI 只做「可解释性」那部分。** 两条线并行，但一旦抢同一份工作量，按 `wtt_ux-refactor/PLAN.md:30` 让给推荐质量。

1. **[内容闸门，先于一切 UI]** 修 `recommend.py` 三处：`_kind()` 对「故宫」类露天场所的误判（`:68-89, :225-226`）、`MOTIVATION_RULES["美食/感官"]` 补美食信号（`:57-60`）、`to_dict():118` 取消 `round(...,3)`。验收用 [实跑] 那两条命令复现前后对比。
2. **[数据契约，零风险]** 在 `Scored` 补 `score_breakdown` / `match_reasons(code)` / `penalties` / `data_confidence`；`flow.generate_itinerary()` 补 `d["ui"]["context"]`。全部是「把已在算的东西留下来」，不加 LLM、不加表、不改顶层响应。
3. **[生成式 UI 最小形态]** `app/services/itinerary_flow.py` 加纯函数 `build_ui_manifest()`，`app/static/app.js` 加白名单组件渲染器，`app/templates/chat.html` 的 `#result-block` 加一个容器。**LLM 调用数 +0**。
4. **[交互式视频降级]** 只在 `app/static/app.js` 加 `previewItinerary(d)`（复用全局 `map` / `mapLayer` / `stops[].arrive`），零后端改动。交付时明说「无视频文件，是时间轴预演」。
5. **[测试]** 新增 `tests/test_ui_manifest.py`（第 1 层）+ 在 `test_itinerary_endpoint.py` 加一条 `ui.schema` 断言（第 2 层），跑 `./.venv/Scripts/python.exe -m pytest -q` 确认 ≥275 passed 且全绿。JS 侧断言留在 `spike_sse_stream/` 手动跑。
6. **[暂不做]** SSE 流式重构（`PLAN.md:117-126` 独立大改）、任何素材/视频资产、任何顶层新 API、任何 ORM/框架/构建链。

---

## 9. 本诊断未验证的事项（留给后续，不冒充结论）

- GLM-4-Flash 生成结构化 UI 描述的**墙钟延迟** [未实测]：需按 §4.1 加一次计时探针再定预算。
- `wtt_ux-refactor/PLAN.md:40` 的 7 动机 Top-5 Jaccard **全表矩阵** [文档转述，未重跑]；本诊断只复现了其中两个具体症状。
- Google Research「一分钟以上」的原始论文/实验条件 [文档转述自 `waiting-and-process-visibility.md`]，未核原文；且它测的是生成完整网页，与本项目的短 JSON 不同量级。
- `docs/research/quality-and-feasibility-evaluation.md` 里高德协议条款、Wikidata 可入库性、世界遗产数量 [文档转述]，本诊断未复核官方原文。
- 前端 `app.js:346-368` 的 XSS 面是 [实读] 代码观察，**未做渗透验证**；结论是「不要扩大这个面」，不是「已存在可利用漏洞」。
