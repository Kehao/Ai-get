"""资格标准与判定：挖掘链路里唯一属于「我们自己的智能」的部分。

分成两级：

- `criteria.build_criteria()` —— **L0**：把自然语言画像解析成一组带权重的判断标准。
  **LLM 优先、规则兜底**：`build_criteria_detailed()` 会先试 LLM，失败或校验不通过时
  静默回退到内置规则引擎，并通过返回的 `CriteriaBuild` 说明这批标准是谁产出的；
- `judge.judge()` / `person_judge.judge_person()` —— **L3**：对每个候选逐条判定标准，
  给出加权得分与可解释结论。两种模式共用同一套计分口径（`scoring.py`）。

判定这一级完全不依赖外部服务，是确定性的：同一份标准在同一个候选上永远得到同一个结论。
接入真实数据源只是把中间「谁提供候选」这一步换掉，这两级逻辑完全不用动。

**两套维度不共用一份词表**：会社模式看地域/行业/规模/融资（`criteria.py`），
人物模式看姓名/职位/职级/公司特征（`person_criteria.py`）。合并成一份的后果是
「找公司」的画像会产出姓名标准，或反过来——两者的召回对象不同，标准就不该同源。
"""

from __future__ import annotations

from ..models import CriteriaSource
from .criteria import (
    CATEGORY_WEIGHTS,
    FULL_SCORE_THRESHOLD,
    HARD_WEIGHT_THRESHOLD,
    INDUSTRY_FAMILIES,
    PARTIAL_SCORE_THRESHOLD,
    SOURCE_LABELS,
    CriteriaBuild,
    CompanyHints,
    Criterion,
    CriterionCategory,
    build_criteria,
    build_criteria_detailed,
    company_hints,
    detect_city,
    detect_region,
    employee_range,
    industry_hints,
)
from .judge import judge
from .person_criteria import (
    PERSON_CATEGORY_WEIGHTS,
    PersonCriterionCategory,
    build_person_criteria,
    build_person_criteria_detailed,
    person_hints,
)
from .person_judge import judge_person
from .scoring import (
    MATCH_FULL,
    MATCH_PARTIAL,
    MATCH_UNCONFIRMED,
    CriterionVerdict,
    Judgment,
    Verdict,
)

__all__ = [
    "CATEGORY_WEIGHTS",
    "FULL_SCORE_THRESHOLD",
    "HARD_WEIGHT_THRESHOLD",
    "INDUSTRY_FAMILIES",
    "MATCH_FULL",
    "MATCH_PARTIAL",
    "MATCH_UNCONFIRMED",
    "PARTIAL_SCORE_THRESHOLD",
    "PERSON_CATEGORY_WEIGHTS",
    "SOURCE_LABELS",
    "CompanyHints",
    "CriteriaBuild",
    "CriteriaSource",
    "Criterion",
    "CriterionCategory",
    "CriterionVerdict",
    "Judgment",
    "PersonCriterionCategory",
    "Verdict",
    "build_criteria",
    "build_criteria_detailed",
    "build_person_criteria",
    "build_person_criteria_detailed",
    "company_hints",
    "detect_city",
    "detect_region",
    "employee_range",
    "industry_hints",
    "judge",
    "judge_person",
    "person_hints",
]
