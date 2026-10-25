#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多轮动机对话（Travel for What）

与 v0.1 的区别：
  - v0.1：单轮，一句话 → 直接出动机标签（本质是表单）
  - v0.2：多轮开放对话，每轮调一次 LLM 做两件事：
      ① 生成回复（接住用户的话 / 追问 / 建议看行程）
      ② 抽取并合并线索到画像 JSON

会话状态存服务端（sessions 表），用户可无限轮聊下去。
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.db import connect
from app.services import cities
from app.services.llm import LLM
from app.services.tools import get_tools

# ── 动机分类（沿用 PRD 七类）──
MOTIVATIONS = {
    "恢复/逃离": "想放松、逃离日常、需要休息",
    "连接/关系": "和家人朋友一起、增进感情",
    "探索/新奇": "想看没见过的东西、尝鲜",
    "表达/展示": "想拍照、出片、分享",
    "成就/完成": "想打卡、完成心愿清单",
    "文化/沉浸": "想深入了解历史文化",
    "美食/感官": "冲着吃去的",
}

# 画像字段说明（给 LLM 看，用于判断信息是否充分）
PROFILE_FIELDS = {
    "destination": "目的地城市（如「北京」「上海」）。用户提到去哪就填。**没说就省略这个字段**，不要填「未知」。",
    "origin": "出发地城市（可选）。用户提到从哪出发才填。",
    "primary": "主动机（七类之一）",
    "primary_intensity": "主动机强度 1-5",
    "secondary": "次要动机列表（0-2 个）",
    "hours": "可用时长（1-12 整数，小时）",
    "companions": "同伴（独自/情侣/父母/朋友/带娃）",
    "pace": "节奏偏好（紧凑/适中/松散）",
    "interests": "具体兴趣点列表（如『古建筑』『咖啡馆』）",
    "avoid": "明确不想要的列表",
    "must_see": "必去清单",
    "summary": "**用一两句自然语言概括用户这次想要什么**，保留他自己的说法与语气。",
}

# 列表类字段（支持增删）
LIST_FIELDS = {"secondary", "interests", "avoid", "must_see"}


@dataclass
class Conversation:
    """一次多轮对话的状态"""
    session_id: str = ""
    messages: list = field(default_factory=list)      # [{role, content}]
    profile: dict = field(default_factory=dict)       # 累积的画像
    turn: int = 0
    ready: bool = False                               # 信息是否足够生成行程
    created_at: str = ""
    tool_calls: list = field(default_factory=list)    # 本轮 LLM 请求调用的工具
    itinerary: dict = field(default_factory=dict)     # 当前行程（匿名会话需要）

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "profile": self.profile,
            "turn": self.turn,
            "ready": self.ready,
            "created_at": self.created_at,
        }


REPLY_PROMPT = """你是「Where to Travel」的旅行需求访谈助手。通过自然对话搞清楚用户**这次为什么想旅行**——不是去哪，而是想获得什么。

## 你的风格
- 像朋友聊天，不像问卷调查
- **接住用户的话**，顺着往下问，不要生硬换话题
- 一次只问一个问题
- 回复**简短**，2-3 句就够

## ⚠️ 不要编造事实（重要）
- **你不知道景点的营业时间、票价、电话、具体地址**
- 用户问这类问题，就说「这个我这边查不到准确信息，建议出行前在官方渠道确认」
- 可以说的：人流指数、所在区、景区等级、行程距离——这些数据你有
- **宁可说不知道，不要编一个看起来对的时间**

## ⚠️ 你只有这些城市的数据（重要！）
- **你的景点数据库覆盖：{supported}。**
- 用户提到其他城市（上海/成都/西安…）时，**必须老实说**：
  「我目前只有{supported}的数据，别的城市还查不了。」
- **绝不能说「我有上海的」「上海有很多好玩的」这类话 —— 那是撒谎。**
- 你可以说：这几个城市的数据能给你具体安排；其他城市当前帮不上。
- 如果用户想去别的城市，可以问要不要先看支持的城市，或说明现在是 MVP 阶段。

## ⚠️ 用户明确要求时，先执行，不要追问
- 用户说「生成行程」「帮我排一下」时 → **直接调用工具**，不要再问问题
- 信息不全（比如不知道城市）时：**用默认值直接生成，并在回复里说明假设**
  （例：「我先按北京给你排，如果要换城市告诉我」）
- **追问是缺信息时的默认行为，但不能压过用户的明确指令**

## 追问技巧（按需选用，别连续追问）
- **投射式**：「如果这次旅行是一种状态，你希望是哪一种？」
- **对比选择**：给两个方向让用户挑
- **场景回忆**：「上一次觉得特别好的旅行是什么样的？」
- **反向问题**：「有什么是你这次特别不想遇到的？」

## 判断何时可以给建议
当主动机已明确，且时长或同伴至少有一个明确时 → 主动问：
「我大概明白了，要不要看看给你排的行程？」
在此之前不要急着提议。

直接输出你要说的话，不要任何格式标记、不要 JSON、不要加引号。
"""

EXTRACT_PROMPT = """你是信息抽取器。从旅行对话中抽取结构化信息。

## 主动机分类（`primary` 只能选一个）

判断依据是**用户想获得什么**，不是字面词：

| 动机 | 用户会怎么说（判据） |
|---|---|
| `恢复/逃离` | 「太累了」「想放松」「放空」「逃离」「安静」「不想动脑」「压力大」「休息」「人少」 |
| `连接/关系` | 「和家人」「陪爸妈」「朋友一起」「增进感情」「陪孩子」「纪念日」 |
| `探索/新奇` | 「想看看没见过的」「尝鲜」「小众」「没去过」「猎奇」「新鲜感」 |
| `表达/展示` | 「拍照」「出片」「发朋友圈」「好看」「机位」「打卡照」 |
| `成就/完成` | 「打卡」「必去」「都走一遍」「心愿清单」「经典路线」「集邮」 |
| `文化/沉浸` | 「历史文化」「想了解」「深度」「讲解」「本地生活」「古建筑」「博物馆」 |
| `美食/感官` | 「吃」「美食」「小吃」「老字号」「馆子」「探店」 |

**易混淆点（重要）：**
- 「想找人少的地方」→ 是 `恢复/逃离`，**不是** `探索/新奇`（关键词是"人少"=躲避人群）
- 「想去没去过的地方」→ 才是 `探索/新奇`
- 「想去故宫长城」→ 通常是 `成就/完成`（打卡），除非用户说想了解历史 → `文化/沉浸`
- 判不准就**不填 primary**，宁缺勿错

## 其他字段
- `destination`：目的地城市。用户提到「去北京」「上海玩」就填「北京」「上海」
  ⚠️ **不知道就省略这个字段，绝对不要填「未知」「不确定」「待定」「无」这类占位词** ——
  那会被下游当成「一个叫未知的城市」，输出荒谬回复
- `origin`：出发地。用户说「从天津出发」才填，没说省略
- `primary_intensity`：1-5 整数。明确强烈（"特别累""就想"）=4-5；随口提=2-3
- `secondary`：次要动机列表（0-2 个，同样从七类里选）
- `hours`：可用时长，**1-12 的整数**（「一天」=8，「半天」=4，「一天半」=12，「一下午」=4）
- `companions`：**只在用户明说时填**（独自/情侣/父母/朋友/带娃）。没说就**省略这个字段**
- `pace`：节奏（紧凑/适中/松散），只在明说时填
- `interests`：具体兴趣点列表（如「古建筑」「咖啡馆」）
- `avoid`：明确不想要的列表
- `must_see`：必去清单
- `summary`：**用一两句自然语言概括用户这次想要什么**，尽量保留他自己的说法和语气

## ⚠️ 列表字段的增删（重要）

`secondary` / `interests` / `avoid` / `must_see` 是列表，支持**增加**和**删除**：

- 用户**新增**某项 → 正常写在对应列表里
- 用户**否定/撤回**某项 → 用 `"字段名_remove"` 作为键，值是**要删掉的内容**

例：用户先说「想逛博物馆和咖啡馆」，后来说「不用博物馆了」
→ 第二次抽取输出：
```json
{"interests": ["咖啡馆"], "interests_remove": ["博物馆"]}
```

例：用户说「不去故宫了」
```json
{"must_see_remove": ["故宫"]}
```

**别用负号或 `-` 表示删除，就用 `字段名_remove` 这个键。**

## 规则
1. **只输出本轮新得知或修正的字段**，没提到的一律省略（不要填 null）
2. **不要推测**：用户没说同伴就别填 companions
3. **用户纠正时以最新为准**：如果后来说的和前面矛盾，输出修正后的值
4. 输出是 JSON 对象

例：「太累了想找个人少的地方待着」
→ {"primary":"恢复/逃离","primary_intensity":4}
（没提到的字段直接省略，不要写 null）
"""


def _build_system_prompt() -> str:
    fields = "\n".join(f"- `{k}`：{v}" for k, v in PROFILE_FIELDS.items())
    # 注意：模板里的 {{ }} 是给 format 转义用的，这里用 replace 拼接，要还原。
    sp = EXTRACT_PROMPT
    sp = sp.replace("{{", "{").replace("}}", "}")
    return sp


def _merge_profile(old: dict, new: dict) -> dict:
    """合并画像

    规则：
      - 标量字段：新值覆盖旧值
      - `xxx_remove`：从 xxx 列表里删掉这些项（新增于 v0.3）
      - 其他列表：去重累加
    """
    out = dict(old or {})

    # ① 先处理删除指令 —— 必须在累加之前，否则刚加的又被删
    for k, v in (new or {}).items():
        if not k.endswith("_remove"):
            continue
        base = k[:-len("_remove")]
        if base not in LIST_FIELDS:
            continue
        cur = out.get(base) or []
        drop = v if isinstance(v, list) else [v]
        out[base] = [x for x in cur if x not in drop]

    # ② 再处理常规字段
    for k, v in (new or {}).items():
        if k.endswith("_remove"):
            continue
        if v is None or v == "" or v == []:
            continue
        if isinstance(v, list):
            prev = out.get(k) or []
            merged = list(prev)
            for item in v:
                if item and item not in merged:
                    merged.append(item)
            out[k] = merged
        elif k == "primary_intensity":
            try:
                iv = int(v)
                out[k] = max(1, min(5, iv))
            except (ValueError, TypeError):
                continue
        elif k == "hours":
            iv = _norm_hours(v)
            if iv:
                out[k] = iv
        elif k == "primary":
            # 校验：必须是七类之一，否则忽略（防止模型自造分类）
            if v in MOTIVATIONS:
                out[k] = v
        else:
            out[k] = v
    return out


# 各字段的"证据要求"：用户话里必须出现这些词，才接受该字段
_FIELD_EVIDENCE = {
    "companions": ["一个人", "独自", "自己", "单独", "爸妈", "父母", "爸", "妈",
                   "女朋友", "男朋友", "对象", "老婆", "老公", "朋友", "同事",
                   "孩子", "娃", "家人", "全家", "情侣", "带", "陪", "跟", "和"],
    "pace": ["赶", "紧凑", "慢", "松", "悠闲", "不赶", "轻松"],
}


def _has_evidence(field: str, user_text: str) -> bool:
    """检查用户话里是否有该字段的证据。

    实测教训：glm-4-flash 会无视 prompt 里「不要推测」的要求，
    在用户没说同伴时自己补一个 companions。这类需在代码层拦。
    """
    words = _FIELD_EVIDENCE.get(field)
    if not words:
        return True
    return any(w in user_text for w in words)


def _all_user_text(conv: "Conversation") -> str:
    return " ".join(m["content"] for m in conv.messages if m.get("role") == "user")


def _norm_hours(h):
    """时长规范化（复刻 v0.1 的逻辑）"""
    import re
    if h is None:
        return None
    if isinstance(h, (int, float)):
        iv = int(h)
        return iv if 1 <= iv <= 12 else None
    s = str(h).strip().lower()
    num = None
    if "一天半" in s or "1.5" in s:
        num = 1.5
    elif "半天" in s:
        num = 0.5
    elif any(x in s for x in ("上午", "早上", "下午")):
        num = 4
    elif "晚上" in s:
        num = 3
    elif "中午" in s:
        num = 2
    else:
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        if m:
            num = float(m.group(1))
        else:
            for ch, v in {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4,
                          "五": 5, "六": 6, "七": 7, "八": 8}.items():
                if ch in s:
                    num = v
                    break
    if num is None:
        return None
    if "day" in s or "天" in s or "日" in s:
        num *= 8
    iv = int(round(num))
    return iv if 1 <= iv <= 12 else None


def _format_itinerary_brief(itinerary: dict) -> str:
    """把行程压成摘要（给 LLM 看，省 token）

    只给关键信息：站名、时间、区、人流。不给全量 JSON。
    """
    if not itinerary or not itinerary.get("stops"):
        return ""
    stops = itinerary["stops"]
    lines = []
    for s in stops:
        crowd = ""
        if s.get("crowd") is not None:
            crowd = f" 人流{s['crowd']:.0f}"
        lines.append(f"{s.get('order', 0)}. {s.get('arrive', '')} "
                     f"{s.get('name', '')}（{s.get('level', '')}·"
                     f"{s.get('district', '')}{crowd}）")
    risk = "；".join(itinerary.get("risks", [])[:2])
    return (f"\n\n【当前行程】\n"
            f"动机：{itinerary.get('motivation', '')} | "
            f"{itinerary.get('hours', '')} 小时 | "
            f"共 {len(stops)} 站 | "
            f"{itinerary.get('total_distance_km', '')} 公里\n"
            + "\n".join(lines)
            + (f"\n风险：{risk}" if risk else ""))


def _build_reply_messages(conv: "Conversation", itinerary: dict = None):
    """生成回复用的消息（带对话历史 + 当前行程）

    itinerary：右侧当前展示的行程。传进来让 AI「看得见」用户在看什么，
    这样用户说「最后那个太远了」时，AI 知道「最后那个」指哪。
    """
    # ⚠️ 城市列表从数据库算，不写死在 prompt 里 —— 加城市只导入数据，不改代码
    system = REPLY_PROMPT.replace(
        "{supported}", cities.supported_description())
    msgs = [{"role": "system", "content": system}]

    ctx = []
    if conv.profile:
        known = "、".join(f"{k}={v}" for k, v in conv.profile.items()
                          if v and not k.startswith("_"))
        if known:
            ctx.append(f"已知信息：{known}")
    if itinerary:
        ctx.append(_format_itinerary_brief(itinerary).strip())
    if ctx:
        msgs.append({"role": "system", "content": "\n\n".join(ctx)})

    msgs += conv.messages[-20:]
    return msgs


def _build_extract_messages(conv: "Conversation"):
    """抽取画像用的消息

    ⚠️ 关键：**只给最近几轮的用户原话，绝不给 assistant 回复、也不给完整对话结构。**
    实测教训：一旦把对话历史（含 assistant 消息）塞进来，模型会「续写对话」
    而不是执行抽取 —— 表现为返回自然语言，parse_json 得到 None。
    """
    msgs = [{"role": "system", "content": EXTRACT_PROMPT}]

    # 取用户的完整发言（不只是最近几句）—— 动机往往在后面的话里才显出来
    user_lines = [m["content"] for m in conv.messages if m.get("role") == "user"]

    parts = []
    if conv.profile:
        parts.append("已抽取到的信息（**如有新信息，可以修正之前的判断**）："
                     + json.dumps(conv.profile, ensure_ascii=False))
    parts.append("用户的完整发言（按时间顺序）：\n"
                 + "\n".join(f"{i+1}. {t}" for i, t in enumerate(user_lines)))
    parts.append(
        "请综合以上全部内容抽取结构化信息，只返回 JSON。\n"
        "注意：**如果后面的发言推翻了前面的判断，以最新的为准**。"
    )

    msgs.append({"role": "user", "content": "\n\n".join(parts)})
    return msgs


def _fallback_reply(tool_calls: list, conv: "Conversation") -> str:
    """模型返回 tool_calls 但 content 为空时的兜底回复

    实测：模型决定调工具时常不写正文，直接给 tool_calls。
    """
    if not tool_calls:
        return _substantive_fallback(conv)

    tc = tool_calls[0]
    name = tc.get("name")
    args = tc.get("args") or {}

    if name == "generate_itinerary":
        return "好，我按你现在说的给你排一条行程。"

    if name == "propose_modify_itinerary":
        act = args.get("action")
        target = args.get("target") or ""
        reason = args.get("reason") or ""
        label = {
            "replace": "换掉", "remove": "去掉", "add": "加一个",
            "reorder": "调整顺序", "regenerate": "重新生成",
        }.get(act, "调整")
        s = f"我建议{label}"
        if target:
            s += f"「{target}」"
        if reason:
            s += f"——{reason}"
        s += "。要改吗？"
        return s

    return "好的，我来处理。"


def _substantive_fallback(conv: "Conversation") -> str:
    """正文为空且无工具调用时的兜底 —— 给实质内容，不敷衍

    优先级：有动机 → 顺着动机问最关键的一个缺口；
            没动机 → 问动机（这是产品的核心入口）。
    """
    p = conv.profile or {}
    mot = p.get("primary")
    dest = _clean_field_value(p.get("destination"))
    hours = p.get("hours")

    if not mot:
        return ("我先问最关键的一件事：**你这次出去是为了什么？**\n\n"
                "比如想歇一歇、想陪家人、想找点新鲜感——说法随意，"
                "我按这个来挑地方。")

    if not hours:
        return f"明白，这次是「{mot}」。\n\n那你大概能空出多久？半天还是一整天？"

    if not dest:
        return (f"好，这次是「{mot}」，大概 {hours} 小时。\n\n"
                f"想去哪个城市？我目前有**{cities.supported_description()}**的完整数据。")

    return "我先把条件理一理，你要补充什么随时说。"


# 「等于没填」的占位词 —— 模型有时会把它们当字面值填进字段
_PLACEHOLDER_VALUES = {
    "未知", "不清楚", "不确定", "不知道", "待定", "未定", "未提及",
    "未指定", "未提供", "未说明", "暂无", "无", "没有", "none", "null",
    "n/a", "na", "-", "--", "?", "？", "不限", "都可以", "随便", "都行",
    "任意", "其他", "其它",
}


def _clean_field_value(v):
    """清洗字段值：占位词/纯符号 → 空串

    ⚠️ 实测教训：模型会把「未知」这类占位词当字面值填进 destination，
    下游 _is_beijing("未知") 返回 False → 误判为「非北京城市」，
    输出「未知还查不了」这种荒谬回复。必须在入口就归一成空。
    """
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    # 纯标点/空白
    if all(c in "-—–_./\\|*#?？!！,，。.、;；:：" for c in s):
        return ""
    if s.lower() in _PLACEHOLDER_VALUES or s in _PLACEHOLDER_VALUES:
        return ""
    return s


def _is_supported_destination(dest: str) -> bool:
    """判断目的地是否在数据覆盖范围内

    ⚠️ 不再硬编码「北京」—— 从数据库的城市注册表判断（app/services/cities.py）。
       加第二座城市只需导入数据，不用改这里。

    ⚠️ 「未知」「不确定」这类占位词 = 用户没说过目的地 → 视为空（True）。
       不能当成「一个叫未知的城市」。
    """
    d = _clean_field_value(dest)
    if not d:
        return True
    return cities.is_supported(d)


def _clean_reply(reply: str) -> str:
    """清理回复里的杂质

    实测：模型调工具时，有时会把流式响应碎片（JSON 片段）当正文吐出来，
    形如 `我查一下{"index":0,"finish_reason":"tool_calls","delta":...`
    """
    if not reply:
        return ""
    t = reply.strip()

    # 砍掉从 `{"index"` 开始的流式碎片
    for marker in ('{"index"', '{"id"', '"finish_reason"'):
        i = t.find(marker)
        if i > 0:
            t = t[:i].rstrip()
            break

    # 若是纯 JSON 对象，丢弃（不该当正文）
    if t.startswith("{") and t.endswith("}"):
        return ""

    return t.strip()


def _is_generate_intent(user_text: str) -> bool:
    """判断用户是否真的要生成行程

    实测教训：glm-4-flash 会在用户只是提问时也调 generate_itinerary。
    光靠工具描述里写「不要调用」不够，服务端要二次把关。

    这是**白名单式**判断：只有用户明确表达生成意愿才放行。
    """
    t = (user_text or "").strip()
    if not t:
        return False
    triggers = [
        "生成", "排个", "排一下", "安排", "规划", "出个", "做个",
        "看看行程", "看行程", "出方案", "怎么玩", "怎么安排",
        "换一批", "重新来", "再来一版",
    ]
    return any(k in t for k in triggers)


def _should_allow_propose(user_text: str) -> bool:
    """判断是否该允许 propose_modify

    实测教训：服务端过滤太严会让该调的也不调。
    场景「最后那个太远了，换一个」应触发 propose —— 不能因为
    它不含「生成」类词就被砍掉。
    """
    t = (user_text or "").strip()
    if not t:
        return False
    # 排除「换一批」这类整条重来的（那该走 generate）
    if any(k in t for k in ("换一批", "重新生成", "重新来", "再来一版",
                            "其他的", "别的")):
        return False
    triggers = [
        "换", "太远", "太赶", "不想去", "去掉", "删", "加一个", "加点",
        "顺序", "倒过来", "调整", "改一下", "改成", "不好", "不合适",
        "有没有别的", "还有其他",
    ]
    return any(k in t for k in triggers)


def _sanitize_tool_calls(tool_calls: list, user_text: str,
                         has_itinerary: bool) -> list:
    """服务端校验 + 过滤工具调用

    过滤规则：
      1. 没有行程时，不允许 propose_modify（工具层面已不给，这里是双保险）
      2. propose 需要「调整意图」，否则丢弃
      3. generate 需要「生成意图」，否则丢弃
      4. 参数非法时丢弃
    """
    out = []
    for tc in tool_calls or []:
        name = tc.get("name")
        args = tc.get("args") or {}

        if name == "propose_modify_itinerary":
            if not has_itinerary:
                continue
            if args.get("action") not in ("replace", "remove", "add", "reorder"):
                continue
            if not _should_allow_propose(user_text):
                continue
            out.append(tc)

        elif name == "generate_itinerary":
            if not _is_generate_intent(user_text):
                continue
            out.append(tc)

    return out


def chat(session_id: Optional[str], user_text: str,
         llm: Optional[LLM] = None,
         current_itinerary: dict = None,
         user_id: str = None) -> Conversation:
    """处理一轮对话：用户说话 → AI 回复 + 更新画像 + 可能的工具调用

    关键设计：
      - **生成回复**与**抽取画像**是两次独立调用。
        实测教训：合成一次调用时，多轮历史会让模型「学样」回自然语言，
        忽略 JSON 格式要求（即使是 glm-4-flash 开了 response_format）。
      - **current_itinerary** 让 AI「看得见」右侧行程，用户说「最后那个太远」
        时它知道指哪。
      - 回复调用带 tools，模型可请求 `generate_itinerary` /
        `propose_modify_itinerary`；真正的执行由上层做。
      - **user_id**：为空 = 匿名（会话只存内存，刷新即丢）
    """
    llm = llm or LLM()

    # 1. 取或建会话
    conv = load_session(session_id, user_id) if session_id else None
    if conv is None:
        conv = Conversation(
            session_id=uuid.uuid4().hex[:12],
            created_at=datetime.now().isoformat(),
        )
    if not conv.created_at:
        conv.created_at = datetime.now().isoformat()

    # 2. 追加用户消息
    conv.messages.append({"role": "user", "content": user_text})
    conv.turn += 1

    # 3. 抽取画像（独立调用，强制 JSON）
    new_profile = {}
    extract_error = None
    try:
        extracted = llm.json_chat(_build_extract_messages(conv), temperature=0.0)
        if isinstance(extracted, dict):
            new_profile = extracted
        else:
            extract_error = f"抽取返回非 dict: {type(extracted).__name__}"
    except Exception as e:
        extract_error = f"{type(e).__name__}: {e}"

    # 4. 生成回复（独立调用，带 tools，可能返回 tool_calls）
    reply = ""
    tool_calls = []
    try:
        msg = llm.chat_raw(
            _build_reply_messages(conv, itinerary=current_itinerary),
            temperature=0.6,
            tools=get_tools(has_itinerary=bool(current_itinerary)),
        )
        reply = (msg.content or "").strip().strip('"').strip("'").strip()
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "name": tc.function.name,
                    "args": args,
                })
    except Exception as e:
        if not reply:
            reply = f"（回复生成异常：{e}）"

    # 清理：模型有时把工具参数当正文吐出来（流式碎片）
    reply = _clean_reply(reply)

    # 服务端校验 tool_calls（防误触发）
    has_itin = bool(current_itinerary)
    _raw_count = len(tool_calls)
    tool_calls = _sanitize_tool_calls(tool_calls, user_text, has_itin)

    # ⚠️ 关键补救：模型本打算调工具（所以没写正文），但服务端把工具拦掉了
    #    → 此刻 reply 和 tool_calls 双空，用户会收到空洞兜底。
    #    正确做法：**重新让模型用文字回答**（去掉 tools 再问一次），
    #    而不是套模板 —— 模板不看用户说了什么，必然答非所问。
    if not reply and not tool_calls and _raw_count > 0:
        try:
            msg2 = llm.chat_raw(
                _build_reply_messages(conv, itinerary=current_itinerary),
                temperature=0.6,
                tools=None,          # ← 不给工具，逼它说话
            )
            reply = _clean_reply((msg2.content or "").strip())
        except Exception:
            pass

    # ⚠️ 数据边界拦截：只有数据覆盖的城市
    # 实测教训：模型会声称「我有上海的数据」并给出北京行程（静默错误）。
    # 光靠 prompt 告知无效，必须服务端硬拦。
    # ⚠️ 且必须先清洗 —— 模型会把「未知」当目的地填进来，不能当「一个叫未知的城市」。
    # ⚠️ 关键时序：合并画像在下面第 5 步，此处 conv.profile 还是**上一轮**的值。
    #    必须优先用本轮新抽到的 destination，否则「这轮才说上海」会被漏拦。
    dest = _clean_field_value(
        new_profile.get("destination")
        if isinstance(new_profile, dict) and new_profile.get("destination")
        else conv.profile.get("destination"))
    blocked = bool(dest) and not _is_supported_destination(dest)

    # 反向补齐：用户明确要求生成，但模型没调工具 → 强制补上
    # 实测教训：加了 destination 字段后，模型会优先追问「去哪个城市」
    # 而忽略用户明确的「生成行程」指令。光靠 prompt 纠正不可靠。
    # ⚠️ 若目的地不支持，不能补 —— 否则强行生成北京行程给上海需求（静默错误）
    if (not tool_calls and not has_itin and not blocked
            and _is_generate_intent(user_text)):
        tool_calls = [{
            "name": "generate_itinerary",
            "args": {"hours": conv.profile.get("hours")} if conv.profile.get("hours") else {},
            "forced": True,
        }]
        if reply and "生成行程" not in reply and "排" not in reply:
            reply = f"好，我先按{cities.city_names()[0]}给你排一条，要换城市随时说。"

    # ⚠️ 数据边界拦截：只有数据覆盖的城市
    if blocked:
        tool_calls = [t for t in tool_calls if t["name"] != "generate_itinerary"]
        supported = cities.supported_description()
        if not any(c in reply for c in cities.city_names()):
            reply = (f"我目前只有**{supported}**的景点数据，"
                     f"{dest}还查不了。\n\n"
                     f"要不要先看看这几个城市的安排？或者等我们接入{dest}的数据。")

    if not reply:
        # 模型返回 tool_calls 时 content 常为空 —— 不能直接兜底成「能再多说说吗」
        reply = _fallback_reply(tool_calls, conv)

    # 5. 合并画像（先做证据校验，拦掉模型瞎补的字段）
    user_text_all = _all_user_text(conv)
    filtered = {}
    for k, v in (new_profile or {}).items():
        if k in _FIELD_EVIDENCE and not _has_evidence(k, user_text_all):
            continue          # 用户没说，拒绝这个字段
        # 清洗：占位词（「未知」「不确定」「无」…）不该进画像
        if isinstance(v, str):
            v = _clean_field_value(v)
            if not v:
                continue
        elif isinstance(v, list):
            v = [x for x in (_clean_field_value(i) for i in v) if x]
            if not v:
                continue
        filtered[k] = v
    conv.profile = _merge_profile(conv.profile, filtered)

    if extract_error:
        conv.profile["_extract_error"] = extract_error
    # 记录轮数（供 ready 判据用；不对外暴露）
    conv.profile["_turns"] = conv.turn

    # 6. 服务端判据（不信 LLM 自报）
    conv.ready = _is_ready(conv.profile)

    conv.messages.append({"role": "assistant", "content": reply})
    conv.tool_calls = tool_calls          # 供上层执行
    save_session(conv, user_id)
    return conv


def _is_ready(profile: dict) -> bool:
    """服务端判据：至少聊过 2 轮，且动机明确 +（时长或同伴）有一个

    加轮数门槛的原因：实测第 1 轮「想去北京玩一天」就被判成「探索/新奇」，
    但那句话里根本没有动机信息。动机要聊几句才显出来。
    """
    if profile.get("_turns", 0) < 2:
        return False
    has_motive = bool(profile.get("primary"))
    has_ctx = bool(profile.get("hours")) or bool(profile.get("companions"))
    return has_motive and has_ctx


# ── 会话持久化 ──

def save_session(conv: Conversation, user_id: str = None):
    """保存会话

    ⚠️ 核心规则：**匿名会话不落库**（阿哲定）。
    user_id 为空时只更新内存里的匿名会话，不写数据库。
    """
    if not user_id:
        _anon_put(conv)
        return
    with connect() as conn:
        conn.execute(
            """INSERT INTO sessions
                 (id, user_id, created_at, turn_count, profile, motivations, itinerary)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 profile     = excluded.profile,
                 motivations = excluded.motivations,
                 turn_count  = excluded.turn_count""",
            (conv.session_id, user_id, conv.created_at, conv.turn,
             json.dumps({
                 "profile": conv.profile,
                 "messages": conv.messages,
                 "turn": conv.turn,
                 "ready": conv.ready,
             }, ensure_ascii=False),
             json.dumps(conv.profile, ensure_ascii=False),
             "{}"))


def load_session(session_id: str, user_id: str = None) -> Optional[Conversation]:
    """载入会话

    user_id 为空 → 从匿名内存取；否则从 DB 取（且必须是该用户的）
    """
    if not user_id:
        return _anon_get(session_id)

    with connect() as conn:
        row = conn.execute(
            "SELECT id, created_at, profile FROM sessions "
            "WHERE id=? AND user_id=?",
            (session_id, user_id)).fetchone()
    if not row:
        return None
    payload = json.loads(row["profile"] or "{}")
    return Conversation(
        session_id=row["id"],
        created_at=row["created_at"],
        profile=payload.get("profile", {}),
        messages=payload.get("messages", []),
        turn=payload.get("turn", 0),
        ready=payload.get("ready", False),
    )


# ── 匿名会话：进程内存储，带 TTL ──
# 设计：匿名不落库，刷新即丢；服务端只是暂存，避免一轮请求之间状态丢失
import time as _time
import threading as _threading

_ANON_SESSIONS: dict = {}
_ANON_LOCK = _threading.Lock()
ANON_TTL = 3600          # 1 小时没访问就清


def _anon_put(conv: "Conversation"):
    with _ANON_LOCK:
        _ANON_SESSIONS[conv.session_id] = (conv, _time.time())


def _anon_get(session_id: str) -> Optional["Conversation"]:
    with _ANON_LOCK:
        item = _ANON_SESSIONS.get(session_id)
        if not item:
            return None
        conv, _ = item
        _ANON_SESSIONS[session_id] = (conv, _time.time())
        return conv


def _anon_cleanup():
    """清理过期匿名会话（由后台线程定期调用）"""
    now = _time.time()
    with _ANON_LOCK:
        dead = [k for k, (_, ts) in _ANON_SESSIONS.items()
                if now - ts > ANON_TTL]
        for k in dead:
            del _ANON_SESSIONS[k]
    return len(dead)


def profile_summary(profile: dict) -> str:
    """画像 → 一句话摘要（过滤内部字段）"""
    if not profile:
        return "还没了解到什么"
    p = {k: v for k, v in profile.items() if not k.startswith("_")}
    if not p:
        return "还没了解到什么"
    parts = []
    if p.get("primary"):
        s = p["primary"]
        if p.get("primary_intensity"):
            s += f"（强度 {p['primary_intensity']}/5）"
        parts.append(s)
    if p.get("secondary"):
        parts.append("次要：" + "、".join(p["secondary"]))
    if p.get("hours"):
        parts.append(f"{p['hours']} 小时")
    if p.get("companions"):
        parts.append(f"同伴：{p['companions']}")
    if p.get("pace"):
        parts.append(f"节奏：{p['pace']}")
    if p.get("interests"):
        parts.append("兴趣：" + "、".join(p["interests"][:3]))
    if p.get("avoid"):
        parts.append("避开：" + "、".join(p["avoid"][:2]))
    if p.get("must_see"):
        parts.append("必去：" + "、".join(p["must_see"][:3]))
    return " · ".join(parts) if parts else "还没了解到什么"


def public_profile(profile: dict) -> dict:
    """对外暴露的画像（剔除 _ 开头的内部字段）"""
    return {k: v for k, v in (profile or {}).items() if not k.startswith("_")}
