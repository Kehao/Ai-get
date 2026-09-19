"""寻找对象的文本解析：把一段自然语言画像拆成条件条目与挖掘策略分组。

条件条目的左侧色条颜色由这里统一分配，避免前后端各写一份色表后逐渐漂移。
"""

from __future__ import annotations

from ..models import StrategyGroup, TargetCondition
from .synth import CITIES

# 与参考站一致的四色循环：violet / orange / sky / emerald
CONDITION_COLORS: tuple[str, ...] = ("#8b5cf6", "#fb923c", "#0ea5e9", "#10b981")

_SEPARATORS: tuple[str, ...] = ("，", ",", "；", ";", "。", "、", "\n")

MAX_CONDITION_COUNT = 4


def split_query(text: str) -> list[str]:
    """按中文/英文标点切句，返回保留顺序的片段列表。"""
    normalized = text
    for separator in _SEPARATORS:
        normalized = normalized.replace(separator, "|")
    return normalized.split("|")


def shorten(text: str, limit: int = 22) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= limit else f"{stripped[:limit]}…"


def detect_city(text: str) -> str | None:
    return next((city for city in CITIES if city in text), None)


def conditions_from_texts(texts: list[str]) -> list[TargetCondition]:
    """按顺序把条件文本包装成条目，颜色按位置循环分配。

    保存配置时直接走这里，因此用户删掉的条件不会在保存后被重新补回来。
    """
    return [
        TargetCondition(
            id=f"condition-{index}",
            text=text,
            color=CONDITION_COLORS[index % len(CONDITION_COLORS)],
        )
        for index, text in enumerate(texts)
    ]


def build_conditions(query: str) -> list[TargetCondition]:
    """把画像正文拆成展示用条件条目，单条保持简短，最多 4 条再补 2 条兜底规则。"""
    texts = [shorten(item) for item in split_query(query) if item.strip()][:MAX_CONDITION_COUNT]

    city = detect_city(query)
    if city:
        texts.append(f"优先选择在{city}的企业")
    texts.append("补齐行业、规模与联系方式后再进入触达")

    return conditions_from_texts(texts)


def build_strategy_groups(query: str) -> list[StrategyGroup]:
    """生成两组挖掘策略：第一组解释核心诉求，第二组解释覆盖范围如何外扩。

    示例条目直接取自画像原文片段，因此用户改完「寻找对象」后策略说明会同步变化。
    """
    segments = [item.strip() for item in split_query(query) if item.strip()]
    if not segments:
        segments = [shorten(query, 30)]

    city = detect_city(query)
    region = city or "目标市场"
    primary = segments[0]
    rest = segments[1:3]

    expand_examples = [shorten(item, 60) for item in rest] or [
        f"{region}范围内与「{shorten(primary, 18)}」上下游相关的中小企业。",
        f"公开信息中已体现数字化投入，但未被第一组条件覆盖的{region}企业。",
    ]

    return [
        StrategyGroup(
            id="strategy-core",
            title="核心需求匹配",
            description=f"聚焦「{shorten(primary, 24)}」的潜在使用者，优先命中画像中明确写出的场景与需求。",
            examples=[shorten(item, 60) for item in segments[:3]],
        ),
        StrategyGroup(
            id="strategy-expand",
            title=f"{region}行业场景扩展",
            description=f"在{region}范围内补齐相邻业态与上下游企业，保留中小微规模与数字化诉求两条主线。",
            examples=expand_examples,
        ),
    ]
