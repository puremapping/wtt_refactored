#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地区智能体统一抽象（双轨架构的「插座」）

## 为什么要有这一层

智能体有两个来源：

  轨道 A｜builtin  —— 文旅局在我们平台 `/console` 只填了名称/地区/提示词
  轨道 B｜external —— 文旅局自己用 Dify/Coze 做好了，只给一个调用地址

主对话不该知道有两条轨。它只认一个契约：

    agent.region           覆盖地区（路由用）
    agent.answer(question) -> str

本模块把两种来源各自包成同一个契约。**加第三轨（比如接某个开源编排引擎）
只需要再写一个 RegionAgent 子类 + 在 build_agent 里加一个分支，主对话零改动。**

## 纪律

- 本模块**不碰数据库**。它只接收一行 agents 记录（dict），产出可调用对象。
  读写库仍是 `app/services/agents.py` 的事。
- `answer()` 失败不抛异常，返回兜底文案 —— 一个外站智能体挂掉不该拖垮主对话。
  但会在返回体里带上 `degraded=True`，让上层决定怎么向用户解释。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional

# ──────────────────────────────────────────────────────────────
# 抽象
# ──────────────────────────────────────────────────────────────


class Answer:
    """一次智能体回答的结果

    degraded=True 表示这个智能体本该回答但没能回答（超时/报错/空回），
    上层据此决定：是拿这段兜底文案回复用户，还是退回本地逻辑重跑。
    """

    __slots__ = ("text", "degraded", "reason")

    def __init__(self, text: str, degraded: bool = False, reason: str = ""):
        self.text = text
        self.degraded = degraded
        self.reason = reason

    def __repr__(self):
        return (f"Answer(degraded={self.degraded}, reason={self.reason!r}, "
                f"text={self.text[:40]!r})")


class RegionAgent:
    """地区智能体的统一契约 —— 两种实现，对调用方完全同形"""

    kind = "unknown"

    def __init__(self, row: dict):
        self.row = row
        self.id: str = row.get("id") or ""
        self.name: str = row.get("name") or ""
        self.region: str = (row.get("region") or "").strip()
        self.team_id: str = row.get("team_id") or ""
        self.team_name: str = row.get("team_name") or ""
        self.description: str = row.get("description") or ""

    def answer(self, question: str, context: Optional[dict] = None) -> Answer:
        raise NotImplementedError

    def __repr__(self):
        return f"<{type(self).__name__} {self.name!r} region={self.region!r}>"


# ──────────────────────────────────────────────────────────────
# 轨道 A：平台内自建（调 GLM）
# ──────────────────────────────────────────────────────────────


class BuiltinAgent(RegionAgent):
    """用 agents.prompt 当人设，直接调 GLM 回答

    零额外部署：文旅局在后台填一段话，平台就用自家模型跑。
    """

    kind = "builtin"

    def __init__(self, row: dict, llm=None):
        """llm 可注入 —— 测试时传 fake，生产时传 app.services.llm.LLM()"""
        super().__init__(row)
        self.prompt = row.get("prompt") or ""
        self._llm = llm

    @property
    def llm(self):
        # 延迟构造：没配 GLM_API_KEY 时不该在 import 期就炸
        if self._llm is None:
            from app.services.llm import LLM
            self._llm = LLM()
        return self._llm

    def answer(self, question: str, context: Optional[dict] = None) -> Answer:
        q = (question or "").strip()
        if not q:
            return Answer("", degraded=True, reason="问题为空")
        if not self.prompt:
            return Answer("", degraded=True, reason="缺少人设/话术")

        system = (
            f"你是{self.team_name or '地方文旅部门'}的智能体「{self.name}」，"
            f"负责回答关于{self.region or '本地'}的问题。\n"
            f"{self.prompt}\n\n"
            "要求：\n"
            "- 只谈你负责的地区，超出范围就直说不知道，不要编\n"
            "- 回答简洁，2-4 句，不要罗列长清单\n"
            "- 不要暴露你是被平台调用的，就当自己是这个文旅局的助手"
        )
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": q}]
        try:
            text = self.llm.chat(msgs, temperature=0.6) or ""
        except Exception as e:                       # 模型/网络异常都不该拖垮主对话
            return Answer("", degraded=True, reason=f"模型调用失败: {e}")

        text = text.strip()
        if not text:
            return Answer("", degraded=True, reason="模型返回空")
        return Answer(text)


# ──────────────────────────────────────────────────────────────
# 轨道 B：外部智能体注册（HTTP 转发）
# ──────────────────────────────────────────────────────────────


class ExternalAgent(RegionAgent):
    """把问题 POST 到外部地址，拿回答案

    只做**转发**，不打包对方的运行时 —— 对方用什么引擎与我们无关。

    请求体（本项目定义的统一协议）：
        {"question": "...", "region": "...", "context": {...}}
    对方可以返回：
        {"answer": "..."}   或   纯文本

    鉴权放在 agents.auth 里，格式 `Bearer xxx` / `Token xxx`，
    原样塞进 Authorization 头。留空则不带。
    """

    kind = "external"
    TIMEOUT = 8          # 秒。外部智能体是别人的服务，必须设上限

    def __init__(self, row: dict, opener=None):
        """opener 可注入（测试用）—— 签名 (url, data, headers, timeout) -> bytes"""
        super().__init__(row)
        self.endpoint = (row.get("endpoint") or "").strip()
        self.auth = (row.get("auth") or "").strip()
        self._opener = opener or _default_opener

    def answer(self, question: str, context: Optional[dict] = None) -> Answer:
        q = (question or "").strip()
        if not q:
            return Answer("", degraded=True, reason="问题为空")
        if not self.endpoint:
            return Answer("", degraded=True, reason="缺少调用地址")

        payload = {"question": q, "region": self.region, "context": context or {}}
        headers = {"Content-Type": "application/json"}
        if self.auth:
            headers["Authorization"] = self.auth

        try:
            raw = self._opener(self.endpoint, payload, headers, self.TIMEOUT)
        except urllib.error.HTTPError as e:
            return Answer("", degraded=True, reason=f"外部智能体返回 {e.code}")
        except Exception as e:
            return Answer("", degraded=True, reason=f"外部智能体调用失败: {e}")

        return self._parse(raw)

    @staticmethod
    def _parse(raw: Any) -> Answer:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                return Answer("", degraded=True, reason="外部返回非 UTF-8")
        if not isinstance(raw, str):
            return Answer("", degraded=True, reason="外部返回类型异常")

        text = raw.strip()
        if not text:
            return Answer("", degraded=True, reason="外部返回空")

        # 先试 JSON（{"answer": "..."}），失败就当纯文本
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                for key in ("answer", "text", "content", "reply"):
                    v = obj.get(key)
                    if isinstance(v, str) and v.strip():
                        return Answer(v.strip())
            elif isinstance(obj, str) and obj.strip():
                return Answer(obj.strip())
        except json.JSONDecodeError:
            pass

        return Answer(text)


def _default_opener(url: str, payload: dict, headers: dict, timeout: int) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ──────────────────────────────────────────────────────────────
# 工厂
# ──────────────────────────────────────────────────────────────

_KINDS = {"builtin": BuiltinAgent, "external": ExternalAgent}


def build_agent(row: dict, **kwargs) -> Optional[RegionAgent]:
    """把一行 agents 记录变成可调用对象

    返回 None 表示这条记录不该参与路由：
      - 缺 id / region（没有地区就无从路由）
      - kind 不认识（数据脏了，宁可跳过也不要瞎猜）

    kwargs（llm= / opener=）透传给具体实现，供测试注入。
    """
    if not row or not (row.get("id") or ""):
        return None
    if not (row.get("region") or "").strip():
        return None

    kind = (row.get("kind") or "builtin").strip().lower()
    cls = _KINDS.get(kind)
    if cls is None:
        return None

    accept = {"llm": "llm", "opener": "opener"}
    pass_kwargs = {accept[k]: v for k, v in kwargs.items() if k in accept}
    return cls(row, **pass_kwargs)
