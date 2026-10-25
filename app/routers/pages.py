#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""页面路由：浏览 / 对话 / 个人主页 / 登录 / 文旅局开发台 / 数据看板"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.routers.deps import current_user_optional, templates

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    """浏览页（内容社区）—— 匿名可访问"""
    return templates.TemplateResponse(request, "browse.html")


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request, q: str = None):
    """AI 对话页

    ⚠️ `q` 从浏览页搜索框的 AI 按钮带过来，前端填进输入框（不自动发送）
    """
    return templates.TemplateResponse(request, "chat.html", {"q": q or ""})


@router.get("/me", response_class=HTMLResponse)
def me_page(request: Request):
    """个人主页"""
    return templates.TemplateResponse(request, "me.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """独立的登录 / 注册页

    role 可选：person | agency，用来预选身份（如从「我是文旅局」入口进来）
    next：登录成功后的跳转目标
    """
    return templates.TemplateResponse(request, "login.html", {
        "role": "agency" if request.query_params.get("role") == "agency" else "person",
        "next": request.query_params.get("next") or "/",
    })


@router.get("/console", response_class=HTMLResponse)
def console_page(request: Request, user=Depends(current_user_optional)):
    """文旅局的智能体开发页

    ⚠️ 只有 agency 身份可访问。个人用户进来会看到提示。
    """
    if not user:
        return templates.TemplateResponse(request, "login.html", {
            "role": "agency",
            "next": "/console",
        }, status_code=200)
    if user.get("role") != "agency":
        return templates.TemplateResponse(request, "console_denied.html",
                                          {"user": user}, status_code=200)
    return templates.TemplateResponse(request, "console.html", {"user": user})


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    # Starlette 新版签名：TemplateResponse(request, name, context)
    return templates.TemplateResponse(request, "admin.html")
