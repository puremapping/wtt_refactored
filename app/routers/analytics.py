#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行为分析路由（内部）—— ADMIN_TOKEN 门禁，凭证走请求头"""
import hmac
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.services import analytics as ana

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/report")
def analytics_report(request: Request, days: int = 30, token: str = None):
    admin = os.environ.get("ADMIN_TOKEN", "")
    if not admin:
        return JSONResponse({"error": "未配置 ADMIN_TOKEN，分析接口已禁用"},
                            status_code=403)
    # ⚠️ BUG-6：凭证优先走 X-Admin-Token 请求头（不进访问日志）；
    # query 参数仅作旧调用兼容，日志里不再出现新凭证。
    supplied = request.headers.get("X-Admin-Token") or token or ""
    if not hmac.compare_digest(supplied, admin):
        return JSONResponse({"error": "token 不正确"}, status_code=403)
    return ana.report(days)
