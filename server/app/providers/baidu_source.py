"""百度 AI 搜索企业富化源（P6 免费路径 6-免1b）。

千帆「百度搜索」API（不传 model 即纯搜索模式）：POST /v2/ai_search/chat/completions，
Bearer API Key 鉴权，返回 `references[]`（title/url/content/…）。中文场景价值在于
**爱企查（aiqicha.baidu.com，百度自家）站点限定**：其页面摘要常含照面信息
（注册资本、法定代表人、成立日期），是免费路径里唯一能碰到照面字段的源。

## 诚实边界（同名实体风险）

短名称会命中同名企业（实测「云杉网络」返回「邢台云杉网络科技」）。因此：
- 照面字段**只进 `attributes`**（`registered_capital` / `legal_rep` / `founded`），
  绝不写核心字段冒充权威数据；同时带 `matched_title` 记录命中的页面标题，
  让读者能一眼看出数据描述的是哪家实体。
- 摘要（summary）同理只补叙述性内容，`attributes["source"]` 如实标注
  `aiqicha_web`（爱企查命中）或 `web_search`（泛搜索兜底）。

## 计费与缓存

按次计费（标准版约 0.036 元/次，免费额度按天发放），缓存键与企业一一对应，
「检索过但无相关页面」用空串哨兵，同 TTL 内不重复花钱。
"""

from __future__ import annotations

import re
from typing import Any

import requests

from .. import config
from .cache import get as cache_get
from .cache import set as cache_set
from .contracts import (
    CompanyEnrichQuery,
    CompanyRecord,
    EnrichTarget,
    Evidence,
    SourceError,
    SourceManifest,
)
from .registry import register_source

_API_ENDPOINT = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"

_AIQICHA_SITE = "aiqicha.baidu.com"

_MANIFEST = SourceManifest(
    id="baidu",
    name="百度 AI 搜索（爱企查）",
    capabilities=("company_enrich",),
    description="站点限定爱企查补照面信息、泛搜索补摘要；中国企业的网页富化兜底。",
    regions=("GLOBAL",),
    # 权威源（PDL，20）优先；爱企查站点限定比 Tavily 泛搜索（40）更相关，居中。
    priority=30,
    cost_per_call=0.036,
    requires_credentials=True,
)

# 每家企业每阶段的检索条数：只找一条相关结果，多了是浪费。
_ENRICH_TOP_K = 5

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
            self._search_baidu(_build_enrich_text(target), site=_AIQICHA_SITE), target
        )
        if content is None:
            return None
        attributes = {"source": "aiqicha_web", "matched_title": title}
        attributes.update(_extract_registry_fields(content))
        return _build_record(target, content, title, url, attributes)

    def _enrich_via_web(self, target: EnrichTarget) -> CompanyRecord | None:
        """阶段二：泛搜索兜底（不限站点），只补摘要——非爱企查页面不抽照面字段。"""
        content, title, url = self._first_relevant(
            self._search_baidu(_build_enrich_text(target), site=None), target
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

    def _search_baidu(self, text: str, site: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": text[:72]}],  # 接口限制 72 字符
            "search_source": "baidu_search_v2",
            "resource_type_filter": [{"type": "web", "top_k": _ENRICH_TOP_K}],
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
