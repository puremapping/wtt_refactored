#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地假外站智能体 —— 用来验证平台 external 轨的转发链路

## 它做什么

监听 127.0.0.1:8791，接收平台转发的
    POST {"question": ..., "region": ..., "context": {...}}
返回
    {"answer": "..."}

答案里带明显标记，一眼就能看出「这条是外站答的，不是平台自己答的」。
同时把收到的请求原样打印到 stdout，方便核对平台发过来的字段对不对。

## 用法

    python -m app.scripts.fake_external_agent
或（不装进项目时）
    python _fake_external_agent.py

## 验收要点

在 /console 建智能体时：
    类型      外部智能体
    覆盖地区  西安
    调用地址  http://127.0.0.1:8791/chat
    鉴权      Bearer verify-token-2026

然后去 /chat 问「西安有什么好玩的」。
"""
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

# 与 /console 里填的鉴权保持一致；-1 表示不校验
EXPECTED_AUTH = "Bearer verify-token-2026"
PORT = 8791


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)

        # ⚠️ 不要假设对方发的是 UTF-8 —— Windows 上 curl 传中文常常是 GBK。
        #    解码失败不该让整个请求崩掉，先降级成 unicode_escape 留证。
        body = {}
        parse_note = ""
        for enc in ("utf-8", "gbk"):
            try:
                body = json.loads(raw.decode(enc))
                break
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                parse_note = f"{enc}: {e}"
                body = {"__parse_error__": raw[:200].decode("utf-8", "replace")}
        else:
            pass

        auth = self.headers.get("Authorization", "")
        auth_ok = (EXPECTED_AUTH == "-1") or (auth == EXPECTED_AUTH)

        q = body.get("question", "")
        region = body.get("region", "")
        ctx = body.get("context") or {}

        # 打印到终端，供人工核对平台实际发过来的字段
        print(f"\n[{datetime.now():%H:%M:%S}] ── 收到转发 ──")
        print(f"  question : {q}")
        print(f"  region   : {region}")
        print(f"  context  : {json.dumps(ctx, ensure_ascii=False)[:180]}")
        print(f"  auth     : {auth or '（无）'}  {'✓ 匹配' if auth_ok else '✗ 不匹配'}")
        if parse_note:
            print(f"  ⚠ 解码: {parse_note}")

        if not auth_ok:
            payload = {"answer": f"【假外站】鉴权不匹配，收到的是「{auth or '空'}」"}
        else:
            payload = {
                "answer": (
                    f"【假外站·西安】收到你的问题「{q}」。"
                    f"这是一条由本地假外站服务生成的回答，"
                    f"用来证明平台的外部智能体转发链路是通的。"
                    f"（时间 {datetime.now():%H:%M:%S}）"
                ),
                "echo": {"question": q, "region": region},
            }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        """浏览器直接访问端口时给个提示页，方便确认服务活着"""
        msg = ("假外站智能体正在运行。\n"
               f"请在平台的 /console 里把调用地址填成 http://127.0.0.1:{PORT}/chat\n"
               f"鉴权填 {EXPECTED_AUTH}\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    def log_message(self, *args):
        pass          # 用上面的自定义打印，不要默认的访问日志刷屏


if __name__ == "__main__":
    print(f"假外站智能体已启动：http://127.0.0.1:{PORT}")
    print(f"  POST 路径: /chat")
    print(f"  期望鉴权: {EXPECTED_AUTH}")
    print("  在 /console 建外部智能体时，覆盖地区填「西安」")
    print("  Ctrl+C 停止\n")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
