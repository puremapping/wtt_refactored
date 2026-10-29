import json
import time

import httpx

B = "http://127.0.0.1:8077"


def stream(plan="chat", fail_at=None):
    params = {"plan": plan}
    if fail_at:
        params["fail_at"] = fail_at
    httpx.get(f"{B}/api/_mode", params=params)
    t0 = time.monotonic()
    rows, events = [], []
    with httpx.stream("POST", f"{B}/api/chat/stream",
                      json={"text": "想去北京散心"}, timeout=60) as r:
        print(f"[{plan}/{fail_at}] status={r.status_code} "
              f"ctype={r.headers.get('content-type')} "
              f"xaccel={r.headers.get('x-accel-buffering')}")
        for line in r.iter_lines():
            if not line:
                continue
            rows.append((round(time.monotonic() - t0, 2), line[:110]))
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    for t, l in rows[:10]:
        print(f"  {t:5.2f}s {l}")
    print("  ...")
    for t, l in rows[-3:]:
        print(f"  {t:5.2f}s {l}")
    kinds = [e["kind"] + ":" + str(e.get("target") or e.get("status")
                                   or e.get("name") or "")
             for e in events]
    print("  kinds:", kinds)
    print("  terminal:", events[-1]["kind"] if events else None)
    print("  reply_chars_streamed:",
          len([e for e in events if e.get("target") == "reply"]))
    return events


print("=== A. 正常对话 ===")
stream()
print("\n=== B. 工具轮（正文为空）===")
stream("tool")
print("\n=== C. 抽取阶段上游炸 ===")
stream("chat", "extract")
print("\n=== D. 同步接口复用同一生成器 ===")
r = httpx.get(f"{B}/api/chat", params={"text": "想去北京"})
print("  ", r.status_code,
      {k: r.json().get(k) for k in ("reply", "turn", "action")})
print("\n=== E. reply 阶段炸 ===")
stream("chat", "reply")
print("\n=== F. 正文流到一半上游炸（前端必须能收尾巴）===")
stream("chat", "midway")
