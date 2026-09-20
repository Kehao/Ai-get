"""百度 AI 搜索源（P6 免费路径 6-免1b / P7 主力网页源）。

千帆「百度搜索」API（不传 model 即纯搜索模式）：POST /v2/ai_search/chat/completions，
Bearer API Key 鉴权，返回 `references[]`（title/url/content/…）。

## 两个能力

- **company_search（召回）**：中文场景的主力召回。两阶段查询——先泛搜索拿**企业官网**
  （有域名才能去重与触达），数量不足时再用爱企查站点限定补一轮（拿企业全名与照面字段，
  域名留空）。映射规则与 Tavily 共用 `web_mapping`，本源只管检索策略。
- **company_enrich（富化）**：对缺摘要的企业做两阶段检索（爱企查站点限定 → 泛搜索兜底），
  爱企查页面摘要常含照面信息（注册资本、法定代表人、成立日期），是免费路径里唯一
  能碰到照面字段的源。

## 诚实边界（同名实体风险）

短名称会命中同名企业（实测「云杉网络」返回「邢台云杉网络科技」）。因此：
- 照面字段**只进 `attributes`**（`registered_capital` / `legal_rep` / `founded`），
  绝不写核心字段冒充权威数据；同时带 `matched_title` 记录命中的页面标题，
  让读者能一眼看出数据描述的是哪家实体。
- 摘要（summary）同理只补叙述性内容，`attributes["source"]` 如实标注
  `aiqicha_web`（爱企查命中）或 `web_search`（泛搜索兜底）。

## 计费与缓存

按次计费（标准版约 0.036 元/次，免费额度按天发放），缓存键与查询/企业一一对应，
「检索过但无相关页面」用空串哨兵，同 TTL 内不重复花钱。
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

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
    is_directory_domain,
    is_non_company_domain,
    name_from_domain,
    name_from_title,
    registrable_domain,
)

_API_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"

logger = logging.getLogger(__name__)

_AIQICHA_SITE = "aiqicha.baidu.com"

_MANIFEST = SourceManifest(
    id="baidu",
    name="百度 AI 搜索（爱企查）",
    capabilities=("company_search", "company_enrich"),
    description="中文网页检索：泛搜索召回企业官网、爱企查站点限定补照面信息。",
    regions=("GLOBAL",),
    # 召回不走瀑布（默认源是单源取值），priority 只影响 company_enrich 的先后：
    # 权威源（PDL，20）优先，爱企查站点限定比 Tavily 泛搜索（40）更相关，居中。
    priority=30,
    cost_per_call=0.036,
    requires_credentials=True,
)

# 每家企业每阶段的检索条数：只找一条相关结果，多了是浪费。
_ENRICH_TOP_K = 5

# 召回单次检索的条数上限。接口对 top_k 有天花板（20），
# 一次挖掘的目标量（默认 25）本就指望不上单次凑齐——不足的由第二阶段补。
_SEARCH_TOP_K = 20

_REQUEST_TIMEOUT_SECONDS = 20

# 照面字段的保守抽取模式：只认「字段名 + 值」的显式句式，抽不到就放弃，绝不猜。
_CAPITAL_PATTERN = re.compile(r"注册资本[为:：]?\s*([0-9][0-9,.]*\s*万?[元人民币]*)")
_LEGAL_REP_PATTERN = re.compile(r"法定代表人[为:：]?\s*([\u4e00-\u9fa5·]{2,5})")
_FOUNDED_PATTERN = re.compile(r"成立[于日期:：]*\s*(\d{4}[年-]\d{1,2}[月-]\d{1,2}日?)")


class BaiduSearchSource:
    """基于百度千帆 AI 搜索（纯搜索模式）的企业字段富化源。"""

    manifest = _MANIFEST

    def __init__(self, api_key: str | None = None, client: Any = None) -> None:
        self.api_key = api_key if api_key is not None else config.BAIDU_SEARCH_API_KEY
        # client 允许注入：测试用它塞入「payload -> 响应 dict」的假实现，生产路径一律现建。
        self._client = client

    @staticmethod
    def is_configured() -> bool:
        return bool(config.BAIDU_SEARCH_API_KEY)

    # ── company_search ──────────────────────────────────────────────────

    def search_companies(self, query: CompanyQuery) -> list[CompanyRecord]:
        """两阶段召回：泛搜索拿企业官网 → 爱企查站点限定补量。

        之所以要两阶段：泛搜索的结果里企业官网只是少数（其余是媒体、目录、招聘页），
        单靠它凑不满一次挖掘的目标量；而爱企查的结果**没有企业域名**（域名是爱企查的），
        只能按名称去重。两段合并后，「有域名的优先、没有的按名称保留」——
        宁可给出「名字对但官网待补」的候选，也不拿无关公司凑数。
        """
        search_text = _build_search_text(query)
        cache_key = f"baidu:search:{search_text}:{query.limit}"
        cached = cache_get(cache_key)
        if isinstance(cached, list):
            return cached

        records = _to_company_records(
            self._search_baidu(search_text, site=None, top_k=_SEARCH_TOP_K), query
        )
        if len(records) < query.limit:
            try:
                extra = _to_company_records(
                    self._search_baidu(search_text, site=_AIQICHA_SITE, top_k=_SEARCH_TOP_K),
                    query,
                )
            except SourceError:
                # 补量失败不影响已经拿到的结果：这两段是同一个源的两次查询，
                # 第一段成功就已经有可用的召回，没必要整批判失败。
                logger.warning("百度召回补量阶段失败，仅保留第一阶段结果", exc_info=True)
                extra = []
            # 两段各自淘汰了多少条也要留痕：覆盖率上不去时，得能分清是
            # 「检索没返回」还是「返回了但都不像企业页」——这两种的修法完全不同。
            logger.info(
                "百度召回：泛搜索 %d 条 + 爱企查补量 %d 条（目标 %d 条）",
                len(records),
                len(extra),
                query.limit,
            )
            records = _merge_deduped(records, extra)

        records = records[: query.limit]
        cache_set(cache_key, records)
        return records

    # ── company_enrich ──────────────────────────────────────────────────

    def enrich_companies(self, query: CompanyEnrichQuery) -> list[CompanyRecord]:
        """对缺摘要的企业做两阶段检索（爱企查站点限定 → 泛搜索兜底）。

        逐目标容错：单家失败不拖垮整批；但全部失败时抛出第一个错误——
        源故障不能被伪装成「都查不到」。
        """
        records: list[CompanyRecord] = []
        first_error: SourceError | None = None

        for target in query.targets:
            if "summary" not in target.missing:
                continue  # 已有摘要：本源帮不上别的忙，一次调用都不花
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
        cache_key = f"baidu:webenrich:{target.cache_key}"
        cached = cache_get(cache_key)
        # 空串是「检索过但没有相关页面」的哨兵：不再为同一家企业重复花钱。
        if cached == "":
            return None
        if cached is not None:
            return cached  # type: ignore[return-value]

        record = self._enrich_via_aiqicha(target) or self._enrich_via_web(target)
        cache_set(cache_key, record if record is not None else "")
        return record

    def _enrich_via_aiqicha(self, target: EnrichTarget) -> CompanyRecord | None:
        """阶段一：站点限定爱企查。命中则补摘要，并尝试从摘要抽照面字段进 attributes。"""
        content, title, url = self._first_relevant(
            self._search_baidu(_build_enrich_text(target), site=_AIQICHA_SITE, top_k=_ENRICH_TOP_K), target
        )
        if content is None:
            return None
        attributes = {"source": "aiqicha_web", "matched_title": title}
        attributes.update(_extract_registry_fields(content))
        return _build_record(target, content, title, url, attributes)

    def _enrich_via_web(self, target: EnrichTarget) -> CompanyRecord | None:
        """阶段二：泛搜索兜底（不限站点），只补摘要——非爱企查页面不抽照面字段。"""
        content, title, url = self._first_relevant(
            self._search_baidu(_build_enrich_text(target), site=None, top_k=_ENRICH_TOP_K), target
        )
        if content is None:
            return None
        return _build_record(target, content, title, url, {"source": "web_search"})

    def _first_relevant(
        self, data: dict[str, Any], target: EnrichTarget
    ) -> tuple[str | None, str, str]:
        """取第一条指向目标企业本人的结果，返回 (content, title, url)；没有则 (None, "", "")。"""
        for item in data.get("references") or []:
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", ""))
            content = str(item.get("content", "")).strip()
            if not content or not _is_relevant(item, target):
                continue
            return content, title, url
        return None, "", ""

    def _search_baidu(self, text: str, site: str | None, *, top_k: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": text[:72]}],  # 接口限制 72 字符
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": top_k}],
            "stream": False,
        }
        if site:
            payload["search_filter"] = {"match": {"site": [site]}}
        try:
            if self._client is not None:
                return self._client(payload)
            response = requests.post(
                _API_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except SourceError:
            raise
        except Exception as error:  # noqa: BLE001 — HTTP 状态码是唯一稳定信号
            raise _classify(error, str(error)) from error
        if response.status_code != 200:
            raise _classify(response, f"{response.status_code} {response.text[:200]}")
        data = response.json()
        code, message = data.get("code"), data.get("message")
        if code and not data.get("references") and not data.get("choices"):
            # HTTP 200 但业务报错（如 216003 鉴权失败）。
            raise SourceError(
                f"百度 AI 搜索调用失败：{code} {message}",
                kind="upstream_unavailable",
                retryable=True,
                source_id=_MANIFEST.id,
            )
        return data


def _build_search_text(query: CompanyQuery) -> str:
    """召回查询：画像文本为主，行业提示只取前三个拼在后面——提示是相关性信号，
    不是查询本身。截断到接口允许的长度由 `_search_baidu` 负责。"""
    hints = " ".join(query.industry_hints[:3])
    return f"{query.text} {hints}".strip()


def _to_company_records(data: dict[str, Any], query: CompanyQuery) -> list[CompanyRecord]:
    """把一批网页结果折算成企业候选。

    站点三分类见 `web_mapping`：媒体/UGC 整条丢弃；工商目录站保留记录但**域名留空**
    （域名是目录站自己的，拿去当企业身份会污染去重键与联系人链路）；企业官网保留域名。
    **取不出名称的结果也丢弃**——名称是判定层唯一的抓手，无名候选进了列表只能白占一行。
    """
    records: list[CompanyRecord] = []
    seen: set[str] = set()

    for item in data.get("references") or []:
        url = str(item.get("url", ""))
        title = str(item.get("title", "")).strip()
        content = str(item.get("content", "")).strip()
        domain = extract_domain(url)
        # 判定顺序不能反：目录站（aiqicha.baidu.com）的注册域是 baidu.com，
        # 而 baidu.com 本身在「非企业站」清单里——先判目录站才能豁免掉它，
        # 否则爱企查页面会被当成搜索引擎页面整条丢掉，第二阶段就白跑了。
        directory = bool(domain) and is_directory_domain(domain)
        if domain and not directory and is_non_company_domain(domain):
            continue
        if directory:
            domain = ""
        # 目录站没有域名可退化，取名失败即整条丢弃（如「陈华」这类法人页面）。
        name = name_from_title(title, domain) or name_from_domain(domain)
        if not name:
            continue
        # 去重按注册域：360 的 saas./ent.online. 是同一家，不该占两行。
        key = registrable_domain(domain) if domain else name.lower()
        if key in seen:
            continue
        seen.add(key)

        attributes = {
            "source": "aiqicha_web" if directory else "web_search",
            "matched_title": title,
        }
        # 目录页正文常带照面字段，顺手抽进台账；抽不到就不标 enriched_by，
        # 免得台账冒出一条「有来源但没有字段」的空记录。
        registry = _extract_registry_fields(content) if directory else {}
        if registry:
            attributes.update(registry)
            attributes["enriched_by"] = _MANIFEST.id

        missing: set[str] = {"contacts", "official_contact"}
        if not content:
            missing.add("summary")

        records.append(
            CompanyRecord(
                external_id=f"baidu-{domain or name}",
                name=name,
                domain=domain,
                industries=tuple(
                    hint
                    for hint in query.industry_hints
                    if hint and (hint in title or hint in content)
                ),
                summary=content,
                contact_count=0,
                evidence=(Evidence(title=title or name, url=url, snippet=content[:200]),),
                missing_fields=frozenset(missing),  # type: ignore[arg-type]
                source_id=_MANIFEST.id,
                attributes=attributes,
            )
        )
        if len(records) >= query.limit:
            break

    logger.debug(
        "百度检索结果映射：原始 %d 条 → 保留 %d 条",
        len(data.get("references") or []),
        len(records),
    )
    return records


def _merge_deduped(
    primary: list[CompanyRecord], extra: list[CompanyRecord]
) -> list[CompanyRecord]:
    """合并两段召回：先按注册域，再按**名称**兜一道，先到的优先。

    名称这道不能省：同一家公司在两段里的键根本不同——泛搜索给的是企业官网
    （键 = 域名），爱企查给的是目录页（键 = 名称）。只按域名去重会让同一家公司
    在列表里占两行，一行有官网一行没有。
    """
    merged = list(primary)
    seen_keys = {_company_key(record) for record in primary}
    seen_names = {record.name.strip().lower() for record in primary if record.name}

    for record in extra:
        name = record.name.strip().lower()
        if _company_key(record) in seen_keys or (name and name in seen_names):
            continue
        seen_keys.add(_company_key(record))
        if name:
            seen_names.add(name)
        merged.append(record)
    return merged


def _company_key(record: CompanyRecord) -> str:
    """一条记录的合并键：有域名用注册域，没有（目录站）用名称。"""
    return registrable_domain(record.domain) if record.domain else record.name.strip().lower()


def _build_enrich_text(target: EnrichTarget) -> str:
    """富化查询：名称最精确（中文尤其如此），缺失时退化到域名。"""
    subject = target.name.strip() or target.domain.strip()
    return f"{subject} 企业简介"


def _is_relevant(item: dict[str, Any], target: EnrichTarget) -> bool:
    """结果必须指向目标企业本人：名称出现在标题/正文，或域名主体出现在 URL。
    同名企业的实体消歧靠 attributes 里的 matched_title 交给读者判断——
    短名称在这里没有更强的程序化手段，诚实标注比假装精确好。"""
    title = str(item.get("title", ""))
    content = str(item.get("content", ""))
    url = str(item.get("url", "")).lower()
    name = target.name.strip()
    domain_root = target.domain.strip().lower().split(".", 1)[0]
    if name and (name in title or name in content):
        return True
    return bool(domain_root) and len(domain_root) > 2 and domain_root in url


def _extract_registry_fields(content: str) -> dict[str, str]:
    """从爱企查摘要里抽照面字段。只认显式句式，抽不到就放弃——宁缺毋假。"""
    fields: dict[str, str] = {}
    if match := _CAPITAL_PATTERN.search(content):
        fields["registered_capital"] = match.group(1).strip()
    if match := _LEGAL_REP_PATTERN.search(content):
        fields["legal_rep"] = match.group(1).strip()
    if match := _FOUNDED_PATTERN.search(content):
        fields["founded"] = match.group(1).strip()
    return fields


def _build_record(
    target: EnrichTarget,
    content: str,
    title: str,
    url: str,
    attributes: dict[str, str],
) -> CompanyRecord:
    return CompanyRecord(
        external_id=f"baidu-web-{target.cache_key}",
        name=target.name or target.domain,
        domain=target.domain,
        summary=content[:400],
        contact_count=0,
        evidence=(Evidence(title=title or target.name, url=url, snippet=content[:200]),),
        missing_fields=frozenset({"contacts", "official_contact"}),
        source_id=_MANIFEST.id,
        attributes=attributes,
    )


def _classify(error: Any, message: str) -> SourceError:
    """把 HTTP/网络异常映射成带 kind 的 SourceError（与 tavily/pdl 同一口径）。"""
    text = str(message)
    if "401" in text or "403" in text or "216003" in text or "Authentication" in text:
        return SourceError(
            f"百度 AI 搜索凭据无效：{text}", kind="auth_failed", source_id=_MANIFEST.id
        )
    if "429" in text or "rate limit" in text.lower():
        return SourceError(
            f"百度 AI 搜索限流：{text}", kind="rate_limited", retryable=True, source_id=_MANIFEST.id
        )
    return SourceError(
        f"百度 AI 搜索调用失败：{text}",
        kind="upstream_unavailable",
        retryable=True,
        source_id=_MANIFEST.id,
    )


# 凭据就绪才注册，理由同 tavily_source：无 key 的源只会污染瀑布失败日志。
if BaiduSearchSource.is_configured():
    register_source(BaiduSearchSource())
