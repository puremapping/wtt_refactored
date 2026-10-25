# Where to Travel

> 不只告诉你「去哪」，先帮你搞清楚「为什么去」。

以 AI 对话为核心入口的旅游决策平台。通过动机挖掘（Travel for What）理解旅行本质需求，
结合北京官方开放数据与高德地图能力，输出个性化行程、可解释推荐与行程预演。

**课程作业 MVP。** 北京真实数据驱动，其他城市可通过导入数据接入（见 §7，零改代码）。

---

## 核心差异化

| | 大众点评 | 小红书 | **Where to Travel** |
|---|---|---|---|
| 核心逻辑 | 评价驱动 | 内容种草 | **动机驱动 + 真实数据交叉** |
| 推荐粒度 | 单点商户 | 单篇笔记 | **个性化一日行程** |
| 可解释性 | 评分展示 | 弱 | **多源来源 + 置信度 + 推荐理由** |

**同样说「想放松」，一个想恢复元气的人和一个想陪家人的人，会得到完全不同的行程。**

---

# 操作手册

## 1. 首次部署

```bash
cd D:/fs/workspace/projects/wtt_refactored

# 1.1 建虚拟环境（Python 3.13）
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"

# 1.2 配置凭证
cp .env.example .env
#    编辑 .env，填入各项 key（获取方式见下方「凭证获取」）

# 1.3 生成 SECRET_KEY（登录 cookie 签名用，必须 —— 不配则拒绝启动）
.venv/Scripts/python.exe -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env

# 1.4 生成 ADMIN_TOKEN（数据看板用，可选但建议）
.venv/Scripts/python.exe -c "import secrets; print('ADMIN_TOKEN=' + secrets.token_hex(16))" >> .env
```

**数据：** 仓库目录已含 `data/wtt.db`（212 景区 / 216 交通 / 217 人流，坐标已补，
交通与人流带城市维度）。**不需要重跑**导入与地理编码。仅在数据库损坏或换新数据源时才需要：

```bash
.venv/Scripts/python.exe -m app.scripts.import_data    # 从 .research/ 重建库
.venv/Scripts/python.exe -m app.scripts.geocode_all    # 补坐标（消耗 212 次高德配额）
```

## 2. 日常启动

```bash
scripts\start.bat          # 或：
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8100
```

| 地址 | 用途 |
|---|---|
| http://127.0.0.1:8100/ | 浏览页（瀑布流社区：内容 / 行程灵感 / 今日热榜） |
| http://127.0.0.1:8100/chat | AI 对话页（动机挖掘 + 行程生成） |
| http://127.0.0.1:8100/me | 个人主页（资料 / 旅游回忆 / 站内消息） |
| http://127.0.0.1:8100/login | 登录 / 注册（person 或 agency 身份） |
| http://127.0.0.1:8100/console | 文旅局智能体开发台（仅 agency 身份） |
| http://127.0.0.1:8100/admin | 数据看板（需 ADMIN_TOKEN） |
| http://127.0.0.1:8100/docs | FastAPI 自动文档 |
| http://127.0.0.1:8100/api/health | 健康检查 |

**对外访问**（手机 / 局域网）：把启动命令里 `--host 127.0.0.1` 改成 `0.0.0.0`。

## 3. 重启服务（改代码后必做）

改代码不会自动生效，必须重启。用脚本处理端口占用：

```bash
scripts\kill.bat     # 结束占用 8100 的旧进程
scripts\start.bat    # 重新启动（端口占用会明确提示，不会静默失败）
```

开发模式（改代码自动重载）：`scripts\dev.bat`。

**前端缓存已自动化**：静态资源版本号启动时按文件时间戳自动生成，
改完前端重启即生效，**不再需要手动改 `?v=N`**。

## 4. 用户系统

### 两种使用方式

| | 匿名 | 登录 |
|---|---|---|
| 能聊天 / 生成行程 / 改行程 | ✅ | ✅ |
| 数据保存 | ❌ **刷新即丢** | ✅ 存库，可查历史 |
| 行为记录 | ❌ 不记录 | ✅ 记 11 种事件 |

**不强制注册。** 匿名能完整走完整个流程，只在生成行程后提示「登录可保存」。

### 匿名数据政策

- **匿名会话不落库** —— 只存在服务进程内存里（TTL 1 小时），刷新页面就没了
- **不存对话原文** —— 行为事件只记长度、类型等结构化字段，不记内容
- 退出登录后当前对话仍在页面上，但刷新即丢

### 注册 / 登录

独立登录页 `/login`。邮箱 + 密码（≥6 位），密码用 pbkdf2_hmac 20 万次迭代存储。
身份二选一：个人（person）或 文旅局（agency，自动建机构）—— **不锁定可升级**。

### 查看历史

登录后个人主页可查所有已保存会话（含行程回忆），可继续聊，也可删除。

## 5. 数据看板

访问 `/admin`，填入 `.env` 里的 `ADMIN_TOKEN`。

**未设置 `ADMIN_TOKEN` 时接口直接禁用**（不会裸奔）。
凭证走 `X-Admin-Token` 请求头传输（不进服务器访问日志；旧式 URL 参数仅过渡期兼容）。

看板内容：用户数 / 会话数 / 转化漏斗 / 动机分布 / 事件统计 / 用户活跃度。

```bash
curl -H "X-Admin-Token: <ADMIN_TOKEN>" "http://127.0.0.1:8100/api/analytics/report?days=30"
```

## 6. AI 对话限流

`/api/chat` 每次调用真实消耗 GLM 费用，已加滑动窗口限流：

| | 限制（默认） | 调整 |
|---|---|---|
| 未登录 | 每 IP 20 次/分钟 | `.env` 的 `RATE_LIMIT_ANON_PER_MIN` |
| 登录用户 | 60 次/分钟 | `.env` 的 `RATE_LIMIT_USER_PER_MIN` |

超限返回 429「请求太频繁」。单进程内存实现，重启即清零。

## 7. 接入第二座城市（零改代码）

城市与区名一律从数据库现算（`app/services/cities.py` 原则），加城市 = 导数据：

1. 景区数据导入 `attractions` 表，**`city` 列填城市名**（如「成都」）
2. 交通 / 人流数据导入 `transport` / `crowd_index`，**`city` 列必须同步填写** ——
   按 (景点名, 城市) 关联，两城同名景点（如都有「人民公园」）数据绝不串
3. 重启服务。城市列表、对话 prompt 的数据边界声明、推荐过滤全自动跟上

同名区（如两城都有「朝阳区」）无上下文时按景区数多的城市解析（记录在 cities.py）。

## 8. 测试

```bash
# 全量测试（117 项，秒级，0 次 LLM 真调用，不碰真实数据库）
.venv/Scripts/python.exe -m pytest

# 端到端（需服务已启动；会真实调用 LLM，消耗费用）
.venv/Scripts/python.exe app/scripts/test_user_system_e2e.py
.venv/Scripts/python.exe app/scripts/test_regression_modern.py   # 阿哲四轮对话回归
```

测试安全网覆盖：画像合并/占位词清洗/时长归一、城市解析、认证加密、
行程算法（聚类/TSP/剪枝/修改操作）、对话编排三历史坑回归、
用户数据隔离、帖子权限、多城市隔离、限流器。

## 9. 常见问题

| 症状 | 原因 | 处理 |
|---|---|---|
| 启动报「缺少 SECRET_KEY」 | `.env` 未配置（v0.8 起拒绝启动，防止重启全员掉登录） | 按 §1.3 生成 |
| 页面 200 但功能是旧的 | 端口被旧进程占用 | `scripts\kill.bat` 后重启 |
| 数据看板 403 | 没配 `ADMIN_TOKEN` 或 token 错 | 检查 `.env`；看板页填 token |
| AI 对话返回 429 | 触发限流（BUG-7 防刷） | 稍后再试，或调 `.env` 阈值 |
| 登录后仍显示未登录 | cookie 没发出去 | 前端 `fetch` 必须带 `credentials: 'include'` |
| 生成行程超时 | LLM + 编排较慢 | 耐心等，或看日志 |

## 10. 常见维护操作

```bash
# 查数据库状态
.venv/Scripts/python.exe -c "
import sqlite3; c=sqlite3.connect('data/wtt.db')
for t in ('users','sessions','events','attractions'):
    print(t, c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0])
"

# 查各城市数据分布
.venv/Scripts/python.exe -c "
import sqlite3; c=sqlite3.connect('data/wtt.db')
print(c.execute('SELECT city,COUNT(*) FROM attractions GROUP BY city').fetchall())
print(c.execute('SELECT city,COUNT(*) FROM transport GROUP BY city').fetchall())
"

# 匿名会话随进程重启自动清空，无需手动
```

---

## 架构

```
用户输入自然语言
    ↓
[动机挖掘]  GLM-4 Flash → 七类动机 + 强度 + 约束
    ↓
[推荐引擎]  动机→偏好映射 × 真实数据（等级/人流/交通）× 城市隔离
    ↓
[行程编排]  距离聚类 → TSP 排序 → 区收敛 → 时间预算剪枝
    ↓
[行程叙述]  GLM-4 Flash → 自然语言叙述 + 幻觉校验 + 强度评估
    ↓
时间线 + Leaflet 地图 + 其他推荐
```

```
app/
├── main.py                  # 应用装配（60 行）
├── core/
│   ├── config.py            # 配置（SECRET_KEY 缺失拒绝启动）
│   ├── db.py                # SQLite schema + 幂等迁移
│   └── ratelimit.py         # 滑动窗口限流
├── routers/                 # 按业务域拆分的路由（只做校验+调服务+组装响应）
│   ├── pages / auth / chat / itinerary / history
│   ├── analytics / posts / me / agents
│   └── deps.py              # 模板实例 + 认证依赖 + 静态资源自动版本号
├── services/
│   ├── conversation/        # 多轮对话（models/profile/prompts/policies/store/orchestrator）
│   │                        #   七类动机与画像逻辑内聚于 profile.py
│   ├── itinerary_flow.py    # 行程生成管线（画像→城市→候选→编排→叙述→存储）
│   ├── recommend.py         # 推荐引擎（动机→偏好映射，支持城市过滤）
│   ├── itinerary.py         # 行程编排（聚类 + TSP + 剪枝）
│   ├── narrative.py         # 行程叙述 + 幻觉校验 + 评估
│   ├── cities.py            # 城市注册表（从库里算，不写死）
│   └── llm.py / tools.py / auth.py / analytics.py / posts.py / agents.py
├── templates/  static/      # Jinja2 + 原生 JS + Leaflet（无构建链）
└── scripts/                 # 数据导入 / 地理编码 / e2e 脚本
tests/                       # pytest 安全网（117 项）
```

**技术栈：** FastAPI · SQLite · Jinja2 · Leaflet · GLM-4 Flash
**刻意不用：** 前后端分离构建链、Chainlit（地图需自写组件且依赖重）、bcrypt/passlib（标准库够用）、ORM（SQLite 直用）

## 关键设计

- **抽取与回复拆两次独立 LLM 调用** —— 合成一次时，多轮历史会让模型「续写对话」而非抽取
- **画像合并在回复生成之前**（v0.8 BUG-11）—— 本轮刚说的话对回复上下文、强制补调、兜底、数据边界全部可见
- **服务端硬拦数据边界** —— 模型会声称「我有上海数据」并静默给北京行程，prompt 声明无效
- **服务端校验 tool_calls（白名单）** —— 且按意图分别设计，一刀切会误杀该调用的
- **所有查询强制 `AND user_id=?`** —— 前端不显示不算隔离，后端不返回才算
- **多城市按 (名称, 城市) 关联** —— 同名景点的人流/交通数据绝不互串（Phase 2c）
- **行程不依赖 LLM 排序** —— 纯 Python 聚类+TSP，LLM 只负责叙述

---

## 数据源

| 来源 | 用途 | 状态 |
|---|---|---|
| [北京市公共数据开放平台](https://data.beijing.gov.cn) | 景区名录/门票/交通/人流 | ✅ 12 数据集 119,518 行 |
| [高德地图 Web 服务](https://lbs.amap.com) | 地理编码/路径规划 | ✅ 212 景区坐标已补 |
| VisitBeijing MCP | ~~实时人流~~ | ❌ 域名已失效，用平台数据替代 |
| 和风天气 | 天气 | ⬜ 未接入 |

**关键数据（真实，非占位）：**

| 数据集 | 条数 |
|---|---|
| 北京市等级景区信息 | 212 |
| 等级景区门票信息 | 218 |
| 等级景区交通信息 | 216 |
| **重点景区饱和指数**（实时人流） | 217（去重后） |

> 平台数据来自市文化和旅游局，实时人流用官方「重点景区饱和指数」——
> 原方案依赖的 VisitBeijing MCP 域名已 NXDOMAIN，这是替代方案。

---

## 凭证获取

<details>
<summary>北京市公共数据开放平台</summary>

1. 注册 https://data.beijing.gov.cn
2. 【用户中心 - 我的唯一码】获取 key
3. ⚠️ key 是**滚动值**，每次访问页面都会刷新并使旧值失效

**注：** 数据已随仓库提供（`data/wtt.db`），日常运行不需要此 key。
</details>

<details>
<summary>高德地图</summary>

1. https://lbs.amap.com → 控制台 → 应用管理 → 创建应用
2. **服务平台必须选「Web服务」**（不是 JS API，两者 key 不通用）
3. 配额（个人认证，日）：地理编码/路径规划 5000，**POI 搜索仅 100**
</details>

<details>
<summary>智谱 GLM</summary>

1. https://open.bigmodel.cn/
2. 实测：`glm-4-flash` 可用且最省；`glm-4.7` 可用但贵约 16 倍；5.x 系列需充值
</details>

<details>
<summary>阿里云百炼（Embedding）</summary>

1. https://bailian.console.aliyun.com/
2. ⚠️ **必须用 Workspace 专属端点**——公共端点 `dashscope.aliyuncs.com` 不被接受
3. 端点形如 `https://<WORKSPACE_ID>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`
</details>

---

## 动机分类

| 动机 | 推荐策略倾向 |
|---|---|
| 恢复/逃离 | 自然景观、小众、低人流（**排除纪念馆等严肃场所**） |
| 连接/关系 | 交通便利、老少皆宜 |
| 探索/新奇 | 小众、非典型 |
| 表达/展示 | 视觉冲击、出片率高 |
| 成就/完成 | 5A 标志性、打卡优先 |
| 文化/沉浸 | 历史文化属性、博物馆/遗址 |
| 美食/感官 | 餐饮驱动 |

---

## 文档索引

| 文档 | 内容 |
|---|---|
| `REFACTOR_PLAN.md` | v0.8 重构计划（12 个修复项、结构重组、验收单） |
| `docs/DESIGN-three-pages.md` | 三页式 + 身份系统设计（v0.7） |
| `docs/DESIGN-user-system.md` | 用户系统与行为分析设计（v0.4） |
| `docs/DESIGN-conversation-itinerary-loop.md` | 对话-行程闭环设计（v0.3） |
| `DESIGN.md` | 总体设计 |
| `docs/reference/PRD.md` | 产品需求文档 V1.2 |
| `docs/reference/analysis.md` | 竞品分析与学术支撑 |
| `docs/research/` | 调研报告（数据源/竞品/Coze Studio/arXiv/ITINERA） |
| `timeline.md` | 项目事件时间线 |
| `sessions.md` | 经手 session 台账 |

---

## 已知限制

- **仅北京**：其他省份数据未接入（管线已就绪，见 §7 零改代码接入）
- **单日行程**：多日行程未实现
- **直线距离**：行程距离为球面直线估算，未走高德路径规划 API
- **时间估算粗略**：每站固定 75 分钟，未按景点类型区分
- **匿名历史不归并**：匿名 → 登录只归并当前会话，不追溯合并
- **密码无法重置**：需要邮件服务，未做
- **`session_end` 事件无触发点**：等明确的「结束」信号
- **叙述防幻觉有盲区**：无景点后缀的幻觉（如「杭州西湖」）漏检，靠 prompt 硬约束兜底

---

## License

课程作业项目。数据来源为北京市公共数据开放平台（[开放协议](https://data.beijing.gov.cn)），
使用时需注明数据来源。行程编排思路参考 [ITINERA](https://github.com/YihongT/ITINERA)（GPL-3.0）。
