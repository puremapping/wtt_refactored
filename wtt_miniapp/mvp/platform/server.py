#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wtt_miniapp MVP — 平台侧：画像 → 结构化 context

⚠️ 这是 MVP 版平台服务，**不是生产代码**（见 README「真集成时要补什么」）。
它做三件事：
  1. 复用主项目 app/services/conversation/profile.py 的真实画像逻辑
     （占位词清洗、public_profile、profile_summary），不自己另造一套
  2. 提供 R1 账密登录（真的验密码）+ /api/context 导出
  3. **结构性不导出用户原话**：profile.summary 只留库内，出平台的只有结构化概括

真实集成时，端点应落在主项目里，数据取自 sessions.profile JSON，
token 换成与使用者身份绑定的正式实现。
"""
from __future__ import annotations

import secrets
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 复用主项目真实的画像模块与密码校验（零改动主项目代码）
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from app.services.conversation.profile import (  # noqa: E402
    PROFILE_FIELDS, public_profile, profile_summary,
)
from app.services.auth import hash_password, verify_password  # noqa: E402

from fixtures import DEMO_USERS, DEMO_PASSWORD  # noqa: E402
from prompt_injection import build_system_prompt, select_guide_version  # noqa: E402

app = FastAPI(title="wtt platform (MVP stub)", version="0.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # MVP 本地演示；生产必须收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 会话 token（MVP 内存实现）──
# 方案一「免密」：token 存小程序端 storage，所以 TTL 必须够长，
# 否则用户下次进来 token 已过期，免密形同虚设。
# 对齐主项目 auth.COOKIE_MAX_AGE（30 天），换个量级才能验证「下次免密」。
# ⚠️ 仍是内存实现：服务端重启后 token 失效，小程序端会静默退回账密 —— 这是
#    有意保留的降级演示，不是缺陷。生产应持久化、可撤销、绑真实身份、HTTPS。
_TOKENS: dict[str, dict] = {}
_TOKEN_TTL = 30 * 24 * 3600  # 30 天，与主项目 cookie 对齐

# 演示账号的密码 hash（运行时生成，不写进 fixtures 文件）
_PWD_HASH = hash_password(DEMO_PASSWORD)


class LoginBody(BaseModel):
    email: str
    password: str


@app.get("/api/auth/me")
def auth_me():
    """匿名态：模拟器的 wx.request 不带平台 cookie，这里如实返回未登录。

    ⚠️ 这正是为什么小程序必须有自己的登录（R1/R2/R3）：
       平台 cookie 跨不过小程序这一侧。
    """
    return {"user": None, "note": "小程序侧不携带平台 cookie，需走 /api/auth/login"}


@app.post("/api/auth/login")
def login(body: LoginBody):
    """R1：平台账密登录，签发会话 token。真的验密码。

    这是 MVP 的默认登录路径。R2（微信 code 换票据，一键绑定）需要
    绑定表与微信身份字段，属待定决策，本 MVP 不实现。
    """
    email = (body.email or "").strip().lower()
    user = DEMO_USERS.get(email)
    # 用 constant-time 校验；未知账号也走一次 verify，避免时序区分账号是否存在
    ok = verify_password(body.password or "", _PWD_HASH)
    if not user or not ok:
        raise HTTPException(401, "邮箱或密码不正确")

    token = secrets.token_urlsafe(24)
    _TOKENS[token] = {
        "user_id": user["id"],
        "scope": "miniapp_context",
        "created_at": time.time(),
    }
    return {
        "token": token,
        "expires_in": _TOKEN_TTL,
        "user": {"id": user["id"], "email": email, "nickname": user["nickname"]},
    }


def _use_token(token: str) -> dict:
    rec = _TOKENS.get(token)
    if not rec:
        raise HTTPException(401, "登录已失效，请重新登录")
    if time.time() - rec["created_at"] > _TOKEN_TTL:
        _TOKENS.pop(token, None)
        raise HTTPException(401, "登录已过期，请重新登录")
    return rec


@app.get("/api/auth/verify")
def verify_token(token: str = Query(...)):
    """方案一的探活端点：小程序启动时拿本地存的 token 问平台「还有效吗」。

    ⚠️ 为什么不能拿 /api/context 当探活：那个端点会顺带把画像组装出来，
       小程序 onLoad 时调它等于没经用户确认就刷出讲解，语义和开销都不对。
    有效返回 {valid:true, user}，失效返回 {valid:false}（**不是 401**）——
    让小程序端静默退回账密框，不弹错误吓用户。
    """
    try:
        rec = _use_token(token)
    except HTTPException:
        return {"valid": False}
    user = next((u for u in DEMO_USERS.values()
                 if u["id"] == rec["user_id"]), None)
    if not user:
        return {"valid": False}
    return {
        "valid": True,
        "user": {"id": user["id"], "nickname": user["nickname"]},
        "expires_in": max(0, int(_TOKEN_TTL - (time.time() - rec["created_at"]))),
    }


@app.get("/api/context")
def get_context(token: str = Query(...)):
    """画像 + 行程 → 结构化 context（G1 缺口的 MVP 实现）。

    ⚠️ D1 已定（阿哲 2026-11-13）：**不留原话，只导出概括**。
       - `profile.summary` 是用户原话的保留形态，留库内，**绝不出现在响应里**
       - 出平台的只有结构化字段 + 由它们拼出的概括（`profile_summary`）
       - 没有开关、没有 query 参数可以把它打开 —— 这是结构性约束，不是选项
    """
    rec = _use_token(token)
    user = next(u for u in DEMO_USERS.values() if u["id"] == rec["user_id"])

    raw = user["profile"]
    profile = public_profile(raw)          # 剔除 _ 内部字段
    # 结构性剥离：原话不出平台。用 pop 而不是过滤条件，
    # 保证即使将来 public_profile 改了也不会把它带出去。
    profile.pop("summary", None)

    # 概括 = 结构化字段拼接（profile_summary 只处理固定字段，不含自由文本）
    # 传的是已剥离的 profile —— 防御性写法：将来函数改了也不会泄漏原话
    abstract = profile_summary(profile)

    version = select_guide_version(profile)
    prompt = build_system_prompt(profile, version, abstract=abstract)

    return {
        "schema": "wtt.context/v0.2",
        "user": {"id": user["id"], "nickname": user["nickname"]},
        "profile": profile,
        "profile_fields": list(PROFILE_FIELDS.keys()),
        "abstract": abstract,
        "guide_version": version,
        "injected_system_prompt": prompt,
        "known_fields": sorted(profile.keys()),
        "unknown_fields": sorted(set(PROFILE_FIELDS) - set(profile) - {"summary"}),
        "itinerary": user.get("itinerary") or {},
        "caveats": [
            "MVP：profile 来自演示 fixtures，非真实用户数据",
            "D1 已定：响应中不含 profile.summary（用户原话），只有结构化概括 abstract",
            "MVP：token 内存实现，生产须绑定真实身份并持久化",
            "injected_system_prompt 是真实组装结果；讲解正文来自预置知识库，未调 LLM",
        ],
    }


@app.get("/api/demo-users")
def demo_users():
    """给小程序端的演示账号列表（只给 email，不给密码）。"""
    return {
        "users": [
            {"email": email, "nickname": u["nickname"], "hint": u["hint"]}
            for email, u in DEMO_USERS.items()
        ],
        "note": "演示账号，密码见 mvp/README.md",
    }


@app.get("/health")
def health():
    return {"ok": True, "tokens_issued": len(_TOKENS)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="info")
