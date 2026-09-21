"""把本项目的搜索、模型与抓取接进 agent 的三个协议。

agent 本体就在本包（`app/agents/`）里；这一层是**项目侧的耦合点**：
百度搜索、DeepSeek、网页抓取这些具体实现，只在这里被翻译成协议——
换搜索服务时改这里，agent 本体一行不动。

三个适配器都刻意写得极薄——它们的职责只是「翻译形状」，**不含任何业务判断**。
业务判断属于 agent 的提炼与深挖，或者属于本项目的判定层。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .agent import DiscoveryRun, deepen_entity, run_discovery_agent
from .extract import _MAX_DOCUMENTS as _DEFAULT_MAX_DOCUMENTS
from .extract import _MAX_ROUNDS as _DEFAULT_MAX_ROUNDS
from .extract import extract_entities
from .spec import DEFAULT_SPEC_NAME, DiscoverySpec, load_spec, read_spec

from ...llm.client import complete_json
from ...providers import company_source
from ...providers.web_fetch import fetch_page_icon, fetch_page_links, fetch_page_text


class BaiduWebSearch:
    """把项目的百度源包成 `WebSearch`。

    包要求**失败抛异常**、不能返回空列表假装没搜到——本源本来就按这个口径抛
    `SourceError`，所以这里不需要额外处理，让它透出去就行。
    """

    def __init__(self, source: Any = None) -> None:
        # 允许注入：测试塞假的源，生产走默认。
        self._source = source

    def search(
        self, query: str, *, top_k: int, site: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        source = self._source or company_source()
        search_pages = getattr(source, "search_pages", None)
        if search_pages is None:
            raise RuntimeError(f"当前数据源不支持网页检索，无法承担 agent 的检索职责")
        return list(search_pages(query, site=site, top_k=top_k))


class ProjectJsonLlm:
    """把项目的 LLM 客户端包成 `JsonLlm`。

    项目那层已经把开关、超时、错误分类都做好了，契约也一致（返回 dict、
    失败抛 `LlmError`），所以这里只做形状转换。
    """

    def complete_json(
        self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 4096
    ) -> Mapping[str, Any]:
        return complete_json(system, user, temperature=temperature, max_tokens=max_tokens).data


class ProjectPageFetcher:
    """把项目的网页抓取包成 `PageFetcher`（失败返回空串，契约本就一致）。

    额外提供两个可选扩展：`fetch_links`（深挖 v2 的子页探索靠它拿首页里的
    同域候选子页）与 `fetch_icon_url`（抓企业 logo）。不实现它们 agent 也能跑
    ——只是分别退回 v1、少了 logo 而已。
    """

    def fetch(self, url: str, *, max_chars: int) -> str:
        return fetch_page_text(url, max_chars=max_chars)

    def fetch_links(self, url: str, *, max_links: int = 60) -> list[str]:
        return fetch_page_links(url, max_links=max_links)

    def fetch_icon_url(self, url: str) -> str:
        return fetch_page_icon(url)


def load_project_spec(name: str = DEFAULT_SPEC_NAME) -> DiscoverySpec:
    """读本项目的 agent 配置（`app/agents/configs/<name>.json`）。

    直接委托 `load_spec`：配置已随 agent 收进 `configs/`，它的查找顺序
    （环境变量 → cwd/configs → 包内）会命中。
    """
    return load_spec(name)


def run_project_discovery(
    profile: str, *, spec_name: str = DEFAULT_SPEC_NAME
) -> DiscoveryRun:
    """用本项目的搜索、模型与抓取跑一次发现。**全量发现走这个入口。**"""
    return run_discovery_agent(
        profile,
        llm=ProjectJsonLlm(),
        search=BaiduWebSearch(),
        fetcher=ProjectPageFetcher(),
        spec=load_project_spec(spec_name),
    )


# 单点深挖的抓取页数。与全量发现共用同一份配置，只把规模压到「用户点一下按钮
# 愿意等」的量级——按全量的 6 页去抓，按钮后面的等待时间会翻倍。
_SINGLE_ENTITY_PAGES = 3


@dataclass(frozen=True, slots=True)
class EntityCandidates:
    """流程前两段的产出：候选清单 ＋ 它们依据的原始网页。

    `documents` 不是副产品——它是第③步深挖的第二份输入
    （第一份是公司名），两段之间就靠它衔接。
    """

    profile: str
    entities: tuple[dict, ...]
    documents: tuple[dict, ...]


def discover_project_entities(
    profile: str, *, spec_name: str = DEFAULT_SPEC_NAME
) -> EntityCandidates:
    """流程前两段：检索 ＋ 提炼，产出候选清单（名字／依据／初判），**不深挖**。

    快而便宜：1 次检索 + 1~3 次分批提炼调用。挑中哪家再走
    `deepen_project_entity` 逐家补全。
    """
    spec = load_project_spec(spec_name)
    documents = search_project_documents(profile, spec_name=spec_name)
    entities = extract_project_entities(profile, documents, spec_name=spec_name)
    return EntityCandidates(profile=profile, entities=entities, documents=documents)


def search_project_documents(
    profile: str, *, top_k: int = 0, spec_name: str = DEFAULT_SPEC_NAME
) -> tuple[dict, ...]:
    """只做第①段：检索一批网页（智能发现的分批提炼要拿它当共同材料）。

    `top_k` 传 0（或不传）＝用 agent 配置的默认检索量；前端「结果数量」
    折算后从这里进来。
    """
    spec = load_project_spec(spec_name)
    return tuple(
        BaiduWebSearch().search(
            spec.query or profile,
            top_k=top_k or spec.budget.search_top_k,
            site=spec.site or None,
        )
    )


def extract_project_entities(
    profile: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    on_batch: Any | None = None,
    max_documents: int = 0,
    max_rounds: int = 0,
    spec_name: str = DEFAULT_SPEC_NAME,
) -> tuple[dict, ...]:
    """只做第②段：分批提炼。`on_batch` 每批（5 家）回调一次，供调用方增量落库。

    `max_documents` / `max_rounds` 传 0＝用默认规模，非 0 时覆盖——
    前端「结果数量」放大检索与轮数就是这两个口子。
    """
    spec = load_project_spec(spec_name)
    return extract_entities(
        profile,
        documents,
        llm=ProjectJsonLlm(),
        spec=spec,
        on_batch=on_batch,
        max_documents=max_documents or _DEFAULT_MAX_DOCUMENTS,
        max_rounds=max_rounds or _DEFAULT_MAX_ROUNDS,
    )


def deepen_project_entity(
    profile: str,
    name: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    domain: str = "",
    spec_name: str = DEFAULT_SPEC_NAME,
) -> dict:
    """对**已知的**一家实体做单点深挖（详情页的「深挖」按钮走这条）。

    与 `run_project_discovery` 的区别只在规模：这里把 `max_entities` 钉成 1、
    抓取页数压到 `_SINGLE_ENTITY_PAGES`，其余（字段表、补缺轮数、检索词）完全一致。
    """
    spec = load_project_spec(spec_name)
    single = replace(
        spec, budget=replace(spec.budget, max_entities=1, max_pages=_SINGLE_ENTITY_PAGES)
    )
    return deepen_entity(
        profile,
        name,
        documents,
        llm=ProjectJsonLlm(),
        search=BaiduWebSearch(),
        fetcher=ProjectPageFetcher(),
        spec=single,
        domain=domain,
    )
