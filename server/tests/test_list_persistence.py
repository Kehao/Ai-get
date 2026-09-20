"""P7 第二步：挖掘列表持久化的测试。

通过两遍实例化仓库（≈ 模拟进程重启）验证「创建 → 重启 → 可回看」的完整语义。
LLM 与真实补齐全部 monkeypatch 断开：测试只关心持久化，不依赖网络。
"""

from __future__ import annotations

import pytest

from app.providers.contracts import CompanyRecord, Evidence
from app.qualification.criteria import CriteriaBuild
from app.repositories import targets as targets_mod
from app.repositories.targets import TargetListRepository
from app.serialize import dumps, loads


# ── serialize：dataclass 编解码保真 ───────────────────────────────────────


def test_serialize_judgment_roundtrip():
    from app.qualification.criteria import Criterion
    from app.qualification.scoring import CriterionVerdict, Judgment

    criterion = Criterion(
        id="c1", name="地域", question="是否在杭州？", category="geo", weight=80,
        tokens=("杭州",), expected="杭州", rationale="画像明确要求", lenient=False,
    )
    verdict = CriterionVerdict(
        criterion=criterion,
        verdict="符合",
        explanation="总部在杭州。",
        reference_count=1,
        source_label="官网",
        source_url="https://acme.cn",
        references=(("官网", "https://acme.cn"), ("百科", "https://baike.example/acme")),
    )
    judgment = Judgment(verdicts=(verdict,), score=80, ratio=1.0, match_level="明确符合", reason="全部命中。")

    restored = loads(dumps(judgment), Judgment)

    assert restored == judgment  # 嵌套 tuple[tuple[str, str]] 与 Criterion 全部保真


def test_serialize_company_record_roundtrip():
    record = CompanyRecord(
        external_id="tavily-acme.cn",
        name="Acme",
        domain="acme.cn",
        industries=("云安全",),
        summary="企业云安全服务商。",
        evidence=(Evidence(title="t", url="https://acme.cn", snippet="s"),),
        missing_fields=frozenset({"contacts"}),
        source_id="tavily",
        attributes={"source": "web_search"},
    )

    assert loads(dumps(record), CompanyRecord) == record


# ── 列表持久化：创建 → 模拟重启 → 可回看 ─────────────────────────────────


@pytest.fixture
def repo_factory(monkeypatch):
    """断开 LLM 与真实补齐，并每次返回一个新仓库实例（≈ 重启后的进程）。"""
    fake_build = CriteriaBuild(criteria=(), source="rule", label="规则引擎")

    class _FakeLlm:
        @staticmethod
        def settings():
            raise AssertionError("测试不应触达 LLM")

    monkeypatch.setattr(targets_mod, "build_criteria_detailed", lambda *a, **k: fake_build)
    monkeypatch.setattr(targets_mod, "build_person_criteria_detailed", lambda *a, **k: fake_build)
    monkeypatch.setattr(targets_mod, "enrich_companies", lambda records: records)
    return TargetListRepository


def test_company_list_survives_restart(repo_factory):
    repo = repo_factory()
    created = repo.create_list("找华东的 SaaS 公司", "company", 5)

    hydrated = repo_factory()  # 新实例 ≈ 重启后的进程

    loaded = hydrated.get_list(created.id)
    assert loaded is not None
    assert loaded.query == created.query
    assert loaded.mode == "company"
    # running 列表在水合时按完成处理（见 list_store docstring）。
    assert loaded.status == "completed"
    page = hydrated.page_companies(created.id, page=1, page_size=10)
    assert page.total > 0
    first = page.items[0]
    # 行与判定都完整还原：详情页依赖的字段不能是空壳。
    assert first.match_reason != "" or first.score == 0
    detail = hydrated.company_detail(created.id, first.id)
    assert detail is not None


def test_people_list_survives_restart(repo_factory):
    repo = repo_factory()
    created = repo.create_list("找新能源行业的高管", "people", 3)

    hydrated = repo_factory()

    loaded = hydrated.get_list(created.id)
    assert loaded is not None
    assert loaded.mode == "people"
    page = hydrated.page_people(created.id, page=1, page_size=10)
    assert page.total > 0


def test_delete_list_persists(repo_factory):
    repo = repo_factory()
    created = repo.create_list("找医疗信息化公司", "company", 3)
    assert repo.delete_list(created.id) is True

    hydrated = repo_factory()

    assert hydrated.get_list(created.id) is None


# ── 富化台账：详情页 company_detail 下发 enrich 痕迹 ──────────────────────


def _complete_like_hydrate(repo: TargetListRepository, list_id: str) -> None:
    """create_list 之后行还没「验证」，页面上看不到；按水合语义直接置完成。"""
    state = repo._states[list_id]
    targets_mod._apply_progress(state, stage="completed", verified=len(state.rows), completed=True)


def test_company_detail_carries_enrichment_ledger(repo_factory, monkeypatch):
    """attributes 带 enriched_by 的记录，详情接口要给出可读台账；没富化过就是空台账。"""

    def _fake_enrich(records):
        if records:
            records[0].attributes.update(
                {
                    "enriched_by": "baidu",
                    "registered_capital": "1000万人民币",
                    "matched_title": "邢台云杉网络科技",  # 同名风险样本
                    "tavily_score": "0.9",  # 内部键，不上屏
                }
            )
        return records

    monkeypatch.setattr(targets_mod, "enrich_companies", _fake_enrich)
    repo = repo_factory()
    created = repo.create_list("找华东的 SaaS 公司", "company", 5)
    _complete_like_hydrate(repo, created.id)
    page = repo.page_companies(created.id, page=1, page_size=10)

    detail = repo.company_detail(created.id, page.items[0].id)

    assert detail is not None
    ledger = detail.enrichment
    assert ledger.source_id == "baidu"
    assert ledger.fields["registered_capital"] == "1000万人民币"
    assert ledger.fields["matched_title"] == "邢台云杉网络科技"
    assert "tavily_score" not in ledger.fields


def test_company_detail_empty_ledger_without_enrichment(repo_factory):
    repo = repo_factory()
    created = repo.create_list("找华东的 SaaS 公司", "company", 5)
    _complete_like_hydrate(repo, created.id)
    page = repo.page_companies(created.id, page=1, page_size=10)

    detail = repo.company_detail(created.id, page.items[0].id)

    assert detail is not None
    assert detail.enrichment.source_id == ""
    assert detail.enrichment.fields == {}
