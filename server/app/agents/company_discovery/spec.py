"""配置模型：把「找什么、要抽出什么、最多花多少」变成一份可声明的 JSON。

## 一份 spec 决定三件事

| 组 | 决定什么 |
| --- | --- |
| 目标 | 检索用哪句话、用哪个源、找什么实体 |
| 契约 | 字段表——同时决定提示词里的字段说明、`missing` 白名单、定向检索词、输出形状 |
| 预算 | 循环的硬上限 |

## 字段表是唯一的语义来源

新增一个字段只需要在字段表里加一行，四处（提示词 / 校验 / 定向检索 / 落点）自动跟上。
反过来也成立：**没有落点的字段不该写进表里**——抽出来了却没处存，等于白花检索费。

## 配置从哪找

`load_spec("company-discovery")` 依次在下面三处找 `<name>.json`：

1. `$DISCOVERY_AGENT_CONFIGS` 指向的目录（部署时外挂配置覆盖内置默认）
2. 当前工作目录下的 `configs/`
3. 本包内置的 `configs/`

传路径（含 `/` 或以 `.json` 结尾）则直接用那个路径。
"""

from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_SPEC_NAME = "company_discovery"

_ENV_CONFIGS = "DISCOVERY_AGENT_CONFIGS"
_PACKAGE_CONFIGS = Path(__file__).resolve().parent / "configs"

_ALLOWED_KINDS = frozenset({"text", "list"})


class SpecError(RuntimeError):
    """配置缺失或格式非法。属于部署问题，宁可起不来也不静默用默认值兜住。"""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """一个可补字段。`search_hint` 是定向检索用的词，不是字段名的直译。"""

    name: str
    label: str
    kind: str = "text"
    required: bool = False
    search_hint: str = ""

    @property
    def is_list(self) -> bool:
        return self.kind == "list"


@dataclass(frozen=True, slots=True)
class Budget:
    """一次 run 的规模上限。全部有默认值，省略即用默认。"""

    max_entities: int = 3
    max_pages: int = 6
    max_gap_rounds: int = 1
    search_top_k: int = 20
    page_chars: int = 2500
    max_materials: int = 9
    """进模型整理的材料上限。v1 时代一轮最多 6 份够用；v2 加了 3 个子页后，
    6 会在 L3 前就把材料截满，L3 的检索成果永远进不了模型——所以提到 9。"""
    homepage_top_k: int = 5
    gap_top_k: int = 6
    gap_pages_per_round: int = 2
    max_subpages: int = 3
    """深挖 v2：官网子页探索最多抓几个子页。设 0 = 关闭子页探索（v1 行为）。"""


@dataclass(frozen=True, slots=True)
class DiscoverySpec:
    """一份完整的发现配置。`fields` 是唯一的语义来源，其余都是参数。"""

    name: str
    entity: str
    fields: tuple[FieldSpec, ...]
    budget: Budget = field(default_factory=Budget)
    query: str = ""
    site: str = ""
    """限定检索站点。留空＝全网；填了要求 `WebSearch` 实现支持站点限定。"""
    extra: dict[str, Any] = field(default_factory=dict)
    """给宿主用的自由字段——本包不解释它，适配器可以读它来决定行为。"""

    skip_hosts: tuple[str, ...] = ()
    """追加要跳过的站点（注册域形式，如 `example.com`）。

    用于「找官网」那一步：内置的通用清单之外再排除这些。不同业务关心的媒体不同，
    所以它是配置而不是常量。
    """

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields)

    @property
    def required_names(self) -> tuple[str, ...]:
        """必填字段。只有这些会驱动补缺检索——全设成必填等于让循环永远追不完。"""
        return tuple(item.name for item in self.fields if item.required)

    def field(self, name: str) -> FieldSpec | None:
        return next((item for item in self.fields if item.name == name), None)

    def search_hint(self, name: str) -> str:
        """定向检索词。没写就用字段标签兜底，总比空串让检索退化成搜名字强。"""
        item = self.field(name)
        if item is None:
            return name
        return item.search_hint or item.label or name

    def field_table(self) -> str:
        """渲染成提示词里的字段说明块。必填与否要写进去，模型才会照此标记 `missing`。"""
        lines = []
        for item in self.fields:
            suffix = "，必填" if item.required else ""
            kind = "，多个值用数组" if item.is_list else ""
            lines.append(f"- `{item.name}`（{item.label}{suffix}{kind}）")
        return "\n".join(lines)

    def json_fields(self, indent: str = "    ") -> str:
        """渲染 JSON 输出骨架里的字段行。

        **示例必须逐字对得上字段表**：模型倾向于照抄示例的形状，示例里没有的字段
        它永远也不会输出——那样新增字段就只是配置里的一行摆设。
        """
        lines = []
        for item in self.fields:
            example = '["标签"]' if item.is_list else f'"{item.label}"'
            lines.append(f'{indent}"{item.name}": {example},')
        return "\n".join(lines)


def candidate_dirs() -> tuple[Path, ...]:
    """配置查找顺序。环境变量优先，便于部署时用外挂配置覆盖包内默认。"""
    dirs: list[Path] = []
    from_env = os.environ.get(_ENV_CONFIGS, "").strip()
    if from_env:
        dirs.append(Path(from_env).expanduser())
    dirs.append(Path.cwd() / "configs")
    dirs.append(_PACKAGE_CONFIGS)
    return tuple(dirs)


def resolve_spec_path(source: str | Path = DEFAULT_SPEC_NAME) -> Path:
    """把「名字或路径」解析成一个确定的文件路径。"""
    text = str(source).strip()
    if not text:
        raise SpecError("配置名不能为空")
    if text.endswith(".json") or "/" in text or os.sep in text:
        return Path(text).expanduser()

    for directory in candidate_dirs():
        candidate = directory / f"{text}.json"
        if candidate.is_file():
            return candidate

    searched = "、".join(str(item) for item in candidate_dirs())
    raise SpecError(f"找不到名为 {text} 的配置；已查找：{searched}")


_specs: dict[str, DiscoverySpec] = {}


def load_spec(source: str | Path = DEFAULT_SPEC_NAME) -> DiscoverySpec:
    """读配置，按解析后的路径缓存（同一文件被不同写法指向也只读一次）。"""
    path = resolve_spec_path(source)
    key = str(path)
    cached = _specs.get(key)
    if cached is None:
        cached = read_spec(path)
        _specs[key] = cached
    return cached


def read_spec(path: str | Path) -> DiscoverySpec:
    """从指定文件读一份配置，**不走缓存**。"""
    file = Path(path)
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SpecError(f"找不到配置文件：{file}") from error
    except json.JSONDecodeError as error:
        raise SpecError(f"{file} 不是合法 JSON：{error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"{file} 的顶层必须是对象")

    fields = tuple(
        _read_field(item, file, index)
        for index, item in enumerate(_require_list(raw, "fields", file))
    )
    if not fields:
        raise SpecError(f"{file} 的 fields 不能为空")

    names = [item.name for item in fields]
    duplicated = {name for name in names if names.count(name) > 1}
    if duplicated:
        raise SpecError(f"{file} 的字段名重复：{sorted(duplicated)}")

    extra = raw.get("extra")
    return DiscoverySpec(
        name=_require_str(raw, "name", file) or file.stem,
        entity=_require_str(raw, "entity", file) or "条目",
        fields=fields,
        budget=_read_budget(raw.get("budget"), file),
        query=str(raw.get("query", "")).strip(),
        site=str(raw.get("site", "")).strip(),
        extra=extra if isinstance(extra, dict) else {},
        skip_hosts=tuple(
            str(item).strip() for item in (raw.get("skip_hosts") or []) if str(item).strip()
        ),
    )


def reset_cache() -> None:
    """丢弃已读入的配置（改了配置文件又不重启时用）。"""
    _specs.clear()


def _read_field(item: Any, path: Path, index: int) -> FieldSpec:
    if not isinstance(item, dict):
        raise SpecError(f"{path} 的 fields[{index}] 必须是对象")
    kind = str(item.get("kind", "text")).strip() or "text"
    if kind not in _ALLOWED_KINDS:
        raise SpecError(
            f"{path} 的 fields[{index}].kind 只能是 {sorted(_ALLOWED_KINDS)}，收到 {kind!r}"
        )
    name = _require_str(item, "name", path)
    return FieldSpec(
        name=name,
        label=str(item.get("label", "")).strip() or name,
        kind=kind,
        required=bool(item.get("required", False)),
        search_hint=str(item.get("search_hint", "")).strip(),
    )


def _read_budget(raw: Any, path: Path) -> Budget:
    if raw is None:
        return Budget()
    if not isinstance(raw, dict):
        raise SpecError(f"{path} 的 budget 必须是对象")
    known = {item.name for item in dataclasses.fields(Budget)}
    unknown = set(raw) - known
    if unknown:
        # 拼错的键比缺键更危险：它会静默地不生效，让人以为改过了。
        raise SpecError(
            f"{path} 的 budget 里有未知键：{sorted(unknown)}；可用键：{sorted(known)}"
        )
    values: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise SpecError(f"{path} 的 budget.{key} 必须是非负整数，收到 {value!r}")
        values[key] = value
    return Budget(**values)


def _require_list(raw: dict, key: str, path: Path) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise SpecError(f"{path} 缺少 {key} 数组")
    return value


def _require_str(raw: dict, key: str, path: Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{path} 的 {key} 必须是非空字符串")
    return value.strip()


if __name__ == "__main__":
    # 自检：不联网（`python -m discovery_agent.spec`）。
    assert Budget().max_entities == 3 and Budget().page_chars == 2500
    assert Budget().max_subpages == 3

    spec = DiscoverySpec(
        name="t",
        entity="公司",
        fields=(
            FieldSpec("domain", "官网", required=True, search_hint="官网"),
            FieldSpec("products", "产品", kind="list"),
        ),
    )
    assert spec.field_names == ("domain", "products")
    assert spec.required_names == ("domain",)
    assert spec.search_hint("products") == "产品", "没写 search_hint 时退回 label"
    assert spec.search_hint("不存在") == "不存在"
    assert "必填" in spec.field_table() and "数组" in spec.field_table()
    assert spec.field("domain") is not None and spec.field("nope") is None
    rendered = spec.json_fields()
    assert '"domain": "官网",' in rendered and '"products": ["标签"],' in rendered, rendered

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        good = root / "ok.json"
        good.write_text(
            json.dumps(
                {
                    "name": "ok",
                    "entity": "公司",
                    "fields": [{"name": "domain", "label": "官网"}],
                    "budget": {"max_entities": 5},
                }
            ),
            encoding="utf-8",
        )
        parsed = read_spec(good)
        assert parsed.budget.max_entities == 5 and parsed.budget.max_pages == 6

        # 加了 .json 后缀的按路径处理；不带后缀的按名字在候选目录里找
        assert resolve_spec_path(str(good)) == good
        os.environ[_ENV_CONFIGS] = str(root)
        try:
            assert resolve_spec_path("ok") == good, "环境变量指定的目录要优先命中"
            try:
                resolve_spec_path("不存在的配置")
            except SpecError:
                pass
            else:
                raise AssertionError("找不到配置时应当抛 SpecError")

            bad = root / "bad.json"
            for payload, reason in (
                ({"name": "x", "entity": "y", "fields": []}, "空 fields"),
                ({"name": "x", "entity": "y", "fields": [{"label": "无名字"}]}, "字段缺 name"),
                ({"name": "x", "entity": "y", "fields": [{"name": "a", "kind": "no"}]}, "非法 kind"),
                (
                    {"name": "x", "entity": "y", "fields": [{"name": "a"}], "budget": {"max_entites": 3}},
                    "拼错预算键",
                ),
                (
                    {"name": "x", "entity": "y", "fields": [{"name": "a"}], "budget": {"max_pages": -1}},
                    "负数预算",
                ),
                (
                    {"name": "x", "entity": "y", "fields": [{"name": "a"}, {"name": "a"}]},
                    "字段名重复",
                ),
            ):
                bad.write_text(json.dumps(payload), encoding="utf-8")
                try:
                    read_spec(bad)
                except SpecError:
                    continue
                raise AssertionError(f"应当拒绝：{reason}")
        finally:
            os.environ.pop(_ENV_CONFIGS, None)

    print(f"spec 自检通过（默认预算 {Budget().max_entities} 个 / {Budget().max_pages} 页）")
