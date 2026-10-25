#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where to Travel — FastAPI 应用装配

路由按业务域拆在 app/routers/，业务逻辑在 app/services/。
本文件只做：应用创建、静态资源挂载、路由注册、启动初始化。
"""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import BASE_DIR
from app.core.db import init_db
from app.routers import (
    agents,
    analytics,
    auth,
    chat,
    history,
    itinerary,
    me,
    pages,
    posts,
)
from app.services import conversation as convo_svc


def _start_anon_cleanup_thread():
    """后台清理匿名会话（每小时一次）"""

    def _loop():
        import time
        while True:
            time.sleep(3600)
            try:
                convo_svc._anon_cleanup()
            except Exception:
                pass

    threading.Thread(target=_loop, daemon=True).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _start_anon_cleanup_thread()
    yield


app = FastAPI(title="Where to Travel", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")),
          name="static")

for r in (pages.router, auth.router, chat.router, itinerary.router,
          history.router, analytics.router, posts.router, me.router,
          agents.router):
    app.include_router(r)
