"""L3 判定的计分部分：与「判哪些维度」无关的那一半。

公司与人物两套判定的维度**完全不同**（企业看行业与规模，人物看姓名与职级），
但下面这套口径对两者是同一件事，因此只有一份实现：

- 每条标准的得分系数：符合 `1.0` / 不确定 `0.5` / 不符合 `0.0`；
- 总分为**按权重加权的平均值**，而不是简单计数——权重 5 的姓名没对上，
  不该和一个权重 1 的可触达性没拿到同样处理；
- **硬性标准一票否决**：任何一条硬性标准判为「不符合」，结论就不能落到「明确符合」。
  否则一个姓名、职位全不对的档案，只要地域与可触达性命中，也能凑够分被判成明确符合；
- `lenient` 的标准（履历背景、意向信号、用户手写条件）**永远不判「不符合」**，
  由各自的判定器保证，这里只负责在算分时如实反映 `verdict`。

把这套口径抽出来的直接原因是「改一处漏一处」的风险：阈值调了、或者硬性分界线调了，
公司与人物两边必须同时生效，否则同一个 `match_level` 在两种模式下含义不同，
前端按它排序就会出现两种解释。

**结论的文案不在这里**——「为什么符合」要说的是姓名、职位还是行业，是各自领域的事，
由 `judge.py` 与 `person_judge.py` 分别组织。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .criteria import (
    FULL_SCORE_THRESHOLD,
    PARTIAL_SCORE_THRESHOLD,
    Criterion,
)

# 判定结果沿用接口层已有的三种取值，详情页的「准入条件评估」直接消费它。
Verdict = Literal["符合", "不确定", "不符合"]

MATCH_FULL = "明确符合"
MATCH_PARTIAL = "可能符合"
MATCH_UNCONFIRMED = "待确认"

VERDICT_FACTOR: dict[Verdict, float] = {"符合": 1.0, "不确定": 0.5, "不符合": 0.0}

# 没有可用标准时的结论文案。两种模式共用：这时说的不是「没匹配上」，
# 而是「根本没有可比的标准」，与「信息不足」是两回事。
NO_CRITERIA_REASON = "本轮没有可用的判断标准，无法给出匹配结论。"


@dataclass(frozen=True, slots=True)
class CriterionVerdict:
    """一条标准在某条记录上的判定结果，是详情页准入条件评估的一行。

    `references` 是这条结论**可回溯的公开来源**（标题, 网址）列表，按相关度排序；
    `source_label` / `source_url` 永远等于第一条的展示形式，供表格等只读单链接的
    场景复用。参考站每条评估卡下方挂着多条来源 chip，这里就是它们的数据来源。
    """

    criterion: Criterion
    verdict: Verdict
    explanation: str
    reference_count: int
    source_label: str
    source_url: str
    references: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        # references 为空时退回单来源形式，保证旧调用点（不传 references）行为不变。
        if not self.references and self.source_url:
            object.__setattr__(self, "references", ((self.source_label, self.source_url),))

    @property
    def factor(self) -> float:
        return VERDICT_FACTOR[self.verdict]


@dataclass(frozen=True, slots=True)
class Judgment:
    """一条记录的完整判定结果。企业与人物共用同一个形状。"""

    verdicts: tuple[CriterionVerdict, ...]
    score: int
    ratio: float
    match_level: str
    reason: str

    @property
    def is_full(self) -> bool:
        return self.match_level == MATCH_FULL

    @property
    def is_qualified(self) -> bool:
        """是否通过资格验证。对应上游 `match.status` 有值（full 或 partial）。"""
        return self.match_level in (MATCH_FULL, MATCH_PARTIAL)


@dataclass(frozen=True, slots=True)
class Score:
    """加权计分的结果。`hard_miss` 一并返回，供结论文案区分「分够了但硬伤在」。"""

    ratio: float
    value: int
    match_level: str
    hard_miss: bool


def score_verdicts(verdicts: Sequence[CriterionVerdict]) -> Score:
    """按权重汇总逐条判定。空列表得到 0 分与「待确认」，不假装通过。"""
    total_weight = sum(item.criterion.weight for item in verdicts)
    earned = sum(item.criterion.weight * item.factor for item in verdicts)
    ratio = earned / total_weight if total_weight else 0.0
    hard_miss = any(item.verdict == "不符合" and item.criterion.is_hard for item in verdicts)

    if ratio >= FULL_SCORE_THRESHOLD and not hard_miss:
        match_level = MATCH_FULL
    elif ratio >= PARTIAL_SCORE_THRESHOLD:
        match_level = MATCH_PARTIAL
    else:
        match_level = MATCH_UNCONFIRMED

    return Score(ratio=ratio, value=int(round(ratio * 100)), match_level=match_level, hard_miss=hard_miss)


def empty_judgment() -> Judgment:
    """没有可用标准时的结论。"""
    return Judgment(
        verdicts=(),
        score=0,
        ratio=0.0,
        match_level=MATCH_UNCONFIRMED,
        reason=NO_CRITERIA_REASON,
    )
