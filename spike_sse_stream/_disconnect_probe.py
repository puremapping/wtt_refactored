"""验证：客户端中断后，上游 LLM 是否被取消（不能让它继续烧钱）。"""
import asyncio, time, httpx

async def one(label, cut_after_bytes):
    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=30) as c:
        async with c.stream("POST", "http://127.0.0.1:8077/api/chat/stream",
                            json={"text": "想去北京"}) as r:
            n = 0
            async for chunk in r.aiter_raw():
                n += len(chunk)
                if n >= cut_after_bytes:
                    break                     # 模拟用户关页
    print(f"{label}: 客户端在 {n} 字节处断开, 耗时 {time.monotonic()-t0:.2f}s")

asyncio.run(one("中途断开", 400))
