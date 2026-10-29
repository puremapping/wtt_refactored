#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外部智能体的协议适配

## 为什么需要这一层

平台对外的统一协议是：

    POST {"question": "...", "region": "...", "context": {...}}
    返回 {"answer": "..."} 或纯文本

但现成的智能体平台各有一套自己的格式。最典型的是 Dify：

    POST {"inputs": {...}, "query": "...", "response_mode": "blocking", "user": "..."}
    返回 {"answer": "...", "conversation_id": "...", ...}

如果让主流程去分辨对方是哪种，`ExternalAgent` 会迅速变成一堆 if。
所以把「怎么构造请求 / 怎么读响应」抽成协议对象，
`ExternalAgent` 只管转发和容错。

## 加一种新协议

写一个 `Protocol` 子类，注册进 `PROTOCOLS`，其余代码零改动。
不需要改 `ExternalAgent`、不需要改数据库 schema（`protocol` 是文本字段）。

## 为什么不自动嗅探

看 URL 里有没有 `/v1/chat-messages` 之类能猜个八九不离十，但换个部署路径
或加个反代前缀就失效，而且失效时表现为「对方答非所问」而不是报错 —— 很难查。
所以协议**显式存库**，由文旅局在表单里选。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional


class Protocol:
    """协议适配基类

    子类实现两件事：把内部统一入参转成对方的请求体，把对方的响应转成文本。
    """

    key = "generic"
    label = "通用（平台统一协议）"
    description = "我们定义的格式：发 {question, region, context}，收 {answer} 或纯文本"

    def build_payload(self, *, question: str, region: str,
                      context: dict, agent_id: str = "") -> dict:
        return {"question": question, "region": region, "context": context}

    def parse_response(self, raw: Any) -> Optional[str]:
        """从对方响应里抠出回答文本；抠不出来返回 None"""
        text = _as_text(raw)
        if text is None:
            return None

        obj = _try_json(text)
        if isinstance(obj, dict):
            for key in ("answer", "text", "content", "reply", "output"):
                v = obj.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        elif isinstance(obj, str) and obj.strip():
            return obj.strip()

        return text


class DifyProtocol(Protocol):
    """Dify Service API

    端点：POST {base}/v1/chat-messages
    鉴权：Authorization: Bearer app-xxxxx  （应用级 API key，不是账号 token）

    ⚠️ 三个必填/必给字段，缺一个 400：
       - response_mode: blocking（我们要同步拿结果，不能走 streaming）
       - user: Dify 用来区分终端用户，同一 user 共享会话上下文。
               这里用固定的平台标识，避免用户 A 的上下文串到用户 B。
       - inputs: 必须存在，即使为空对象。Start 节点没定义变量时是 {}。
    """

    key = "dify"
    label = "Dify"
    description = "Dify Service API：发 {inputs, query, response_mode, user}，收 {answer}"

    # Dify 用 user 字段划分会话上下文。固定成平台标识，
    # 不让不同游客的对话互相污染。
    USER = "wtt-platform"

    def build_payload(self, *, question: str, region: str,
                      context: dict, agent_id: str = "") -> dict:
        # Dify 的 inputs 对应 Start 节点声明的变量。
        # 我们的 region / context 原样塞进去，用同名变量接收。
        inputs = {}
        if region:
            inputs["region"] = region
        if context:
            inputs["context"] = (json.dumps(context, ensure_ascii=False)
                                 if not isinstance(context, str) else context)

        return {
            "inputs": inputs,
            "query": question,
            "response_mode": "blocking",
            "user": self.USER,
        }

    def parse_response(self, raw: Any) -> Optional[str]:
        text = _as_text(raw)
        if text is None:
            return None

        obj = _try_json(text)
        if isinstance(obj, dict):
            # Dify 出错时返回 {"code": "...", "message": "...", "status": 4xx}
            if obj.get("code") and obj.get("message") and not obj.get("answer"):
                raise RuntimeError(f"Dify 返回错误: {obj.get('code')} "
                                   f"{obj.get('message')}")
            ans = obj.get("answer")
            if isinstance(ans, str) and ans.strip():
                return ans.strip()
            return None

        return None


class CozeProtocol(Protocol):
    """扣子（Coze）开放平台 /v3/chat

    ⚠️ 未实测 —— 这条是照着官方文档写的形状，没有跑通过。
       真要用请先验证，别当成能用的实现。
    """

    key = "coze"
    label = "Coze（未验证）"
    description = "扣子 /v3/chat 格式；未实测，使用前请自行验证"

    def build_payload(self, *, question: str, region: str,
                      context: dict, agent_id: str = "") -> dict:
        return {
            "bot_id": agent_id,
            "user_id": "wtt-platform",
            "stream": False,
            "additional_messages": [
                {"role": "user", "content": question, "content_type": "text"}
            ],
        }

    def parse_response(self, raw: Any) -> Optional[str]:
        text = _as_text(raw)
        if text is None:
            return None
        obj = _try_json(text)
        if isinstance(obj, dict):
            msgs = obj.get("data") or []
            if isinstance(msgs, list):
                for m in reversed(msgs):
                    if isinstance(m, dict) and m.get("role") == "assistant":
                        c = m.get("content")
                        if isinstance(c, str) and c.strip():
                            return c.strip()
        return None


# ──────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────


def _as_text(raw: Any) -> Optional[str]:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _try_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


PROTOCOLS = {p.key: p() for p in (Protocol, DifyProtocol, CozeProtocol)}


def get_protocol(key: Optional[str]) -> Protocol:
    """按 key 取协议实例；不认识的一律退回通用协议

    ⚠️ 不抛异常：库里存了个不知道的协议名（手工改库/版本回退），
       宁可按通用协议试一次，也不要让整条智能体不可用。
    """
    return PROTOCOLS.get((key or "generic").strip().lower(), PROTOCOLS["generic"])


def protocol_choices() -> list:
    """给前端下拉用：[{key, label, description}, ...]"""
    return [{"key": p.key, "label": p.label, "description": p.description}
            for p in PROTOCOLS.values()]


def new_user_id() -> str:
    """预留：将来要按访客区分 Dify 会话时用"""
    return uuid.uuid4().hex[:16]
