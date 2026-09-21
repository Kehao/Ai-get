"""实体发现 agent：一句画像 → 一批补全后的档案。

| 阶段 | 动作 | 次数 |
| --- | --- | --- |
| ① 检索 | 用注入的 `WebSearch` 拿一批网页 | 1 |
| ② 提炼 | 让模型认出实体、初判是否符合画像 | 1 |
| ③ 深挖 | 每个实体最多三级（见 `deep_dive`） | 由预算决定 |

## 为什么叫 agent

段与段之间的取舍（提炼出几个、哪个值得花三级深挖的钱、缺哪个字段才值得再搜一次）
全部由内部按 `missing` 与预算决定，调用方只给画像和配置，**不需要知道中间该调什么**。
每一步都落进 `steps`——「它干了什么」要能被展示，而不是只能从结果倒推。

## 预算有界

一次 run 的外部调用量可以算出来：`1 次检索 + 1 次模型调用`，加上
`max_entities × (抓取 + 检索 + 整理)`。所有上限都在 `spec.budget` 里，
**没有「跑着跑着自己决定多跑几步」的余地**——这条性质比「更自主」值钱。

## 失败语义

- **检索失败**：不抛，记进 `steps`（`ok=False`）并返回空结果。顶层入口返回结构化结果，
  比抛异常更便于调用方展示「哪一步没成」。
- **提炼失败**：抛。那是「模型不可用」的事实，伪装成「没有实体」会让调用方做错决策。
- **深挖失败**：静默降级成字段少几个，见 `deep_dive`。
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from typing import Any

from .deep_dive import deepen_entity
from .extract import extract_entities
from ..common.protocols import JsonLlm, PageFetcher, WebSearch
from .spec import DiscoverySpec, load_spec

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentStep:
    """agent 的一步。`target` 为空表示这一步作用在整批上、不针对某个实体。"""

    action: str
    target: str
    detail: str
    ok: bool = True


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    """一次 run 的产物：档案 + 全过程 + 规模统计。"""

    spec_name: str
    entity: str
    profile: str
    dossiers: tuple[dict, ...]
    steps: tuple[AgentStep, ...]
    web_results: int
    shortlisted: int

    @property
    def matched(self) -> tuple[dict, ...]:
        """初判符合画像的那些档案。"""
        return tuple(item for item in self.dossiers if item.get("matched"))

    def to_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的结构（CLI 与接口都用它）。"""
        return {
            "spec": self.spec_name,
            "entity": self.entity,
            "profile": self.profile,
            "web_results": self.web_results,
            "shortlisted": self.shortlisted,
            "matched_count": len(self.matched),
            "steps": [dataclasses.asdict(step) for step in self.steps],
            "dossiers": [dict(item) for item in self.dossiers],
        }


def discover_entities(
    profile: str,
    documents: Sequence[Mapping[str, Any]] | None = None,
    *,
    llm: JsonLlm,
    search: WebSearch,
    spec: DiscoverySpec | None = None,
    on_batch: Any | None = None,
) -> tuple[dict, ...]:
    """流程的前两段：检索一批网页，让模型认出其中的实体（**分批多轮**）。

    与 `run_discovery_agent` 的区别：**到这里就停**——产出的是候选清单
    （名字、依据、初判），不带深挖档案。适合「先便宜地看一眼都有谁，
    再挑值得的逐家深挖」的两段式用法。

    `on_batch` 在每轮提炼结束时收到该批实体（最多 5 家/批）——调用方可以
    先把这批落库上屏，再等下一轮，不必等全部提炼完。

    `deepen_entity` 是它的下半场，参数正是这里的产出：实体名（可以是
    大概的名字，定位官网与同名确认都在那一步）＋ 这批原始网页。

    `documents` 省略时自己检索；调用方如果已经检索过（比如要把同一批网页
    传给下游的深挖），传进来即可——**不会重复花一次检索的钱**。
    """
    asset = spec or load_spec()
    profile = profile.strip()
    if not profile:
        return ()
    documents = (
        tuple(documents)
        if documents
        else tuple(search_web(asset.query or profile, asset.budget.search_top_k))
    )
    if not documents:
        return ()
    return extract_entities(profile, documents, llm=llm, spec=asset, on_batch=on_batch)


def run_discovery_agent(
    profile: str,
    *,
    llm: JsonLlm,
    search: WebSearch,
    fetcher: PageFetcher,
    spec: DiscoverySpec | None = None,
) -> DiscoveryRun:
    """跑一次实体发现。

    三个依赖都由调用方注入——本包不认识任何具体的搜索服务或模型供应商。
    `spec` 省略时用 `configs/` 里的默认配置。画像为空时**一次外部调用都不发**。
    """
    asset = spec or load_spec()
    profile = profile.strip()
    steps: list[AgentStep] = []
    if not profile:
        return DiscoveryRun(asset.name, asset.entity, "", (), (), 0, 0)

    query = asset.query or profile
    try:
        documents = tuple(
            search.search(query, top_k=asset.budget.search_top_k, site=asset.site or None)
        )
    except Exception as error:  # noqa: BLE001 — 顶层入口返回结构化结果而不是抛
        logger.warning("检索失败：%s", error, exc_info=True)
        steps.append(AgentStep("search", "", f"检索失败：{error}", ok=False))
        return DiscoveryRun(asset.name, asset.entity, profile, (), tuple(steps), 0, 0)

    steps.append(
        AgentStep(
            "search",
            "",
            f"检索「{query}」，拿到 {len(documents)} 条网页",
            ok=bool(documents),
        )
    )
    if not documents:
        return DiscoveryRun(asset.name, asset.entity, profile, (), tuple(steps), 0, 0)

    entities = extract_entities(profile, documents, llm=llm, spec=asset)
    steps.append(
        AgentStep(
            "extract",
            "",
            f"认出 {len(entities)} 个{asset.entity}，"
            f"初判符合画像 {sum(1 for item in entities if item['matched'])} 个",
        )
    )

    dossiers: list[dict] = []
    for brief in entities[: asset.budget.max_entities]:
        name = str(brief.get("name", ""))
        before = _filled(brief, asset)
        dossier = deepen_entity(
            profile,
            name,
            documents,
            llm=llm,
            search=search,
            fetcher=fetcher,
            spec=asset,
            domain=str(brief.get("domain", "")),
        )
        steps.append(
            AgentStep(
                "deepen",
                name,
                _deepen_detail(before, _filled(dossier, asset), dossier, asset),
                ok=bool(dossier.get("matched")),
            )
        )
        dossiers.append(dossier)

    return DiscoveryRun(
        spec_name=asset.name,
        entity=asset.entity,
        profile=profile,
        dossiers=tuple(dossiers),
        steps=tuple(steps),
        web_results=len(documents),
        shortlisted=len(entities),
    )


def _filled(dossier: dict, spec: DiscoverySpec) -> int:
    """已填上的字段数。列表类字段按「非空即算填上」处理。"""
    count = 0
    for name in spec.field_names:
        value = dossier.get(name)
        if isinstance(value, (list, tuple)):
            count += 1 if value else 0
        else:
            count += 1 if str(value or "").strip() else 0
    return count


def _deepen_detail(before: int, after: int, dossier: dict, spec: DiscoverySpec) -> str:
    """深挖这步做了什么：补了几个字段、还剩什么没补到。"""
    detail = f"补全 {after - before} 个字段（{before} → {after}/{len(spec.field_names)}）"
    missing = [str(item) for item in dossier.get("missing") or []]
    if missing:
        detail += f"，仍缺 {'、'.join(missing)}"
    return detail


if __name__ == "__main__":
    # 自检：不联网、不调模型（`python -m discovery_agent.agent`）。
    from .spec import FieldSpec

    spec = DiscoverySpec(
        name="test",
        entity="公司",
        fields=(FieldSpec("domain", "官网", required=True), FieldSpec("tags", "标签", kind="list")),
    )
    assert _filled({}, spec) == 0
    assert _filled({"domain": "a.com", "tags": ("x",)}, spec) == 2
    assert _filled({"domain": "  ", "tags": ()}, spec) == 0, "空白与空列表都不算填上"

    described = _deepen_detail(0, 1, {"missing": ["domain"]}, spec)
    assert "1 个字段" in described and "domain" in described, described
    assert _deepen_detail(1, 1, {"missing": []}, spec) == f"补全 0 个字段（1 → 1/2）"

    # 传 spec 而不走默认配置：这个断言要检查的是 spec_name 有没有被带出来
    empty = run_discovery_agent(  # type: ignore[arg-type]
        "   ", llm=None, search=None, fetcher=None, spec=spec
    )
    assert empty.dossiers == () and empty.steps == (), "空画像不该发任何调用"
    payload = empty.to_dict()
    assert payload["spec"] == "test" and payload["steps"] == [] and payload["matched_count"] == 0

    print("agent 自检通过")
