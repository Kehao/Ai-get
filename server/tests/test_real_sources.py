"""P4/P5 真实数据源 adapter 的单元测试：全部用假 client，不产生任何网络请求。

覆盖三件事：
1. Tavily 召回的映射规则（域名提取、名称截取、去重、缺失字段如实上报）与错误分类；
2. PDL 补齐的映射规则与缓存语义（命中不重复计费、空档企业缓存空哨兵）；
3. 补齐编排的字段合并（只填空字段、证据去重、missing_fields 收敛）。
"""

from __future__ import annotations

import pytest

from app.providers import cache as source_cache
from app.providers.contracts import (
    CompanyEnrichQuery,
    CompanyQuery,
    CompanyRecord,
    EnrichTarget,
    SourceError,
)
from app.providers.enrichment import enrich_companies, merge_enrichment
from app.providers.pdl_source import PdlSource
from app.providers.tavily_source import TavilySource


@pytest.fixture(autouse=True)
def _clean_cache():
    source_cache.clear()
    yield
    source_cache.clear()


# ── Tavily：召回映射 ──────────────────────────────────────────────────────


class FakeTavilyClient:
    def __init__(self, results: list[dict], fail_with: Exception | None = None):
        self.results = results
        self.fail_with = fail_with
        self.calls = 0

    def search(self, **kwargs):
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        return {"results": self.results}


def _tavily_results() -> list[dict]:
    return [
        {
            "title": "云杉网络 - 企业云安全服务",
            "url": "https://www.yunshan.net/about",
            "content": "云杉网络是企业云安全服务商，提供微分段与容器安全。",
            "score": 0.87,
        },
        {
            # 同一域名（去 www 后重复）：必须被去重掉。
            "title": "重复条目",
            "url": "https://yunshan.net/team",
            "content": "重复",
            "score": 0.5,
        },
        {
            # 没有合法域名：整条丢弃。
            "title": "不是企业的页面",
            "url": "https://example.org/blog/post",
            "content": "博客页",
            "score": 0.3,
        },
        {
            # 标题切不出名称：退化到域名主体。
            "title": "Shop SaaS Tools Online",
            "url": "https://shopsaas.com",
            "content": "Tools for shops.",
            "score": 0.4,
        },
    ]


def test_tavily_maps_results_to_company_records():
    source = TavilySource(api_key="test", client=FakeTavilyClient(_tavily_results()))
    query = CompanyQuery(
        text="找云安全公司",
        limit=10,
        industry_hints=("云安全", "企业服务"),
    )

    records = source.search_companies(query)

    assert [record.domain for record in records] == ["yunshan.net", "shopsaas.com"]
    first = records[0]
    assert first.name == "云杉网络"
    assert first.external_id == "tavily-yunshan.net"
    # 行业提示里只有真实出现在标题/正文的词才记进来。
    assert first.industries == ("云安全",)
    assert first.summary.startswith("云杉网络是企业云安全服务商")
    assert first.missing_fields == frozenset({"contacts", "official_contact"})
    assert first.evidence[0].url == "https://www.yunshan.net/about"
    assert first.source_id == "tavily"
    # 标题切不出名称时退化到域名主体。
    assert records[1].name == "Shopsaas"


def test_tavily_summary_missing_is_reported():
    results = [{"title": "某公司", "url": "https://acme.cn", "content": "", "score": 0.1}]
    source = TavilySource(api_key="test", client=FakeTavilyClient(results))

    records = source.search_companies(CompanyQuery(text="测试", limit=5))

    assert records[0].summary == ""
    assert "summary" in records[0].missing_fields


def test_tavily_result_is_cached():
    client = FakeTavilyClient(_tavily_results())
    source = TavilySource(api_key="test", client=client)
    query = CompanyQuery(text="找云安全公司", limit=10)

    source.search_companies(query)
    source.search_companies(query)

    assert client.calls == 1


@pytest.mark.parametrize(
    ("message", "expected_kind"),
    [
        ("401 Unauthorized", "auth_failed"),
        ("429 Too Many Requests", "rate_limited"),
        ("432 quota exceeded for plan", "quota_exhausted"),
        ("connection reset", "upstream_unavailable"),
    ],
)
def test_tavily_errors_are_classified(message: str, expected_kind: str):
    source = TavilySource(api_key="test", client=FakeTavilyClient([], fail_with=Exception(message)))

    with pytest.raises(SourceError) as caught:
        source.search_companies(CompanyQuery(text="测试", limit=5))

    assert caught.value.kind == expected_kind
    assert caught.value.source_id == "tavily"


# ── PDL：字段补齐 ─────────────────────────────────────────────────────────


class FakePdlCompanyEndpoint:
    def __init__(self, responses: dict[str, dict] | None = None, not_found: set[str] | None = None):
        self.responses = responses or {}
        self.not_found = not_found or set()
        self.calls: list[dict] = []

    def enrich(self, **kwargs):
        self.calls.append(kwargs)
        key = str(kwargs.get("website") or kwargs.get("name") or "")
        if key in self.not_found or key not in self.responses:
            return {"status": 404, "error": {"type": "NOT_FOUND", "message": "404 Not Found"}}
        return {"status": 200, "data": self.responses[key]}


class FakePdlClient:
    def __init__(self, responses: dict[str, dict] | None = None, not_found: set[str] | None = None):
        self.company = FakePdlCompanyEndpoint(responses, not_found)


_PDL_PROFILE = {
    "id": "pdl-123",
    "name": "云杉网络",
    "website": "yunshan.net",
    "industry": "computer & network security",
    "tags": ["cloud", "saas", "security"],
    "size": "51-200",
    "founded": 2011,
    "locality": "beijing",
    "region": "beijing",
    "country": "china",
    "linkedin_url": "https://linkedin.com/company/yunshan",
}


def test_pdl_maps_profile_to_company_record():
    source = PdlSource(api_key="test", client=FakePdlClient({"yunshan.net": _PDL_PROFILE}))

    records = source.enrich_companies(
        CompanyEnrichQuery(targets=(EnrichTarget(domain="yunshan.net"),))
    )

    assert len(records) == 1
    record = records[0]
    assert record.name == "云杉网络"
    assert record.domain == "yunshan.net"
    # 主行业在前，tags 补后——顺序即权重。
    assert record.industries[0] == "computer & network security"
    assert record.employees == "51-200"
    # locality 与 region 相同时只保留一份——重复地名没有信息量。
    assert record.location == "beijing，china"
    assert record.attributes["founded"] == "2011"
    assert record.attributes["pdl_id"] == "pdl-123"
    # 免费层没有联系人数据：contact_count 不写，缺失如实上报。
    assert record.contact_count == 0
    assert "contacts" in record.missing_fields
    assert any(item.url == "https://linkedin.com/company/yunshan" for item in record.evidence)


def test_pdl_enrich_params_prefer_domain():
    source = PdlSource(api_key="test", client=FakePdlClient({}))

    source.enrich_companies(CompanyEnrichQuery(targets=(EnrichTarget(domain="yunshan.net"),)))

    assert source._pdl().company.calls[0]["search_type"] == "strict"
    assert source._pdl().company.calls[0]["website"] == "yunshan.net"


def test_pdl_not_found_is_cached_as_empty():
    client = FakePdlClient(not_found={"ghost.io"})
    source = PdlSource(api_key="test", client=client)
    query = CompanyEnrichQuery(targets=(EnrichTarget(domain="ghost.io"),))

    assert source.enrich_companies(query) == []
    # 第二次查询同一空档企业：命中空哨兵，不再打 API。
    assert source.enrich_companies(query) == []
    assert len(client.company.calls) == 1


def test_pdl_same_target_hits_cache_once():
    client = FakePdlClient({"yunshan.net": _PDL_PROFILE})
    source = PdlSource(api_key="test", client=client)
    query = CompanyEnrichQuery(targets=(EnrichTarget(domain="yunshan.net"),))

    source.enrich_companies(query)
    source.enrich_companies(query)

    assert len(client.company.calls) == 1


def test_pdl_target_without_domain_and_name_is_skipped():
    client = FakePdlClient({})
    source = PdlSource(api_key="test", client=client)

    records = source.enrich_companies(CompanyEnrichQuery(targets=(EnrichTarget(),)))

    assert records == []
    assert client.company.calls == []


# ── 编排：瀑布补齐 + 字段合并 ─────────────────────────────────────────────


def test_merge_enrichment_fills_only_empty_fields():
    from app.providers.contracts import Evidence

    base = CompanyRecord(
        external_id="mock-1",
        name="已有完整名称的企业",
        domain="acme.cn",
        industries=("软件",),
        summary="召回阶段就拿到了摘要",
        location="",
        employees="",
        funding_stage="",
        evidence=(Evidence(title="召回证据", url="https://acme.cn", snippet=""),),
        missing_fields=frozenset({"contacts", "official_contact"}),
        source_id="mock",
    )
    enriched = CompanyRecord(
        external_id="pdl-1",
        name="PDL 里的名字",
        domain="acme.cn",
        industries=("software",),
        summary="PDL 的摘要，不应覆盖召回已有的",
        location="hangzhou，china",
        employees="51-200",
        funding_stage="B轮",
        evidence=(Evidence(title="重复证据", url="https://acme.cn", snippet=""),),
        missing_fields=frozenset(),
        source_id="pdl",
    )

    merged = merge_enrichment(base, enriched)

    assert merged.summary == "召回阶段就拿到了摘要"  # 已有字段不被覆盖
    assert merged.location == "hangzhou，china"
    assert merged.employees == "51-200"
    assert merged.industries == ("软件",)  # 已有行业不并
    assert merged.funding_stage == "B轮"
    assert merged.source_id == "mock"  # 结果仍是召回源的记录
    assert merged.attributes["enriched_by"] == "pdl"
    # 证据按 URL 去重。
    assert len(merged.evidence) == 1
    # base 的 summary 本来就没缺，missing 不含 summary；本次也没补它。
    assert merged.missing_fields == frozenset({"contacts", "official_contact"})


def test_merge_enrichment_shrinks_missing_fields():
    from app.providers.contracts import Evidence

    base = CompanyRecord(
        external_id="mock-2",
        name="摘要缺失的企业",
        domain="ghost.cn",
        evidence=(Evidence(title="e", url="https://ghost.cn", snippet=""),),
        missing_fields=frozenset({"summary", "contacts", "official_contact"}),
        source_id="mock",
    )
    enriched = CompanyRecord(
        external_id="pdl-2",
        name="Ghost",
        domain="ghost.cn",
        summary="PDL 补到的摘要",
        missing_fields=frozenset(),
        source_id="pdl",
    )

    merged = merge_enrichment(base, enriched)

    assert merged.summary == "PDL 补到的摘要"
    assert merged.missing_fields == frozenset({"contacts", "official_contact"})


def test_merge_enrichment_without_enriched_returns_base():
    base = CompanyRecord(external_id="m", name="n", domain="d.cn")
    assert merge_enrichment(base, None) is base


def test_enrich_companies_degrades_to_noop_without_sources(monkeypatch):
    import app.providers.enrichment as enrichment

    monkeypatch.setattr(enrichment, "sources_for", lambda capability: [])
    base = CompanyRecord(external_id="m", name="n", domain="d.cn")

    assert enrich_companies([base]) == [base]
