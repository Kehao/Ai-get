"""企业详情页的内容装配。

职责被收窄成「把已有数据翻译成接口模型」：

- **准入条件评估**来自 L3 判定结果（`qualification.judge` / `judge_person`），
  本模块只做格式转换。它不再自己随机生成结论——那是「为什么这家匹配」的答案，
  必须与列表页的结论同源。
- **References** 来自数据源返回的证据列表，因此接入真实数据源后会自动变成真实 URL。
- 智能调研与触达说明仍是演示内容，等对应的爬虫能力接上后再替换。

会社与人物两套装配函数**并列放在这里**而不是合并成一个：区块骨架相同，
但证据来源、调研项与触达文案的依据字段都不一样（公司看官网，
人物看职业档案），合并只会得到一堆 `if mode == ...`。
"""

from __future__ import annotations

from ..models import (
    ConditionEvaluation,
    ReferenceItem,
    ResearchResult,
    TargetCompany,
    TargetPerson,
)
from ..providers import CompanyRecord, PersonRecord
from ..qualification import Judgment


def build_references(company: TargetCompany, record: CompanyRecord | None) -> list[ReferenceItem]:
    """详情页 References 区块。

    优先用数据源给出的证据；没有证据时退回企业官网首页，
    而不是编造一条看起来像证据的链接。
    """
    if record is not None and record.evidence:
        return [ReferenceItem(title=item.title, url=item.url) for item in record.evidence]
    return [ReferenceItem(title=f"{company.company_name}（官网首页）", url=f"https://{company.website}")]


def build_evaluations(judgment: Judgment | None) -> list[ConditionEvaluation]:
    """把逐条判定结果转成准入条件评估。

    没有判定结果时返回空列表：**不生成占位结论**。详情页会因此少一个区块，
    这比展示一条与列表页结论矛盾的假评估要好。
    """
    if judgment is None:
        return []
    return [
        ConditionEvaluation(
            condition=item.criterion.name,
            status=item.verdict,
            reference_count=item.reference_count,
            explanation=item.explanation,
            source_label=item.source_label,
            source_url=item.source_url,
            weight=item.criterion.weight,
        )
        for item in judgment.verdicts
    ]


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


def build_outreach_note(company: TargetCompany, has_plan: bool) -> str:
    """智能触达区块的说明文案。没有触达计划时与参考站一致，给出占位提示。"""
    if not has_plan:
        return "当前未加载触达详情。"
    if company.contact_state != "ready" or company.contact_count == 0:
        return "该企业尚未挖掘到关键联系人，触达序列会停在第一封邮件。"
    return f"已纳入触达序列，首轮将面向 {company.contact_count} 位联系人按渠道顺序推进。"


# ── 人物档案 ──────────────────────────────────────────────────────────────


def build_person_references(person: TargetPerson, record: PersonRecord | None) -> list[ReferenceItem]:
    """人物详情页 References 区块。

    优先用数据源给出的证据（职业档案页 + 所属机构团队页）；没有证据时退回档案地址本身，
    而不是编造一条看起来像证据的链接。
    """
    if record is not None and record.evidence:
        return [ReferenceItem(title=item.title, url=item.url) for item in record.evidence]
    if person.source_url:
        return [ReferenceItem(title=f"{person.name} · {person.source_label or '公开档案'}", url=person.source_url)]
    return []


def build_person_research_results(person: TargetPerson) -> list[ResearchResult]:
    """人物侧的智能调研。

    只有两项，且与会社侧**不是同一套**：人物没有「企业关键联系人」这一层下钻
    （他本人就是结果实体），换成「联系方式」与「档案完整度」。
    """
    reachable = person.contact_state == "ready" and person.contact_count > 0
    complete = person.summary_state == "ready" and bool(person.title)

    return [
        ResearchResult(
            key="person_contact",
            title="联系方式挖掘",
            state="ready" if reachable else "failed",
            summary="已获取邮箱或电话" if reachable else "未找到结果",
            evidence=(
                [f"{person.source_label or '公开档案'}上可获知其现任职位与所属机构", "交叉核对了团队页的在职状态"]
                if reachable
                else ["档案页对爬虫返回访问受限", "公开渠道未出现可验证的邮箱或电话"]
            ),
        ),
        ResearchResult(
            key="profile_completeness",
            title="档案完整度",
            state="ready" if complete else "blocked",
            summary="职位与归属齐备" if complete else "缺少职位或所属机构",
            evidence=(
                [f"档案给出了现任职位「{person.title}」", f"所属机构为{person.company or '未给出'}"]
                if complete
                else ["档案未给出职位", "无法确认其是否仍在职"]
            ),
        ),
    ]


def build_person_outreach_note(person: TargetPerson, has_plan: bool) -> str:
    """人物侧的触达说明。口径与会社侧一致：没有计划就直说，有联系人就说清首轮面向谁。"""
    if not has_plan:
        return "当前未加载触达详情。"
    if person.contact_state != "ready" or person.contact_count == 0:
        return "该档案尚未取到可用的联系方式，触达序列会停在第一封邮件。"
    return f"已纳入触达序列，首轮将面向 {person.name_local or person.name} 按渠道顺序推进。"
