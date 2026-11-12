#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模拟景区侧：AI 讲解代理服务端

⚠️ 这是**景区侧参考实现**，不是 wtt 平台侧契约的一部分。
   真合作时景区按自己的工程规范重写；平台侧只提供 /api/context 导出的 context。

为什么要有这一层：
  - 小程序是纯客户端，写死在前端的 key 能被反编译看到（参考文档第 03 节）
  - 密钥只从环境变量 WTT_BUPT_API_KEY 读，绝不写进代码/仓库/前端
  - 平台侧注入的 system prompt 由小程序端带过来，景区侧负责拼知识库 + 调模型

端点：
  POST /api/guide/ask   {system_prompt, knowledge, question?} -> {answer, model, usage}
  GET  /health          -> {ok, llm_configured}
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 密钥：优先环境变量；没设则读桌面上的本地文件（仅本机 MVP）
# ⚠️ 该文件不进仓库、不打印、不进前端
_KEY_FILE = Path(os.environ.get(
    "WTT_BUPT_KEY_FILE",
    "C:/Users/mengzhe/Desktop/wtt_miniapp_bupt.txt"))

API_URL = os.environ.get(
    "WTT_BUPT_API_URL",
    "https://myai.bupt.edu.cn/llm-gw/v1/chat/completions")
MODEL = os.environ.get("WTT_BUPT_MODEL", "deepseek-v4-flash")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

app = FastAPI(title="simulated scenic-area guide proxy", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # MVP 本地演示；生产必须收紧
    allow_methods=["*"],
    allow_headers=["*"],
)


def _key() -> str:
    k = (os.environ.get("WTT_BUPT_API_KEY") or "").strip()
    if not k and _KEY_FILE.exists():
        k = _KEY_FILE.read_text(encoding="utf-8").strip()
    if not k:
        raise HTTPException(500, "未配置 WTT_BUPT_API_KEY（且本地 key 文件不存在）")
    return k


class AskBody(BaseModel):
    system_prompt: str          # 来自 wtt 平台 /api/context 的 injected_system_prompt
    knowledge: str              # 景区知识库片段
    question: str = ""          # 游客追问（MVP 默认问「请讲解这一站」）


@app.get("/health")
def health():
    configured = bool(os.environ.get("WTT_BUPT_API_KEY")) or _KEY_FILE.exists()
    return {"ok": True, "llm_configured": configured, "model": MODEL}


@app.post("/api/guide/ask")
def ask(body: AskBody):
    # 知识库是事实来源：放在 system 里，明确只能依据它作答
    system = (
        body.system_prompt.strip()
        + "\n\n## 景区知识库（唯一事实来源）\n"
        + body.knowledge.strip()
        + "\n\n⚠️ 只能依据上面知识库里的内容讲解。知识库没有的信息一律说"
          "「这个问题建议咨询景区服务台」，不要编造、不要补充你知道的史实。\n"
          "⚠️ 长度：一段话讲完，控制在 150 字以内，务必写完完整句子，不要中途收尾。"
    )
    q = (body.question or "").strip() or "请讲解这一站。"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ],
        "max_tokens": 600,
        # deepseek-v4-flash 非推理模型；给足预算防截断，但不烧思考
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + _key(),
            "Content-Type": "application/json",
            "User-Agent": UA,          # 网关拦非浏览器 UA（见 llm-api-scripting 技能）
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        detail = (e.read() or b"").decode("utf-8", "replace")[:300]
        raise HTTPException(502, f"上游返回 {e.code}：{detail}")
    except Exception as e:
        raise HTTPException(502, f"模型调用失败：{e}")

    try:
        ch = data["choices"][0]
        text = (ch["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, "上游响应里没有回答")
    if not text:
        raise HTTPException(502, "模型返回空内容（可能被 max_tokens 截断）")

    return {
        "answer": text,
        "model": data.get("model", MODEL),
        "usage": data.get("usage") or {},
        "finish_reason": ch.get("finish_reason"),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8200, log_level="info")
