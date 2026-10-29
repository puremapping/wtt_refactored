# 同步对话接口改流式（SSE）技术方案

> 针对 `wtt_refactored`：FastAPI 0.162 + Starlette 1.10 + uvicorn 0.54、Python 3.13、
> 原生 JS（无构建链）、`POST /api/chat` 同步一次性返回。
>
> 本文每个结论都在本仓库里跑过。可执行原型在 `spike_sse_stream/`，
> `node spike_sse_stream/_ui_test.mjs` 会真的开 headless Chrome 点前端，15/15 通过。

---

## 结论先行

| 问题 | 结论 |
|---|---|
| 1. SSE / WebSocket / chunked 选哪个 | **SSE（`text/event-stream`）**，但用 `fetch`+`ReadableStream` 消费，不用 `EventSource`。WebSocket 在这个场景是纯负担（见 §1） |
| 2. 生成器怎么 yield | 业务层 yield **dict 事件**，SSE 线格式只在 ASGI 边界拼一次；必须带**终止帧**、心跳、`X-Accel-Buffering: no` |
| 3. 同步接口留不留 | **留**，改成「抽干同一份事件流」的消费器。逻辑一份，零分叉 |
| 4. 前端怎么绕 EventSource 限制 | `fetch` + `ReadableStream` + 30 行手写 SSE 解析器。Chrome 43+/Safari 10.1+/Firefox 65+ 支持（ReadableStream 本体）；**Safari 15.4 以下**没有 `TextDecoder` 的 `stream:true`，需 polyfill |
| 5. 流中途异常 | 三层兜底：① 终止帧 `event: error` ② 流 EOF 但没收到终止帧 ③ `catch` 兜底。三者都必须把 UI 落到终态，并 `finally` 解锁输入框 |
| 6. 同步函数改造模式 | 见 §6。**推荐「同步生成器 + 消费器」**，不要为流式把整链 async 化 |

**最重要的一个判断**：这个需求真正的难点不是 SSE，而是**「工具轮没有正文可流」**。
真实 GLM 实测（`spike_openai_tools.py`）：模型决定调工具时 `content` 是空的。

```
[plain]  chunks=7  text_len=7  tool_calls=[]
[tool]   chunks=2  text_len=0  tool_calls=[{"name":"generate_itinerary","args":{"hours":4}}]
```

所以「正文流式」这条路对**工具轮天然无内容**。过程面板（步骤/工具/路由）才是
主要的实时性来源 —— 这恰好也是需求里要的可折叠面板。

---

## 1. SSE vs WebSocket vs 纯 chunked

### 1.1 对比

| 维度 | SSE | WebSocket | chunked（非 SSE 的裸流） |
|---|---|---|---|
| 协议 | HTTP/1.1 分块或 h2 | 升级握手，独立协议 | HTTP/1.1 |
| 方向 | 单向（服务端→客户端） | 双向 | 单向 |
| 自动重连 | ✅ 内置 + `Last-Event-ID` | ❌ 自己写 | ❌ |
| 消息边界 | ✅ `\n\n` 天然分帧 | ✅ 帧 | ❌ **字节流，要自己设计长度前缀** |
| FastAPI 实现 | `StreamingResponse` 一行 | `@app.websocket` + 会话生命周期 + 心跳 + 并发管理 | 同 SSE，但解析在浏览器更难 |
| 反代/网关 | 需要关缓冲，少数老代理会拦 | 需 Upgrade 头透传，某些 WAF/CDN 直接断 | 同 SSE + 更易被缓冲 |
| 对本项目 | **合适** | 过重 | 没有好处 |

**WebSocket 不适用的具体理由**（不只是"用不上"）：

1. 它绕开了 FastAPI 的依赖注入链 —— 本项目 `/api/chat` 依赖
   `Depends(current_user_optional)`（cookie 会话）和 `SlidingWindowLimiter`（BUG-7 限流）。
   WS 端点里要**手写**这两份逻辑，等于给「匿名严/登录宽限流」开了第二条实现路径，
   两套阈值迟早分叉。
2. WS 连接是长生命周期对象。本场景每轮对话是一条独立请求，一问一答完就结束。
   用 WS 就得自己管「这个连接属于哪个 session、断线了要不要重放」—— SSE 靠
   HTTP 语义白拿。
3. 部署侧：现在 `uvicorn` 单进程；将来加 nginx 时 WS 要多配 `proxy_set_header
   Upgrade`，SSE 只要一行 `proxy_buffering off`。

**纯 chunked（不带 SSE 分帧）的问题**：浏览器 `ReadableStream` 给你的是
**任意切分的字节块**。实测看到一个事件被劈成两半是常态（本原型里
`_ui_test.mjs` 采样到长度 2,3,6,9…，说明每块大小不定）。不带 `\n\n` 分帧就必须
自己造长度前缀协议，等于重新发明 SSE 且更难调试。

### 1.2 FastAPI 里的实现成本与坑

```python
from fastapi.responses import StreamingResponse

return StreamingResponse(gen(), media_type="text/event-stream", headers={
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",     # ← nginx 不关这个，流会攒到最后一次性吐出
    "Connection": "keep-alive",
})
```

**坑清单（都实测过）**：

| 坑 | 症状 | 处置 |
|---|---|---|
| `X-Accel-Buffering` 缺失 | 本地开发看着正常，上了 nginx 变成"转圈 8 秒然后整段出现" | 必须加，且 `Cache-Control` 带 `no-transform`（否则某些 CDN 会 gzip 缓冲） |
| gzip 中间件 | 同上，`GZipMiddleware` 会缓冲整个 response | **SSE 路由要排除** gzip（本项目目前没装，加的时候注意） |
| `media_type` 写成 `application/json` | 浏览器不按流处理 | `text/event-stream; charset=utf-8` |
| 没发任何字节 | fetch 的 `response` promise 不 resolve → 前端"连接中"一直不结束 | **先发一帧 `hello`** 再开始干活 |
| 头已发出后抛异常 | HTTP 状态码锁死 200，用户看不到 500 | 错误只能走终止帧，前端必须实现该分支 |
| `StreamingResponse` 里抛异常 | Starlette 直接断流，**无任何终止信号** | 生成器内必须有 `try/except` → `yield error帧` → `return` |
| uvicorn 0.54 / ASGI spec 2.4 | 没有独立断线监听协程（`stream_response` 只在 `send()` 抛 `OSError` 时知道客户端走了） | 心跳要短（3–15s），长时间无事件时不能假设客户端还在 |

Starlette 1.10 的实际实现（`inspect.getsource`）：

```python
if spec_version >= (2, 4):
    try:
        await self.stream_response(send)     # ← 无 listen_for_disconnect
    except OSError:
        raise ClientDisconnect()
```

---

## 2. 生成器里怎么 yield 事件

### 2.1 分层：dict 事件 → SSE 线格式，只转换一次

业务层不认识 SSE，只产出 dict；线格式在端点里拼。

```python
# 业务层（services/conversation/stream.py）
yield {"kind": "step", "name": "extract", "status": "start", "label": "理解你的想法"}
yield {"kind": "token", "target": "reply", "text": "后"}
yield {"kind": "tool", "name": "generate_itinerary", "args": {...}, "status": "running"}
yield {"kind": "done", "result": {...}}      # 与老 /api/chat 完全同构

# 端点层（routers/chat.py）
def sse(ev: dict) -> bytes:
    return f"event: {ev['kind']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n".encode()
```

好处：`done.result` 与现有同步接口的响应体结构一致 → 前端渲染逻辑几乎不用改，
只多一个「过程面板」的分支。而且这套事件将来换 WebSocket 也能直接复用。

### 2.2 事件设计（本项目的具体字段）

| kind | 何时发 | 关键字段 | 前端用途 |
|---|---|---|---|
| `hello` | 立刻 | — | 让 response 头与首字节尽快落地 |
| `route` | 路由判定后 | `engine`/`label`/`reason` | 面板显示「谁在答」（对应 `delegated_to`） |
| `step` | 每阶段开始/结束 | `name`(extract/reply/tools)、`status`、`detail` | 面板主骨架 |
| `token` | 正文/推理增量 | `target`(`reply`/`reasoning`)、`text` | reply→气泡打字机；reasoning→面板 `<pre>` |
| `profile` | 画像合并后 | `profile`、`ready` | 右侧画像面板**提前**更新 |
| `tool` | 工具执行前后 | `name`、`args`、`status`、`ms` | 折叠面板里的工具条目 |
| `decision` | 治理动作发生时 | `type`、`label` | **见 §2.4，最重要的一条** |
| `done` | 收尾 | `result`（与老接口同构） | 一切以它为准 |
| `error` | 任意阶段失败 | `message`、`code` | **终止帧** |

注释行 `: ping\n\n` 做心跳，两端都要忽略（手写解析器里 `line.startsWith(':')`）。

### 2.3 异常处理模板

```python
async def body():
    terminal = False
    try:
        async for ev in chat_events(...):
            yield sse(ev)
            if ev["kind"] in ("done", "error"):
                terminal = True
                return
        if not terminal:                 # 生成器悄悄 return 了
            yield sse({"kind": "error", "code": "NoTerminalEvent",
                       "message": "上游没有给出结果"})
    except asyncio.CancelledError:
        raise                            # 客户端断开：别吞，交给 ASGI
    except Exception as e:               # noqa: BLE001
        yield sse({"kind": "error", "code": type(e).__name__,
                   "message": str(e)})
```

**注意 `except Exception` 里不要再 yield 与它无关的事件**；`error` 之后立刻 return。

### 2.4 必须设计进去：`decision` 事件

现有 `orchestrator.chat()` 里有大量**隐式治理**：

- `_sanitize_tool_calls()` 把模型的工具调用拦掉
- 数据边界检查把 `generate_itinerary` 过滤掉并改写话术（"我目前只有北京的景点数据"）
- 反向补齐：用户说"生成行程"但模型没调工具 → 强制补一个 `forced: True`
- 模型只调工具没写正文 → 二次调用逼它说话

同步接口里这些全部无声发生。**流式化后如果不显式 emit，用户会看到
"我让它排行程，它却在讲别的"** —— 这是比"没有实时输出"严重得多的体验倒退。

```python
yield {"kind": "decision", "type": "tool_no_text",
       "label": "模型只调工具没写正文，正文由兜底二次调用生成"}
yield {"kind": "decision", "type": "boundary",
       "label": f"{dest}不在数据覆盖范围"}
```

面板折叠时的摘要直接来自这些：`第 2 轮 · 1 个工具 · generate · 正文来自兜底`
（本原型实测输出）。

### 2.5 断线与"白烧钱"

实测链路：客户端中途关页 → uvicorn 取消 SSE 协程 → `finally` 里 cancel 上游 task。
`_disconnect_probe.py` 验证 0.48s 内客户端侧断开，服务端协程随之取消。

**但同步线程池不行**：`asyncio.to_thread` 的任务**默认不可取消**。
实测：取消协程后 300ms，工作线程仍存活、队列积压 15 条 —— 那就是继续烧的 GLM 钱。

```
== 不用 bridge.stop() 会怎样 ==
   取消后 300ms 线程存活=True 队列积压=15 ← 这就是白烧的钱
== 用 bridge.stop() ==
   stop 后线程存活=False, join 耗时 0.02s
```

→ 走同步方案时，`finally: bridge.stop()` 是**强制项**，写在 §6。

---

## 3. 同步接口留不留？怎么不分叉

**留。** 理由：

1. 它是公开契约，`tests/test_agent_routing.py` 有 8 个用例直接 `client.post("/api/chat")`
2. 非流的调用方（未来的 CLI、第三方）不需要过程信息
3. 降级路径：老浏览器 / 反代不支持流式时，前端可以回落到它

**不分叉的唯一做法：同步接口变成消费器。**

```python
def chat(session_id, user_text, llm=None, ...):
    """对外签名与行为完全不变。内部抽干同一份事件流。"""
    result = None
    for ev in chat_events(session_id, user_text, llm=llm, ...):
        if ev["kind"] == "done":
            result = ev["result"]
        elif ev["kind"] == "error":
            raise RuntimeError(ev["message"])     # 保持老接口「抛异常→500」语义
    return _Conv(result)
```

关键是最后那行：**错误语义必须保持「抛异常」**，否则 `routers/chat.py` 现有的
`try/except → JSONResponse(500)` 就接不到错误了。

路由层两种写法并存（可以是一个路由里按 `Accept` 分流）：

```python
@router.post("/api/chat")
async def chat(request, user=Depends(current_user_optional)):
    ...限流 + 参数校验（这段两头共用，且必须放在开流之前，才能返回真 400/429）...
    if "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(body(), media_type="text/event-stream", headers=SSE_HEADERS)
    return await run_sync(...)        # 老路径
```

> ⚠️ 限流与参数校验**必须在返回 StreamingResponse 之前做完**。一旦开始 yield，
> 就只能返回 200；429/400 会变成「流里的一帧 error」，前端得二次解析。

---

## 4. 前端不引框架，怎么绕 EventSource

### 4.1 EventSource 的三个硬限制（本项目全中）

| 限制 | 本项目的具体损失 |
|---|---|
| **只能 GET** | 对话正文得塞 query string → 进 access log、URL 长度上限、中文编码 |
| **不能带自定义 header** | 加 CSRF / `Accept` / 未来的 Bearer 就没法用 |
| **拿不到 status 和 header** | 401/429 全被它当成"网络错误"重连，无法区分 |

再加上：`EventSource` 出错后**自动重连**（这对一次性对话是灾难 —— 会重复触发 LLM），
而且没有可靠的关闭时机（`close()` 在 error 回调里调用会漏）。

### 4.2 用 fetch + ReadableStream（推荐）

```js
const resp = await fetch('/api/chat/stream', {
  method: 'POST',
  credentials: 'include',                                  // ← cookie 会话必须
  headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
  body: JSON.stringify({ text, session_id: sessionId }),
  signal: ctrl.signal,                                     // ← 可中断
});
if (!resp.ok) { /* 头发出前的 400/429：正常读 json */ }
```

解析器（30 行，无依赖）：

```js
async function* sseEvents(resp) {
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = '', ev = { event: 'message', data: null, id: null };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });   // ← 关键：多字节字符跨块安全
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      let line = buf.slice(0, i); buf = buf.slice(i + 1);
      if (line.endsWith('\r')) line = line.slice(0, -1);   // ← CRLF 兼容
      if (line === '') {
        if (ev.data !== null) yield { ...ev, data: JSON.parse(ev.data) };
        ev = { event: 'message', data: null, id: null };
        continue;
      }
      if (line.startsWith(':')) continue;          // 心跳注释
      const c = line.indexOf(':');
      const field = c === -1 ? line : line.slice(0, c);
      let val = c === -1 ? '' : line.slice(c + 1);
      if (val.startsWith(' ')) val = val.slice(1);
      if (field === 'event') ev.event = val;
      else if (field === 'data') ev.data = (ev.data === null ? '' : ev.data + '\n') + val;
    }
  }
}
```

**三个必踩的坑**：

1. **chunk 边界 ≠ 行边界**。不保留 `buf` 残余会把一条事件劈成两条 JSON 解析失败。
2. **UTF-8 多字节跨块**。中文一个字 3 字节。`dec.decode(value, {stream:true})`
   是必须的；不加会把中文字符变成 `�`。
3. **`\r\n` vs `\n`**。safari 某些情况、以及自建代理可能补 `\r`。

### 4.3 浏览器兼容性（2026 年视角）

| API | Chrome | Safari | Firefox |
|---|---|---|---|
| `fetch` + `body.getReader()` | 43+ | 10.1+ | 65+ |
| `TextDecoder({stream:true})` | 全 | **15.4+** | 全 |
| `ReadableStream` async iterate (`for await`) | **不支持** | 不支持 | 不支持 |

→ 所以解析器**不要**写 `for await (const chunk of resp.body)`，要写
`reader.read()` 循环（原型里就是这么写的，`_ui_test.mjs` 在真 Chrome 里跑通）。
Safari 15.4 以下的占比现在可忽略；如果真需要，加个 `TextDecoder` polyfill 或
退回同步接口。

### 4.4 可折叠过程面板的最小实现

结构（无框架、无虚拟 DOM）：

```html
<div class="proc" data-open="0">        <!-- 折叠状态放 dataset，CSS 控制 -->
  <button class="proc-head">▸ <span class="sum">正在处理…</span></button>
  <div class="proc-body">…步骤/工具/决策…</div>
</div>
```

```css
.proc-body { display: none; }
.proc[data-open="1"] .proc-body { display: block; }
.proc[data-open="1"] .chev { transform: rotate(90deg); }
```

要点（都在原型里验证过）：

1. **正文气泡挂在面板外侧**，不是面板内部 —— 折叠面板不能把正文一起藏起来。
   `_ui_test.mjs` 专门测了 `done` 用权威全文覆盖：
   `check('正文：done 用权威全文覆盖（未重复拼接）', len=52)`。
2. **进行中默认展开，完成后自动折叠**（实测 `open=0`），摘要给结论：
   `第 2 轮 · 1 个工具 · generate · 正文来自兜底`。
3. **`textContent` 而非 `innerHTML`**。流式增量拼 HTML 会因未闭合标签导致
   重排闪烁 + XSS 面。面板里的 `<pre>` 同理。
4. **不要每个 token 都 `scrollIntoView({smooth})`** —— 会产生滚动抖动和掉帧。
   原型里只 `window.scrollTo`，且只在必要时。
5. 打字机效果：正文按 token 到达就直接 append。若后端只能整段给（见 §6），
   前端用 `setInterval` 分批显示，但要**允许被打断**（下一块到达立刻刷全）。
6. **折叠状态不要因重渲染丢失**：用 `data-open` 属性而非 class 切换，
   `_ui_test.mjs` 实测点击后 `dataset.open === '1'` 可复现。

---

## 5. 流中途异常，前端怎么不永远转圈

这是最有价值的实战部分。**一个终止帧不够，要三层兜底**：

```js
let terminal = false;

try {
  const resp = await fetch(...);
  if (!resp.ok) throw new Error(...);              // ① 头发出前的错误

  for await (const ev of sseEvents(resp)) {
    switch (ev.data.kind) {
      case 'done':  terminal = true; renderFinal(ev.data.result); break;
      case 'error': terminal = true; showError(ev.data.message);  break;
      // ...
    }
  }
  if (!terminal) showError('连接提前结束，没收到完整结果');   // ② EOF 但无终止帧
} catch (e) {
  if (e.name === 'AbortError') showError('已取消');
  else if (!terminal) showError(e.message);                    // ③ 网络异常
} finally {
  busy = false;                                   // ④ 无条件解锁
  sendBtn.disabled = false;
}
```

**为什么每一层都必要**（都有实测剧本）：

| 场景 | 后端实际行为 | 不加这层会怎样 |
|---|---|---|
| 抽取阶段上游超时 | 发 `hello` → `error` 帧，正常 close | — |
| 正文流到一半上游 502 | 已发 9 个 token → `error` 帧 | — |
| 生成器被提前 return | 干净 EOF，**无任何终止帧** | **永远转圈** |
| nginx `proxy_read_timeout` 切断 | 干净 EOF，无终止帧 | **永远转圈** |
| uvicorn 进程被杀 | fetch 抛 `TypeError` | **永远转圈** |
| 用户点取消 | `AbortError` | 转圈 + 输入框锁死 |

`_ui_test.mjs` 对应的 15 个断言里，有 4 个专门测这些：

```
PASS  失败：显示错误框（不是永远转圈）  — 抽取调用超时（模拟）
PASS  失败：面板保持展开且头部标红  — ✕ 出错了
PASS  失败：输入框已解锁
PASS  中途失败：保留已流出的正文  — 保留 9 字
PASS  中途失败：有错误提示 + 解锁  — 上游在第 9 个 token 后断开（模拟）
```

**错误 UI 的两条原则**：

1. **保留已流出的正文**，加省略号，而不是清空。用户已经读了一半。
2. **面板保持展开且头部标红**，不要静默折叠 —— 折叠状态下用户看不到错误。

前端「取消按钮」也要实现：`ctrl.abort()` + `finally` 解锁。没它的话，
一个卡住的请求会锁死输入框直到用户刷新。

---

## 6. 同步函数改生成器的重构模式

### 6.1 三种模式

| 模式 | 改动量 | 同步接口 | 测试 | 能否 token 级流 |
|---|---|---|---|---|
| A. 同步生成器 + 消费器 | 中 | 保留，行为不变 | 不改 | ❌ 只能「每步一帧」 |
| B. 全链路 async | 大 | 需要 `run_sync` 包 | FakeLLM 全改 | ✅ |
| C. 同步生成器 + 线程桥 | 中 | 保留 | 不改 | ❌ 同 A |

**推荐 A**（`sync_generator_refactor.py` 可跑）。核心是三条机械规则，不需要重写业务：

**规则 ①：把「每完成一步 → 一个事件」插进现有代码，`return` 改成 `yield done`。**

```python
# 改前
def chat(...) -> Conversation:
    ...  # 第 1..8 步
    save_session(conv, user_id)
    return conv

# 改后
def chat_events(...) -> Iterator[dict]:
    ...
    yield {"kind": "step", "name": "extract", "status": "start"}
    extracted = llm.json_chat(...)
    yield {"kind": "step", "name": "extract", "status": "done", "fields": [...]}
    ...
    save_session(conv, user_id)
    yield {"kind": "done", "result": _public(conv)}     # ← 结构与老接口一致
```

**规则 ②：同步接口变成抽干器**（见 §3），签名和行为不变。

**规则 ③：LLM 调用点加 `on_token=None` 回调。**

```python
def chat_raw(self, messages, temperature=0.3, model=None,
             tools=None, tool_choice="auto", on_token=None):
    ...
    if on_token:                        # ← 新增，默认 None = 行为不变
        stream = self.client.chat.completions.create(..., stream=True)
        for ch in stream:
            if ch.choices[0].delta.content:
                on_token(ch.choices[0].delta.content)
        ...
```

### 6.2 不破坏已有测试的关键

现有测试是这么注入假货的（`tests/test_agent_routing.py:247`）：

```python
monkeypatch.setattr(orch, "LLM", lambda: fake)
```

所以只要 `chat()` 的**签名与返回类型不变**、`LLM.chat_raw()` 只**新增可选 kwarg**，
12 个测试文件一行都不用改。

⚠️ 唯一真实风险：`_sanitize_tool_calls` / `_try_delegate` 这类**纯函数**最好是
「输入相同 → 输出相同」。如果重构时顺手把状态塞进 `conv.profile`（像现在的
`_delegated_to` / `_turns` / `_extract_error`），就把「显式参数」变成了「隐式状态」，
测试会因执行顺序出现偶发失败。**重构期间不要顺手改这部分。**

### 6.3 同步方案的硬限制（必须提前告知）

**同步生成器不能在 LLM 调用内部 yield。** `on_token` 回调只能攒字符串，
攒完才能 yield：

```python
buf = []
msg = llm.chat_raw([], tools=..., on_token=buf.append)   # 阻塞到完
yield {"kind": "token", "target": "reply", "text": "".join(buf), "whole": True}
```

→ 结果：**步骤/工具是真实时，正文是「整段到达 + 前端打字机动画」**。
`sync_generator_refactor.py` 里已经用 `whole: True` 标记区分，前端可据此
决定"直接显示"还是"播放动画"。

要做到**真 token 级**，只需把 `app/services/llm.py` 一个文件改成 async
（`openai.AsyncOpenAI`），编排逻辑（`orchestrator.py` 的 8 步业务）**不用动** ——
用 `stream_core.py` 的 `chat_events()` 那种 async 生成器即可。
`chat()` 同步接口用 `anyio.to_thread.run_sync` 或保留同步 LLM 双实现兜住。

### 6.4 如果走同步 + 线程桥

`sync_bridge.py` 可跑。用 `SyncEventBridge` 把同步生成器推到异步 SSE：

```python
bridge = SyncEventBridge(chat_events_sync(...))
async def body():
    try:
        while True:
            ev = await asyncio.to_thread(bridge.get, 15)
            if ev is None:
                if bridge.finished:
                    yield sse({"kind": "error", "code": "NoTerminalEvent"})
                    return
                yield b": ping\n\n"
                continue
            yield sse(ev)
            if ev["kind"] in ("done", "error"):
                return
    finally:
        bridge.stop()          # ⚠️ 强制：不写就白烧 LLM 钱（实测见 §2.5）
```

---

## 7. 落地步骤（建议顺序）

1. **`app/services/llm.py`**：`chat_raw` / `json_chat` 加 `on_token=None`，默认行为不变。
   跑一遍现有测试，应该全绿（这一步零风险）。
2. **`app/services/conversation/stream.py`**：新建 `chat_events()` 生成器，
   把 `orchestrator.chat()` 的 8 步照搬过来，插入 `yield`。**先不删老函数。**
3. **`orchestrator.chat()` 改成抽干器**，跑现有测试。这一步是回归验证的关键卡点 ——
   12 个测试文件必须全绿才算重构正确。
4. **`routers/chat.py`** 加 `POST /api/chat/stream`：限流/校验在前，`StreamingResponse`
   在后；`done` 帧复用第 3 步现有的 `result` 组装代码（不要复制一份）。
5. **前端** `app/static/app.js`：加 `sseEvents()` + `makePanel()`；
   `send()` 里 `postJSON` 换成流式读；保留 `postJSON('/api/chat')` 作为降级分支。
6. **测试**：新增 `tests/test_chat_stream.py`，用 `TestClient` 读流（见 §8），
   断言「一定有终止帧」「工具轮不空转」「error 后不再有事件」。

---

## 8. 测试要点

`TestClient` 直接支持流式，**不需要真起服务**：

```python
def test_stream_always_has_terminal_frame(client, monkeypatch):
    fake = FakeLLMFull(fail_at="extract")
    monkeypatch.setattr(orch, "LLM", lambda: fake)
    with client.stream("POST", "/api/chat/stream",
                       json={"text": "想去北京"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        kinds = [json.loads(l[6:])["kind"]
                 for l in r.iter_lines() if l.startswith("data: ")]
    assert kinds[0] == "hello"
    assert kinds[-1] == "error"                     # ← 最关键的一条断言
    assert "done" not in kinds
```

必测的四个用例：

1. 正常对话：`kinds[-1] == "done"` 且 `result` 里字段与老 `/api/chat` 一致
2. 上游失败：`kinds[-1] == "error"`
3. 工具轮：有 `tool` running→ok 两个事件，且 `done.result.tool_calls` 非空
4. **两套接口一致性**：同一输入分别打 `/api/chat` 和 `/api/chat/stream`，
   `done.result` 与同步响应体**逐字段相等**（防分叉的最强回归测试）

---

## 9. 原型文件清单

| 文件 | 作用 |
|---|---|
| `spike_openai_tools.py` | 真实 GLM 流式验证：token 碎片 vs tool_calls 碎片拼装 |
| `stream_core.py` | async 生成器 + 事件总线 + 可控假 LLM（可模拟各阶段失败） |
| `app.py` | FastAPI 端点：SSE 线格式、心跳、`Last-Event-ID`、同步抽干器 |
| `spike_client.html` | 原生 JS：`sseEvents()` 解析器 + 可折叠过程面板 + 三层错误兜底 |
| `sync_bridge.py` | 同步生成器 → 异步流 的线程桥（含"不可取消"实测） |
| `sync_generator_refactor.py` | 同步 `chat()` → 生成器 → 抽干器的完整重构模板 |
| `_ui_test.mjs` | headless Chrome 端到端：15 个断言（流式渐进、折叠、四类失败） |
| `_probe.py` / `_disconnect_probe.py` | 服务端事件流时序列 + 断线行为探针 |

跑法：

```bash
cd D:/fs/workspace/projects/wtt_refactored
.venv/Scripts/python.exe -m uvicorn spike_sse_stream.app:app --port 8077
# 浏览器打开 http://127.0.0.1:8077/spike
node spike_sse_stream/_ui_test.mjs          # 15/15 通过
```

---

## 附录：踩过的坑（都是"看起来能用但生产会出问题"的）

1. **同路径注册两次 GET，先注册的先匹配。** 调试开关我写了个只读端点，结果所有
   写请求都打到它，返回的恰好是默认值 `{"plan":"tool"}`，看上去像成功了 —— 实际上
   场景切换一直没生效，浪费了 3 轮排查。**调试开关做成单一读写端点。**

2. **`emit("decision", kind=...)` 炸出 `TypeError: got multiple values for 'kind'`。**
   业务字段名和事件类型参数撞车。这个异常被外层兜底吞成 `error` 帧，面板上只显示
   「出错了」，日志堆栈指向外层 `except` —— 完全看不出是发事件那一行炸的。
   **事件工厂要用位置参数，payload 禁用同名键，并在 emit 里显式断言。**

3. **`async def` + 只有内部协程、没有 `yield` → 拿到的是 coroutine 不是生成器。**
   `async for` 直接 `TypeError: 'async for' requires an object with __aiter__ method`。
   花了两次迭代才定位。**写流式函数后先 `inspect.isasyncgenfunction()` 自检。**

4. **后台进程 `&` 拒绝 + 残留进程占端口静默失败。**
   新 uvicorn 起不来（`WinError 10048`）但旧进程还在服务，于是"改了代码没生效"。
   **改代码后先 `curl` 一个行为锚点（如 `/api/_mode`）确认新进程在跑。**

5. **心跳 15s 太粗。** 一旦卡住（无事件），前端要等 15s 才发心跳，日志里像死机。
   本原型里改到 3s，排查体验差别巨大。**心跳间隔 = 排查容忍度，不是协议上限。**
