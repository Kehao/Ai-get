"""Tavily 真实召回源（P4）：公开网页检索 → 企业候选。

Tavily 是 Agent 原生检索服务（免费层每月 1000 credits），在这里承担**召回**职责：
把画像文本 + 行业提示发给它，把返回的网页结果映射成 `CompanyRecord` 候选。
它不知道判定标准是什么——相关性的进一步筛选是判定层（L3）的事。

## 映射规则

网页结果 → `CompanyRecord` 的折算规则（域名提取、标题取名、站点过滤）在两个网页
检索源之间共用，见 `web_mapping`。这里只保留 Tavily 自己的检索策略：查什么、
查几次、怎么计价。

- **域名**是去重键与后续补齐（PDL enrich）的主键；不带合法域名、或命中媒体/UGC
  清单的结果直接丢弃——没有域名的「公司」既无法去重也无法触达，假公司比少一条
  候选更有害。
- **摘要**用 Tavily 返回的 content；拿不到就如实上报 `missing_fields`，
  绝不用空字符串冒充摘要。
- **行业**只把画像提示里**真实出现在标题或正文**的词记进来，不做推断——
  行业字段会被判定层的行业标准逐条匹配，写多了会造成「弱命中给满分」的虚高。

## web 富化（company_enrich 兜底）

权威补齐源（PDL 等）优先；Tavily 只对**缺摘要**的目标（`EnrichTarget.missing` 提示）
做一次针对性检索，从相关页面的正文补 `summary` 与证据。照面字段（注册资本、法定代表人）
从网页摘要里抽不可靠，**不做**——抽得到也不写，宁缺毋假。

## 失败语义

凭据缺失/配额耗尽等全部收敛为带 `kind` 的 `SourceError`，由注册表记入
`meta["failures"]`；mock 源仍在瀑布里兜底，所以召回永远不会因为 Tavily 挂掉而中断。

## 开关

`AIGET_TAVILY_ENABLED=false` 时不注册（密钥保留），用于暂时停用换别的源。
"""

from __future__ import annotations

from typing import Any

from tavily import TavilyClient

from .. import config
from .cache import get as cache_get
from .cache import set as cache_set
from .contracts import (
    CompanyEnrichQuery,
    CompanyQuery,
    CompanyRecord,
    EnrichTarget,
    Evidence,
    SourceError,
    SourceManifest,
)
from .registry import register_source
from .web_mapping import (
    extract_domain,
    is_non_company_domain,
    name_from_domain,
    name_from_title,
    registrable_domain,
)

# Tavily 单次检索的候选上限。免费层的 basic depth 一次最多返回 20 条，
# 一次挖掘的目标量（默认 25）本就不指望网页检索一次凑齐——数量由 mock 兜底。
_MAX_RESULTS_PER_SEARCH = 20

# web 富化每家企业的检索条数：只找一条相关摘要，多了是浪费。
_ENRICH_MAX_RESULTS = 5
_MANIFEST = SourceManifest(
    id="tavily",
    name="Tavily 网页召回",
    capabilities=("company_search", "company_enrich"),
    description="公开网页检索：召回真实企业线索；对缺摘要的企业做 web 富化。",
    regions=("GLOBAL",),
    # 权威补齐源（PDL，priority=20）先用，web 富化只做兜底——同样是 enrich 能力，
    # 按次计费的网页检索永远排在 profile 库之后。
    priority=40,
    cost_per_call=0.008,
    requires_credentials=True,
)


class TavilySource:
    """基于 Tavily 官方 SDK（tavily-python）的公司召回源。"""

    manifest = _MANIFEST

    def __init__(self, api_key: str | None = None, client: Any = None) -> None:
        self.api_key = api_key if api_key is not None else config.TAVILY_API_KEY
        # client 允许注入：测试用它塞入假实现，生产路径一律现建。
        self._client = client

    @staticmethod
    def is_configured() -> bool:
        return bool(config.TAVILY_API_KEY)

    @staticmethod
    def is_enabled() -> bool:
        """显式开关（`AIGET_TAVILY_ENABLED`）。关掉时即便 key 就在 .env 里也不注册——
        用于「暂时停用换别的源试试」，不必删除密钥。"""
        return bool(config.TAVILY_ENABLED)

    def _tavily(self) -> TavilyClient:
        if self._client is None:
            if not self.api_key:
                raise SourceError(
                    "Tavily 未配置 API key（AIGET_TAVILY_API_KEY）",
                    kind="missing_credentials",
                    source_id=_MANIFEST.id,
                )
            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    # ── company_search ──────────────────────────────────────────────────

    def search_companies(self, query: CompanyQuery) -> list[CompanyRecord]:
        search_text = _build_search_text(query)
        cache_key = f"tavily:search:{search_text}:{query.limit}"
        cached = cache_get(cache_key)
        if isinstance(cached, list):
            return cached

        response = self._search(search_text, query)
        records = _to_company_records(response, query)

        cache_set(cache_key, records)
        return records

    def _search(self, search_text: str, query: CompanyQuery) -> dict[str, Any]:
        try:
            return self._tavily().search(
                query=search_text,
                max_results=min(max(query.limit, 5), _MAX_RESULTS_PER_SEARCH),
                search_depth="basic",
            )
        except SourceError:
            raise
        except Exception as error:  # noqa: BLE001 — SDK 的异常类型不稳定，按状态码文案分类
            raise _classify(error, str(error)) from error

    # ── company_enrich（web 富化兜底）────────────────────────────────────

    def enrich_companies(self, query: CompanyEnrichQuery) -> list[CompanyRecord]:
        """对缺摘要的企业做针对性网页检索。逐目标容错：单家失败不拖垮整批，
        但全部失败时抛出第一个错误——源故障不能被伪装成「都查不到」。"""
        records: list[CompanyRecord] = []
        first_error: SourceError | None = None

        for target in query.targets:
            if "summary" not in target.missing:
                continue  # 已有摘要：网页富化帮不上别的忙，一次 credit 都不花
            try:
                record = self._web_enrich_one(target)
            except SourceError as error:
                first_error = first_error or error
                continue
            if record is not None:
                records.append(record)

        if not records and first_error is not None:
            raise first_error
        return records

    def _web_enrich_one(self, target: EnrichTarget) -> CompanyRecord | None:
        """检索单家企业。查不到相关页面不是错误——返回 None，编排层原样保留召回记录。"""
        cache_key = f"tavily:webenrich:{target.cache_key}"
        cached = cache_get(cache_key)
        # 空串是「检索过但没有相关页面」的哨兵：不再为同一家企业重复花钱。
        if cached == "":
            return None
        if cached is not None:
            return cached  # type: ignore[return-value]

        response = self._search(
            _build_enrich_text(target),
            CompanyQuery(text="", limit=_ENRICH_MAX_RESULTS),
        )
        record = _enrich_record_from_results(response, target)
        cache_set(cache_key, record if record is not None else "")
        return record


def _build_search_text(query: CompanyQuery) -> str:
    """画像文本为主，行业提示只取前三个拼在后面——提示是相关性信号，不是查询本身。"""
    hints = " ".join(query.industry_hints[:3])
    return f"{query.text} {hints}".strip()


def _build_enrich_text(target: EnrichTarget) -> str:
    """富化查询：名称最精确（中文尤其如此），缺失时退化到域名。"""
    subject = target.name.strip() or target.domain.strip()
    return f"{subject} 企业简介"


def _is_relevant_result(item: dict[str, Any], target: EnrichTarget) -> bool:
    """结果必须指向目标企业本人：名称出现在标题/正文，或域名主体出现在 URL。
    否则那条摘要属于别的公司，合并进召回记录就是张冠李戴。"""
    title = str(item.get("title", ""))
    content = str(item.get("content", ""))
    url = str(item.get("url", "")).lower()
    name = target.name.strip()
    domain_root = target.domain.strip().lower().split(".", 1)[0]
    if name and (name in title or name in content):
        return True
    return bool(domain_root) and len(domain_root) > 2 and domain_root in url


def _enrich_record_from_results(
    response: dict[str, Any],
    target: EnrichTarget,
) -> CompanyRecord | None:
    """取第一条相关结果映射成补齐记录；没有相关结果时返回 None。"""
    for item in response.get("results") or []:
        if not _is_relevant_result(item, target):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", ""))
        return CompanyRecord(
            external_id=f"tavily-web-{target.cache_key}",
            name=target.name or target.domain,
            domain=target.domain,
            summary=content,
            contact_count=0,
            evidence=(Evidence(title=title or target.name, url=url, snippet=content[:200]),),
            missing_fields=frozenset({"contacts", "official_contact"}),
            source_id=_MANIFEST.id,
            attributes={"source": "web_search"},
        )
    return None


def _to_company_records(response: dict[str, Any], query: CompanyQuery) -> list[CompanyRecord]:
    results = response.get("results") or []
    records: list[CompanyRecord] = []
    seen: set[str] = set()

    for item in results:
        domain = extract_domain(str(item.get("url", "")))
        if not domain or is_non_company_domain(domain):
            continue
        # 去重按注册域：同一家公司的不同子域不该在列表里占两行。
        domain_key = registrable_domain(domain)
        if domain_key in seen:
            continue
        seen.add(domain_key)

        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        name = name_from_title(title, domain) or name_from_domain(domain)
        industries = tuple(
            hint
            for hint in query.industry_hints
            if hint and (hint in title or hint in content)
        )
        missing: set[str] = {"contacts", "official_contact"}
        if not content:
            missing.add("summary")

        records.append(
            CompanyRecord(
                external_id=f"tavily-{domain}",
                name=name,
                domain=domain,
                industries=industries,
                summary=content,
                contact_count=0,
                evidence=(
                    Evidence(
                        title=title or name,
                        url=str(item.get("url", "")),
                        snippet=content[:200],
                    ),
                ),
                missing_fields=frozenset(missing),  # type: ignore[arg-type]
                source_id="tavily",
                attributes={"tavily_score": str(item.get("score", ""))},
            )
        )
        if len(records) >= query.limit:
            break
    return records


def _classify(error: Exception, message: str) -> SourceError:
    """把 SDK 抛出的原始异常映射成带 kind 的 SourceError。

    tavily-python 的异常类型随版本变动，状态码是最稳定的信号：
    401/403 是凭据问题（不重试），429/432 是限流与配额（可重试/可降级）。
    """
    if "401" in message or "403" in message or "unauthorized" in message.lower():
        return SourceError(f"Tavily 凭据无效：{message}", kind="auth_failed", source_id=_MANIFEST.id)
    if "429" in message or "rate limit" in message.lower():
        return SourceError(
            f"Tavily 限流：{message}", kind="rate_limited", retryable=True, source_id=_MANIFEST.id
        )
    if "432" in message or "quota" in message.lower() or "plan" in message.lower():
        return SourceError(
            f"Tavily 配额耗尽：{message}", kind="quota_exhausted", source_id=_MANIFEST.id
        )
    return SourceError(
        f"Tavily 调用失败：{message}",
        kind="upstream_unavailable",
        retryable=True,
        source_id=_MANIFEST.id,
    )


# 凭据就绪**且未被显式关闭**才注册：没有 key 的 tavily 留在注册表里只会在每次瀑布尝试时
# 产生一条 missing_credentials 失败记录，毫无价值还污染 failures 日志。
if TavilySource.is_configured() and TavilySource.is_enabled():
    register_source(TavilySource())
