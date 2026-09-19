"""企业详情页（详细档案 / 智能调研 / 准入条件评估）的虚拟内容生成。

全部内容按企业 ID 确定性生成，刷新页面后保持一致；不含任何真实第三方数据源。
"""

from __future__ import annotations

import zlib

from ..models import (
    ConditionEvaluation,
    ConditionStatus,
    ReferenceItem,
    ResearchResult,
    TargetCompany,
    TargetCondition,
)

_EVALUATION_STATUS: tuple[ConditionStatus, ...] = ("符合", "不确定", "不符合")

_EXPLANATION_TEMPLATES: dict[ConditionStatus, str] = {
    "符合": "公开资料显示其为{location}的{industry}企业，规模 {employees}，与该条件一致。",
    "不确定": "仅能确认其{industry}经营范围，公开信息未出现与该条件对应的动作，暂无法确认。",
    "不符合": "其业务集中在{industries}方向，公开信息中未见与该条件相关的内容。",
}


def _seed_of(company: TargetCompany) -> int:
    return zlib.crc32(company.id.encode()) % 100_000


def build_references(company: TargetCompany) -> list[ReferenceItem]:
    """详情页 References 区块。只引用企业自身的公开页面，不引用第三方站点。"""
    domain = company.website
    references = [
        ReferenceItem(title=f"{company.company_name}（官网首页）", url=f"https://{domain}"),
    ]
    if company.summary_state == "ready":
        references.append(ReferenceItem(title=f"{company.company_name} · 业务介绍", url=f"https://{domain}/about"))
    return references


def build_research_results(company: TargetCompany) -> list[ResearchResult]:
    domain = company.website
    contacts_ready = company.contact_state == "ready" and company.contact_count > 0
    official_ready = company.official_contact_state == "ready"

    return [
        ResearchResult(
            key="contacts",
            title="企业关键联系人挖掘",
            state=company.contact_state,
            summary="未找到结果" if not contacts_ready else f"已挖掘到 {company.contact_count} 位",
            evidence=(
                [f"{domain} 的团队介绍页面列出了决策岗位人选", "结合公开报道交叉验证了姓名与职位"]
                if contacts_ready
                else ["站内未发现团队或管理层页面", "公开报道中未出现可验证的负责人姓名"]
            ),
        ),
        ResearchResult(
            key="official_contact",
            title="官网联系方式挖掘",
            state=company.official_contact_state,
            summary="已获取邮箱" if official_ready else "未找到结果",
            evidence=(
                [f"{domain} 页脚公开了客服邮箱与联系电话"]
                if official_ready
                else ["官网对爬虫返回访问受限页面", "暂未取到可用的邮箱或电话"]
            ),
        ),
    ]


def build_evaluations(
    company: TargetCompany,
    conditions: list[TargetCondition],
) -> list[ConditionEvaluation]:
    """逐条条件给出判定、参考数量、解释与来源。"""
    seed = _seed_of(company)
    industry = company.industries[0] if company.industries else "综合"

    evaluations: list[ConditionEvaluation] = []
    for index, condition in enumerate(conditions):
        status = _EVALUATION_STATUS[(seed + index) % len(_EVALUATION_STATUS)]
        if index == 0:
            # 第一条条件通常就是行业画像，企业能出现在结果里说明它至少没跑偏
            status = "符合"
        explanation = _EXPLANATION_TEMPLATES[status].format(
            location=company.location,
            industry=industry,
            employees=company.employees,
            industries="、".join(company.industries),
        )
        reference_count = 2 if status == "符合" else 1
        evaluations.append(
            ConditionEvaluation(
                condition=condition.text,
                status=status,
                reference_count=reference_count,
                explanation=explanation,
                source_label=f"官网 · {company.website}",
                source_url=f"https://{company.website}",
            )
        )
    return evaluations


def build_outreach_note(company: TargetCompany, has_plan: bool) -> str:
    """智能触达区块的说明文案。没有触达计划时与参考站一致，给出占位提示。"""
    if not has_plan:
        return "当前未加载触达详情。"
    if company.contact_state != "ready" or company.contact_count == 0:
        return "该企业尚未挖掘到关键联系人，触达序列会停在第一封邮件。"
    return f"已纳入触达序列，首轮将面向 {company.contact_count} 位联系人按渠道顺序推进。"
