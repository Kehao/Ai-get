"""领域 dataclass 的 JSON 编解码（P7 持久化用）。

`mining_rows.record_json` / `judgment_json` 与 `mining_lists.criteria_json`
存的是 dataclass（CompanyRecord / PersonRecord / Judgment / Criterion…）。
编解码**由类型注解驱动**：字段增删不需要改这里；嵌套（Judgment →
CriterionVerdict → Criterion、CompanyRecord → Evidence）自动递归。

约定：
- tuple / frozenset 编码成 JSON 数组，解码时按注解还原（含 `tuple[tuple[str, str], ...]`
  这类嵌套形状）；
- 非 JSON 原生类型（datetime 等）**不允许**出现在注册的 dataclass 里——
  现有六个类都满足；未来新增字段若带复杂类型，在 `types` 注册前先想清楚。
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, get_args, get_origin, get_type_hints

from .providers.contracts import CompanyRecord, Evidence, PersonRecord
from .qualification.criteria import Criterion
from .qualification.scoring import CriterionVerdict, Judgment

# 允许持久化的 dataclass。decode 按「目标类型 + 注解」重建，注册表用于校验。
types: dict[str, type] = {
    cls.__name__: cls
    for cls in (CompanyRecord, PersonRecord, Evidence, Criterion, CriterionVerdict, Judgment)
}


def dumps(obj: Any) -> str:
    """把 dataclass（可含 tuple/frozenset 嵌套）编码为 JSON 字符串。"""
    return json.dumps(_encode(obj), ensure_ascii=False, separators=(",", ":"))


def loads(text: str, cls: Any) -> Any:
    """按目标类型（含 `list[Criterion]` 这类泛型别名）从 JSON 还原对象。"""
    return _decode(json.loads(text), cls)


def _encode(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple, frozenset)):
        return [_encode(item) for item in obj]
    return obj  # str / int / float / bool / None


def _decode(data: Any, hint: Any) -> Any:
    if data is None or hint is None:
        return data
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        if not args:
            return tuple(data)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0]) for item in data)
        return tuple(_decode(item, arg) for item, arg in zip(data, args))
    if origin is frozenset:
        args = get_args(hint)
        arg = args[0] if args else None
        return frozenset(_decode(item, arg) for item in data)
    if origin is list:
        args = get_args(hint)
        arg = args[0] if args else None
        return [_decode(item, arg) for item in data]
    if origin is dict:
        _key_type, value_type = get_args(hint)
        return {key: _decode(value, value_type) for key, value in data.items()}
    if dataclasses.is_dataclass(hint) and isinstance(hint, type):
        field_hints = get_type_hints(hint)
        names = {f.name for f in dataclasses.fields(hint)}
        kwargs = {
            key: _decode(value, field_hints[key])
            for key, value in data.items()
            if key in names
        }
        return hint(**kwargs)
    return data  # str / int / float / bool / None
