"""语料用尽后的人物档案合成。

与 `synth.py`（企业条目合成）并列，但**不共用实现**：人物的「补齐维度」是职位与职级，
企业的补齐维度是行业与规模，两边的组合方式没有共同部分，硬合并只会得到一堆分支。

组合规则与 `synth.py` 保持一致：同一个 index 必须得到同一条档案（演示可复现），
不同 index 通过互不相同的取模周期错开姓名、职位、公司与城市。
"""

from __future__ import annotations

from .people_corpus import PERSON_SEEDS, PersonSeed
from .synth import BRANDS, CITIES

# 姓与名分开存中英文：英文写法的姓在前、名在后（Wei Zhang），
# 而中文写法是姓在前、名在后（张伟）——两者都从同一份表推导，不靠运行时猜拼音。
SURNAMES: tuple[tuple[str, str], ...] = (
    ("张", "Zhang"),
    ("李", "Li"),
    ("王", "Wang"),
    ("刘", "Liu"),
    ("陈", "Chen"),
    ("杨", "Yang"),
    ("黄", "Huang"),
    ("周", "Zhou"),
    ("吴", "Wu"),
    ("徐", "Xu"),
    ("孙", "Sun"),
    ("马", "Ma"),
    ("朱", "Zhu"),
    ("胡", "Hu"),
    ("郭", "Guo"),
    ("何", "He"),
)

GIVEN_NAMES: tuple[tuple[str, str], ...] = (
    ("维", "Wei"),
    ("子墨", "Zimo"),
    ("思远", "Siyuan"),
    ("嘉禾", "Jiahe"),
    ("若彤", "Ruotong"),
    ("依冉", "Yiran"),
    ("书宁", "Shuning"),
    ("亦辰", "Yichen"),
    ("彦霖", "Yanlin"),
    ("明哲", "Mingzhe"),
    ("知微", "Zhiwei"),
    ("乐然", "Leran"),
    ("启帆", "Qifan"),
    ("安琪", "Anqi"),
    ("牧野", "Muye"),
    ("清和", "Qinghe"),
)

# 职位包：中文职称、英文职称、该职位自带的履历关键词。
ROLE_PACKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("销售副总裁", "VP of Sales", ("销售管理", "渠道体系", "大客户")),
    ("首席营收官", "Chief Revenue Officer", ("营收管理", "客户成功", "续约")),
    ("商务拓展负责人", "Head of Business Development", ("商务拓展", "渠道合作")),
    ("市场总监", "Marketing Director", ("市场营销", "品牌", "行业活动")),
    ("增长负责人", "Growth Lead", ("增长", "获客", "转化率")),
    ("产品总监", "Head of Product", ("产品管理", "用户研究")),
    ("技术总监", "Engineering Director", ("技术管理", "架构", "性能优化")),
    ("客户成功负责人", "Head of Customer Success", ("客户成功", "续费", "上手周期")),
)

# 合成档案的来源轮换。**只放来源标签，不放域名**：档案地址由数据源层按「来源 + 句柄」
# 拼装（见 `providers/mock_source._source_url`），模板留在那里一份，这里再存一遍就是第二个真源。
SOURCE_ROTATION: tuple[str, ...] = (
    "领英",
    "公司团队页",
    "会议嘉宾页",
    "行业论坛",
)

_LOCATIONS: tuple[str, ...] = CITIES


class _PersonIndex:
    """把「第 N 个人物」映射到语料或合成档案，两种来源共享同一取用顺序。"""

    def __init__(self) -> None:
        self._corpus_size = len(PERSON_SEEDS)

    @property
    def corpus_size(self) -> int:
        return self._corpus_size

    def at(
        self,
        index: int,
        preferred_city: str | None = None,
        role_hints: tuple[str, ...] = (),
    ) -> PersonSeed:
        """取第 index 条档案；超出语料范围时合成。"""
        if index < self._corpus_size:
            return PERSON_SEEDS[index]
        return self.synthesize(index - self._corpus_size, preferred_city, role_hints)

    def synthesize(
        self,
        index: int,
        preferred_city: str | None = None,
        role_hints: tuple[str, ...] = (),
    ) -> PersonSeed:
        """按 index 合成一条档案。

        姓名用**两个独立周期**错开：姓每步换、名也每步换，靠 `index // len(GIVEN_NAMES)`
        施加的位移把两者的配对周期拉到 256 条以上。
        曾经姓与名各自周期都是 16、且都直接取 `index % 16`，于是配对周期只有 16，
        一屏 25 个人里会出现「Wei Zhang / Wei Li / Wei Wang」一整列同名不同姓的档案，
        看着像数据生成器坏了。职位包同理加了位移，避免连续 8 条同一个头衔。
        """
        city = preferred_city or _LOCATIONS[index % len(_LOCATIONS)]
        given_cn, given_py = GIVEN_NAMES[index % len(GIVEN_NAMES)]
        surname_cn, surname_py = SURNAMES[(index + index // len(GIVEN_NAMES)) % len(SURNAMES)]
        packs = roles_matching(role_hints) or ROLE_PACKS
        title_cn, title_en, keywords = packs[(index + index // len(packs)) % len(packs)]
        brand_cn, brand_py = BRANDS[(index + index // len(BRANDS)) % len(BRANDS)]
        company = f"{city}{brand_cn}科技"
        domain = f"{brand_py}{index % 9000 + 1000}.com"
        source_label = SOURCE_ROTATION[index % len(SOURCE_ROTATION)]
        name_local = f"{surname_cn}{given_cn}"
        name = f"{given_py} {surname_py}"
        handle = f"{given_py.lower()}-{surname_py.lower()}{index % 90 + 10}"
        summary = (
            f"{name_local}是{company}的{title_cn}，负责{'、'.join(keywords)}相关工作，"
            f"常驻{city}。公开档案显示其此前有同类岗位经历，"
            "并参与过面向企业客户的长期项目交付。"
        )
        return PersonSeed(
            name=name,
            company=company,
            company_domain=domain,
            title=title_cn,
            name_local=name_local,
            location=city,
            summary=summary,
            source_label=source_label,
            source_handle=handle,
            aliases=(f"{surname_py} {given_py}", name_local),
            keywords=(title_en, *keywords),
            contact_email=f"{given_py.lower()}.{surname_py.lower()}@{domain}",
        )


def roles_matching(role_hints: tuple[str, ...]) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """挑出职位提示命中的职位包。词表同时覆盖中文职称、英文职称与履历关键词。"""
    if not role_hints:
        return ()
    return tuple(
        pack for pack in ROLE_PACKS if any(token in f"{pack[0]}{pack[1]}{''.join(pack[2])}" for token in role_hints)
    )


PERSON_INDEX = _PersonIndex()
