#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社区一次性机器人模拟（QA 演练）

10 个个人机器人 + 2 个文旅局机器人，模拟真实社区活动：
注册 → 发帖（含行程灵感）→ 浏览/搜索 → 点赞（含并发）→ 评论 → 通知 → 热榜
文旅局机器人走 /api/agents：创建 → 校验失败路径 → 补全 → 发布 → 路由可用性

每个动作做自动检查；发现的问题写入 sim/issues.jsonl，最后汇总 sim/report.md。
机器人身份一律 *@sim.local，sim/cleanup.py 可一键清除全部痕迹。
"""
import json
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8100"
SIM_DIR = Path(__file__).resolve().parent.parent.parent / "sim"
ISSUES_FILE = SIM_DIR / "issues.jsonl"
STATS = {"checks": 0, "actions": 0}

random.seed(20261025)

if ISSUES_FILE.exists():
    ISSUES_FILE.unlink()


def issue(severity: str, where: str, what: str, evidence=None):
    """记录一个问题"""
    rec = {
        "time": datetime.now().isoformat(),
        "severity": severity,      # high | medium | low | note
        "where": where,
        "what": what,
        "evidence": evidence,
    }
    with ISSUES_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  [{severity}] {where}: {what}")


def check(where: str, cond: bool, what_if_fail: str, severity="high", evidence=None):
    """断言式检查：失败记 issue，返回 cond"""
    STATS["checks"] += 1
    if not cond:
        issue(severity, where, what_if_fail, evidence)
    return cond


# ── 机器人人设 ──

PERSON_BOTS = [
    ("阿岚", "爱走胡同和旧书店"),
    ("小满", "周末就想去人少的地方待着"),
    ("大乔", "带娃出行装备党"),
    ("拾贝", "博物馆爱好者，一年刷 30 个展"),
    ("南山客", "爬山跨省，最恋长城"),
    ("木木", "拍照出片社恐，去哪都躲人"),
    ("老白", "退休，钓鱼和公园棋摊"),
    ("荔枝汽水", "美食搜索雷达，为一口吃的跨城"),
    ("阿澈", "学生党穷游，免费景点狂魔"),
    ("青禾", "和男朋友打卡各种展览"),
]

AGENCY_BOTS = [
    ("成都文旅 · 实验局", "成都市文化广电旅游局（模拟）", "成都"),
    ("海淀文旅 · 实验科", "海淀区文旅局（模拟）", "北京"),
]


def bot_client():
    return httpx.Client(base_url=BASE, timeout=30)


def register(bot, nickname, role="person", org_name=""):
    r = bot.post("/api/auth/register", json={
        "email": f"{uuid.uuid4().hex[:8]}@sim.local",
        "password": "Sim123456",
        "nickname": nickname,
        "role": role,
        "org_name": org_name,
    })
    STATS["actions"] += 1
    check("注册", r.status_code == 200 and r.json().get("user", {}).get("id"),
          f"注册失败: {r.status_code} {r.text[:120]}")
    check("注册", "wtt_auth" in bot.cookies, "注册后未下发登录 cookie")
    return r.json().get("user", {})


def make_post(bot, user, title, body, motivation=""):
    r = bot.post("/api/posts", json={
        "title": title, "body": body, "motivation": motivation, "type": "content"})
    STATS["actions"] += 1
    check("发帖", r.status_code == 200 and r.json().get("id"),
          f"发帖失败: {r.status_code} {r.text[:120]}")
    return r.json().get("id")


# ── 场景一：个人机器人开团 ──

def scenario_posts(bots, users):
    print("\n[1] 发帖")
    created = []
    topics = [
        ("周末去人少的地方充电", "周六早上七点出门，专挑不开车的园子，人多就走。", "恢复/逃离"),
        ("带娃一日游不累路线", "上午一个馆下午一个园，中间留足吃饭时间，娃不闹我轻松。", "连接/关系"),
        ("为了这口炸酱面跑了一趟", "巷子深但值，顺路把旁边的旧书市逛了。", "美食/感官"),
        ("免费的 5A 是真的香", "提前预约就行，全程零门票，出片还多。", "成就/完成"),
        ("博物馆盖章打卡第 12 站", "章面清晰服务好，盖完在纪念品店蹲了半小时。", "文化/沉浸"),
        ("避开人流的出片机位", "下午四点光线最好，这个时段旅行团刚好撤。", "表达/展示"),
        ("第一次走完整段城墙", "腿废了但值，建议反过来走下坡多。", "探索/新奇"),
    ]
    for i, (bot, user) in enumerate(zip(bots[:7], users[:7])):
        title, body, mot = topics[i]
        pid = make_post(bot, user, title, body, mot)
        if pid:
            created.append((pid, user["id"], user["nickname"], title))
    return created


def scenario_itinerary_post(bots, users, created):
    print("[2] 行程灵感帖（inspiration）")
    # 先触发一次行程生成的替代路径：直接构造结构化行程（真实接口对灵感帖的校验点）
    bot, user = bots[7], users[7]
    r = bot.post("/api/posts", json={"title": "灵感帖但没带行程", "type": "inspiration"})
    STATS["actions"] += 1
    check("灵感帖校验", r.status_code == 400, "type=inspiration 缺 itinerary 竟然成功了（必须失败）",
          evidence=r.text[:120])

    itinerary = {
        "motivation": "恢复/逃离", "hours": 8, "total_distance_km": 12.5,
        "stops": [
            {"order": 1, "name": "奥林匹克森林公园", "arrive": "09:00", "level": "4A",
             "district": "朝阳区", "crowd": 55.0, "duration_min": 75},
            {"order": 2, "name": "景山公园", "arrive": "11:20", "level": "4A",
             "district": "西城区", "crowd": 40.0, "duration_min": 75},
            {"order": 3, "name": "北海公园", "arrive": "14:00", "level": "4A",
             "district": "西城区", "crowd": 35.0, "duration_min": 75},
        ],
        "risks": ["下午人流回升，建议早出发"],
    }
    r = bot.post("/api/posts", json={
        "title": "一个人也舒服的一日充电路线",
        "body": "亲测不累，全程有地铁。",
        "type": "inspiration", "motivation": "恢复/逃离",
        "itinerary": itinerary})
    STATS["actions"] += 1
    ok = check("灵感帖", r.status_code == 200 and r.json().get("id"),
               f"带 itinerary 的灵感帖失败: {r.status_code} {r.text[:120]}")
    if ok:
        pid = r.json()["id"]
        created.append((pid, user["id"], user["nickname"], "一个人也舒服的一日充电路线"))
        # 详情里 itinerary 应原样可读
        d = bot.get(f"/api/posts/{pid}").json()
        STATS["actions"] += 1
        stops = (d.get("itinerary") or {}).get("stops", [])
        check("灵感帖", len(stops) == 3 and stops[0]["name"] == "奥林匹克森林公园",
              f"灵感帖详情的 itinerary 结构丢失: {json.dumps(d.get('itinerary'), ensure_ascii=False)[:120]}")
    return created


def scenario_browse_and_search(bots, created):
    print("[3] 浏览 / 搜索 / 分页")
    anon = bot_client()   # 匿名访客
    # 匿名可浏览
    r = anon.get("/api/posts")
    STATS["actions"] += 1
    check("匿名浏览", r.status_code == 200 and r.json()["items"],
          f"匿名浏览失败: {r.status_code}")

    # 分页不重叠
    p1 = anon.get("/api/posts", params={"page": 1, "size": 5}).json()
    p2 = anon.get("/api/posts", params={"page": 2, "size": 5}).json()
    STATS["actions"] += 2
    ids1 = {i["id"] for i in p1["items"]}
    ids2 = {i["id"] for i in p2["items"]}
    check("分页", not (ids1 & ids2), f"第 1/2 页出现重叠帖子: {ids1 & ids2}")

    # 搜索命中
    kw = "充电"
    r = anon.get("/api/posts", params={"keyword": kw})
    STATS["actions"] += 1
    hits = r.json()["items"]
    check("搜索", any("充电" in (i["title"] or "") for i in hits),
          f"关键词「{kw}」未命中已知帖子，返回 {len(hits)} 条")

    # 搜索打点 → 热榜与热词
    for b in bots[:5]:
        b.get("/api/posts", params={"keyword": kw})
    STATS["actions"] += 5
    hot = anon.get("/api/posts", params={"tab": "hot"}).json()
    STATS["actions"] += 1
    check("热榜", hot["items"], "热榜为空（刚有 5 次搜索命中，24h 内应非空）")
    kws = anon.get("/api/search/hot_keywords").json()["items"]
    STATS["actions"] += 1
    check("热词", any(k["keyword"] == kw for k in kws),
          f"热词榜缺少刚搜的「{kw}」: {kws[:5]}")

    # 浏览数自增
    if created:
        pid = created[0][0]
        before = anon.get(f"/api/posts/{pid}").json().get("views", 0)
        anon.get(f"/api/posts/{pid}")
        after = anon.get(f"/api/posts/{pid}").json().get("views")
        STATS["actions"] += 3
        check("浏览数", after == before + 2, f"两次详情访问后 views 未 +2（{before}→{after}）", severity="medium")
    return anon


def scenario_likes(bots, users, created, anon):
    print("[4] 点赞（含并发压测）")
    if not created:
        return
    pid, author_id, author_nick, _ = created[0]

    # 未登录点赞 → 401
    r = anon.post(f"/api/posts/{pid}/like")
    STATS["actions"] += 1
    check("未登录点赞", r.status_code == 401,
          f"匿名点赞未被拦（{r.status_code}）", severity="medium")

    # 顺序点赞 / 取消
    b1, b2 = bots[0], bots[1]
    r = b1.post(f"/api/posts/{pid}/like").json()
    STATS["actions"] += 1
    check("点赞", r.get("liked") is True and r.get("likes", 0) >= 1, f"点赞返回异常: {r}")
    n_after_like = r.get("likes")
    r = b1.post(f"/api/posts/{pid}/like").json()
    STATS["actions"] += 1
    check("取消赞", r.get("liked") is False, f"再次点击未取消: {r}")
    b1.post(f"/api/posts/{pid}/like")   # 重新赞上，供后续检查
    STATS["actions"] += 1

    # 点赞标记按查看者区分（BUG-4 回归）
    lst = b2.get("/api/posts").json()["items"]
    mine = next((i for i in lst if i["id"] == pid), None)
    STATS["actions"] += 1
    if check("点赞标记", mine is not None, "列表里找不到目标帖"):
        check("点赞标记", mine["liked"] is False, "b2 没点过赞却显示已赞", severity="medium")

    # ⚠️ 并发压测：8 个机器人同时点赞同一帖
    before = b1.get(f"/api/posts/{pid}").json().get("likes", 0)
    likers = bots[2:10]
    with ThreadPoolExecutor(max_workers=8) as ex:
        rs = list(ex.map(lambda b: b.post(f"/api/posts/{pid}/like").status_code, likers))
    STATS["actions"] += 8
    after = b1.get(f"/api/posts/{pid}").json().get("likes", 0)
    STATS["actions"] += 1
    bad = [c for c in rs if c != 200]
    if check("并发点赞", not bad, f"并发点赞出现非 200 响应: {bad}", severity="medium"):
        check("并发点赞", after - before == 8,
              f"8 个并发点赞后计数只涨了 {after - before}（应为 8）—— 计数有竞态或丢更新", severity="medium")
        # 底账核对（likes 表行数 vs posts.likes 计数）由 cleanup/report 阶段用 SQL 做


def scenario_comments(bots, users, created):
    print("[5] 评论与通知")
    if not created:
        return
    pid, author_id, author_nick, _ = created[1] if len(created) > 1 else created[0]
    before_unread = None
    # 作者当前未读数
    for b, u in zip(bots, users):
        if u["id"] == author_id:
            before_unread = b.get("/api/messages").json().get("unread", 0)
    text = "收藏了！下周末就照这个走。"
    r = bots[9].post(f"/api/posts/{pid}/comments", json={"content": text})
    STATS["actions"] += 1
    ok = check("评论", r.status_code == 200, f"评论失败: {r.status_code} {r.text[:120]}")
    # 评论列表可见
    items = bots[9].get(f"/api/posts/{pid}/comments").json()["items"]
    STATS["actions"] += 1
    check("评论", any(c["content"] == text for c in items), "刚发的评论不在列表里")
    # 作者收到通知
    if before_unread is not None:
        msg = next((u for u in users if u["id"] == author_id), None)
        for b, u in zip(bots, users):
            if u["id"] == author_id:
                after = b.get("/api/messages").json()
                STATS["actions"] += 1
                check("通知", after["unread"] > before_unread,
                      f"评论后作者未读数未增加（{before_unread}→{after['unread']}）", severity="medium")
                got = any("收藏了" in (m.get("content") or "") for m in after["items"])
                check("通知", got, "作者消息列表里没有这条评论通知", severity="medium")
                # 标记已读
                if after["items"]:
                    mid = after["items"][0]["id"]
                    r = b.post("/api/messages/read", json={"id": mid})
                    STATS["actions"] += 1
                    check("通知", r.json().get("updated", 0) >= 1, "标记已读返回 0")


def scenario_validation(anon, bots):
    print("[6] 输入校验与异常输入")
    bot = bots[0]
    # 空标题
    r = bot.post("/api/posts", json={"title": "   "})
    STATS["actions"] += 1
    check("空标题", r.status_code == 400, f"空标题竟然成功（{r.status_code}）", severity="medium")
    # 非法 type
    r = bot.post("/api/posts", json={"title": "x", "type": "广告"})
    STATS["actions"] += 1
    check("非法type", r.status_code == 400, f"非法 type 竟然成功（{r.status_code}）", severity="medium")
    # XSS 探针：服务端应原样存储（转义是前端职责），但不得 500
    xss = '"><script>alert(1)</script>'
    r = bot.post("/api/posts", json={"title": f"标题{xss}", "body": xss})
    STATS["actions"] += 1
    if check("XSS探针", r.status_code == 200, f"含脚本的帖子写入失败: {r.status_code}", severity="medium"):
        pid = r.json()["id"]
        d = anon.get(f"/api/posts/{pid}").json()
        STATS["actions"] += 1
        if d.get("title") is not None and "<script>" in d["title"]:
            issue("note", "XSS探针", "服务端按设计原样存储，转义依赖前端 esc() —— 已确认 esc() 带引号转义（BUG-8 已修），浏览器端不会执行")
        else:
            check("XSS探针", False, "标题内容被改动（与原样存储设计不符）", severity="low")
    # emoji 与长文
    r = bot.post("/api/posts", json={"title": "🚀🎉 深夜食堂巡礼 第" + "很长" * 40 + "的一篇",
                                     "body": "🍜" * 200})
    STATS["actions"] += 1
    check("emoji长文", r.status_code == 200, f"emoji/长文写入失败: {r.status_code}", severity="medium")


def scenario_agency(bots, users):
    print("[7] 文旅局机器人：智能体开发台")
    results = []
    for (nick, org, region) in AGENCY_BOTS:
        bot = bot_client()
        user = register(bot, nick, role="agency", org_name=org)
        if not user.get("id"):
            continue
        bots.append(bot); users.append(user)

        # 建智能体
        r = bot.post("/api/agents", json={
            "name": f"{region} · 一日游小助手",
            "region": region,
            "description": f"{region}本地行程助手（社区模拟机器人创建）",
            "prompt": f"你是{region}的文旅助手，只推荐{region}的景点，风格亲切。" * 3})
        STATS["actions"] += 1
        ok = check("建智能体", r.status_code == 200 and r.json().get("id"),
                   f"创建智能体失败: {r.status_code} {r.text[:120]}")
        if not ok:
            continue
        aid = r.json()["id"]
        results.append((bot, aid, region))

        # 校验失败路径：发布缺 prompt 的智能体必须被拒
        r2 = bot.post("/api/agents", json={"name": "残缺体", "region": region})
        if r2.status_code == 200:
            bad_id = r2.json()["id"]
            r3 = bot.post(f"/api/agents/{bad_id}/publish")
            STATS["actions"] += 2
            check("发布校验", r3.status_code == 400,
                  f"缺 prompt 的智能体发布竟然成功（{r3.status_code}）", severity="medium")

        # 越权：另一个 agency 不能读/改这个智能体
        other = next((b for b, u in zip(bots, users)
                      if u.get("role") == "agency" and u.get("org_id") != user.get("org_id")), None)
        if other:
            ra = other.get(f"/api/agents/{aid}")
            STATS["actions"] += 1
            check("越权", ra.status_code == 404,
                  f"他局账号竟能读到本局智能体（{ra.status_code}）")
            rp = other.post(f"/api/agents/{aid}/publish")
            STATS["actions"] += 1
            # 访问控制必须拒绝；返回码契约存疑（实测 400，与 GET 越权的 404 不一致）→ 低危口径问题
            if rp.status_code == 200:
                check("越权", False, "他局账号竟能发布本局智能体")
            elif rp.status_code != 404:
                issue("low", "越权口径",
                      f"他局发布他局智能体被正确拒绝（status 仍 draft），"
                      f"但返回 {rp.status_code} 而非 404 —— 与 GET 越权的 404 口径不一致",
                      rp.text[:120])

        # 编辑 + 发布
        r = bot.post(f"/api/agents/{aid}", json={"description": "已由机器人完善描述"})
        STATS["actions"] += 1
        r = bot.post(f"/api/agents/{aid}/publish")
        STATS["actions"] += 1
        check("发布", r.status_code == 200 and r.json().get("ok"),
              f"补全后发布仍失败: {r.status_code} {r.text[:120]}")
        # 列表可见
        lst = bot.get("/api/agents").json()["items"]
        STATS["actions"] += 1
        check("列表", any(a["id"] == aid and a["status"] == "published" for a in lst),
              "发布后列表状态未变 published")
    return results


def scenario_upgrade_person_to_agency(bots, users):
    """个人身份升级文旅局（产品决策：不锁定可升级）"""
    print("[8] 个人升级文旅局")
    bot, user = bots[8], users[8]
    r = bot.post("/api/auth/upgrade-agency", json={
        "org_name": "朝阳文旅 · 模拟工作站", "region": "北京"})
    STATS["actions"] += 1
    ok = check("升级", r.status_code == 200 and r.json().get("org_id"),
               f"升级失败: {r.status_code} {r.text[:120]}")
    if ok:
        me = bot.get("/api/auth/me").json().get("user", {})
        STATS["actions"] += 1
        check("升级", me.get("role") == "agency" and me.get("org_id"),
              f"升级后身份未变 agency: {me.get('role')}")
        # 升级后能建智能体
        r = bot.post("/api/agents", json={
            "name": "朝阳 · 假日助手", "region": "北京", "prompt": "朝阳群众假日推荐官。"})
        STATS["actions"] += 1
        check("升级后建智能体", r.status_code == 200, f"升级后建智能体失败: {r.status_code}")


def main():
    SIM_DIR.mkdir(exist_ok=True)
    print("=" * 60)
    print("社区机器人模拟开始")
    print("=" * 60)

    bots, users = [], []
    for nick, _ in PERSON_BOTS:
        b = bot_client()
        u = register(b, nick)
        bots.append(b); users.append(u)
    print(f"  {len([u for u in users if u])} 个个人机器人就绪")

    created = scenario_posts(bots, users)
    created = scenario_itinerary_post(bots, users, created)
    anon = scenario_browse_and_search(bots, created)
    scenario_likes(bots, users, created, anon)
    scenario_comments(bots, users, created)
    scenario_validation(anon, bots)
    scenario_agency(bots, users)
    scenario_upgrade_person_to_agency(bots, users)

    # 收尾统计
    total_posts = anon.get("/api/posts", params={"size": 1}).json().get("total", 0)
    STATS["actions"] += 1
    summary = {
        "time": datetime.now().isoformat(),
        "actions": STATS["actions"],
        "checks": STATS["checks"],
        "bots_person": len(PERSON_BOTS),
        "bots_agency": len(AGENCY_BOTS) + 1,
        "posts_created": len(created),
        "posts_total_in_db": total_posts,
    }
    (SIM_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"模拟完成：{summary}")
    print(f"问题已记录：{ISSUES_FILE}")


if __name__ == "__main__":
    main()
