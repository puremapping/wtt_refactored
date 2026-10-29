#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文旅局智能体开发台路由（仅 agency 身份）"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.routers.deps import require_user
from app.services import agents as agent_svc

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _require_agency(user):
    """取当前用户的团队。非文旅局返回 (None, 错误响应)"""
    if not user:
        return None, JSONResponse({"error": "请先登录"}, status_code=401)
    if user.get("role") != "agency":
        return None, JSONResponse({"error": "仅文旅局账号可管理智能体"}, status_code=403)
    if not user.get("org_id"):
        return None, JSONResponse({"error": "账号未关联机构"}, status_code=400)
    return user["org_id"], None


@router.get("/protocols")
def api_protocols():
    """外部智能体可选的协议（给 /console 表单的下拉用）

    ⚠️ 不需要认证 —— 只是静态选项清单，不含任何凭据或机构信息。
    """
    from app.services.agent_protocols import protocol_choices
    return {"items": protocol_choices()}


@router.get("")
def api_list_agents(user=Depends(require_user)):
    team_id, err = _require_agency(user)
    if err:
        return err
    return {"items": agent_svc.list_agents(team_id)}


@router.post("")
async def api_create_agent(request: Request, user=Depends(require_user)):
    team_id, err = _require_agency(user)
    if err:
        return err
    body = await request.json()
    try:
        aid = agent_svc.create_agent(
            team_id, user["id"],
            name=body.get("name", ""),
            region=body.get("region", ""),
            description=body.get("description", ""),
            prompt=body.get("prompt", ""),
            kind=body.get("kind", "builtin"),
            endpoint=body.get("endpoint", ""),
            auth=body.get("auth", ""),
            protocol=body.get("protocol", "generic"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"id": aid, "ok": True}


@router.get("/{agent_id}")
def api_get_agent(agent_id: str, user=Depends(require_user)):
    team_id, err = _require_agency(user)
    if err:
        return err
    a = agent_svc.get_agent(agent_id, team_id)
    if not a:
        return JSONResponse({"error": "不存在或无权限"}, status_code=404)
    return a


@router.post("/{agent_id}")
async def api_update_agent(agent_id: str, request: Request,
                           user=Depends(require_user)):
    team_id, err = _require_agency(user)
    if err:
        return err
    body = await request.json()
    fields = {k: body[k] for k in
              ("name", "region", "description", "prompt", "endpoint", "auth",
               "protocol")
              if k in body}
    ok = agent_svc.update_agent(agent_id, team_id, **fields)
    return {"ok": ok}


@router.post("/{agent_id}/publish")
def api_publish_agent(agent_id: str, user=Depends(require_user)):
    team_id, err = _require_agency(user)
    if err:
        return err
    r = agent_svc.publish_agent(agent_id, team_id)
    if not r.get("ok"):
        return JSONResponse({"error": r.get("error", "发布失败")}, status_code=400)
    return r


@router.delete("/{agent_id}")
def api_delete_agent(agent_id: str, user=Depends(require_user)):
    team_id, err = _require_agency(user)
    if err:
        return err
    if not agent_svc.delete_agent(agent_id, team_id):
        return JSONResponse({"error": "不存在或无权限"}, status_code=404)
    return {"ok": True}
