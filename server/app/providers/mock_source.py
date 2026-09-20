"""内置演示语料数据源。

作用是把 `mock/` 下已有的语料生成器**包成符合契约的数据源**——语料本身一行没改，
只是补上统一的能力声明与记录转换。这样演示模式与将来的真实模式会走完全相同的
业务链路，切换数据源不需要动业务代码。

本数据源声明了三种能力，用来演示「一个数据源可以具备多种能力、而查找按能力进行」：
- `company_search`：按画像召回公司；
- `person_search`：按画像召回**人物职业档案**（找人模式的召回入口）；
- `contact_search`：按**已验证域名**查找联系人。

`person_search` 与 `contact_search` 虽然都产出「人」，但回答的不是同一个问题，所以是两种能力：
前者按画像直接找人（人物本身就是结果），后者是拿到公司之后的下钻（人是公司的附属信息）。
把它们合成一种能力的后果是找人模式只能返回公司结构，或者公司模式被迫带上人物字段。

它如实上报字段缺失（`missing_fields`），不假装所有字段都拿到了——这正是多源瀑布
补齐的驱动信号，也让前端「重试该字段」这类入口有真实依据。
"""

from __future__ import annotations

from typing import TypeVar

from ..matching import NameMatch, match_name
from ..mock.company_corpus import CompanySeed
from ..mock.people import build_contacts
from ..mock.people_corpus import SOURCE_DESCRIPTIONS, PersonSeed
from ..mock.people_synth import PERSON_INDEX
from ..mock.synth import COMPANY_INDEX
from .contracts import (
    CompanyQuery,
    CompanyRecord,
    ContactQuery,
    ContactRecord,
    EnrichableField,
    Evidence,
    PersonQuery,
    PersonRecord,
    SourceError,
    SourceManifest,
)
from .registry import register_source

# 演示语料的字段可用性分布。刻意保留一定比例的失败，使「字段重试」链路始终有样本可测。
_SUMMARY_MISSING_EVERY = 9
_SUMMARY_MISSING_OFFSET = 3
_CONTACTS_MISSING_EVERY = 6
_CONTACTS_MISSING_OFFSET = 2
_OFFICIAL_MISSING_EVERY = 7
_OFFICIAL_MISSING_OFFSET = 5


@register_source
class MockSource:
    """进程内确定性生成，不访问任何外部服务。"""

    manifest = SourceManifest(
        id="mock",
        name="内置演示语料",
        capabilities=("company_search", "person_search", "contact_search"),
        description="进程内确定性生成的演示数据，用于在未接入真实数据源时跑通整条链路。",
        regions=("CN",),
        priority=10,
        cost_per_call=0.0,
        requires_credentials=False,
    )

    # ── company_search ──────────────────────────────────────────────────

    def search_companies(self, query: CompanyQuery) -> list[CompanyRecord]:
        seeds = select_seeds(query.seed, query.limit, query.preferred_city, query.industry_hints)
        records: list[CompanyRecord] = []
        for index, seed in enumerate(seeds):
            name = query.names[index] if index < len(query.names) else seed.name
            missing = _missing_fields(index)
            has_summary = "summary" not in missing
            records.append(
                CompanyRecord(
                    external_id=f"mock-{seed.domain}",
                    name=name,
                    domain=seed.domain,
                    industries=tuple(seed.industries),
                    summary=seed.summary if has_summary else "",
                    location=seed.location,
                    employees=seed.employees,
                    funding_stage=seed.funding_stage,
                    contact_count=_contact_count(index, missing),
                    evidence=_evidence_for(
                        name,
                        seed.domain,
                        has_summary=has_summary,
                        has_official="official_contact" not in missing,
                    ),
                    missing_fields=missing,
                    source_id=self.manifest.id,
                )
            )
        return records

    # ── person_search ───────────────────────────────────────────────────

    def search_people(self, query: PersonQuery) -> list[PersonRecord]:
        seeds = select_people(
            query.seed,
            query.limit,
            query.preferred_city,
            query.name_hints,
            query.role_hints,
            query.company_hints,
        )
        records: list[PersonRecord] = []
        for index, seed in enumerate(seeds):
            missing = _person_missing_fields(index)
            has_summary = "summary" not in missing
            source_url = _source_url(seed)
            records.append(
                PersonRecord(
                    external_id=f"mock-person-{seed.name_local or seed.name}",
                    name=seed.name,
                    name_local=seed.name_local,
                    title=seed.title,
                    company=seed.company,
                    company_domain=seed.company_domain,
                    location=seed.location,
                    summary=seed.summary if has_summary else "",
                    source_label=seed.source_label,
                    source_url=source_url,
                    aliases=tuple(seed.aliases),
                    keywords=tuple(seed.keywords),
                    contact_email=seed.contact_email,
                    confidence=88 - (index % 4) * 7,
                    evidence=_evidence_for_person(seed, source_url, has_summary=has_summary),
                    missing_fields=missing,
                    source_id=self.manifest.id,
                )
            )
        return records

    # ── contact_search ──────────────────────────────────────────────────

    def search_contacts(self, query: ContactQuery) -> list[ContactRecord]:
        domain = query.domain.strip().lower()
        if not domain:
            # 契约层面就拒绝按公司名查人：同名企业极多，用名称猜域名必然捞到无关公司的人。
            raise SourceError(
                "按联系人检索必须提供已验证的域名，不接受公司名称",
                kind="invalid_request",
                source_id=self.manifest.id,
            )

        contacts = build_contacts(query.seed, domain, max(0, query.limit))
        if query.positions:
            wanted = tuple(item.strip().lower() for item in query.positions if item.strip())
            contacts = [item for item in contacts if any(token in item.title.lower() for token in wanted)]

        return [
            ContactRecord(
                external_id=item.id,
                name=item.name,
                title=item.title,
                email=item.email,
                phone=item.phone,
                linkedin=item.linkedin,
                domain=domain,
                confidence=item.confidence,
                source_id=self.manifest.id,
            )
            for item in contacts
        ]


def select_seeds(
    seed: int,
    count: int,
    preferred_city: str | None,
    industry_tokens: tuple[str, ...] = (),
) -> list[CompanySeed]:
    """决定这一轮召回哪些企业。

    召回顺序体现「相关性优先」：**先取命中行业的语料，再取其余，最后才合成补齐**。
    城市只是先缩小池子，行业才决定排序——**两个分支的排序规则必须一致**。
    曾经没有城市时直接整池轮转、把 `industry_tokens` 丢掉，于是「消费品行业的商家」
    这类不带城市的画像会召回一堆人工智能与工业软件公司，行业标准成批落空；
    那是**召回策略的问题**，不该让判定层替它扣分。

    末尾的合成补齐也是有意为之：语料覆盖有限，不为凑数去拉不相关的企业，
    而是按目标城市与行业合成。真实数据源在这里会做分页请求，逻辑上是同一件事。

    传入的 `industry_tokens` 为空时，结果与「整池轮转」等价——没有相关性信号时
    只做确定性打散，不假装自己知道该优先谁。
    """
    corpus_size = COMPANY_INDEX.corpus_size
    pool = [COMPANY_INDEX.at(index) for index in range(corpus_size)]

    if preferred_city:
        scoped = [item for item in pool if preferred_city in item.location]
        if not scoped:
            # 目标城市没有语料覆盖：直接为该城市合成，而不是返回别处的企业。
            return [COMPANY_INDEX.synthesize(index, preferred_city, industry_tokens) for index in range(count)]
    else:
        # 没有城市约束时行业是唯一的相关性信号，池子就是全部语料。
        scoped = pool

    matched = [item for item in scoped if _matches_industry(item, industry_tokens)]
    rest = [item for item in scoped if item not in matched]
    offset = seed % max(1, len(matched) or len(scoped))
    ordered = _rotate(matched, offset) + _rotate(rest, offset) if matched else _rotate(rest, offset)

    if len(ordered) >= count:
        return ordered[:count]

    return ordered + [
        COMPANY_INDEX.synthesize(index, preferred_city, industry_tokens)
        for index in range(count - len(ordered))
    ]


def _matches_industry(seed: CompanySeed, industry_tokens: tuple[str, ...]) -> bool:
    if not industry_tokens:
        return False
    haystack = "".join(seed.industries)
    return any(token in haystack for token in industry_tokens)


ItemT = TypeVar("ItemT")


def _rotate(items: list[ItemT], offset: int) -> list[ItemT]:
    """按 offset 做确定性打散。公司与人物两种语料共用——打散规则本来就不是领域知识。"""
    if not items:
        return []
    pivot = offset % len(items)
    return items[pivot:] + items[:pivot]


# ── 人物召回 ──────────────────────────────────────────────────────────────

# 姓名命中的计分：整名对上远强于只对上姓或半个名。
_NAME_SCORES: dict[str, int] = {"full": 4, "partial": 2}


def select_people(
    seed: int,
    count: int,
    preferred_city: str | None,
    name_hints: tuple[str, ...] = (),
    role_hints: tuple[str, ...] = (),
    company_hints: tuple[str, ...] = (),
) -> list[PersonSeed]:
    """决定这一轮召回哪些人物档案。

    排序按**相关性分级**，与公司召回同一条原则：姓名命中排最前（找一个人时它几乎决定一切），
    其次职位与公司特征命中，最后才是无关条目。

    与公司召回的一处**有意为之的差别**：命中的那一段**不随 seed 轮转**。
    公司画像是一组条件，换个 seed 换一批候选是合理的；而按人名找人是**唯一答案式**的检索，
    把最相关的挪到第二页只会让人以为没找到。重复召回由上层按 `dedupe_key` 去重解决。

    城市在这里只做**排序加权而不是硬过滤**：人物档案的公开信息里所在地常常缺失或滞后，
    硬筛会让「上海的目标人」在只写了城市的情况下整批落空。
    """
    corpus_size = PERSON_INDEX.corpus_size
    pool = [PERSON_INDEX.at(index) for index in range(corpus_size)]

    def relevance(item: PersonSeed) -> int:
        score = _NAME_SCORES.get(_match_person_name(item, name_hints).level, 0)
        if _role_matches(item, role_hints):
            score += 2
        if _company_matches(item, company_hints):
            score += 2
        if preferred_city and preferred_city in item.location:
            score += 1
        return score

    ranked = sorted(pool, key=relevance, reverse=True)
    matched = [item for item in ranked if relevance(item) > 0]
    rest = [item for item in ranked if relevance(item) == 0]

    if matched:
        ordered = matched + _rotate(rest, seed % max(1, len(rest)))
    else:
        ordered = _rotate(rest, seed % max(1, len(rest)))

    if len(ordered) >= count:
        return ordered[:count]

    return ordered + [
        PERSON_INDEX.synthesize(index, preferred_city, role_hints) for index in range(count - len(ordered))
    ]


def _match_person_name(item: PersonSeed, name_hints: tuple[str, ...]) -> NameMatch:
    """这条档案的姓名是否命中。规则本身在 `app.matching`，判定层用的是同一份。"""
    return match_name((item.name, item.name_local, *item.aliases), name_hints)


def _role_matches(item: PersonSeed, role_hints: tuple[str, ...]) -> bool:
    if not role_hints:
        return False
    haystack = f"{item.title}{''.join(item.keywords)}"
    return any(token in haystack for token in role_hints)


def _company_matches(item: PersonSeed, company_hints: tuple[str, ...]) -> bool:
    if not company_hints:
        return False
    haystack = f"{item.company}{item.company_domain}{''.join(item.keywords)}"
    return any(token in haystack for token in company_hints)


# 档案地址的拼装模板：**职位来源决定域名归属**，句柄只补充路径。
# 曾经这里对非领英来源直接写 `https://{句柄}`，于是「网址」列出现 `https://heng-xiao`
# 这种没有域名的地址——列显示、跳转、以及「按域名回推所属企业」都会一起坏掉。
_SOURCE_URL_PATTERNS: dict[str, str] = {
    "领英": "https://linkedin.com/in/{handle}",
    "公司团队页": "https://{domain}/team/{handle}",
}
# 其余来源（会议嘉宾页、学术主页、专利发明人页等）在演示语料里没有各自的域名，
# 统一挂在所属机构域名下；来源类型由 `source_label` 表达，不靠域名区分。
_DEFAULT_SOURCE_PATTERN = "https://{domain}/people/{handle}"


def _source_url(item: PersonSeed) -> str:
    """把档案来源与句柄拼成可访问的地址。

    「网址」列在参考站里显示成「来源 + 域名 + 路径」，所以地址必须能拆出域名，
    不能只存一个来源名或句柄。
    """
    pattern = _SOURCE_URL_PATTERNS.get(item.source_label, _DEFAULT_SOURCE_PATTERN)
    return pattern.format(handle=item.source_handle, domain=item.company_domain)


def _person_missing_fields(index: int) -> frozenset[EnrichableField]:
    """人物档案刻意保留一定比例缺摘要，使「重试该字段」链路在找人模式下也有样本。"""
    if index % _SUMMARY_MISSING_EVERY == _SUMMARY_MISSING_OFFSET:
        return frozenset({"summary"})
    return frozenset()


def _evidence_for_person(item: PersonSeed, source_url: str, *, has_summary: bool) -> tuple[Evidence, ...]:
    source_desc = SOURCE_DESCRIPTIONS.get(item.source_label, "公开档案")
    items = [
        Evidence(
            title=f"{item.name} · {item.source_label}",
            url=source_url,
            snippet=f"公开职业档案，用于确认其现任职位、所属机构与履历（来源：{source_desc}）。",
        )
    ]
    if has_summary and item.company_domain:
        items.append(
            Evidence(
                title=f"{item.company} · 团队页",
                url=f"https://{item.company_domain}/team",
                snippet="所属机构的团队介绍页，用于交叉确认其在职状态。",
            )
        )
    # 本人公开动态：换岗、招聘这类意向信号就发在那里，评估卡引用它才能
    # 与参考站一样给出「本人加入团队的动态」这条佐证。只有领英类档案有动态页。
    if has_summary and item.source_label == "领英":
        items.append(
            Evidence(
                title=f"{item.name} · 公开动态",
                url=f"https://linkedin.com/posts/{item.source_handle}",
                snippet="本人的公开动态流，用于捕捉新上任、扩张、招聘等触达窗口期线索。",
            )
        )
    return tuple(items)


def _missing_fields(index: int) -> frozenset[EnrichableField]:
    missing: list[EnrichableField] = []
    if index % _SUMMARY_MISSING_EVERY == _SUMMARY_MISSING_OFFSET:
        missing.append("summary")
    if index % _CONTACTS_MISSING_EVERY == _CONTACTS_MISSING_OFFSET:
        missing.append("contacts")
    if index % _OFFICIAL_MISSING_EVERY == _OFFICIAL_MISSING_OFFSET:
        missing.append("official_contact")
    return frozenset(missing)


def _contact_count(index: int, missing: frozenset[EnrichableField]) -> int:
    if "contacts" in missing:
        return 0
    return 1 + (index % 4) + (3 if index % 5 == 0 else 0)


def _evidence_for(name: str, domain: str, *, has_summary: bool, has_official: bool) -> tuple[Evidence, ...]:
    """只引用企业自身的公开页面，不引用第三方站点。"""
    items = [
        Evidence(
            title=f"{name}（官网首页）",
            url=f"https://{domain}",
            snippet="官网首页，用于确认企业名称、业务范围与所在地区。",
        )
    ]
    if has_summary:
        items.append(
            Evidence(
                title=f"{name} · 业务介绍",
                url=f"https://{domain}/about",
                snippet="官网「关于我们」页，用于确认主营业务与规模表述。",
            )
        )
    if has_official:
        items.append(
            Evidence(
                title=f"{name} · 联系我们",
                url=f"https://{domain}/contact",
                snippet="官网联系方式页，用于确认可触达的公开渠道。",
            )
        )
    return tuple(items)
