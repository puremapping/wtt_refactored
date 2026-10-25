#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where to Travel — 配置"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---- 从 .env 读凭证 ----
def _load_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

# ---- 数据库 ----
DB_PATH = BASE_DIR / "data" / "wtt.db"

# ---- 数据源 ----
RESEARCH_DIR = BASE_DIR / ".research"

# ---- 大模型（GLM，OpenAI 兼容） ----
# 实测 2026-09-18：glm-4-flash 可用且最省（12 tokens），glm-4.7 可用但贵 16 倍
GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
GLM_BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-4-flash")
GLM_MODEL_FALLBACK = os.environ.get("GLM_MODEL_FALLBACK", "glm-4.7")

# ---- Embedding（阿里云百炼） ----
# ⚠️ 必须用 Workspace 专属端点（PUBLIC_HOST 已废弃，公共端点是敏感值，从 .env 注入）
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.environ.get("DASHSCOPE_BASE_URL", "")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-v3")
EMBEDDING_DIM = 1024

# ---- 高德（按需查询，不做批量预热） ----
AMAP_KEY = os.environ.get("AMAP_KEY", "")

# ---- 认证 ----
# 用于签名登录 cookie。
# ⚠️ BUG-5 修复：缺失不再随机生成（每次重启所有用户被静默登出），启动即报错。
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError(
        "[config] 缺少 SECRET_KEY —— 登录 cookie 的签名密钥。\n"
        "  不设置的话每次重启服务所有人都会被登出，因此拒绝启动。\n"
        "  生成并追加到 .env：\n"
        "    python -c \"import secrets; print('SECRET_KEY=' + secrets.token_hex(32))\" >> .env")
