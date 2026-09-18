"""企业背调报告的虚拟生成。

报告用 Markdown 组织，前端直接按标题层级渲染，因此这里的结构必须保持稳定。
"""

from __future__ import annotations

from .company_corpus import COMPANY_SEEDS

_CREDIT_CODE_PREFIX = "91330106MA"
_TOOL_NAMES: tuple[str, ...] = (
    "企业工商信息检索",
    "官网与产品页抓取",
    "公开新闻与公告检索",
    "股权与关键人员穿透",
)


def tool_names_for(query: str) -> list[str]:
    """按查询词确定展示用的工具调用清单。"""
    return list(_TOOL_NAMES)


def build_report(query: str, seed: int) -> str:
    """生成一份结构完整的背调报告。命中语料时使用企业真实字段，否则生成通用结论。"""
    matched = _match_seed(query)
    if matched is None:
        return _generic_report(query, seed)

    seed_index, company = matched
    credit_code = f"{_CREDIT_CODE_PREFIX}{seed_index:02d}{(seed_index * 7919) % 100000:05d}"
    return "\n".join(
        [
            f"# {company.name}公开背景概览",
            "",
            "## 核心结论",
            "",
            f"{company.name}是一家以 **{company.industries[0]}、{company.industries[1]}** 为核心的"
            f"{company.location}企业，员工规模约 {company.employees}，当前融资阶段为 **{company.funding_stage}**。"
            "公开资料能够支撑对其主营业务与组织形态的基本判断，但最新经营规模与主要客户结构仍需在正式沟通中确认。",
            "",
            "## 公司基本信息",
            "",
            f"- **公司名称：** {company.name}",
            f"- **统一社会信用代码：** {credit_code}",
            f"- **注册地：** {company.location}",
            f"- **所属行业：** {'、'.join(company.industries)}",
            f"- **官网：** {company.domain}",
            f"- **员工规模：** {company.employees}",
            f"- **融资阶段：** {company.funding_stage}",
            "- **经营状态：** 存续",
            "",
            "## 业务与产品结构",
            "",
            company.summary,
            "",
            "结合官网与公开报道，其收入结构以主营业务为主导，产品线相对集中；"
            "近年动作显示其正在通过渠道扩张或产品形态调整来寻找新的增长点。",
            "",
            "## 组织与关键角色",
            "",
            "| 角色 | 关注点 | 建议切入方式 |",
            "| --- | --- | --- |",
            "| 创始人 / 总经理 | 增长效率与投入产出 | 用同行案例说明可量化的产出提升 |",
            "| 采购 / 供应链负责人 | 交付稳定性与成本 | 提供试点范围与小批量验证方案 |",
            "| 市场 / 品牌负责人 | 线索质量与转化 | 用线索到成交的漏斗数据切入 |",
            "",
            "## 采购习惯推断",
            "",
            "- 决策链路偏短，通常由业务负责人发起评估，创始人参与最终判断。",
            "- 对可量化效果的工具接受度较高，倾向先小范围试点再扩大采购范围。",
            "- 对长期合同的接受度取决于交付确定性与同行业参考客户。",
            "",
            "## 风险与不确定项",
            "",
            "- 公开信息更新时间存在滞后，最新人员规模与营收口径无法核实。",
            "- 官网部分内容长期未更新，需通过直接沟通确认业务现状。",
            "- 未发现重大负面舆情，但供应商与客户集中度信息不足。",
            "",
            "## 建议下一步",
            "",
            f"1. 以「{company.industries[0]}行业的增长与获客效率」为话题发起首轮触达，避免直接推销。",
            "2. 在首轮对话中确认其当前的组织规模与预算归属，用于修正本报告的推断。",
            "3. 若对方表示正在评估相关方案，再进入需求澄清并安排 30 分钟会议。",
        ]
    )


def _match_seed(query: str) -> tuple[int, object] | None:
    """在语料中按公司名关键词定位，命中返回 (序号, CompanySeed)。"""
    for index, seed in enumerate(COMPANY_SEEDS):
        short_name = seed.name.replace("有限公司", "").replace("股份", "")
        if short_name and short_name in query:
            return index, seed
        brand = short_name[-4:] if len(short_name) > 4 else short_name
        if brand and brand in query:
            return index, seed
    return None


def _generic_report(query: str, seed: int) -> str:
    subject = query.strip().rstrip("。？！? !")[:40] or "目标企业"
    return "\n".join(
        [
            f"# {subject}背景调研",
            "",
            "## 核心结论",
            "",
            f"针对「{subject}」的公开信息梳理显示，该主体在公开渠道可检索到的信息量有限，"
            "尚不足以对其经营规模、客户结构与最新经营状态做出确定判断。"
            "以下结论基于可获取的公开资料，需要在后续触达中逐项核实。",
            "",
            "## 已获取信息",
            "",
            "- 主体名称与基本工商登记信息可查，经营状态正常。",
            "- 官网或公开页面存在，但内容更新频率较低。",
            "- 未检索到明确的融资、并购或重大负面信息。",
            "",
            "## 信息缺口",
            "",
            "- 最新员工规模与组织架构无法确认。",
            "- 主要客户与供应商结构未公开。",
            "- 采购决策链条与预算归属缺少公开线索。",
            "",
            "## 建议下一步",
            "",
            "1. 先用一次轻量触达确认对接人角色，再决定是否继续深挖。",
            "2. 补充官网、招聘信息与行业媒体三个方向的信息源，交叉验证主体画像。",
            "3. 若确认存在相关需求，将其加入潜客列表并附带智能调研字段。",
        ]
    )
