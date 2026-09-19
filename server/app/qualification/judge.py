"""L3 资格判定器（会社模式）：对每个候选企业逐条判定标准，给出加权得分与可解释结论。

判定是**确定性的**——给定同一份标准与同一条记录，结论永远一致。这是「为什么这家匹配」
能被前端逐条展示、被用户复核的前提，也是它与「让 LLM 自由发挥」的根本区别。

计分口径（加权平均、硬性一票否决、`lenient` 不扣分）与人物模式**共用一份实现**，
见 `scoring.py`；本模块只负责「会社的七个维度各自怎么判」以及结论文案。

## 结论口径

| 结论 | 成立条件 | 上游对应 |
| --- | --- | --- |
| 明确符合 | 加权得分 ≥ 0.75，且**没有任何硬性标准判为「不符合」** | `match.status = full` |
| 可能符合 | 加权得分 ≥ 0.45 | `match.status = partial` |
| 待确认 | 其余 | 未通过资格验证 |

「硬性标准一票否决」这条约束很关键：否则一家行业完全不对的企业，只要地域、规模、
可触达性都命中，就能凑到 0.78 的加权分被判成「明确符合」。
"""

from __future__ import annotations

from typing import Sequence

from ..providers import CompanyRecord
from .criteria import Criterion, employee_range
from .scoring import (
    MATCH_FULL,
    MATCH_PARTIAL,
    CriterionVerdict,
    Judgment,
    Score,
    Verdict,
    empty_judgment,
    score_verdicts,
)

_PAGE_LABELS: dict[str, str] = {
    "": "官网首页",
    "/about": "关于我们",
    "/contact": "联系我们",
}


def judge(criteria: Sequence[Criterion], record: CompanyRecord) -> Judgment:
    """对单条记录执行完整判定。标准为空时返回「待确认」，而不是假装通过。"""
    if not criteria:
        return empty_judgment()

    verdicts = tuple(_judge_one(criterion, record) for criterion in criteria)
    score = score_verdicts(verdicts)

    return Judgment(
        verdicts=verdicts,
        score=score.value,
        ratio=score.ratio,
        match_level=score.match_level,
        reason=_compose_reason(verdicts, score),
    )


# ── 逐条判定 ──────────────────────────────────────────────────────────────


def _judge_one(criterion: Criterion, record: CompanyRecord) -> CriterionVerdict:
    handler = _HANDLERS.get(criterion.category, _judge_business)
    verdict, explanation, reference_count = handler(criterion, record)
    source_label, source_url = _source_of(criterion, record)
    return CriterionVerdict(
        criterion=criterion,
        verdict=verdict,
        explanation=explanation,
        reference_count=reference_count,
        source_label=source_label,
        source_url=source_url,
    )


def _judge_geo(criterion: Criterion, record: CompanyRecord) -> tuple[Verdict, str, int]:
    location = (record.location or "").strip()
    if not location:
        return "不确定", "公开资料未给出企业所在地区。", 0
    if criterion.tokens:
        if any(token in location for token in criterion.tokens):
            return "符合", f"企业位于{location}，落在「{criterion.expected}」覆盖范围内。", 2
        return "不符合", f"企业位于{location}，不在「{criterion.expected}」覆盖范围内。", 1
    return "不确定", f"企业位于{location}，无法判断是否属于「{criterion.expected}」。", 1


def _judge_industry(criterion: Criterion, record: CompanyRecord) -> tuple[Verdict, str, int]:
    industries = "、".join(record.industries)
    if not industries:
        return "不确定", "公开资料未给出行业分类，无法判断业务归属。", 0

    hits = [token for token in criterion.tokens if token in industries]
    if hits:
        return "符合", f"主营{industries}，命中「{hits[0]}」这一{_family_label(criterion)}环节。", 2

    haystack = f"{record.summary}{record.name}"
    soft = [token for token in criterion.tokens if token in haystack]
    if soft:
        return "不确定", f"公开摘要提到「{soft[0]}」，但行业分类为{industries}，归属需人工确认。", 1

    return "不符合", f"行业分类为{industries}，与「{criterion.expected}」无明显关联。", 1


def _judge_size(criterion: Criterion, record: CompanyRecord) -> tuple[Verdict, str, int]:
    actual = employee_range(record.employees)
    if actual is None:
        return "不确定", f"公开资料未给出可解析的员工规模（当前为「{record.employees or '未知'}」）。", 0

    try:
        low_text, high_text = criterion.expected.split(":")
        target = (int(low_text), int(high_text))
    except ValueError:
        return "不确定", "规模标准缺少可比的区间，无法判定。", 0

    if _covers(actual, target):
        return "符合", f"员工规模 {record.employees}，落在目标区间内。", 2
    return "不符合", f"员工规模 {record.employees}，与目标区间不匹配。", 1


def _judge_funding(criterion: Criterion, record: CompanyRecord) -> tuple[Verdict, str, int]:
    stage = (record.funding_stage or "").strip()
    if not stage:
        return "不确定", "公开资料未给出融资阶段。", 0
    if _normalize_funding(stage) == _normalize_funding(criterion.expected):
        return "符合", f"当前融资阶段为{stage}，与标准一致。", 2
    return "不符合", f"当前融资阶段为{stage}，与「{criterion.expected}」不一致。", 1


def _judge_business(criterion: Criterion, record: CompanyRecord) -> tuple[Verdict, str, int]:
    """业务特征与意向信号的判定。

    命中即符合；未命中时，`lenient` 的标准只记「不确定」——公开资料没写到，
    不足以证明这条特征不成立。
    """
    haystack = f"{record.summary}{record.name}{'、'.join(record.industries)}"
    hits = [token for token in criterion.tokens if token and token in haystack]
    if hits:
        return "符合", f"公开资料中出现「{hits[0]}」的相关表述，与该特征一致。", 2

    if criterion.lenient:
        return "不确定", "公开资料中未出现与该条件对应的动作，暂无法确认。", 1
    return "不符合", "公开资料中未见与该条件相关的内容。", 1


def _judge_reachability(criterion: Criterion, record: CompanyRecord) -> tuple[Verdict, str, int]:
    if record.contact_count > 0:
        return "符合", f"已获取 {record.contact_count} 位可触达联系人。", 1
    return "不确定", "暂未取到可用的公开联系方式，可在表格中对「企业关键联系人挖掘」重试该字段。", 1


_HANDLERS = {
    "geo": _judge_geo,
    "industry": _judge_industry,
    "size": _judge_size,
    "funding": _judge_funding,
    "business": _judge_business,
    "signal": _judge_business,
    "reachability": _judge_reachability,
}


# ── 结论文案与来源 ────────────────────────────────────────────────────────


def _compose_reason(verdicts: tuple[CriterionVerdict, ...], score: Score) -> str:
    total = len(verdicts)
    hits = [item for item in verdicts if item.verdict == "符合"]
    unsure = [item for item in verdicts if item.verdict == "不确定"]
    misses = [item for item in verdicts if item.verdict == "不符合"]

    if score.match_level == MATCH_FULL:
        return (
            f"{len(hits)}/{total} 条标准命中（加权得分 {score.value}），"
            "地域与行业等硬性条件均一致，可直接进入触达序列。"
        )

    if score.match_level == MATCH_PARTIAL:
        if score.hard_miss and misses:
            names = "、".join(item.criterion.name for item in misses[:2])
            return f"{len(hits)}/{total} 条标准命中，但「{names}」不符合，建议人工确认后再跟进。"
        return f"{len(hits)}/{total} 条标准命中（加权得分 {score.value}），仍有 {len(unsure)} 条需补充核实。"

    return f"仅 {len(hits)}/{total} 条标准命中（加权得分 {score.value}），公开信息不足以支撑判断，需要补充调研。"


def _source_of(criterion: Criterion, record: CompanyRecord) -> tuple[str, str]:
    """为每条标准挑一条最相关的证据，让结论可回溯。

    选择依据是标准类别与页面类型的对应关系，而不是简单地取第一条——
    「可触达性」应该指向联系我们页，「行业」应该指向关于我们页。
    """
    preferred_suffix = "/contact" if criterion.category == "reachability" else "/about"
    evidence = next((item for item in record.evidence if item.url.endswith(preferred_suffix)), None)
    evidence = evidence or (record.evidence[0] if record.evidence else None)

    if evidence is None:
        return "无可用来源", ""

    suffix = ""
    for known in _PAGE_LABELS:
        if known and evidence.url.endswith(known):
            suffix = known
            break
    page = _PAGE_LABELS.get(suffix, "官网页面")
    return f"{page} · {record.domain}", evidence.url


def _covers(candidate: tuple[int, int], target: tuple[int, int], min_ratio: float = 0.5) -> bool:
    """判断企业规模是否落在目标区间内。

    不能用「区间有交集」直接判定：企业写「50-200 人」、标准写「50 人以下」时，
    两个区间在 50 这一个点上相交，会被误判成符合小微口径。
    这里要求**企业区间至少有 `min_ratio` 的比例落在目标区间内**，
    才能真正反映「这家企业够不够小」。
    """
    overlap = min(candidate[1], target[1]) - max(candidate[0], target[0])
    if overlap <= 0:
        return False
    span = candidate[1] - candidate[0]
    if span <= 0:
        return True
    return overlap / span >= min_ratio


def _family_label(criterion: Criterion) -> str:
    return (criterion.expected or "目标行业").split("／")[0]


def _normalize_funding(value: str) -> str:
    return value.replace(" ", "").lower()
