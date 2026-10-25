#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多轮动机对话（Travel for What）

Phase 2b 自单文件拆分为包（原 894 行、五种职责）：
  models.py        Conversation 领域模型
  profile.py       画像：合并 / 证据校验 / 占位词清洗 / ready 判据
  prompts.py       回复与抽取两套提示词模板
  policies.py      策略：意图白名单 / 工具过滤 / 数据边界 / 兜底回复
  store.py         会话存取：登录走库、匿名走进程内存 TTL
  orchestrator.py  每轮对话编排（两次独立 LLM 调用 + 策略执行）

对外出口与原单文件模块保持同名，调用方零改动。
"""
from app.services.conversation.models import Conversation
from app.services.conversation.profile import (
    LIST_FIELDS,
    MOTIVATIONS,
    PROFILE_FIELDS,
    _FIELD_EVIDENCE,
    _PLACEHOLDER_VALUES,
    _all_user_text,
    _clean_field_value,
    _has_evidence,
    _is_ready,
    _merge_profile,
    _norm_hours,
    profile_summary,
    public_profile,
)
from app.services.conversation.prompts import (
    EXTRACT_PROMPT,
    REPLY_PROMPT,
    _build_extract_messages,
    _build_reply_messages,
    _format_itinerary_brief,
)
from app.services.conversation.policies import (
    _clean_reply,
    _fallback_reply,
    _is_generate_intent,
    _is_supported_destination,
    _sanitize_tool_calls,
    _should_allow_propose,
    _substantive_fallback,
)
from app.services.conversation.store import (
    ANON_TTL,
    _ANON_LOCK,
    _ANON_SESSIONS,
    _anon_cleanup,
    _anon_get,
    _anon_put,
    load_session,
    save_session,
)
from app.services.conversation.orchestrator import chat

__all__ = [
    "Conversation", "chat", "load_session", "save_session",
    "profile_summary", "public_profile",
    "MOTIVATIONS", "PROFILE_FIELDS", "LIST_FIELDS",
    "REPLY_PROMPT", "EXTRACT_PROMPT", "ANON_TTL",
]
