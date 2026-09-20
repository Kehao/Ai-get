"""百度 AI 搜索源的单元测试：全部用假 client，不产生任何网络请求。

覆盖四件事：
1. 两阶段召回策略（泛搜索拿企业官网 → 爱企查站点限定补量）与调用顺序；
2. 站点三分类的落地（官网保留域名、目录站留空域名、媒体站整条丢弃）；
3. 诚实边界——照面字段只进 `attributes` 并带 `matched_title`，不写核心字段；
4. 缓存语义：同一查询不重复计费。
"""

from __future__ import annotations

import pytest

from app.providers import cache as source_cache
from app.providers.baidu_source import BaiduSearchSource
from app.providers.contracts import CompanyQuery


@pytest.fixture(autouse=True)
def _clean_cache():
    source_cache.clear()
    yield
    source_cache.clear()


class FakeBaiduClient:
    """按 payload 里的站点过滤返回不同结果，并记录每次调用的 payload。"""

    def __init__(self, by_site: dict[str | None, list[dict]]) -> None:
        self.by_site = by_site
        self.payloads: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        site = payload.get("search_filter", {}).get("match", {}).get("site", [None])[0]
        return {"references": self.by_site.get(site, [])}

    @property
    def sites(self) -> list[str | None]:
        """按调用顺序列出每次请求的站点限定（None = 泛搜索）。"""
        return [
            payload.get("search_filter", {}).get("match", {}).get("site", [None])[0]
            for payload in self.payloads
        ]


def _source(client: FakeBaiduClient) -> BaiduSearchSource:
    # api_key 只在没有注入 client 时才会被用到，这里给个占位值即可。
    return BaiduSearchSource(api_key="test-key", client=client)


# ── 泛搜索：企业官网 ──────────────────────────────────────────────────────


def test_web_search_maps_to_company_records():
    client = FakeBaiduClient(
        {
            None: [
                {
                    "title": "云杉网络 - 企业云安全服务",
                    "url": "https://www.yunshan.net/about",
                    "content": "云杉网络是企业云安全服务商，提供微分段与容器安全。",
                },
                # 同一域名（去 www 后重复）：必须被去重掉。
                {
                    "title": "云杉网络",
                    "url": "https://yunshan.net/team",
                    "content": "团队介绍",
                },
                # 同一注册域的不同子域：也是同一家，不能占两行。
                {
                    "title": "云杉网络控制台",
                    "url": "https://console.yunshan.net/login",
                    "content": "控制台",
                },
                # 媒体门户：整条丢弃（讲的是关于企业的事，不是企业本身）。
                {
                    "title": "云安全行业报告",
                    "url": "https://www.36kr.com/p/123456",
                    "content": "行业观察",
                },
                # 取不出名称（纯营销标语）：丢弃。
                {
                    "title": "Shop SaaS Tools Online For Your Business Today",
                    "url": "https://unknown.example.net/",
                    "content": "marketing copy",
                },
            ]
        }
    )

    records = _source(client).search_companies(CompanyQuery(text="企业云安全服务", limit=5))

    assert [(r.name, r.domain) for r in records] == [("云杉网络", "yunshan.net")]
    assert records[0].source_id == "baidu"
    assert records[0].attributes["source"] == "web_search"
    assert records[0].evidence[0].url == "https://www.yunshan.net/about"


# ── 目录站：保留记录但域名留空 ────────────────────────────────────────────


def test_directory_page_keeps_record_without_domain():
    client = FakeBaiduClient(
        {
            None: [],  # 泛搜索什么都没命中 → 一定会进第二阶段
            "aiqicha.baidu.com": [
                {
                    "title": "杭州云杉网络科技有限公司 - 爱企查",
                    "url": "https://aiqicha.baidu.com/company_detail_123456",
                    "content": (
                        "杭州云杉网络科技有限公司，注册资本 1000万人民币，"
                        "法定代表人 张三，成立于 2015-06-01。"
                    ),
                }
            ],
        }
    )

    records = _source(client).search_companies(CompanyQuery(text="云杉网络", limit=5))

    assert len(records) == 1
    record = records[0]
    # 域名是爱企查的，不能当企业身份——留空后退化到按名称去重。
    assert record.domain == ""
    assert record.name == "杭州云杉网络科技有限公司"
    assert record.dedupe_key == "杭州云杉网络科技有限公司"
    # 照面字段只进 attributes，并标出命中的页面标题供人工核对同名实体。
    assert record.attributes["source"] == "aiqicha_web"
    assert record.attributes["registered_capital"] == "1000万人民币"
    assert record.attributes["legal_rep"] == "张三"
    assert record.attributes["founded"] == "2015-06-01"
    assert record.attributes["matched_title"] == "杭州云杉网络科技有限公司 - 爱企查"
    assert record.attributes["enriched_by"] == "baidu"


def test_plain_web_page_does_not_claim_registry_fields():
    """非目录站（企业官网）页面即使正文里出现「注册资本」也不抽——
    抽出来的是别人的数字，写进台账就是伪造。"""
    client = FakeBaiduClient(
        {
            None: [
                {
                    "title": "云杉网络",
                    "url": "https://yunshan.net/",
                    "content": "注册资本 1000万人民币的行业洞察。",
                }
            ]
        }
    )

    records = _source(client).search_companies(CompanyQuery(text="云杉网络", limit=1))

    assert records[0].attributes["source"] == "web_search"
    assert "registered_capital" not in records[0].attributes
    assert "enriched_by" not in records[0].attributes


# ── 两阶段调用策略 ────────────────────────────────────────────────────────


def test_second_stage_runs_only_when_short_of_target():
    enough = [
        {"title": f"企业{i}官网", "url": f"https://company{i}.cn/", "content": "简介"}
        for i in range(3)
    ]
    client = FakeBaiduClient({None: enough})

    records = _source(client).search_companies(CompanyQuery(text="随便", limit=3))

    assert len(records) == 3
    assert client.sites == [None]  # 数量够了就不再花钱


def test_second_stage_appends_and_dedupes():
    client = FakeBaiduClient(
        {
            None: [{"title": "云杉网络", "url": "https://yunshan.net/", "content": "简介"}],
            "aiqicha.baidu.com": [
                # 与泛搜索同一家（按名称命中）：合并时应被去重。
                {"title": "云杉网络", "url": "https://aiqicha.baidu.com/detail_1", "content": "目录页"},
                {"title": "青云科技 - 爱企查", "url": "https://aiqicha.baidu.com/detail_2", "content": "目录页"},
            ],
        }
    )

    records = _source(client).search_companies(CompanyQuery(text="云安全", limit=5))

    assert client.sites == [None, "aiqicha.baidu.com"]
    assert [(r.name, r.domain) for r in records] == [
        ("云杉网络", "yunshan.net"),
        ("青云科技", ""),
    ]


# ── 缓存 ──────────────────────────────────────────────────────────────────


def test_search_hits_cache_on_second_call():
    client = FakeBaiduClient(
        {None: [{"title": "云杉网络", "url": "https://yunshan.net/", "content": "简介"}]}
    )
    source = _source(client)
    query = CompanyQuery(text="云杉网络", limit=1)

    first = source.search_companies(query)
    calls_after_first = len(client.payloads)
    second = source.search_companies(query)

    assert len(client.payloads) == calls_after_first  # 第二次没有再发请求
    assert second == first
