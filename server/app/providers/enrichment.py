"""字段补齐编排（P5）：召回结果 → 瀑布 enrich → 字段合并。

召回源（P4）给的是「这家公司是谁」，补齐源（P5）给的是「这家企业还有什么字段」。
两件事由不同供应商、按不同计费模型完成，所以编排分两层：

1. `collect("company_enrich", ...)` 按 priority 瀑布调用所有已注册的补齐源；
2. `merge_enrichment` 把补齐结果**按字段**合并回召回记录——只填召回时为空的字段，
   证据按 URL 去重后并集，`missing_fields` 减去实际补到的字段。

失败语义：补齐是**锦上添花**，任何一个补齐源整体失败都不该让召回结果作废，
所以这里把 `SourceError` 收敛成「跳过补齐」，最多损失字段完整度，不损失结果。
与「绝不能把源失败伪装成空结果」不冲突——召回层的失败依旧照常抛出，
这条宽限只作用于 enrich 编排。
"""

from __future__ import annotations

from .contracts import CompanyEnrichQuery, CompanyRecord, EnrichTarget, SourceError
from .registry import collect, sources_for

# 允许被补齐覆盖的字段。contact_count 不在其中：联系人属于 L4 职责，
# firmographic 源（PDL 免费层）没有可靠数据，写了就是伪造台账。
_FILLABLE_EMPTY = ("summary", "location", "employees", "funding_stage")


def has_enrich_sources() -> bool:
    """是否注册了任何补齐源。没注册时跳过整个编排，一次多余调用都不发生。"""
    return bool(sources_for("company_enrich"))


def enrich_companies(records: list[CompanyRecord]) -> list[CompanyRecord]:
    """对召回结果做瀑布补齐并合并字段。任何失败都降级为「原样返回」。"""
    if not records or not has_enrich_sources():
        return records

    targets = tuple(
        EnrichTarget(domain=record.domain, name=record.name)
        for record in records
        if record.domain or record.name
    )
    if not targets:
        return records

    try:
        result = collect("company_enrich", CompanyEnrichQuery(targets=targets))
    except SourceError:
        # 所有补齐源都失败：保留召回结果，缺字段交给前端的「重试该字段」链路。
        return records

    enriched_by_key = {record.dedupe_key: record for record in result.items if record.dedupe_key}
    return [merge_enrichment(record, enriched_by_key.get(record.dedupe_key)) for record in records]


def merge_enrichment(
    base: CompanyRecord,
    enriched: CompanyRecord | None,
) -> CompanyRecord:
    """把一条补齐结果合并进召回记录。`enriched` 为 None 时原样返回。"""
    if enriched is None:
        return base

    updates: dict[str, object] = {}
    for field_name in _FILLABLE_EMPTY:
        if getattr(base, field_name) or not getattr(enriched, field_name):
            continue
        updates[field_name] = getattr(enriched, field_name)

    industries = base.industries or enriched.industries
    missing = set(base.missing_fields)
    if "summary" in missing and updates.get("summary"):
        missing.discard("summary")

    evidence = _merge_evidence(base, enriched)
    attributes = {**base.attributes, **enriched.attributes, "enriched_by": enriched.source_id}

    return CompanyRecord(
        external_id=base.external_id,
        name=base.name,
        domain=base.domain,
        industries=industries,
        summary=str(updates.get("summary", base.summary)),
        location=str(updates.get("location", base.location)),
        employees=str(updates.get("employees", base.employees)),
        funding_stage=str(updates.get("funding_stage", base.funding_stage)),
        contact_count=base.contact_count,
        evidence=evidence,
        missing_fields=frozenset(missing),  # type: ignore[arg-type]
        source_id=base.source_id,
        attributes=attributes,
    )


def _merge_evidence(base: CompanyRecord, enriched: CompanyRecord) -> tuple:
    """证据并集，按 URL 去重；召回源的排前面（它是「为什么匹配」的第一证物）。"""
    seen: set[str] = set()
    merged = []
    for item in (*base.evidence, *enriched.evidence):
        if item.url in seen:
            continue
        seen.add(item.url)
        merged.append(item)
    return tuple(merged)
