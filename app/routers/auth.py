#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""认证路由：注册 / 登录 / 登出 / 当前用户 / 删号 / 升级文旅局"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.core.db import connect
from app.routers.deps import current_user_optional, require_user, set_auth_cookie
from app.services import analytics as ana
from app.services import auth as auth_svc

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
async def register(request: Request, response: Response):
    body = await request.json()
    try:
        user = auth_svc.register(
            body.get("email", ""), body.get("password", ""),
            body.get("nickname", ""),
            role=body.get("role", "person"),
            org_name=body.get("org_name", ""),
            region=body.get("region", ""))
    except auth_svc.AuthError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    ana.track(ana.EV_USER_REGISTER, user_id=user["id"], email=user["email"],
              role=user["role"])
    set_auth_cookie(response, user["id"])
    return {"user": user}


@router.post("/login")
async def login(request: Request, response: Response):
    body = await request.json()
    try:
        user = auth_svc.login(body.get("email", ""), body.get("password", ""))
    except auth_svc.AuthError as e:
        return JSONResponse({"error": str(e)}, status_code=401)

    ana.track(ana.EV_USER_LOGIN, user_id=user["id"], email=user["email"])
    set_auth_cookie(response, user["id"])
    return {"user": user}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(auth_svc.COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user_optional)):
    return {"user": user}


@router.delete("/account")
async def delete_account(request: Request, response: Response,
                         user=Depends(require_user)):
    """删除账号（级联删会话与事件）—— 隐私要求"""
    body = await request.json()
    try:
        auth_svc.delete_user(user["id"], body.get("password", ""))
    except auth_svc.AuthError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    response.delete_cookie(auth_svc.COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/upgrade-agency")
async def upgrade_agency(request: Request, user=Depends(require_user)):
    """个人身份升级为文旅局（不锁定，阿哲定的默认）"""
    if user.get("role") == "agency":
        return {"ok": True, "already": True}
    body = await request.json()
    org = (body.get("org_name") or "").strip()
    if not org:
        return JSONResponse({"error": "请填写机构名称"}, status_code=400)
    oid = uuid.uuid4().hex[:16]
    with connect() as conn:
        conn.execute(
            "INSERT INTO teams (id,name,region,owner_id,created_at) VALUES (?,?,?,?,?)",
            (oid, org, (body.get("region") or "").strip() or None,
             user["id"], datetime.now().isoformat()))
        conn.execute("UPDATE users SET role='agency', org_id=? WHERE id=?",
                     (oid, user["id"]))
    return {"ok": True, "org_id": oid, "org_name": org}
