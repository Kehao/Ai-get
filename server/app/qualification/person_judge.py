"""L3 人物判定器：对每条人物档案逐条判定标准，给出加权得分与可解释结论。

与 `judge.py`（会社模式）**并列**：两者的维度不重叠，判定依据也不同——
会社看企业所在地区与行业，人物看姓名与职位。共用一套判定器的后果是
要么人物档案被迫带着「行业」「规模」字段，要么企业判定被迫处理姓名。

计分口径（加权平均、硬性一票否决、`lenient` 不扣分）与会社模式**共用一份实现**，
见 `scoring.py`。这里只负责「人物维度各自怎么判」与结论文案。

## 几条判定口径

- **姓名**：整名对上才判「符合」；只对上姓或半个名（`陈` vs `陈可航`）判「不确定」。
  姓陈的人很多，把片段匹配当成同一人是更大的错。对不上则是硬性不符合——
  找的是陈可航，返回李伟没有意义。
- **职级**：按阶梯比较，**档案职级不低于要求**即判符合；
  只低一级判「不确定」而不是「不符合」，因为低一级的人通常仍在采购决策圈内
  （画像要 VP、实际对接的是总监，这在 B2B 里是常态）；低两级及以上才算不符合。
- **公司特征**：判的是「他所属的机构在做哪门生意」。档案里对雇主的描述通常只有一两句，
  不足以证伪「这家公司不做 AI」，所以**没有可读的机构信息时判不确定**，
  不去硬扣分。
- **履历背景 / 意向信号**：永远是宽松的，找不到对应表述只记不确定。
"""

from __future__ import annotations

from typing import Sequence
from urllib.parse import urlsplit

from ..matching import match_name
from ..providers import PersonRecord
from .criteria import INDUSTRY_FAMILIES, Criterion
from .person_criteria import SENIORITY_BANDS, SENIORITY_LADDER
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


def judge_person(criteria: Sequence[Criterion], record: PersonRecord) -> Judgment:
    """对单条人物档案执行完整判定。"""
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


def _judge_one(criterion: Criterion, record: PersonRecord) -> CriterionVerdict:
    handler = _HANDLERS.get(criterion.category, _judge_background)
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


def _judge_name(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    matched = match_name(record.all_names, criterion.tokens)
    if matched.is_full:
        return "符合", f"个人姓名与「{matched.hint}」完全匹配。", 2
    if matched.matched:
        return (
            "不确定",
            f"姓名片段「{matched.hint}」与档案上的「{record.name_local or record.name}」部分匹配，"
            "无法确认是否为同一人。",
            1,
        )
    display = record.name_local or record.name
    return "不符合", f"档案上的姓名为「{display}」，与「{criterion.expected}」不一致。", 1


def _judge_title(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    title = record.title.strip()
    if not title:
        return "不确定", "公开档案未给出职位，无法判断职能方向。", 0

    lowered = title.lower()
    hits = [token for token in criterion.tokens if token and token.lower() in lowered]
    if hits:
        return "符合", f"现任「{title}」，命中「{hits[0]}」这一职能方向。", 2

    soft = _soft_hits(criterion, record)
    if soft:
        return "不确定", f"公开履历提到「{soft[0]}」，但档案职位为「{title}」，方向需人工确认。", 1

    return "不符合", f"档案职位为「{title}」，与「{criterion.expected}」方向不符。", 1


def _judge_company(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    """判「他所属的机构在做哪门生意」。

    与会社模式判行业是同一套三层口径，只是证据从结构化行业分类换成了公开表述：
    命中即符合；**档案压根没说这家机构做什么**时判不确定（不能把「没写」当「不是」）；
    说了别的方向才判不符合。第三层是关键——个人档案里对雇主的描述常常只有一句，
    少了它会把大量信息不足的档案判成硬性不符合。
    """
    haystack = f"{record.company}{record.company_domain}{record.summary}{''.join(record.keywords)}"
    if not haystack.strip():
        return "不确定", "公开档案未给出所属机构信息，无法判断业务方向。", 0

    hits = [token for token in criterion.tokens if token and token in haystack]
    if hits:
        return "符合", f"所属机构为「{record.company}」，公开资料提到「{hits[0]}」，与该业务方向一致。", 2

    if not _mentions_any_industry(haystack):
        return (
            "不确定",
            f"档案未描述「{record.company}」的业务方向，无法确认是否属于「{criterion.expected}」。",
            1,
        )

    return (
        "不符合",
        f"所属机构为「{record.company}」，公开资料描述的业务方向与「{criterion.expected}」不一致。",
        1,
    )


def _mentions_any_industry(haystack: str) -> bool:
    """档案里是否出现过**任何**行业词。

    用于区分「说了别的方向」与「什么都没说」：前者是不符合，后者只能是不确定。
    """
    return any(token in haystack for _family, tokens in INDUSTRY_FAMILIES for token in tokens)


def _judge_seniority(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    title = record.title.strip()
    level = _level_of(title)
    if level is None:
        return "不确定", f"档案职位「{title or '未给出'}」无法对应到职级阶梯，需人工确认。", 0

    target = criterion.expected
    gap = _rank(level) - _rank(target)

    if gap <= 0:
        return "符合", f"现任「{title}」，职级为{level}，达到「{target}」的要求。", 2
    if gap == 1:
        return (
            "不确定",
            f"现任「{title}」（{level}），比要求低一级，通常仍参与采购决策，建议人工确认。",
            1,
        )
    return "不符合", f"现任「{title}」（{level}），与要求的「{target}」相差 {gap} 级。", 1


def _judge_geo(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    location = record.location.strip()
    if not location:
        return "不确定", "公开档案未给出所在地。", 0
    if criterion.tokens:
        if any(token in location for token in criterion.tokens):
            return "符合", f"常驻{location}，落在「{criterion.expected}」覆盖范围内。", 2
        return "不符合", f"常驻{location}，不在「{criterion.expected}」覆盖范围内。", 1
    return "不确定", f"常驻{location}，无法判断是否属于「{criterion.expected}」。", 1


def _judge_background(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    """履历背景与意向信号。未命中时**只记不确定**，理由是公开履历没写不等于不成立。"""
    haystack = _person_haystack(record)
    hits = [token for token in criterion.tokens if token and token in haystack]
    if hits:
        return "符合", f"公开履历中出现「{hits[0]}」的相关表述，与该条件一致。", 2
    return "不确定", "公开履历中未出现与该条件对应的内容，暂无法确认。", 1


def _judge_reachability(criterion: Criterion, record: PersonRecord) -> tuple[Verdict, str, int]:
    if record.contact_email or record.contact_phone:
        channel = record.contact_email or record.contact_phone
        return "符合", f"已获取公开联系方式（{channel}）。", 1
    if record.source_url:
        return (
            "不确定",
            "仅取到职业档案地址，未取到公开邮箱或电话；可在表格中对「联系方式挖掘」重试该字段。",
            1,
        )
    return "不确定", "暂未取到任何可用的公开联系方式，可在表格中对「联系方式挖掘」重试该字段。", 1


_HANDLERS = {
    "name": _judge_name,
    "title": _judge_title,
    "company": _judge_company,
    "seniority": _judge_seniority,
    "geo": _judge_geo,
    "background": _judge_background,
    "signal": _judge_background,
    "reachability": _judge_reachability,
}


# ── 辅助 ──────────────────────────────────────────────────────────────────


def _person_haystack(record: PersonRecord) -> str:
    return f"{record.summary}{record.company}{''.join(record.keywords)}{'、'.join(record.aliases)}"


def _soft_hits(criterion: Criterion, record: PersonRecord) -> list[str]:
    """在履历正文里找职能方向的间接证据，用于把「方向不符」降级成「不确定」。"""
    haystack = _person_haystack(record)
    return [token for token in criterion.tokens if token and token in haystack]


def _level_of(title: str) -> str | None:
    """把职位名映射到职级阶梯。阶梯从高到低逐个试，命中即返回。"""
    if not title:
        return None
    lowered = title.lower()
    for level, keywords in SENIORITY_BANDS:
        if any(keyword in title or keyword in lowered for keyword in keywords):
            return level
    return None


def _rank(level: str) -> int:
    return SENIORITY_LADDER.index(level) if level in SENIORITY_LADDER else len(SENIORITY_LADDER)


def _source_of(criterion: Criterion, record: PersonRecord) -> tuple[str, str]:
    """为每条标准挑一条最相关的证据。

    可触达性指向所属机构的团队页（那是找到联系方式的地方），其余标准指向
    这条档案本身；两者都能回溯到具体网址，而不是一句「公开资料显示」。
    """
    evidence = record.evidence
    preferred = next((item for item in evidence if "/team" in item.url), None)
    if criterion.category == "reachability":
        chosen = preferred or (evidence[0] if evidence else None)
    else:
        chosen = (evidence[0] if evidence else None) or preferred

    if chosen is None:
        return "无可用来源", ""

    domain = urlsplit(chosen.url).netloc or urlsplit(record.source_url).netloc
    label = record.source_label or "公开档案"
    return (f"{label} · {domain}" if domain else label), chosen.url


def _compose_reason(verdicts: tuple[CriterionVerdict, ...], score: Score) -> str:
    """组织结论文案。

    会社模式那句是写死的「地域与行业等硬性条件均一致」，这里改成**从实际命中的硬性条件推导**：
    人物画像里可能只有一条职位标准（连姓名都没有），写死一句「姓名与职位均一致」就是假话。
    """
    total = len(verdicts)
    hits = [item for item in verdicts if item.verdict == "符合"]
    unsure = [item for item in verdicts if item.verdict == "不确定"]
    misses = [item for item in verdicts if item.verdict == "不符合"]

    if score.match_level == MATCH_FULL:
        hard_hits = [item for item in hits if item.criterion.is_hard]
        subject = "、".join(item.criterion.name.split("：")[0] for item in hard_hits[:2]) or "硬性条件"
        return f"{len(hits)}/{total} 条标准命中（加权得分 {score.value}），{subject}等硬性条件均一致，可进入触达序列。"

    if score.match_level == MATCH_PARTIAL:
        if score.hard_miss and misses:
            names = "、".join(item.criterion.name for item in misses[:2])
            return f"{len(hits)}/{total} 条标准命中，但「{names}」不符合，建议人工确认后再跟进。"
        return f"{len(hits)}/{total} 条标准命中（加权得分 {score.value}），仍有 {len(unsure)} 条需补充核实。"

    return f"仅 {len(hits)}/{total} 条标准命中（加权得分 {score.value}），公开信息不足以支撑判断，需要补充调研。"
