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


# ── Tavily：web 富化兜底（6-免1）──────────────────────────────────────────


def _web_enrich_source(results: list[dict], fail_with: Exception | None = None) -> TavilySource:
    return TavilySource(api_key="test", client=FakeTavilyClient(results, fail_with=fail_with))


def test_tavily_web_enrich_maps_relevant_result():
    results = [
        {  # 与目标无关的页面：必须被跳过。
            "title": "某行业分析报告",
            "url": "https://report.example.com/2026",
            "content": "行业趋势概览。",
        },
        {
            "title": "云杉网络 - 关于我们",
            "url": "https://www.yunshan.net/about",
            "content": "云杉网络是企业云安全服务商，提供微分段与容器安全。",
        },
    ]
    source = _web_enrich_source(results)

    records = source.enrich_companies(
        CompanyEnrichQuery(
            targets=(
                EnrichTarget(
                    domain="yunshan.net",
                    name="云杉网络",
                    missing=frozenset({"summary", "contacts"}),
                ),
            )
        )
    )

    assert len(records) == 1
    record = records[0]
    assert record.summary.startswith("云杉网络是企业云安全服务商")
    assert record.evidence[0].url == "https://www.yunshan.net/about"
    assert record.source_id == "tavily"
    # 网页摘要不是权威工商数据：来源要如实标注，不冒充。
    assert record.attributes["source"] == "web_search"


def test_tavily_web_enrich_skips_targets_that_have_summary():
    source = _web_enrich_source([])

    records = source.enrich_companies(
        CompanyEnrichQuery(
            targets=(EnrichTarget(domain="acme.cn", name="某公司", missing=frozenset({"contacts"})),)
        )
    )

    assert records == []
    assert source._client.calls == 0  # 帮不上忙的目标：一次 credit 都不花


def test_tavily_web_enrich_is_cached():
    results = [
        {"title": "云杉网络", "url": "https://yunshan.net", "content": "云杉网络的介绍。"}
    ]
    source = _web_enrich_source(results)
    query = CompanyEnrichQuery(
        targets=(EnrichTarget(domain="yunshan.net", name="云杉网络", missing=frozenset({"summary"})),)
    )

    source.enrich_companies(query)
    source.enrich_companies(query)

    assert source._client.calls == 1


def test_tavily_web_enrich_no_relevant_result_is_cached_as_empty():
    source = _web_enrich_source(
        [{"title": "无关页面", "url": "https://other.org/x", "content": "别家的内容。"}]
    )
    query = CompanyEnrichQuery(
        targets=(EnrichTarget(domain="ghost.cn", name="幽灵公司", missing=frozenset({"summary"})),)
    )

    assert source.enrich_companies(query) == []
    # 第二次：命中空哨兵，不再打 API。
    assert source.enrich_companies(query) == []
    assert source._client.calls == 1


def test_tavily_web_enrich_all_failures_raise():
    source = _web_enrich_source([], fail_with=Exception("503 Service Unavailable"))
    query = CompanyEnrichQuery(
        targets=(EnrichTarget(domain="acme.cn", name="某公司", missing=frozenset({"summary"})),)
    )

    with pytest.raises(SourceError):
        source.enrich_companies(query)


def test_enrich_orchestration_passes_missing_hints():
    """编排层要把「缺什么」传给补齐源——web 富化靠它决定要不要花 credit。"""
    from app.providers import enrichment
    from app.providers.contracts import CompanyEnrichQuery as Query
    from app.providers.contracts import SourceManifest
    from app.providers.registry import register_source, unregister_source

    captured: list[Query] = []

    class FakeEnrichSource:
        manifest = SourceManifest(
            id="fake-enrich",
            name="假补齐源",
            capabilities=("company_enrich",),
            description="",
            regions=("GLOBAL",),
            priority=99,
            cost_per_call=0.0,
            requires_credentials=False,
        )

        def enrich_companies(self, query: Query) -> list[CompanyRecord]:
            captured.append(query)
            return []

    register_source(FakeEnrichSource())
    try:
        base = CompanyRecord(
            external_id="m",
            name="n",
            domain="d.cn",
            missing_fields=frozenset({"contacts", "official_contact"}),
        )
        enrichment.enrich_companies([base])
    finally:
        unregister_source("fake-enrich")

    assert len(captured) == 1
    target = captured[0].targets[0]
    # base 的 missing_fields 原样传递；summary 为空时编排层补标「缺摘要」。
    assert target.missing == frozenset({"contacts", "official_contact", "summary"})


# ── 百度 AI 搜索：web 富化（6-免1b）───────────────────────────────────────


def test_baidu_web_enrich_aiqicha_extracts_registry_fields():
    """爱企查命中：照面字段进 attributes（不冒充核心字段），并记录命中页标题。"""
    from app.providers.baidu_source import BaiduSearchSource

    def fake_client(payload: dict) -> dict:
        assert payload["search_filter"]["match"]["site"] == ["aiqicha.baidu.com"]
        return {
            "references": [
                {
                    "title": "邢台云杉网络科技有限公司怎么样 - 爱企查",
                    "url": "https://aiqicha.baidu.com/company_comment_11588980866776",
                    "content": (
                        "邢台云杉网络科技有限公司是一家小微企业,该公司成立于2019年04月09日,"
                        "注册资本为5000万人民币,法定代表人为王超杰,目前处于开业状态。"
                    ),
                }
            ]
        }

    source = BaiduSearchSource(api_key="test", client=fake_client)
    records = source.enrich_companies(
        CompanyEnrichQuery(
            targets=(EnrichTarget(name="云杉网络", missing=frozenset({"summary"})),)
        )
    )

    assert len(records) == 1
    record = records[0]
    assert record.summary.startswith("邢台云杉网络科技有限公司")
    assert record.source_id == "baidu"
    assert record.attributes["source"] == "aiqicha_web"
    # 照面字段只在 attributes：诚实标注「这是网页抽的，还带命中页标题供人工核对」。
    assert record.attributes["registered_capital"] == "5000万人民币"
    assert record.attributes["legal_rep"] == "王超杰"
    assert record.attributes["founded"] == "2019年04月09日"
    assert "爱企查" in record.attributes["matched_title"]


def test_baidu_web_enrich_falls_back_to_web_search():
    """爱企查未命中 → 泛搜索兜底，只补摘要、不抽照面字段。"""
    from app.providers.baidu_source import BaiduSearchSource

    def fake_client(payload: dict) -> dict:
        if "search_filter" in payload:
            return {"references": []}  # 阶段一：爱企查没有
        return {
            "references": [
                {
                    "title": "云杉网络 - 官网",
                    "url": "https://www.yunshan.net/about",
                    "content": "云杉网络是企业云安全服务商。",
                }
            ]
        }

    source = BaiduSearchSource(api_key="test", client=fake_client)
    records = source.enrich_companies(
        CompanyEnrichQuery(
            targets=(EnrichTarget(domain="yunshan.net", name="云杉网络", missing=frozenset({"summary"})),)
        )
    )

    assert len(records) == 1
    assert records[0].attributes["source"] == "web_search"
    assert "registered_capital" not in records[0].attributes


def test_baidu_web_enrich_skips_targets_that_have_summary():
    from app.providers.baidu_source import BaiduSearchSource

    calls: list[dict] = []

    def fake_client(payload: dict) -> dict:
        calls.append(payload)
        return {"references": []}

    source = BaiduSearchSource(api_key="test", client=fake_client)
    records = source.enrich_companies(
        CompanyEnrichQuery(
            targets=(EnrichTarget(name="某公司", missing=frozenset({"contacts"})),)
        )
    )

    assert records == []
    assert calls == []  # 帮不上忙的目标：一次调用都不发


def test_baidu_web_enrich_is_cached():
    from app.providers.baidu_source import BaiduSearchSource

    calls: list[dict] = []

    def fake_client(payload: dict) -> dict:
        calls.append(payload)
        return {
            "references": [
                {"title": "云杉网络", "url": "https://aiqicha.baidu.com/x", "content": "介绍。"}
            ]
        }

    source = BaiduSearchSource(api_key="test", client=fake_client)
    query = CompanyEnrichQuery(
        targets=(EnrichTarget(name="云杉网络", missing=frozenset({"summary"})),)
    )

    source.enrich_companies(query)
    source.enrich_companies(query)

    assert len(calls) == 1


def test_baidu_web_enrich_all_failures_raise():
    from app.providers.baidu_source import BaiduSearchSource

    def fake_client(payload: dict) -> dict:
        raise RuntimeError("boom")

    source = BaiduSearchSource(api_key="test", client=fake_client)
    query = CompanyEnrichQuery(
        targets=(EnrichTarget(name="某公司", missing=frozenset({"summary"})),)
    )

    with pytest.raises(SourceError) as caught:
        source.enrich_companies(query)

    assert caught.value.source_id == "baidu"


def test_baidu_enrich_priority_between_pdl_and_tavily():
    """瀑布顺序：权威源(PDL) > 爱企查站点限定(百度) > 泛搜索(Tavily)。"""
    from app.providers.baidu_source import BaiduSearchSource
    from app.providers.pdl_source import PdlSource
    from app.providers.tavily_source import TavilySource

    assert PdlSource.manifest.priority < BaiduSearchSource.manifest.priority
    assert BaiduSearchSource.manifest.priority < TavilySource.manifest.priority
