# Coze Studio 实测与二次开发记录

**日期：** 2026-10-20
**目的：** 评估 Coze Studio 能否作为「各地文旅智能体平台」的底座
**结论：** **可作为底座，发布不受限，但前端门户须自建**

---

## 一、结论先行

| 问题 | 答案 |
|---|---|
| 能否私有化部署 | ✅ 可以（Apache-2.0，12 个容器） |
| 发布是否受限 | ❌ **不受限**，有 OpenAPI 渠道（connector 1024） |
| 能否被我们自己的平台调用 | ✅ **可以**，`POST /v3/chat` 已验证 |
| 要把平台做成它的插件吗 | ❌ **不用**。关系是：**我们是主，Coze 是被调用的引擎** |
| 多租户支持 | ⚠️ **表结构支持，产品层锁死，需二开（已验证可行）** |

**一句话：** Coze 提供「搭智能体的引擎」，你的平台提供「租户、路由、质检、门户」。

---

## 二、部署实录

### 2.1 硬性要求（实测，非官方宣称）

| 项 | 官方说 | 实测 |
|---|---|---|
| 机器 | 2 核 4G | **偏乐观**。ES + Milvus 两个就吃掉大半 |
| 容器数 | — | **12 个** |
| 镜像体积 | — | **约 13 GB** |
| 端口 | 8888 | ✅ 正确 |

**12 个容器：**

```
mysql:8.4.5          bitnamilegacy/redis:8.0
bitnamilegacy/elasticsearch:8.18.0    minio
bitnamilegacy/etcd:3.5                milvusdb/milvus:v2.5.10
nsqio/nsq:v1.2.1  × 3（nsqlookupd / nsqd / nsqadmin）
cozedev/coze-studio-server  +  cozedev/coze-studio-web
```

### 2.2 启动

```bash
git clone https://github.com/coze-dev/coze-studio.git
cd coze-studio
cp ./docker/.env.example ./docker/.env
docker compose -f ./docker/docker-compose.yml up -d
```

访问 `http://localhost:8888/sign` 注册。

### 2.3 部署踩的 5 个坑

#### 坑 1：MinIO 官方镜像已不可拉

**现象：** `minio/minio:RELEASE.2025-...` 三个加速器全 `not found`。

**原因：** MinIO 2025 年起停止免费分发，Docker Hub 已撤。

**解法：** 用 Bitnami legacy 版替代并打 tag：

```bash
docker pull docker.1ms.run/bitnamilegacy/minio:latest
docker tag docker.1ms.run/bitnamilegacy/minio:latest \
           minio/minio:RELEASE.2025-06-13T11-33-47Z-cpuv1
```

#### 坑 2：Bitnami 版 MinIO 的 `mc` 路径不同

**现象：** 容器一直 `Waiting for MinIO to be ready...`，健康检查失败。

**原因：** compose 里 entrypoint 硬编码 `/usr/bin/mc`，Bitnami 版在 `/opt/bitnami/minio-client/bin/mc`。

**解法：** 改 `docker/docker-compose.yml` 的 minio 段，PATH 补上并去掉绝对路径：

```yaml
    entrypoint:
      - /bin/sh
      - -c
      - |
        export PATH=$$PATH:/opt/bitnami/minio-client/bin
        (
          until (mc alias set localminio http://localhost:9000 $${MINIO_ROOT_USER} $${MINIO_ROOT_PASSWORD}) do
            echo "Waiting for MinIO to be ready..."
            sleep 1
          done
          mc mb --ignore-existing localminio/$${STORAGE_BUCKET} || true
          ...
        ) &
        exec minio server /data --console-address ":9001"
    healthcheck:
      test: ['CMD-SHELL', 'export PATH=$$PATH:/opt/bitnami/minio-client/bin; mc alias set health_check http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} >/dev/null 2>&1 && mc ready health_check']
```

#### 坑 3（最隐蔽）：容器继承宿主机代理，导致 etcd/Milvus 起不来

**现象：**

```
etcd 日志：dial tcp 127.0.0.1:7897: connect: connection refused
milvus：  init with etcd failed: context deadline exceeded → panic
```

**原因：** 宿主机有 `HTTP_PROXY=http://127.0.0.1:7897`（Clash）。容器**继承了这个变量**，但**容器内的 127.0.0.1 是容器自身**，不是宿主的 Clash。于是 etcd 的集群通信被发往一个不存在的代理。

**解法：** 在 `docker/.env` 末尾加（compose 会注入所有服务）：

```bash
http_proxy=
https_proxy=
HTTP_PROXY=
HTTPS_PROXY=
no_proxy=*
NO_PROXY=*
```

**⚠️ 这个坑同样影响 Go 编译** —— `docker run` 编译时也要 `-e HTTP_PROXY=` 清空。

#### 坑 4：`ALLOW_REGISTRATION_EMAIL` 为空 → 没人能进管理后台

**现象：** `/api/admin/config/model/list` 返回 401。

**原因：** 管理员权限**不存数据库**，靠环境变量 `ALLOW_REGISTRATION_EMAIL` 里列出的邮箱判定。为空 = 无管理员。

**解法：**

```bash
# docker/.env
export ALLOW_REGISTRATION_EMAIL="admin@yourdomain.com"
```

#### 坑 5：编译无声失败

**现象：** `go build` 打印 `DONE`，exit 0，但 `output/bin/` 是空的。

**原因：** `head -20` 吞掉了错误；`output/bin` 目录不存在时 `-o` 静默失败。

**解法：** 先 `mkdir -p output/bin`，并且**永远验证产物**：

```bash
ls -l output/bin/hertz_service          # 看时间戳
grep -c "新代码里的字符串" output/bin/hertz_service   # 看内容
```

---

## 三、多租户：产品层锁死，表结构支持

### 3.1 原始状态

**数据库完全按多租户设计：**

```sql
space       (id, owner_id, name, description, icon_uri, created_at, ...)
space_user  (space_id, user_id, role_type)   -- 1=owner 2=admin 3=member
```

**所有业务表都带 `space_id`：**
`app_draft` / `app_release_record` / `knowledge` / `knowledge_document` /
`plugin` / `prompt_resource` / `single_agent_draft` / `single_agent_version` /
`draft_database_info` / `online_database_info` / `template`

**但产品层锁死了三处：**

| # | 位置 | 原文 | 问题 |
|---|---|---|---|
| 1 | `application/user/user.go` | `TeamSpaceNum: 0` / `MaxTeamSpaceNum` 缺省 | 前端拿到的上限是 0 |
| 2 | `space` 表 | **根本没有 `space_type` 列** | 团队/个人无法区分 |
| 3 | `domain/user/service/user_impl.go` → `spacePo2Do()` | `SpaceType: userEntity.SpaceTypePersonal` | **每个 space 都被写死成「个人空间」** |
| 4 | 全项目 | `CreateSpace` 只在注册时内部调用 | **没有创建空间的 API** |

### 3.2 二次开发（已完成并验证）

**共 ~120 行 Go + 1 条 ALTER TABLE。**

| # | 文件 | 改动 |
|---|---|---|
| 1 | `domain/user/service/user.go` | 接口加 `CreateTeamSpace(ctx, userID, name, description)` |
| 2 | `domain/user/service/user_impl.go` | 实现（复用已有 `SpaceRepo.CreateSpace` + `AddSpaceUser`）；**`spacePo2Do` 改为读真实 `space_type`** |
| 3 | `domain/user/internal/dal/model/space.gen.go` | model 加 `SpaceType int32` 字段 |
| 4 | `application/user/user.go` | **`TeamSpaceNum: 0` → 真实统计**；`MaxTeamSpaceNum` 放开；加 SVC 方法 |
| 5 | `api/model/playground/playground.go` | 手写 `CreateSpaceRequest` / `CreateSpaceResponse`（未走 IDL 生成） |
| 6 | `api/handler/coze/playground_service.go` | 加 `CreateTeamSpace` handler |
| 7 | `api/router/coze/api.go` | 加路由 `POST /api/playground_api/space/create` |
| 8 | **数据库** | `ALTER TABLE space ADD COLUMN space_type TINYINT NOT NULL DEFAULT 1;` |

**核心代码（Domain 层）：**

```go
func (u *userImpl) CreateTeamSpace(ctx context.Context, userID int64,
	name, description string) (space *userEntity.Space, err error) {
	sid, err := u.IDGen.GenID(ctx)
	now := time.Now().UnixMilli()

	err = u.SpaceRepo.CreateSpace(ctx, &model.Space{
		ID: sid, Name: name, Description: description,
		IconURI:   uploadEntity.EnterpriseIconURI,
		SpaceType: 2,                        // 2 = 团队空间
		OwnerID:   userID, CreatorID: userID,
		CreatedAt: now, UpdatedAt: now,
	})

	// 创建者自动成为 owner
	err = u.SpaceRepo.AddSpaceUser(ctx, &model.SpaceUser{
		SpaceID: sid, UserID: userID, RoleType: 1,
		CreatedAt: now, UpdatedAt: now,
	})

	return &userEntity.Space{ID: sid, Name: name, ..., SpaceType: userEntity.SpaceTypeTeam}, nil
}
```

**修复 `spacePo2Do`（关键，否则所有空间都显示为个人）：**

```go
// 改前
SpaceType: userEntity.SpaceTypePersonal,
// 改后
SpaceType: userEntity.SpaceType(space.SpaceType),
```

### 3.3 验证结果

```
team_space_num     : 3        ← 原来是硬编码 0
max_team_space_num : 100      ← 原来是 0

- Personal Space    type=1 (个人)
- 北京文旅局         type=2 (团队)
- 成都文旅局         type=2 (团队)
- 西安文旅局         type=2 (团队)
```

### 3.4 编译与部署流程

```bash
# 1. 编译（依赖第一次要下 ~4 分钟，之后应加持久化缓存）
docker run --rm \
  -v "D:/.../coze-studio/backend:/app" -w /app \
  -e GOPROXY=https://goproxy.cn,direct \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e http_proxy= -e https_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  golang:1.24-alpine \
  sh -c "mkdir -p /app/output/bin && go build -o /app/output/bin/hertz_service ."

# 2. 验证产物（必须！）
ls -l backend/output/bin/hertz_service

# 3. 替换进容器
docker cp backend/output/bin/hertz_service coze-server:/app/opencoze
docker exec coze-server chmod +x /app/opencoze
docker restart coze-server
```

**⚠️ go.mod 要求 Go >= 1.24，1.23 会直接报错。**

**建议加模块缓存持久化（否则每次重下依赖）：**

```bash
-v "coze_gomod:/go/pkg/mod"
```

---

## 四、发布与 API 调用（核心验证）

### 4.1 发布渠道只有两个

```go
// backend/types/consts/consts.go
WebSDKConnectorID = int64(999)    // 网页 SDK
APIConnectorID    = int64(1024)   // OpenAPI
```

**没有微信 / 飞书 / 抖音**（商业版才有）。

**但这不是限制** —— 你的平台**不需要** Coze 帮你发布到第三方，**只需要调它的 API**。

### 4.2 完整调用链（已实测跑通）

```
① 建智能体     POST /api/draftbot/create
                body: {space_id, name, description, icon_uri, visibility}
                → {bot_id}

② 发布         POST /api/draftbot/publish
                body: {space_id, bot_id, connectors: {"1024": {}}}
                → {publish_result: {"1024": {code: 0, publish_result_status: 1}}}

③ 对话         POST /v3/chat
                header: Authorization: Bearer <api_key>
                body: {bot_id: "<字符串>", user_id, stream: false,
                       additional_messages: [{role: "user", content: "...", content_type: "text"}]}
                → {conversation_id, status: "in_progress"}

④ 取结果       GET  /v3/chat/retrieve?conversation_id=&chat_id=
              GET  /v3/chat/message/list?conversation_id=&chat_id=
```

**⚠️ `bot_id` / `space_id` 必须传字符串**（thrift `js_conv`），传数字会报 `bind body failed`。

### 4.3 API Key 认证

**机制：** `Authorization: Bearer <raw_key>`，服务端算 `md5(raw_key)` 后查 `api_key` 表。

```go
apiKey := parseBearerAuthToken(...)
md5Hash := md5.Sum([]byte(apiKey))
apiKeyInfo, err := openauth.OpenAuthApplication.CheckPermission(ctx, hex.EncodeToString(md5Hash[:]))
```

**⚠️ 开源版没有「创建 API Key」的接口** —— 你得自己做，或者直接插库：

```sql
INSERT INTO api_key (api_key, name, status, user_id, expired_at, created_at, updated_at, last_used_at, ak_type)
VALUES (MD5('<raw_key>'), 'name', 0, <user_id>, 0, <now_ms>, <now_ms>, 0, 0);
```

**`status = 0` 表示正常，`ak_type = 0`。**

### 4.4 模型配置

**支持的 provider：** 豆包 / Claude / Deepseek / Gemini / Ollama / OpenAI / Qwen

**⚠️ 没有 GLM**，虽然 `ModelClass` 枚举里有 `GLM = 13`，但**builder 未实现**，会报：

```
create model builder failed: model class GLM not supported
```

**解法：用 OpenAI 兼容类（`model_class = 1`）指向智谱端点。**

```json
POST /api/admin/config/model/create
{
  "model_class": 1,
  "model_name": "glm-4-flash",
  "enable_base64_url": false,
  "connection": {
    "base_conn_info": {
      "base_url": "https://open.bigmodel.cn/api/paas/v4",
      "api_key": "<ZHIPU_KEY>",
      "model": "glm-4-flash"
    },
    "openai": {"by_azure": false, "api_version": ""}
  }
}
```

**✅ 实测创建成功（model id 100002）。**

---

## 五、能做什么 / 不能做什么

### ✅ 现成可用

| 能力 | 位置 |
|---|---|
| 智能体创建/编辑/发布 | `/api/draftbot/*` |
| 工作流可视化编排 | 前端画布 |
| 知识库（RAG） | `/open_api/knowledge/document/*` |
| 插件 | `/api/plugin_api/*` |
| 对话 API | `/v3/chat` |
| Web SDK 嵌入 | connector 999 |
| 多租户（改造后） | `/api/playground_api/space/*` |

### ❌ 缺的（你要自己补）

| 缺口 | 说明 |
|---|---|
| **前端门户** | 开源版前端**没有团队空间 UI**（`grep` 零命中），也没有「创建空间」入口 |
| **API Key 管理** | 无创建接口 |
| **审核角色** | 只有 owner / admin / member，没有「能编辑不能发布」 |
| **准入质检** | 完全没有 |
| **bot_id 路由表** | 哪个城市 → 哪个 bot，要你自己维护 |
| **跨 space 调用** | `MultiAgentRecognize` 有基础，但能否跨 space 未验证 |

---

## 六、架构建议

```
┌─────────────────────────────────────────────────┐
│  你的平台（主）                                  │
│  · 文旅局账号 / 租户管理                          │
│  · bot_id 路由表（城市 → 智能体）                 │
│  · 准入质检（数据完整性 / 可复现 / 不编造）        │
│  · 动机七类统一话术                               │
│  · 平台门户（上传数据、看报告）                    │
└──────────────────┬──────────────────────────────┘
                   │ Authorization: Bearer <key>
                   │ POST /v3/chat  { bot_id, messages }
                   ▼
┌─────────────────────────────────────────────────┐
│  Coze Studio（引擎）                              │
│  · space = 一个文旅局（已验证可多建）              │
│  · 文旅局在里面搭智能体 / 拖工作流 / 传知识库       │
│  · 发布到 connector 1024                         │
└─────────────────────────────────────────────────┘
```

**关系要点：**

- **不是你做成它的插件** —— 反过来
- **Coze 的发布渠道你一个都不用** —— 只调 API
- **前端可以完全不碰** —— 用 Coze 原始界面给文旅局用，你的门户只做管理和路由

---

## 七、当前部署位置

| 项 | 值 |
|---|---|
| 路径 | `D:/fs/workspace/coze-studio-test/coze-studio` |
| 地址 | http://localhost:8888 |
| 测试账号 | `admin@local.test` / `Test123456` |
| 原版二进制备份 | `coze-studio/opencoze.orig` |
| compose 原配置备份 | `docker/docker-compose.yml.orig` |
| **二开 patch** | `docs/research/coze-studio-multitenant.patch`（13KB，7 个文件） |

**恢复二开：**

```bash
cd coze-studio
git apply /path/to/coze-studio-multitenant.patch
# 并执行数据库迁移
docker exec coze-mysql mysql -uroot -proot opencoze -e \
  "ALTER TABLE space ADD COLUMN space_type TINYINT NOT NULL DEFAULT 1 COMMENT '1=personal 2=team';"
```

**⚠️ 这是临时测试目录**（不在 `fs` 规范位置，也没进 git）。真要长期用，需要重新规划落点。

---

## 八、下一步可选

1. **写门户** —— 用 Coze 原始 UI 给文旅局，自己做管理后台
2. **建路由表** —— bot_id ↔ 城市，写进 `where_to_travel`
3. **质检脚本** —— 按四条标准打电话测每个已发布智能体
4. **前端二开** —— 硬啃 React + pnpm 构建链（成本最高，收益最低）
