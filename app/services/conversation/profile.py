#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画像：动机七类 / 合并 / 证据校验 / 占位词清洗 / ready 判据"""
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.conversation.models import Conversation

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

# 「等于没填」的占位词 —— 模型有时会把它们当字面值填进字段
_PLACEHOLDER_VALUES = {
    "未知", "不清楚", "不确定", "不知道", "待定", "未定", "未提及",
    "未指定", "未提供", "未说明", "暂无", "无", "没有", "none", "null",
    "n/a", "na", "-", "--", "?", "？", "不限", "都可以", "随便", "都行",
    "任意", "其他", "其它",
}

# 各字段的"证据要求"：用户话里必须出现这些词，才接受该字段
_FIELD_EVIDENCE = {
    "companions": ["一个人", "独自", "自己", "单独", "爸妈", "父母", "爸", "妈",
                   "女朋友", "男朋友", "对象", "老婆", "老公", "朋友", "同事",
                   "孩子", "娃", "家人", "全家", "情侣", "带", "陪", "跟", "和"],
    "pace": ["赶", "紧凑", "慢", "松", "悠闲", "不赶", "轻松"],
}


def _clean_field_value(v):
    """清洗字段值：占位词/纯符号 → 空串

    ⚠️ 实测教训：模型会把「未知」这类占位词当字面值填进 destination，
    下游把「未知」当城市名误判，输出「未知还查不了」这种荒谬回复。
    必须在入口就归一成空。
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
