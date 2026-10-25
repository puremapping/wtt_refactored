#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 GLM 可用模型（避开 shell 中文编码问题）

用法: export GLM_API_KEY=<key> && python -m app.scripts.test_glm_models
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import httpx

from app.core.config import GLM_API_KEY, GLM_BASE_URL

if not GLM_API_KEY:
    print("错误：未设置 GLM_API_KEY", file=sys.stderr)
    sys.exit(2)

URL = GLM_BASE_URL.rstrip("/") + "/chat/completions"

MODELS = ["glm-4-flash", "glm-4.7", "glm-5.3-flash", "glm-4.5-air"]

print("=" * 76)
print("GLM 模型可用性测试")
print("=" * 76)

for m in MODELS:
    try:
        r = httpx.post(
            URL,
            headers={"Authorization": f"Bearer {GLM_API_KEY}",
                     "Content-Type": "application/json"},
            json={
                "model": m,
                "messages": [{"role": "user", "content": "回复两个字：可用"}],
                "max_tokens": 20,
            },
            timeout=30,
        )
        d = r.json()
        if "choices" in d:
            content = d["choices"][0]["message"]["content"]
            usage = d.get("usage", {})
            print(f"  ✓ {m:<18} → {content!r:<20} "
                  f"tokens={usage.get('total_tokens', '?')}")
        else:
            err = d.get("error", d)
            msg = err.get("message", str(err))[:70]
            print(f"  ✗ {m:<18} → {msg}")
    except Exception as e:
        print(f"  ✗ {m:<18} → {type(e).__name__}: {e}")
