# 用户系统与行为分析设计（v0.4）

**日期：** 2026-09-18
**目标：** 用户端登录 + 会话归户 + 数据存档 + 长期行为分析

---

## 一、需求（阿哲原话）

> 用户端登录系统，会话要打上用户标签，做用户隔离，会话数据存档，用于长期的用户行为分析

**后续补充的两条硬约束：**

> 不能强制注册
> 1. 不存（对话原文）
> 2. 匿名都不给归档，聊完就刷新

**已确认的决策：**

| 问题 | 决策 |
|---|---|
| 登录方式 | **邮箱 + 密码**（自己存，pbkdf2） |
| 登录与使用的关系 | **匿名可用，不强制注册**；登录后可保存 |
| 匿名会话 | **不落库**，只存内存，刷新即丢 |
| 对话原文 | **不存**，只存结构化字段 |
| 分析粒度 | 基础 + 采纳行为 + 交互细节 |
| 未登录体验 | 能完整用，生成行程后提示「登录可保存」（不拦） |

---

## 二、核心设计

### 2.1 两条路径

```
匿名访问 ──► 内存会话（进程内 dict + TTL 1h）
              │
              │ 刷新页面 = 丢失
              │ 不写 DB，不记事件
              ▼
登录用户 ──► SQLite（user_id 必填）
              │
              │ 持久化，可查历史，记事件
              ▼
```

**关键：`user_id` 是唯一的判据。** 为空走内存，非空走 DB。

### 2.2 数据模型

```sql
-- 用户
CREATE TABLE users (
  id            TEXT PRIMARY KEY,
  email         TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,     -- pbkdf2_hmac，20 万次迭代
  nickname      TEXT,
  created_at    TEXT NOT NULL
);

-- 会话（只有登录用户才有记录）
ALTER TABLE sessions ADD COLUMN user_id TEXT;
ALTER TABLE sessions ADD COLUMN turn_count INTEGER DEFAULT 0;

-- 行为事件（append-only）
CREATE TABLE events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  user_id    TEXT NOT NULL,        -- 匿名事件不允许写入
  event_type TEXT NOT NULL,
  payload    TEXT,                 -- JSON
  created_at TEXT NOT NULL
);
```

### 2.3 事件类型（11 种）

| 事件 | 何时 | payload |
|---|---|---|
| `session_start` | 首轮对话 | — |
| `user_register` | 注册 | email |
| `user_login` | 登录 | email |
| `message_sent` | 每条消息 | turn, text_len |
| `profile_updated` | 画像变化 | fields |
| `itinerary_generated` | 生成行程 | stops_count, motivation, hours |
| `itinerary_modified` | 落实修改 | action |
| `proposal_accepted` | 接受建议 | action |
| `proposal_rejected` | 拒绝建议 | action |
| `session_end` | 会话结束 | — |

**⚠️ 隐私红线：`message_sent` 只记 `text_len`，不记原文。**

---

## 三、接口

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册（邮箱+密码），签发 cookie |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 退出（清 cookie） |
| GET | `/api/auth/me` | 当前用户（未登录返回 `{user: null}`） |
| DELETE | `/api/auth/account` | 注销账号（级联删数据） |

### 用户数据

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/history` | 我的会话列表（自动按 user_id 过滤） |
| GET | `/api/history/{id}` | 某会话详情（**归属校验**） |
| DELETE | `/api/history/{id}` | 删除某会话（**归属校验**） |

### 分析（内部）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/analytics/report?days=30&token=X` | 完整报告 |
| GET | `/admin` | 看板页面 |

**保护：`ADMIN_TOKEN` 环境变量；未设置 = 接口禁用（不裸奔）。**

---

## 四、安全措施

| 风险 | 措施 |
|---|---|
| 密码泄露 | pbkdf2_hmac + 随机 salt，20 万次迭代 |
| Cookie 伪造 | HMAC-SHA256 签名，含时间戳，篡改即失效 |
| XSS 偷 cookie | `httponly=True` |
| CSRF | `samesite=lax` |
| **越权访问他人会话** | **所有查询强制 `AND user_id=?`** |
| 分析接口裸奔 | ADMIN_TOKEN 门禁，constant-time 比较 |

**§ 越权是最容易漏的**：不能只靠前端不显示，必须每个查询都带 user_id 条件。已实测：乙拿甲的 session_id → 404。

---

## 五、实现要点（踩过的坑）

1. **`sessions` 表的迁移顺序**：`CREATE TABLE IF NOT EXISTS` 对已存在表跳过 → 新列不生效。必须 `ALTER TABLE ADD COLUMN`，且**依赖新列的索引要放在迁移之后**，否则 `no such column`。

2. **`fetch` 必须带 `credentials: 'include'`**，否则 cookie 不发送，后端永远认不出登录用户。

3. **`TemplateResponse` 签名变了**：新版是 `TemplateResponse(request, name, context)`，传旧签名 `(name, {"request": ...})` 会报 `unhashable type: 'dict'`。

4. **匿名会话的内存对象**：`Conversation` 需要 `itinerary` 字段，否则匿名生成的行程无处安放。

---

## 六、未做（有意留着）

- **匿名 → 登录的历史归并**：只归并当前会话，不追溯。多设备匿名无法合并（需设备指纹，MVP 不值得）。
- **密码重置**：需要邮件服务。
- **会话结束的自动标记**：`session_end` 事件定了但没触发点（等有明确"结束"信号再做）。
