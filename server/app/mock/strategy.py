"""挖掘策略说明的文本生成。

条件条目本身已经改由 L0 资格标准引擎产出（见 `qualification.criteria`），
这里只保留「挖掘策略」区块的说明文案——它解释的是**这批结果按什么思路被圈出来**，
属于展示层内容，与判定逻辑无关。

会社与找人两种模式的策略结构不同（2 组 vs 6 组，分组依据也不同），所以实现分开：
本模块只做会社模式 + 按模式分发，找人那套在 `people_strategy.py`。
"""

from __future__ import annotations

from ..models import SearchMode, StrategyGroup
from ..qualification.criteria import detect_city
from .people_strategy import build_people_strategy_groups

# 与参考站一致的四色循环：violet / orange / sky / emerald。
# 条件条目的色条由后端统一下发，避免前后端各写一份色表后逐渐漂移。
CONDITION_COLORS: tuple[str, ...] = ("#8b5cf6", "#fb923c", "#0ea5e9", "#10b981")

_SEPARATORS: tuple[str, ...] = ("，", ",", "；", ";", "。", "、", "\n")


def split_query(text: str) -> list[str]:
    """按中文/英文标点切句，返回保留顺序的片段列表。"""
    normalized = text
    for separator in _SEPARATORS:
        normalized = normalized.replace(separator, "|")
    return normalized.split("|")


def shorten(text: str, limit: int = 22) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= limit else f"{stripped[:limit]}…"


def build_strategy_groups(query: str, mode: SearchMode = "company") -> list[StrategyGroup]:
    """按检索模式分发：找人 6 组（`people_strategy`），会社 2 组（本模块）。"""
    if mode == "people":
        return build_people_strategy_groups(query)
    return _build_company_strategy_groups(query)


def _build_company_strategy_groups(query: str) -> list[StrategyGroup]:
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
