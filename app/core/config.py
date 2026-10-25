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
# 用于签名 cookie。首次运行若 .env 里没有，自动生成一个并提示。
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    import secrets as _secrets
    SECRET_KEY = _secrets.token_hex(32)
    # 提示写入 .env（不自动写，避免动用户文件）
    import sys as _sys
    print("[config] 警告：未设置 SECRET_KEY，本次使用临时值。"
          "重启后 cookie 会失效。建议在 .env 加："
          f"SECRET_KEY={SECRET_KEY}", file=_sys.stderr)
