#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""路由层共享：模板实例 + 认证依赖"""
from fastapi import Cookie, Depends, HTTPException, Response
from fastapi.templating import Jinja2Templates

from app.core.config import BASE_DIR
from app.services import auth as auth_svc

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _asset_version() -> str:
    """静态资源版本号 = static/ 目录最新文件 mtime（Phase 3）

    背景（README §3 的持续痛点）：模板里硬编码 ?v=N，改前端文件必须
    手动加一，否则浏览器用旧缓存。现在启动时自动取目录最新改动时间，
    改完前端重启即生效，无需手动维护版本号。
    """
    static_dir = BASE_DIR / "app" / "static"
    latest = 0
    for f in static_dir.iterdir():
        if f.is_file():
            latest = max(latest, int(f.stat().st_mtime))
    return str(latest)


templates.env.globals["ASSET_V"] = _asset_version()


# ── 当前用户（可选，未登录返回 None）──

def current_user_optional(wtt_auth: str = Cookie(default=None)):
    """从签名 cookie 解析当前用户；未登录返回 None（不拦截）"""
    uid = auth_svc.parse_token(wtt_auth) if wtt_auth else None
    return auth_svc.get_user(uid) if uid else None


def require_user(user=Depends(current_user_optional)):
    """需要登录的接口用这个"""
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def set_auth_cookie(response: Response, user_id: str):
    response.set_cookie(
        key=auth_svc.COOKIE_NAME,
        value=auth_svc.make_token(user_id),
        max_age=auth_svc.COOKIE_MAX_AGE,
        httponly=True,          # 防 XSS 读取
        samesite="lax",
        path="/",
    )
