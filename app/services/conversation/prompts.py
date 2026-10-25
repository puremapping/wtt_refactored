#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提示词模板：回复与抽取两套（两次独立 LLM 调用的关键设计）"""
import json
from typing import TYPE_CHECKING

from app.services import cities

if TYPE_CHECKING:
    from app.services.conversation.models import Conversation

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
