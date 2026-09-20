"""会社召回提示从标准派生（`company_hints`）的测试，不产生任何网络请求。

这次针对的是一个**文档与实现不一致**的缺陷：`_recall` 的文档写着「召回提示
从已冻结的标准里派生，而不是重新解析一遍画像」，但公司分支实际一直在重解析
画像（`detect_city(query)` / `industry_hints(query)`）。后果是用户手动补充的
地域条件传不到数据源——召回按画像捞、判定按标准筛，整批系统性落空。
"""

from __future__ import annotations

from app.qualification import Criterion, company_hints
from app.providers.contracts import SourceManifest


def _criterion(
    category: str,
    *,
    tokens: tuple[str, ...] = (),
    expected: str = "",
    weight: int = 3,
) -> Criterion:
    return Criterion(
        id=f"criterion-{category}",
        name=category,
        question="该企业是否符合？",
        category=category,
        weight=weight,
        tokens=tokens,
        expected=expected,
    )


# ── 派生规则 ──────────────────────────────────────────────────────────────


def test_hints_take_city_and_industry_from_frozen_criteria():
    criteria = [
        _criterion("geo", tokens=("上海",), expected="上海"),
        _criterion("industry", tokens=("SaaS", "企业服务", "软件")),
        _criterion("business", tokens=("订阅制",)),
    ]

    hints = company_hints(criteria)

    assert hints.city == "上海"
    # business / signal 不参与召回：业务特征做子串检索只会捞回一堆资讯页。
    assert hints.industry_hints == ("SaaS", "企业服务", "软件")


def test_city_falls_back_to_first_token_when_expected_is_empty():
    assert company_hints([_criterion("geo", tokens=("深圳",))]).city == "深圳"


def test_no_geo_criterion_means_no_city_hint():
    """没有地域标准就是没有——不要回头去画像里猜一个。"""
    assert company_hints([_criterion("industry", tokens=("SaaS",))]).city is None


def test_industry_tokens_are_not_expanded_to_the_whole_family():
    """LLM 收敛出来的词必须原样保留。

    规则引擎产出的行业标准里 tokens 本来就是整个族（「企业服务与软件」共 17 词），
    LLM 产出的则是它自己收敛过的几个词。若在这里再扩回族，
    `_build_search_text` 只取前三个，最终拼进查询的会是**族的前三个词**，
    用户看到的标准写「云计算」、实际发出去的是「企业服务 SaaS saas」。
    """
    hints = company_hints([_criterion("industry", tokens=("云计算",))])

    assert hints.industry_hints == ("云计算",)


def test_industry_tokens_merge_in_order_and_dedupe():
    criteria = [
        _criterion("industry", tokens=("SaaS", "企业服务")),
        _criterion("industry", tokens=("企业服务", "软件")),
    ]

    assert company_hints(criteria).industry_hints == ("SaaS", "企业服务", "软件")


def test_empty_criteria_yields_empty_hints():
    hints = company_hints([])

    assert hints.city is None
    assert hints.industry_hints == ()


# ── 接线：`_recall` 的公司分支真的用了它 ───────────────────────────────────


class _RecordingSource:
    """记下收到的 CompanyQuery 就返回空结果，够用的最小假源。"""

    manifest = SourceManifest(id="fake", name="假源", capabilities=("company_search",))

    def __init__(self) -> None:
        self.queries: list[object] = []

    def search_companies(self, query: object) -> list[object]:
        self.queries.append(query)
        return []


def test_recall_company_branch_uses_criteria_derived_hints(monkeypatch):
    """画像里没有城市、标准里有——这正是用户补充条件后必须生效的那条路径。"""
    from app.repositories import targets

    source = _RecordingSource()
    monkeypatch.setattr(targets, "company_source", lambda: source)
    monkeypatch.setattr(targets, "enrich_companies", lambda records: records)

    criteria = [
        _criterion("geo", tokens=("上海",), expected="上海"),
        _criterion("industry", tokens=("SaaS", "企业服务")),
    ]
    # 画像文本里**故意不写城市**：旧实现按画像解析，这里必然丢掉"上海"。
    records, source_id = targets._recall(
        mode="company",
        query="找一些做 SaaS 的公司",
        limit=5,
        seed=7,
        criteria=criteria,
    )

    assert records == []
    assert source_id == "fake"

    query = source.queries[0]
    assert query.preferred_city == "上海"  # type: ignore[attr-defined]
    assert query.industry_hints == ("SaaS", "企业服务")  # type: ignore[attr-defined]


def test_recall_company_branch_survives_missing_criteria(monkeypatch):
    """`criteria` 缺省时不炸：提示退化成空，而不是回退到重解析画像。"""
    from app.repositories import targets

    source = _RecordingSource()
    monkeypatch.setattr(targets, "company_source", lambda: source)
    monkeypatch.setattr(targets, "enrich_companies", lambda records: records)

    targets._recall(mode="company", query="找一些做 SaaS 的公司", limit=5, seed=7)

    query = source.queries[0]
    assert query.preferred_city is None  # type: ignore[attr-defined]
    assert query.industry_hints == ()  # type: ignore[attr-defined]
