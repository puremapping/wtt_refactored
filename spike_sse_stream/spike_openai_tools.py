#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""灰盒 spike：验证 OpenAI SDK 流式 + tool_calls 碎片拼装 + 纯文本增量。

不碰项目代码，只证明一件事：流式里正文碎片和 tool_calls 碎片能不能分开、
tool_calls 能不能被拼回完整参数（拼错了就不能走「边流边执行工具」的路径）。
跑法：cd wtt_refactored && .venv/Scripts/python.exe spike_sse_stream/spike_openai_tools.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import GLM_BASE_URL, GLM_API_KEY, GLM_MODEL  # noqa: E402
from app.services.tools import get_tools  # noqa: E402
from openai import OpenAI  # noqa: E402


def _acc_tool_calls(chunks):
    """把流式 tool_calls 碎片拼回完整调用。

    ⚠️ 坑：function.arguments 是**逐字**下发的，不能用 += 到 dict 上，
       必须按 index 累积字符串，最后才 json.loads。
    ⚠️ 坑：index 不保证从 0 连续出现；第一个碎片才带 id/name。
    """
    acc = {}
    for ch in chunks:
        for tc in (ch.choices[0].delta.tool_calls or []):
            slot = acc.setdefault(tc.index, {"name": "", "args": ""})
            if tc.function and tc.function.name:
                slot["name"] = tc.function.name
            if tc.function and tc.function.arguments:
                slot["args"] += tc.function.arguments
    out = []
    for idx in sorted(acc):
        slot = acc[idx]
        try:
            args = json.loads(slot["args"] or "{}")
        except json.JSONDecodeError:
            args = {"__parse_error__": slot["args"]}
        out.append({"name": slot["name"], "args": args})
    return out


def run(messages, tools=None, label=""):
    client = OpenAI(api_key=GLM_API_KEY, base_url=GLM_BASE_URL)
    kw = dict(model=GLM_MODEL, messages=messages, temperature=0.3, stream=True)
    if tools:
        kw["tools"] = tools
        kw["tool_choice"] = "auto"
    stream = client.chat.completions.create(**kw)

    text_parts = []
    reasoning_parts = []
    chunks = []
    n = 0
    for ch in stream:
        n += 1
        chunks.append(ch)
        d = ch.choices[0].delta
        # ⚠️ 推理模型会先把思考放这里；GLM 有些版本也会给 reasoning_content
        rc = getattr(d, "reasoning_content", None)
        if rc:
            reasoning_parts.append(rc)
        if d.content:
            text_parts.append(d.content)

    print(f"\n[{label}] chunks={n}")
    print(f"  text_len={len(''.join(text_parts))} reasoning_len={len(''.join(reasoning_parts))}")
    tcs = _acc_tool_calls(chunks)
    print(f"  tool_calls={json.dumps(tcs, ensure_ascii=False)}")
    print(f"  text_head={''.join(text_parts)[:120]!r}")
    if reasoning_parts:
        print(f"  reasoning_head={''.join(reasoning_parts)[:120]!r}")
    return tcs, "".join(text_parts)


if __name__ == "__main__":
    # 用例 1：普通对话（应只有正文，无 tool_calls）
    run([{"role": "user", "content": "北京有什么人少又适合拍照的地方？一句话。"}],
        tools=get_tools(has_itinerary=False), label="plain")
    # 用例 2：明确要工具（应出 tool_calls，正文可能为空）
    run([{"role": "user", "content": "帮我按 4 小时排一条北京一日行程"}],
        tools=get_tools(has_itinerary=False), label="tool")
