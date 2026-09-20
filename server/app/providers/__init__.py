"""数据源层的公共出口。

业务代码只从这里取数据源，不直接 import 具体实现类：

    from ..providers import call_source, company_source

    result = call_source(company_source(), "company_search", query)

切换数据源只需改 `config.DEFAULT_DATA_SOURCE`（或用环境变量 `AIGET_DATA_SOURCE`），
业务代码一行都不用动。

当同一个能力有多个数据源时，改用 `collect()` 做瀑布式编排：它按 `priority` 依次调用、
边收边去重、够量即停，并把每个源的失败记进 `meta["failures"]`。
"""

from __future__ import annotations

from ..config import DEFAULT_DATA_SOURCE
from . import enrichment  # noqa: F401 — 补齐编排随包导出
from . import mock_source  # noqa: F401 — 导入即完成注册，是唯一的注册入口
# 真实源（P4/P5）按凭据就绪与否在各自模块内决定是否注册，缺失时静默跳过。
from . import pdl_source  # noqa: F401
from . import tavily_source  # noqa: F401
from .contracts import (
    CAPABILITY_METHODS,
    CompanyEnrichQuery,
    CompanyQuery,
    CompanyRecord,
    CompanySearchSource,
    ContactQuery,
    ContactRecord,
    CompanyEnrichSource,
    ContactSearchSource,
    EnrichableField,
    EnrichTarget,
    Evidence,
    PersonQuery,
    PersonRecord,
    PersonSearchSource,
    SourceCapability,
    SourceError,
    SourceErrorKind,
    SourceManifest,
    SourceResult,
    WebDocument,
    WebQuery,
    WebSearchSource,
)
from .enrichment import enrich_companies, has_enrich_sources
from .registry import (
    call_source,
    collect,
    get_source,
    has_source,
    manifests,
    register_source,
    sources_for,
    unregister_source,
)

__all__ = [
    "CAPABILITY_METHODS",
    "CompanyEnrichQuery",
    "CompanyEnrichSource",
    "CompanyQuery",
    "CompanyRecord",
    "CompanySearchSource",
    "ContactQuery",
    "ContactRecord",
    "ContactSearchSource",
    "EnrichableField",
    "EnrichTarget",
    "Evidence",
    "enrich_companies",
    "PersonQuery",
    "PersonRecord",
    "PersonSearchSource",
    "SourceCapability",
    "SourceError",
    "SourceErrorKind",
    "SourceManifest",
    "SourceResult",
    "WebDocument",
    "WebQuery",
    "WebSearchSource",
    "call_source",
    "collect",
    "company_source",
    "contact_source",
    "get_source",
    "has_enrich_sources",
    "has_source",
    "manifests",
    "person_source",
    "register_source",
    "sources_for",
    "unregister_source",
]


def company_source(source_id: str = "") -> object:
    """取默认的公司召回数据源。`source_id` 留空时用配置里的默认值。"""
    return get_source(source_id or DEFAULT_DATA_SOURCE)


def person_source(source_id: str = "") -> object:
    """取默认的人物档案召回数据源。

    与 `company_source` 默认指向同一个实现，但**保留成独立函数**：
    真实接入时「找公司」与「找人」通常来自完全不同的供应商
    （公司库 vs 职业档案库），共用取值入口会让将来切换其中一个变成改业务代码。
    """
    return get_source(source_id or DEFAULT_DATA_SOURCE)


def contact_source(source_id: str = "") -> object:
    """取默认的联系人数据源。默认与公司源同一个实现，但两者可以独立替换。"""
    return get_source(source_id or DEFAULT_DATA_SOURCE)
