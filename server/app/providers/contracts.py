"""数据源契约层：业务代码与外部数据获取之间的唯一接口面。

业务代码只认这里定义的**归一化记录**，不认识任何厂商字段名，也不关心数据究竟来自
厂商 API、公开网页爬取还是内置演示语料。因此新增一类爬虫时，业务层不需要任何改动。

## 新增一类爬虫的完整步骤

1. 在 `SourceCapability` 里登记能力名；
2. 在本文件里为它定义归一化记录（参考 `CompanyRecord`）与查询参数（参考 `CompanyQuery`）；
3. 为它定义一个 `Protocol`，只声明这类爬虫**必须**提供的方法（参考 `CompanySearchSource`）；
4. 写实现类：声明 `manifest`、实现对应方法，用 `@register_source` 注册；
5. 在 `config.py` 的 `DEFAULT_*_SOURCE` 里把它指为默认（或用环境变量切换）。

## 两条贯穿设计的约束

- **失败必须可分类**：所有异常都收敛到 `SourceError`，携带 `kind` 与 `retryable`，
  使上层能区分「凭据失效」与「查到了但没数据」。**绝不能把调用失败伪装成空结果**。
- **证据随记录一起返回**：`CompanyRecord.evidence` 是契约的一部分，不是可选项。
  演示语料填演示证据，真实爬虫填真实 URL，上层的「为什么匹配」链路不用改一行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# ── 能力清单 ──────────────────────────────────────────────────────────────
# 一个数据源可以同时具备多种能力；registry 按能力而非按实现类来查找数据源。

SourceCapability = Literal[
    "company_search",  # 公司/机构线索召回
    "person_search",  # 人物职业档案召回（按画像找「人」，不是按域名补联系人）
    "contact_search",  # 按域名捞联系人
    "company_enrich",  # 按域名/名称补齐单家企业的字段（L2 firmographic）
    "web_search",  # 公开网页检索与正文抽取
    "trade_search",  # 海关/贸易记录（预留，尚未实现）
    "news_search",  # 新闻与舆情（预留，尚未实现）
    "tender_search",  # 招投标公告（预留，尚未实现）
]

# ── 错误分类 ──────────────────────────────────────────────────────────────

SourceErrorKind = Literal[
    "missing_credentials",
    "auth_failed",
    "permission_denied",
    "quota_exhausted",
    "rate_limited",
    "invalid_request",
    "upstream_unavailable",
    "timeout",
    "invalid_response",
    "not_implemented",
]


class SourceError(RuntimeError):
    """数据源调用失败。

    `kind` 供上层做分支恢复，`retryable` 决定是否可以原样重试。
    `quota_exhausted` / `rate_limited` 属于**正常运行中一定会遇到**的分支，
    不是异常情况，上层应据此降级或排队，而不是把它当成「没有数据」。
    """

    def __init__(
        self,
        message: str,
        *,
        kind: SourceErrorKind,
        retryable: bool = False,
        retry_after: float | None = None,
        source_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.retry_after = retry_after
        self.source_id = source_id
        self.details = details or {}


# ── 归一化记录 ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Evidence:
    """一条可回溯的证据。title 与 url 必填，snippet 用于在 UI 上展示原文片段。"""

    title: str
    url: str
    snippet: str = ""


# 可以被富化的字段名。数据源用它如实上报「这几个字段我没拿到」，
# 上层据此把对应单元格标成失败并给出重试入口——**缺失是数据源的事实，不是上层的猜测**。
EnrichableField = Literal["summary", "contacts", "official_contact"]


@dataclass(frozen=True, slots=True)
class CompanyRecord:
    """一家公司的归一化画像。

    `attributes` 用来承载某类数据源特有的字段（真实厂商会返回几十个），
    它们**不参与业务判断**，只在需要时透传给前端，因此不会污染核心契约。

    `missing_fields` 是多源补齐的驱动字段：瀑布编排把多个源的结果合并时，
    只对仍然缺失的字段继续向更贵的源求助，已经拿到的字段不再重复付费。
    """

    external_id: str
    name: str
    domain: str
    industries: tuple[str, ...] = ()
    summary: str = ""
    location: str = ""
    employees: str = ""
    funding_stage: str = ""
    contact_count: int = 0
    evidence: tuple[Evidence, ...] = ()
    missing_fields: frozenset[EnrichableField] = frozenset()
    source_id: str = ""
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        """跨数据源去重用的稳定键。域名是行业通行做法，缺失时退化到名称。"""
        return self.domain.strip().lower() or self.name.strip().lower()


@dataclass(frozen=True, slots=True)
class ContactRecord:
    """一个人物联系人。`domain` 与 `confidence` 是所有数据源都应尽量给出的两个字段。"""

    external_id: str
    name: str
    title: str
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    domain: str = ""
    confidence: int = 0
    source_id: str = ""


@dataclass(frozen=True, slots=True)
class WebDocument:
    """公开网页检索结果。text 为空表示只拿到了标题与摘要，正文抽取失败。"""

    url: str
    title: str
    snippet: str = ""
    text: str = ""
    published_at: str = ""
    source_id: str = ""


@dataclass(frozen=True, slots=True)
class PersonRecord:
    """一个人的职业档案画像。

    与 `ContactRecord` 的区别是**这两个契约回答的不是同一个问题**，不要合并：

    - `ContactRecord` 是「已知一家公司，去它官网捞能联系到的人」，输入是**域名**，
      输出的是可直接触达的联系方式，属于公司结果的下钻能力；
    - `PersonRecord` 是「按画像直接找符合条件的人」，输入是**画像**（姓名/职位/公司特征），
      输出的是一个人的职业档案（履历、职位、雇主、档案地址），本身就是**结果实体**。

    所以找人的列表行没有「行业」「规模」「融资」这些公司字段，
    换成了「职位」「所属公司」「来源档案」。这一层的差异必须体现在契约上，
    否则上层只能把人物硬塞进公司模型，出现「行业」列显示职位这种错位。

    `aliases` 是姓名匹配的关键：同一个中文名在英文职业档案里会写成拼音的正序、倒序、
    带连字符等多种形态，召回与判定的姓名比对都靠它，而不是靠上层猜拼音。
    """

    external_id: str
    name: str
    title: str = ""
    company: str = ""
    company_domain: str = ""
    name_local: str = ""
    location: str = ""
    summary: str = ""
    source_label: str = ""
    source_url: str = ""
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    contact_email: str = ""
    contact_phone: str = ""
    confidence: int = 0
    evidence: tuple[Evidence, ...] = ()
    missing_fields: frozenset[EnrichableField] = frozenset()
    source_id: str = ""
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def all_names(self) -> tuple[str, ...]:
        """展示名、中文名与全部别名，姓名比对只认这一份来源。"""
        return tuple(dict.fromkeys(item for item in (self.name, self.name_local, *self.aliases) if item.strip()))

    @property
    def dedupe_key(self) -> str:
        """跨数据源去重用的稳定键。职业档案地址最稳，缺失时退化到「姓名@公司」。"""
        return self.source_url.strip().lower() or f"{self.name}@{self.company}".strip().lower()


# ── 查询参数 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CompanyQuery:
    """公司召回的入参。

    `seed` 用于让同一个数据源在演示模式下产出稳定但可复现的结果；
    真实数据源可以完全忽略它。

    `industry_hints` 由标准引擎（L0）从画像里解析出的行业匹配词。
    **它是提示不是过滤条件**：真实数据源可以完全忽略，也可以据此改写查询、
    或只作为排序权重。之所以要传下来，是因为「找消费品企业却返回一堆无关行业」
    属于**召回层的问题**，让它下移到判定层扣分是找错了责任方。
    """

    text: str
    limit: int
    mode: str = "company"
    preferred_city: str | None = None
    industry_hints: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    seed: int = 0
    locale: str = "zh"


@dataclass(frozen=True, slots=True)
class ContactQuery:
    """按域名查联系人。**不接受公司名**：同名企业极多，用名称猜域名会捞到无关公司的人。"""

    domain: str
    positions: tuple[str, ...] = ()
    limit: int = 10
    seed: int = 0
    locale: str = "zh"


@dataclass(frozen=True, slots=True)
class PersonQuery:
    """人物召回的入参。

    三个 `*_hints` 都来自人物标准引擎（L0），与 `CompanyQuery.industry_hints` 同一条约定：
    **是提示不是过滤条件**。真实数据源多半只能用到其中一部分（例如只有姓名能做精确检索，
    职位与公司特征只能当排序权重），所以不能把它们当作必达的过滤项，否则真实源一接进来
    就会大面积返回空结果。

    `name_hints` 额外承担一个职责：按人名找人是**找人的常态用法**，
    此时「召回什么」几乎完全由这个名字决定，提示缺失才退回按职位/公司特征的画像式召回。
    """

    text: str
    limit: int
    preferred_city: str | None = None
    name_hints: tuple[str, ...] = ()
    role_hints: tuple[str, ...] = ()
    company_hints: tuple[str, ...] = ()
    seed: int = 0
    locale: str = "zh"


@dataclass(frozen=True, slots=True)
class WebQuery:
    """公开网页检索。"""

    queries: tuple[str, ...]
    limit: int = 10
    include_domains: tuple[str, ...] = ()
    locale: str = "zh"


@dataclass(frozen=True, slots=True)
class EnrichTarget:
    """一条待补齐的企业指征。域名与名称至少有一个；两个都有时域名优先（更精确）。

    `missing` 是召回记录缺失的可补字段提示：权威源（按 profile 计费）可以忽略它，
    但按次计费的廉价源（如 web 搜索富化）应当据此跳过帮不上忙的目标——
    「已经拿到的字段不再重复付费」是补齐编排的通行原则。
    """

    domain: str = ""
    name: str = ""
    missing: frozenset[EnrichableField] = frozenset()

    @property
    def cache_key(self) -> str:
        """同一企业的缓存键：域名最稳，缺失时退化到名称。"""
        return (self.domain.strip().lower() or self.name.strip().lower())


@dataclass(frozen=True, slots=True)
class CompanyEnrichQuery:
    """字段补齐的入参：一批企业指征，逐家富化。

    与 `CompanyQuery` 刻意分开：召回回答「这批候选是谁」，补齐回答「这家企业还有
    什么字段」——两者的计费模型完全不同（召回按查询次数，补齐按企业条数），
    合并成一个查询会让缓存键和配额控制都变得含糊。
    """

    targets: tuple[EnrichTarget, ...]
    locale: str = "zh"


# ── 数据源清单 ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """数据源的自描述信息。

    `priority` 越小越先被瀑布式编排选中——便宜的、覆盖率高的排前面，
    昂贵的补充源排后面，这是行业里 waterfall enrichment 的通行做法。
    """

    id: str
    name: str
    capabilities: tuple[SourceCapability, ...]
    description: str = ""
    regions: tuple[str, ...] = ()
    priority: int = 50
    cost_per_call: float = 0.0
    requires_credentials: bool = False

    def supports(self, capability: SourceCapability) -> bool:
        return capability in self.capabilities


@dataclass(slots=True)
class SourceResult[ItemT]:
    """一次数据源调用的结果信封。

    带上 `source_id` / `latency_ms` / `cost` 是为了让上层记账：
    真实数据源按次计费，没有台账就无法定价，也无法定位成本异常。
    """

    items: list[ItemT]
    source_id: str
    latency_ms: int = 0
    cost: float = 0.0
    cache_hit: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


# ── 能力协议 ──────────────────────────────────────────────────────────────
# 一个数据源实现其中任意一个或多个协议即可；registry 会按能力逐一校验。


class CompanySearchSource(Protocol):
    """具备公司召回能力的数据源。"""

    manifest: SourceManifest

    def search_companies(self, query: CompanyQuery) -> list[CompanyRecord]: ...


class ContactSearchSource(Protocol):
    """具备联系人召回能力的数据源。"""

    manifest: SourceManifest

    def search_contacts(self, query: ContactQuery) -> list[ContactRecord]: ...


class PersonSearchSource(Protocol):
    """具备人物职业档案召回能力的数据源。"""

    manifest: SourceManifest

    def search_people(self, query: PersonQuery) -> list[PersonRecord]: ...


class WebSearchSource(Protocol):
    """具备公开网页检索能力的数据源。"""

    manifest: SourceManifest

    def search_web(self, query: WebQuery) -> list[WebDocument]: ...


class CompanyEnrichSource(Protocol):
    """具备企业字段补齐能力的数据源（L2 firmographic：Apollo / PDL / 企查查）。

    返回的 `CompanyRecord` 只承载**该源实际拿到的字段**，拿不到的留空——
    编排层按 `missing_fields` 决定是否向更贵的源继续求助，所以这里
    绝不能用默认值假装字段拿到了。
    """

    manifest: SourceManifest

    def enrich_companies(self, query: CompanyEnrichQuery) -> list[CompanyRecord]: ...


# 能力名 → 该能力必须具备的方法名。registry 用它做注册期校验，
# 把「声明了能力却没实现方法」这类错误提前到启动时暴露。
CAPABILITY_METHODS: dict[SourceCapability, str] = {
    "company_search": "search_companies",
    "person_search": "search_people",
    "contact_search": "search_contacts",
    "company_enrich": "enrich_companies",
    "web_search": "search_web",
    "trade_search": "search_trade_records",
    "news_search": "search_news",
    "tender_search": "search_tenders",
}
