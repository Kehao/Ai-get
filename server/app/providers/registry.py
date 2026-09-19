"""数据源注册表与瀑布式编排。

注册表解决两件事：**按能力而不是按类**查找数据源，以及在多个同能力数据源之间
按 `priority` 做瀑布式补齐（便宜的先用，够量即停）。后者是 B2B 数据行业的通行做法——
没有任何单一数据源是全覆盖的，所以要「宽召回 + 逐级兜底」。

一条硬约束：**任何一个数据源的失败都不能被伪装成空结果**。单个源失败时记录进
`SourceResult.meta["failures"]` 并继续尝试下一个；但如果**所有**候选源都失败，
必须抛出 `SourceError`，绝不允许返回空列表让上层显示「未找到企业」。
"""

from __future__ import annotations

import inspect
import time
from typing import Any, Callable, TypeVar

from .contracts import (
    CAPABILITY_METHODS,
    SourceCapability,
    SourceError,
    SourceManifest,
    SourceResult,
)

ItemT = TypeVar("ItemT")

_SOURCES: dict[str, Any] = {}


def register_source(source: ItemT) -> ItemT:
    """注册一个数据源实现，可直接装饰类或传入已构造的实例。

    注册期即校验 manifest 与实际方法的对应关系，把「声明了能力却没实现方法」
    这类错误提前到进程启动时暴露，而不是等某次挖掘跑到一半才炸。

    传类时按**无参构造**实例化，因此实现类不要依赖构造参数——凭据一律在
    `__init__` 里从 config / 环境变量读取，这与「用环境变量切换数据源」的用法一致。
    """
    target = source() if inspect.isclass(source) else source

    manifest = getattr(target, "manifest", None)
    if not isinstance(manifest, SourceManifest):
        raise ValueError(f"{type(target).__name__} 缺少合法的 manifest")
    if not manifest.capabilities:
        raise ValueError(f"数据源 {manifest.id} 未声明任何能力")
    if manifest.id in _SOURCES:
        raise ValueError(f"数据源 id 重复：{manifest.id}")

    missing = [
        CAPABILITY_METHODS[capability]
        for capability in manifest.capabilities
        if not callable(getattr(target, CAPABILITY_METHODS[capability], None))
    ]
    if missing:
        raise ValueError(f"数据源 {manifest.id} 声明了能力但缺少方法：{'、'.join(missing)}")

    _SOURCES[manifest.id] = target
    return source


def unregister_source(source_id: str) -> None:
    """仅供测试使用：把某个数据源移出注册表。"""
    _SOURCES.pop(source_id, None)


def get_source(source_id: str) -> Any:
    source = _SOURCES.get(source_id)
    if source is None:
        raise SourceError(
            f"未注册的数据源：{source_id}",
            kind="not_implemented",
            source_id=source_id,
            details={"registered": sorted(_SOURCES)},
        )
    return source


def has_source(source_id: str) -> bool:
    return source_id in _SOURCES


def sources_for(capability: SourceCapability) -> list[Any]:
    """返回具备该能力的数据源，按 priority 升序（越小越先用）。"""
    matched = [item for item in _SOURCES.values() if item.manifest.supports(capability)]
    return sorted(matched, key=lambda item: (item.manifest.priority, item.manifest.id))


def manifests() -> list[SourceManifest]:
    """供接口层展示「当前可用的数据源」，也让前端能说明结果来自哪个源。"""
    return sorted((item.manifest for item in _SOURCES.values()), key=lambda item: (item.priority, item.id))


def call_source(source: Any, capability: SourceCapability, *args: Any, **kwargs: Any) -> SourceResult[Any]:
    """统一包裹一次数据源调用：计时、计价、把未分类异常收敛成 `SourceError`。"""
    manifest: SourceManifest = source.manifest
    method_name = CAPABILITY_METHODS[capability]
    method = getattr(source, method_name, None)
    if not callable(method):
        raise SourceError(
            f"数据源 {manifest.id} 不支持能力 {capability}",
            kind="not_implemented",
            source_id=manifest.id,
        )

    started = time.monotonic()
    try:
        items = method(*args, **kwargs)
    except SourceError:
        raise
    except Exception as error:  # noqa: BLE001 — 未分类异常必须收敛，避免上层漏判分支
        raise SourceError(
            f"数据源 {manifest.id} 调用失败：{error}",
            kind="upstream_unavailable",
            retryable=True,
            source_id=manifest.id,
        ) from error

    return SourceResult(
        items=list(items or []),
        source_id=manifest.id,
        latency_ms=int((time.monotonic() - started) * 1000),
        cost=manifest.cost_per_call,
    )


def collect(
    capability: SourceCapability,
    query: Any,
    *,
    source_ids: tuple[str, ...] = (),
    target_items: int = 0,
    dedupe_key: Callable[[Any], str] | None = None,
) -> SourceResult[Any]:
    """瀑布式汇总：按 priority 依次调用同能力数据源，边收边去重，够量即停。

    - `target_items > 0` 时达到数量就停止，避免为凑齐结果把昂贵的补充源全部跑一遍；
    - 单个源失败只记录不中断；全部失败则抛错（**绝不返回空结果**）。
    """
    candidates = [get_source(source_id) for source_id in source_ids] if source_ids else sources_for(capability)
    if not candidates:
        raise SourceError(
            f"没有可用于 {capability} 的数据源",
            kind="not_implemented",
            details={"capability": capability},
        )

    collected: list[Any] = []
    seen: set[str] = set()
    attempted: list[str] = []
    failures: list[dict[str, Any]] = []
    total_latency = 0
    total_cost = 0.0

    for source in candidates:
        try:
            result = call_source(source, capability, query)
        except SourceError as error:
            failures.append(
                {
                    "source_id": error.source_id or source.manifest.id,
                    "kind": error.kind,
                    "retryable": error.retryable,
                    "message": str(error),
                }
            )
            continue

        attempted.append(result.source_id)
        total_latency += result.latency_ms
        total_cost += result.cost

        for item in result.items:
            key = dedupe_key(item) if dedupe_key else str(getattr(item, "dedupe_key", item))
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)

        if target_items and len(collected) >= target_items:
            break

    if not attempted:
        first = failures[0]
        raise SourceError(
            f"所有可用于 {capability} 的数据源均调用失败：{first['message']}",
            kind=first["kind"],
            retryable=bool(first["retryable"]),
            source_id=first["source_id"],
            details={"failures": failures},
        )

    truncated = bool(target_items) and len(collected) > target_items
    return SourceResult(
        items=collected[:target_items] if target_items else collected,
        source_id="+".join(attempted),
        latency_ms=total_latency,
        cost=total_cost,
        meta={
            "attempted": attempted,
            "failures": failures,
            "capability": capability,
            "truncated": truncated,
        },
    )
