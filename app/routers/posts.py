#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内容社区路由：帖子 / 点赞 / 评论 / 搜索热词 / 站内消息

⚠️ 浏览开放（匿名可看），互动需登录。
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.routers.deps import current_user_optional, require_user
from app.services import analytics as ana
from app.services import posts as post_svc

router = APIRouter(tags=["posts"])


@router.get("/api/posts")
def api_list_posts(tab: str = "content", page: int = 1, size: int = 20,
                   keyword: str = None,
                   user=Depends(current_user_optional)):
    """帖子列表

    tab: content（全部）| inspiration（行程灵感）| hot（今日热榜）
    keyword: 搜索词，命中会记入热榜统计
    """
    uid = user["id"] if user else None
    result = post_svc.list_posts(tab=tab, page=page, size=size,
                                 keyword=keyword, viewer_id=uid)
    # 搜索时记录（供热榜）
    if keyword:
        ids = [it["id"] for it in result["items"]]
        post_svc.log_search(keyword, uid, ids)
    return result


@router.get("/api/posts/{post_id}")
def api_get_post(post_id: int, user=Depends(current_user_optional)):
    uid = user["id"] if user else None
    d = post_svc.get_post(post_id, uid)
    if not d:
        return JSONResponse({"error": "帖子不存在"}, status_code=404)
    return d


@router.post("/api/posts")
async def api_create_post(request: Request, user=Depends(require_user)):
    """发帖（需登录）

    body: {title, body?, type?, cover_url?, images?, itinerary?, motivation?}
    ⚠️ type=inspiration 时必须带 itinerary
    """
    body = await request.json()
    title = (body.get("title") or "").strip()
    if not title:
        return JSONResponse({"error": "标题不能为空"}, status_code=400)

    ptype = body.get("type") or "content"
    if ptype not in ("content", "inspiration"):
        return JSONResponse({"error": "type 只能是 content 或 inspiration"},
                            status_code=400)
    if ptype == "inspiration" and not body.get("itinerary"):
        return JSONResponse({"error": "行程灵感必须附带 itinerary"}, status_code=400)

    pid = post_svc.create_post(
        user["id"], title, body.get("body") or "", ptype,
        cover_url=body.get("cover_url"),
        images=body.get("images"),
        itinerary=body.get("itinerary"),
        motivation=body.get("motivation"))

    ana.track(ana.EV_MESSAGE_SENT, user_id=user["id"], action="create_post",
              post_type=ptype)
    return {"id": pid, "ok": True}


@router.delete("/api/posts/{post_id}")
def api_delete_post(post_id: int, user=Depends(require_user)):
    """删帖 —— 归属校验在服务层（AND user_id=?）"""
    if not post_svc.delete_post(post_id, user["id"]):
        return JSONResponse({"error": "帖子不存在或无权限"}, status_code=404)
    return {"ok": True}


@router.post("/api/posts/{post_id}/like")
def api_toggle_like(post_id: int, user=Depends(require_user)):
    return post_svc.toggle_like(post_id, user["id"])


@router.get("/api/posts/{post_id}/comments")
def api_list_comments(post_id: int):
    return {"items": post_svc.list_comments(post_id)}


@router.post("/api/posts/{post_id}/comments")
async def api_add_comment(post_id: int, request: Request,
                          user=Depends(require_user)):
    body = await request.json()
    content = (body.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "评论不能为空"}, status_code=400)
    return post_svc.add_comment(post_id, user["id"], content)


@router.get("/api/search/hot_keywords")
def api_hot_keywords(limit: int = 10):
    """热门搜索词（搜索框下方推荐用）"""
    return {"items": post_svc.hot_keywords(limit)}


# ── 站内消息 ──

@router.get("/api/messages")
def api_messages(user=Depends(require_user)):
    return post_svc.list_messages(user["id"])


@router.post("/api/messages/read")
async def api_messages_read(request: Request, user=Depends(require_user)):
    body = await request.json()
    return {"updated": post_svc.mark_read(user["id"], body.get("id"))}
