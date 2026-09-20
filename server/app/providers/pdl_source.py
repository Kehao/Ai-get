"""PDL 企业字段补齐源（P5）：People Data Labs Company Enrichment。

People Data Labs 的免费层每月 100 credits，返回**真实生产数据的 base 字段**
（行业、规模、成立年份、所在地），但联系方式与 premium 字段被脱敏——
所以这个源只补 `CompanyRecord` 的画像字段，`contact_count` 永远不写：
联系人是 L4 的职责（Apollo / Hunter.io 等），混在一起会让「哪个字段哪个源给的」失去台账。

## 计费与缓存

PDL 按**成功返回的 profile 数**计费（空结果与报错不扣费），因此缓存键是
「域名（或名称）→ 单条画像」：同一企业 TTL 内的重复补齐零成本。TTL 缓存
在 `providers.cache`，P7 换 SQLite 时 adapter 不用动。

## 免费层的诚实边界

免费层拿不到的字段（联系人、融资数据）不写默认值、不伪造，
`missing_fields` 如实上报——上层「字段缺失 → 显示重试入口」的链路依赖这个事实。
"""

from __future__ import annotations

from typing import Any

from peopledatalabs import PDLPY

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

_MANIFEST = SourceManifest(
    id="pdl",
    name="People Data Labs 企业库",
    capabilities=("company_enrich",),
    description="按域名/名称补齐企业的行业、规模、成立年份与所在地（免费层为 base 字段）。",
    regions=("GLOBAL",),
    priority=20,
    cost_per_call=0.0,
    requires_credentials=True,
)

# 免费层的限流很低（10-100 req/min），批量补齐时逐条串行即可，不做并发。
_ERROR_STATUS_HINTS: tuple[tuple[str, str, bool], ...] = (
    ("401", "auth_failed", False),
    ("403", "permission_denied", False),
    ("429", "rate_limited", True),
)


class PdlSource:
    """基于 PDL 官方 SDK（peopledatalabs）的企业字段补齐源。"""

    manifest = _MANIFEST

    def __init__(self, api_key: str | None = None, client: Any = None) -> None:
        self.api_key = api_key if api_key is not None else config.PDL_API_KEY
        # client 允许注入：测试用它塞入假实现，生产路径一律现建。
        self._client = client

    @staticmethod
    def is_configured() -> bool:
        return bool(config.PDL_API_KEY)

    def _pdl(self) -> PDLPY:
        if self._client is None:
            if not self.api_key:
                raise SourceError(
                    "PDL 未配置 API key（AIGET_PDL_API_KEY）",
                    kind="missing_credentials",
                    source_id=_MANIFEST.id,
                )
            self._client = PDLPY(api_key=self.api_key)
        return self._client

    # ── company_enrich ──────────────────────────────────────────────────

    def enrich_companies(self, query: CompanyEnrichQuery) -> list[CompanyRecord]:
        records: list[CompanyRecord] = []
        for target in query.targets:
            profile = self._enrich_one(target)
            if profile is not None:
                records.append(_to_company_record(profile, target))
        return records

    def _enrich_one(self, target: EnrichTarget) -> dict[str, Any] | None:
        """补齐单家企业。查不到（404）不是错误——返回 None 让编排层保留召回原记录。"""
        cache_key = f"pdl:company:{target.cache_key}"
        cached = cache_get(cache_key)
        # 空串是「确认过库里没有」的哨兵：直接返回 None，不再反复探测空档企业。
        if cached == "":
            return None
        if cached is not None:
            return cached  # type: ignore[return-value]

        params = _enrich_params(target)
        if params is None:
            return None

        try:
            response = self._pdl().company.enrich(search_type="strict", **params)
        except SourceError:
            raise
        except Exception as error:  # noqa: BLE001 — HTTP 状态码是唯一稳定信号
            raise _classify(error, str(error)) from error

        if response.get("status") != 200 or not response.get("data"):
            # 明确查过但没有：缓存空哨兵，避免同一空档企业反复扣探测成本。
            cache_set(cache_key, "")
            return None

        profile = dict(response["data"])
        cache_set(cache_key, profile)
        return profile


def _enrich_params(target: EnrichTarget) -> dict[str, str] | None:
    """构造 enrich 参数。域名优先（strict 模式下最精确），名称兜底；两者都空则跳过。"""
    if target.domain:
        website = target.domain.strip().lower().removeprefix("http://").removeprefix("https://")
        return {"website": website}
    if target.name:
        return {"name": target.name}
    return None


def _to_company_record(profile: dict[str, Any], target: EnrichTarget) -> CompanyRecord:
    name = str(profile.get("name") or target.name or target.domain)
    website = str(profile.get("website") or target.domain).strip().lower()
    website = website.removeprefix("http://").removeprefix("https://").strip("/")

    industries = _clean_industries(profile)
    location = _build_location(profile)
    employees = str(profile.get("size") or "").strip()
    summary = str(profile.get("summary") or "").strip()

    missing: set[str] = {"contacts", "official_contact"}
    if not summary:
        missing.add("summary")

    evidence: list[Evidence] = []
    if website:
        evidence.append(
            Evidence(
                title=f"{name}（PDL 企业档案）",
                url=f"https://{website}",
                snippet="企业官网，用于确认业务范围与所在地区。",
            )
        )
    linkedin_url = str(profile.get("linkedin_url") or "").strip()
    if linkedin_url:
        evidence.append(
            Evidence(
                title=f"{name}（LinkedIn 主页）",
                url=linkedin_url,
                snippet="LinkedIn 企业主页，用于交叉确认行业、规模与雇员数。",
            )
        )

    attributes = {"pdl_id": str(profile.get("id") or "")}
    founded = str(profile.get("founded") or "").strip()
    if founded:
        attributes["founded"] = founded

    return CompanyRecord(
        external_id=f"pdl-{profile.get('id') or website or target.cache_key}",
        name=name,
        domain=website,
        industries=industries,
        summary=summary,
        location=location,
        employees=employees,
        evidence=tuple(evidence),
        missing_fields=frozenset(missing),  # type: ignore[arg-type]
        source_id=_MANIFEST.id,
        attributes=attributes,
    )


def _clean_industries(profile: dict[str, Any]) -> tuple[str, ...]:
    """industry 主行业在前，tags 取前三个补充——顺序即权重，别打乱。"""
    items: list[str] = []
    industry = str(profile.get("industry") or "").strip()
    if industry:
        items.append(industry)
    tags = profile.get("tags") or []
    if isinstance(tags, list):
        items.extend(str(tag).strip() for tag in tags[:3] if str(tag).strip())
    return tuple(dict.fromkeys(items))


def _build_location(profile: dict[str, Any]) -> str:
    parts = [
        str(profile.get(key) or "").strip()
        for key in ("locality", "region", "country")
    ]
    return "，".join(dict.fromkeys(part for part in parts if part))


def _classify(error: Exception, message: str) -> SourceError:
    for hint, kind, retryable in _ERROR_STATUS_HINTS:
        if hint in message:
            return SourceError(
                f"PDL 调用受限：{message}", kind=kind, retryable=retryable, source_id=_MANIFEST.id
            )
    if "404" in message:
        # 404 属于「查到了但库里没有」，不该被当成源故障往上层抛。
        return SourceError(f"PDL 未收录该企业：{message}", kind="invalid_request", source_id=_MANIFEST.id)
    return SourceError(
        f"PDL 调用失败：{message}",
        kind="upstream_unavailable",
        retryable=True,
        source_id=_MANIFEST.id,
    )


# 凭据就绪才注册，理由同 tavily_source：无 key 的源只会污染瀑布失败日志。
if PdlSource.is_configured():
    register_source(PdlSource())
