#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 客户端封装（GLM-4 Flash，OpenAI 兼容）"""
import json
import re
from typing import Any

from openai import OpenAI

from app.core.config import GLM_API_KEY, GLM_BASE_URL, GLM_MODEL, GLM_MODEL_FALLBACK


class LLM:
    def __init__(self):
        if not GLM_API_KEY:
            raise RuntimeError("未设置 GLM_API_KEY")
        self.client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_BASE_URL)
        self.model = GLM_MODEL

    def chat_raw(self, messages, temperature=0.3, model=None,
                 tools=None, tool_choice="auto"):
        """返回 message 对象（OpenAI 的 ChatCompletionMessage，带 tool_calls）

        注意：返回的是 `choices[0].message`，不是 `choices[0]`。
        message 上有 .content 和 .tool_calls。
        """
        kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        r = self.client.chat.completions.create(**kwargs)
        return r.choices[0].message

    def chat(self, messages, temperature=0.3, model=None, force_json=False) -> str:
        kwargs = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if force_json:
            # GLM 支持 OpenAI 的 json_object 模式 —— 比在 prompt 里要求可靠得多。
            # 实测：不开这个，glm-4-flash 会无视 prompt 里的 JSON 格式要求，
            # 直接回自然语言（长 prompt 下尤其明显）。
            kwargs["response_format"] = {"type": "json_object"}
        r = self.client.chat.completions.create(**kwargs)
        return r.choices[0].message.content or ""

    def json_chat(self, messages, temperature=0.1) -> Any:
        """要求返回 JSON，并做健壮解析

        先试强制 JSON 模式；失败则回退普通模式 + 解析兜底。
        """
        try:
            text = self.chat(messages, temperature=temperature, force_json=True)
            parsed = parse_json(text)
            if parsed is not None:
                return parsed
        except Exception:
            pass
        # 回退：不带 response_format，靠 parse_json 抠
        text = self.chat(messages, temperature=temperature)
        return parse_json(text)


def parse_json(text: str) -> Any:
    """从 LLM 输出里抠出 JSON。

    GLM 常见返回形式：
      1. 纯 JSON
      2. ```json ... ``` 包裹
      3. 前后带说明文字
    """
    if not text:
        return None
    t = text.strip()

    # 剥 Markdown 代码块
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()

    # 直接试
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass

    # 抠第一个 { ... } 或 [ ... ]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = t.find(open_c)
        end = t.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(t[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None
