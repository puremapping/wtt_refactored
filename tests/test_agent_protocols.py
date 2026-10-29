#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外部智能体协议适配（app/services/agent_protocols.py）

核心验收：
  1. generic 协议行为与适配前完全一致（不能破坏已有外部智能体）
  2. dify 协议能构造出 Dify 认的请求体、能读懂 Dify 的响应
  3. 脏数据（未知协议名）不炸，退回 generic
"""
import json

import pytest

from app.services.agent_protocols import (
    CozeProtocol, DifyProtocol, Protocol, get_protocol, protocol_choices,
)


# ──────────────────────────────────────────────────────────────
# generic：不能破坏既有行为
# ──────────────────────────────────────────────────────────────

def test_generic_payload_shape():
    p = Protocol()
    payload = p.build_payload(question="成都有什么好吃的",
                              region="成都", context={"turn": 1})
    assert payload == {"question": "成都有什么好吃的",
                       "region": "成都", "context": {"turn": 1}}


@pytest.mark.parametrize("raw,expected", [
    ('{"answer": "熊猫基地"}', "熊猫基地"),
    ('{"text": "熊猫基地"}', "熊猫基地"),
    ('{"content": "熊猫基地"}', "熊猫基地"),
    ('{"reply": "熊猫基地"}', "熊猫基地"),
    ('{"output": "熊猫基地"}', "熊猫基地"),
    ('"熊猫基地"', "熊猫基地"),
    ("熊猫基地", "熊猫基地"),
    ('{"answer": "熊猫基地"}'.encode("utf-8"), "熊猫基地"),
])
def test_generic_parses_common_shapes(raw, expected):
    assert Protocol().parse_response(raw) == expected


def test_generic_empty_returns_none():
    assert Protocol().parse_response("   ") is None
    assert Protocol().parse_response("") is None


# ──────────────────────────────────────────────────────────────
# dify：请求体必须能被 Dify 接受
# ──────────────────────────────────────────────────────────────

def test_dify_payload_has_required_fields():
    """⚠️ Dify 对这几个字段是硬要求，缺一个就 400：
    inputs 必须存在（哪怕空对象）、response_mode 必须是 blocking、
    user 必须有值。"""
    p = DifyProtocol()
    payload = p.build_payload(question="成都有什么好玩的",
                              region="成都", context={"turn": 2})

    assert "inputs" in payload, "Dify 要求 inputs 字段必须存在"
    assert payload["query"] == "成都有什么好玩的"
    assert payload["response_mode"] == "blocking"
    assert payload["user"] == DifyProtocol.USER
    assert payload["inputs"]["region"] == "成都"
    # context 被序列化成字符串塞进 inputs
    assert json.loads(payload["inputs"]["context"]) == {"turn": 2}


def test_dify_payload_inputs_always_present():
    """没有 region / context 时 inputs 至少是空对象，不能省掉"""
    p = DifyProtocol()
    payload = p.build_payload(question="hi", region="", context={})
    assert payload["inputs"] == {}


def test_dify_payload_user_is_fixed():
    """固定 user，避免不同游客的 Dify 会话上下文互相污染"""
    p = DifyProtocol()
    a = p.build_payload(question="a", region="成都", context={})
    b = p.build_payload(question="b", region="成都", context={})
    assert a["user"] == b["user"] == DifyProtocol.USER


def test_dify_parses_answer():
    raw = json.dumps({"event": "message", "answer": "武侯祠和杜甫草堂",
                      "conversation_id": "abc"}, ensure_ascii=False)
    assert DifyProtocol().parse_response(raw) == "武侯祠和杜甫草堂"


def test_dify_raises_on_error_response():
    """Dify 的错误响应没有 answer 字段，要显式抛出，
    否则会被当成「答不出来」静默降级，排查时看不到原因"""
    raw = json.dumps({"code": "invalid_param", "message": "inputs is required",
                      "status": 400})
    with pytest.raises(RuntimeError, match="invalid_param"):
        DifyProtocol().parse_response(raw)


def test_dify_empty_answer_returns_none():
    assert DifyProtocol().parse_response('{"event": "message", "answer": ""}') is None


def test_dify_plain_text_returns_none():
    """Dify 不会返回纯文本 —— 收到就说明端点配错了，不该当答案"""
    assert DifyProtocol().parse_response("some plain text") is None


# ──────────────────────────────────────────────────────────────
# 协议注册表
# ──────────────────────────────────────────────────────────────

def test_get_protocol_returns_right_class():
    assert isinstance(get_protocol("dify"), DifyProtocol)
    assert isinstance(get_protocol("generic"), Protocol)
    assert isinstance(get_protocol("coze"), CozeProtocol)


@pytest.mark.parametrize("bad", [None, "", "  ", "unknown", "DIFY!!"])
def test_get_protocol_falls_back_to_generic(bad):
    """⚠️ 库里存了不认识的协议名（手工改库/版本回退），
    宁可退回通用协议试一次，也不要让整条智能体不可用"""
    p = get_protocol(bad)
    assert isinstance(p, Protocol)
    assert p.key == "generic"


def test_get_protocol_case_insensitive():
    assert isinstance(get_protocol("Dify"), DifyProtocol)
    assert isinstance(get_protocol("  DIFY  "), DifyProtocol)


def test_protocol_choices_shape():
    items = protocol_choices()
    keys = [i["key"] for i in items]
    assert "generic" in keys and "dify" in keys
    for i in items:
        assert set(i) == {"key", "label", "description"}
