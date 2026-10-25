# Where to Travel — session 台账

> 维护规则：接手即登记、收工即更新、按时间倒序

## 20260917_150557_2fc998（续：2026-10-15 之后）

- **时间**：2026-10-15 13:06 → 2026-10-21 18:25（仍在进行）
- **模型 / 来源**：qwen3.7-max / tui

### 做了什么

**1. v0.5 对话质量修复（10-15）**
- 阿哲报「感觉变傻了」，三轮对话暴露三个叠加缺陷，根因是一条因果链：
  模型想调工具（content 为空）→ 服务端白名单把 tool_call 拦掉 → reply 与 tool_calls **双空** → 兜底套模板 → 答非所问
- ⚠️ 我**第一版修法是错的**：加了「实质兜底」模板，但模板不读用户输入，第 2、3 轮输出完全同一句
- 正确修法：**工具被拦后去掉 tools 重问一次，逼模型用文字回答**
- 另修：模型把「未知」当 destination 字面值填入 → `_is_beijing("未知")`→False → 输出「未知还查不了」（荒谬）。修法 `_clean_field_value()` 清洗 23 个占位词，两层
- ⚠️ `events.user_id` 改 NOT NULL：把「匿名不落库」从代码约定升级为结构约束（SQLite 重建表迁移）
- **我自己在文档里把它写成已实现的 NOT NULL，实际是可空** —— 自查发现并补齐（不是改文档掩盖）

**2. README 重写为操作手册 + PMS 建制核对（10-15）**
- ⚠️ **发现时间认知错误**：上下文残留「今天是 09-18」，`date` 实际 10-15。项目已停摆一个月，`last_used` 与 sessions.md 时间戳一度会写错
- 补建 `sessions.md`（spec §4.2.2 要求，v0.1 初始化时漏建）；`.pms.yml` 补 `deployment` 字段；INDEX.md 重生成（61 活跃）
- 推送踩坑：repo 级 `git config --local http.proxy ""` **不生效**（global 里有值，`--get-regexp` 会同时列出两条），要用命令级 `-c http.proxy=`

**3. 低代码平台调研与 Coze Studio 实测（10-20）**
- 阿哲提出：做让各地文旅自己搭智能体的平台，主智能体按目的地调用
- **许可证实测（最关键发现）**：Dify LICENSE 明文 `you may not use the Dify source code to operate a multi-tenant environment` —— **直接否掉 Dify 作平台底座**
- 实测 star 数与许可证：Coze Studio 唯一「Apache-2.0 + 完整 Agent 平台」组合
- 部署 12 容器跑通，踩 5 坑：MinIO 官方撤镜像 / Bitnami 版 `mc` 路径不同 / **容器继承宿主 HTTP_PROXY 导致 etcd 集群通信发往 127.0.0.1:7897 失败（Milvus panic）** / `ALLOW_REGISTRATION_EMAIL` 空则无管理员 / **`go build` 打印 DONE 但 `output/bin` 是空的**
- 多租户二开 ~120 行 Go：解除 `TeamSpaceNum: 0` 硬编码 + **`spacePo2Do` 把每个 space 写死 Personal** + 建 `CreateTeamSpace` 接口 + space 表加 `space_type` 列。实测 3 个文旅局空间 type=2
- 发布链路验证：connector 只有 999/1024 两个，**但 1024=OpenAPI 够用** —— 澄清「不是我方做成它的插件，而是我方为主、它为引擎」
- 产出 `docs/research/coze-studio-hands-on.md` + `coze-studio-multitenant.patch`

**4. v0.6 城市抽象（10-20）**
- 阿哲定「先不切平台，只把引擎抽象成流程模板+标准数据包」
- 新增 `app/services/cities.py`：城市与区名**从库算**，不写死；`attractions` 加 `city` 列（同名区「朝阳区」两城无法区分）
- prompt 里「只有北京 212 个景区」→ `{supported}` 运行时替换
- 实测：塞 3 个成都景区进库，**一行代码没改**，城市描述/解析/prompt 全自动跟上
- ⚠️ 改这轮时**制造了一个回归**：上海竟然生成了行程、北京反被拦。根因是老 bug —— 数据边界拦截在画像合并**之前**执行，读的是上一轮值

**5. v0.7 三页式 + 身份系统（10-21）**
- 阿哲提产品形态：浏览页（瀑布流/三页签）+ AI 对话页 + 个人主页
- 先写设计文档再动手；五项决策由阿哲拍板：图片本地/热榜按搜索/要评论/回忆用 LLM/浏览页开放；保留 /chat
- 新增 6 张表（posts/likes/comments/messages/teams/agents）
- **独立登录页 /login，并拆掉 chat 内嵌弹窗**（阿哲原话「而不是像现在这样把登录入口放在 chat」）—— 第一版只加了 /login 没拆旧弹窗，自查发现是两套并存，才补拆
- 身份 person|agency，注册二选一**不锁定可升级**；agency 自动建 team；`/console` 三态（未登录→预选 agency 的登录页 / 个人→提示升级 / 文旅局→开发台）
- 发布校验在服务端：缺 prompt/region 拒发布 —— region 是主智能体路由唯一依据，空着发布=路由黑洞
- 匿名跳转会丢会话 → `sessionStorage.pending_share` 暂存 30 分钟，登录回来自动重弹
- 5 个测试套件全过

### 留下的

**新增文件**：`app/services/cities.py`、`posts.py`、`agents.py`；
`browse/me/login/console/console_denied` 四组模板+静态资源；
`docs/DESIGN-three-pages.md`、`docs/research/` 三份；4 个测试脚本

**修改**：`app/main.py`（/chat /me /login /console 路由 + 帖子/消息/个人/智能体 API）、
`app/core/db.py`（6 新表 + users/attractions 迁移）、`auth.py`（身份）、`conversation.py`（占位词清洗+城市抽象）、`app.js`（分享+跳登录）

**未做（明确记录）**：图片上传接口 / 热榜与 Coze 打通（agents.external_id 留空位）/
回忆的 AI 总结实际生成 / README 的入口地址更新（/ 已改浏览页）

**遗留问题**：同名区歧义（北京/成都都有「朝阳区」，无上下文时按景区数多的解析）

### 状态

进行中

---

## 20260917_150557_2fc998

- **时间**：2026-09-17 16:36 → **2026-10-15 13:09（仍在进行）**
- **模型 / 来源**：deepseek-v4.1-flash / tui

### 做了什么

**本项目从 0 到 v0.4 的唯一主线 session**（1683 条消息，跨一个月）。

> ⚠️ 注意：这是一个**长会话**，中间经历多次上下文压缩。
> 上下文里曾残留「今天是 09-18」的过期认知，实际已到 10-15。
> 本条记录于 10-15 补写，早前阶段的时间点为事后追溯。

**1. 调研阶段（09-17）**
- 环境排障：curl 全体 000 根因是 Schannel OCSP 吊销检查（加 `--ssl-no-revoke`）
- 数据源实测：北京公共数据开放平台打通，12 数据集 119,518 行；确认 VisitBeijing MCP 域名已死
- analysis.md 15 个条目全查，发现两处数据待核实；三个开源仓库评估（思路可借、代码不可用）
- 找到 ITINERA（EMNLP 2024）并实跑验证核心算法（聚类/TSP/坐标转换）

**2. MVP 建设（09-18）**
- 技术栈定案：FastAPI + SQLite + Jinja2 + Leaflet（评估后弃用 Chainlit）
- 数据入库：212 景区 / 216 交通 / 217 人流
- 动机挖掘（七类）、推荐引擎、地理编码（212/212 成功）、行程编排
- 修两个 bug：8 小时排成 14 小时、跨区折返
- **v0.1** 端到端跑通 → PMS 初始化 → 推送 GitHub public

**3. v0.2 对话重做**
- v0.1 单轮表单太简陋 → 多轮开放对话
- 关键设计：**抽取与回复拆两次独立 LLM 调用**（合成一次时模型会「续写对话」）
- 修 5 个 LLM 行为坑，10 场景测试 9 正确 0 误判
- 前端改聊天界面（左对话 + 右画像）

**4. v0.3 对话-行程闭环**
- AI 通过 function calling 主动生成行程、能「看见」右侧行程、修改需用户确认
- 修 6 个工具调用坑；服务端校验 tool_calls 白名单
- 验收发现：浏览器缓存旧 JS（加版本号）、模型谎称有上海数据（**服务端硬拦**）
- 阿哲验收「全绿」→ 提交 v0.3

**5. v0.4 用户系统与行为分析**
- 邮箱+密码登录（pbkdf2_hmac 20 万次）、HMAC 签名 cookie
- 会话打 user_id 标签，**所有查询强制 `AND user_id=?`**
- 11 种行为事件 append-only
- `/admin` 看板 + ADMIN_TOKEN 门禁
- **阿哲定的两条硬约束**：不能强制注册（匿名可完整用）；匿名不落库 + 不存对话原文
- 6 项端到端验证全通过（匿名不落库 / 隔离 / 越权 404 / 未登录 401 / 分析 403）
- 提交 v0.4.0（09-18 18:11）

**6. 停摆与恢复（09-18 → 10-15）**
- v0.4 提交后项目停摆约一个月
- 10-15 恢复：写操作手册（README 重写）+ PMS 建制核对
- 期间发现并纠正「时间认知错误」（上下文残留 09-18，实际 10-15）

### 留下的

**新增文件（v0.4 + 手册阶段）：**
- `app/services/auth.py`、`app/services/analytics.py`
- `app/templates/admin.html`
- `docs/DESIGN-user-system.md`
- `app/scripts/test_auth.py`、`app/scripts/test_user_system_e2e.py`
- `sessions.md`（本文件，补 spec §4.2.2 缺口）

**修改：**
- `app/main.py`（认证/历史/分析路由）、`app/core/db.py`（users/events 表 + 迁移）
- `app/services/conversation.py`（匿名内存会话）、`app/static/app.js`（认证 UI 增量合并）
- `app/static/style.css`、`app/templates/index.html`（登录弹窗 + 历史抽屉）
- `README.md`（重写为操作手册）、`.pms.yml`

**踩过的坑（已记入 .pms.yml avoid）：**
- 数据库迁移顺序：`CREATE TABLE IF NOT EXISTS` 跳过已存在表 → 必须 ALTER TABLE，
  且**依赖新列的索引要放迁移之后**（否则 `no such column`）
- `fetch` 漏 `credentials: 'include'` → cookie 不发送，认不出登录用户
- Starlette 新版 `TemplateResponse(request, name, ctx)` 签名，旧签名报 `unhashable type: 'dict'`
- 别另起新 JS 文件替代旧的（会砍掉已有功能）→ 必须**增量合并**

### 状态

进行中
