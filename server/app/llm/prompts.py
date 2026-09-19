"""L0 提示词的加载与渲染。

## 提示词的真源在技能目录，不在这个文件里

提示词正文与契约表都放在 **`skills/profile-to-weighted-criteria/`**（项目级技能，
见 `SKILL.md`）。这里只负责三件事：读文件、把运行时取值填进模板、缓存。

为什么不再内嵌一份 Python 副本：同一段文字有两份副本**必然漂移**，而
「这批标准是哪版 prompt 产出的」要写进任务记录——漂移会让溯源失效。
技能目录同时被两个使用者读：**运行时**（本模块）与**独立校验器**
（`scripts/validate_criteria.py`），所以契约只声明一次。

## 取值从哪来

模板里的占位符分两类：

- **结构类**（维度枚举、每维度条数上限、宽松维度、`expected` 取值集合）来自
  `contract.json`——它是契约的单一来源，校验器读的也是它；
- **运行态类**（默认权重、硬性权重阈值、融资阶段）来自 `qualification/criteria.py`。
  这些是规则引擎自己的表，不能让技能目录另存一份。

两类之间的一致性在加载时**逐项断言**（见 `_check_contract_consistency`）：
不一致就抛错。这不是防御性编程——它是「改了契约表却忘了改另一处」唯一能被立刻发现的地方。

## 失败策略：起不来，而不是悄悄降级

提示词与契约是**仓库资产**，不是会抖动的外部依赖。缺失或自相矛盾属于「检出损坏」，
必须在加载时立刻炸掉并指出缺了哪个文件；若容忍它降级到规则引擎，
所有人都会以为 LLM 正在工作，而实际上提示词根本没被读到。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from ..qualification.criteria import (
    CATEGORY_WEIGHTS,
    FUNDING_KEYWORDS,
    HARD_WEIGHT_THRESHOLD,
    _DEFAULT_MAX_PER_CATEGORY,
    _LLM_CATEGORIES,
    _MAX_PER_CATEGORY,
)

# 默认技能目录：仓库根下的 skills/<name>。可用 AIGET_LLM_PROMPT_DIR 指向别处，
# 这样换领域时只需换一个目录，不用改代码。
DEFAULT_PROMPT_DIR = "skills/profile-to-weighted-criteria"

# 模板文件名。改文件名要同步改这里与 SKILL.md。
_SYSTEM_TEMPLATE = "prompts/criteria.system.md"
_USER_TEMPLATE = "prompts/criteria.user.md"
_CONTRACT_FILE = "contract.json"


class PromptAssetError(RuntimeError):
    """提示词资产缺失或自相矛盾。**故意用硬错误**，见模块 docstring 的失败策略。"""


@dataclass(frozen=True, slots=True)
class CategorySpec:
    """一个标准维度的契约。渲染提示词与校验器共用同一份数据。"""

    name: str
    max_count: int
    lenient: bool
    expected_kind: str
    tokens_hint: str
    expected_hint: str
    tokens_must_be_empty: bool
    enum_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PromptContract:
    version: str
    min_criteria: int
    max_criteria: int
    categories: tuple[CategorySpec, ...]
    excluded_categories: dict[str, str]

    @property
    def category_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.categories)

    @property
    def lenient_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.categories if item.lenient)

    def spec(self, name: str) -> CategorySpec | None:
        return next((item for item in self.categories if item.name == name), None)


@dataclass(frozen=True, slots=True)
class PromptAsset:
    """一次加载的完整结果：模板原文 + 契约 + 渲染好的提示词。"""

    version: str
    system: str
    user_template: str
    contract: PromptContract
    directory: Path


def prompt_dir_label() -> str:
    """提示词目录的**可读标识**：配置里写的是什么就显示什么，不展开成绝对路径。

    给界面用。排查「这批标准用的哪份提示词」时，看配置值比看一长串绝对路径有用。
    """
    return os.environ.get("AIGET_LLM_PROMPT_DIR", "").strip() or DEFAULT_PROMPT_DIR


def prompt_dir() -> Path:
    """提示词目录的绝对路径，供读文件用。相对路径以仓库根为基准。"""
    path = Path(prompt_dir_label())
    if not path.is_absolute():
        # app/llm/prompts.py → parents[3] 是仓库根
        path = Path(__file__).resolve().parents[3] / path
    return path


def load_contract() -> PromptContract:
    """读 `contract.json`。字段缺失或类型不对时抛出可定位的错误。"""
    path = prompt_dir() / _CONTRACT_FILE
    raw = _read_json(path)

    categories: list[CategorySpec] = []
    for index, item in enumerate(_require_list(raw, "categories", path)):
        if not isinstance(item, dict):
            raise PromptAssetError(f"{path} 的 categories[{index}] 必须是对象")
        categories.append(
            CategorySpec(
                name=_require_str(item, "name", path),
                max_count=_require_int(item, "max", path),
                lenient=_require_bool(item, "lenient", path),
                expected_kind=_require_str(item, "expected_kind", path),
                tokens_hint=_require_str(item, "tokens_hint", path),
                expected_hint=_require_str(item, "expected_hint", path),
                tokens_must_be_empty=bool(item.get("tokens_must_be_empty", False)),
                enum_values=tuple(str(value) for value in (item.get("enum_values") or [])),
            )
        )
    if not categories:
        raise PromptAssetError(f"{path} 的 categories 不能为空")

    return PromptContract(
        version=_require_str(raw, "version", path),
        min_criteria=_require_int(raw, "min_criteria", path),
        max_criteria=_require_int(raw, "max_criteria", path),
        categories=tuple(categories),
        excluded_categories={
            str(key): str(value)
            for key, value in (raw.get("excluded_categories") or {}).items()
        },
    )


def load_asset() -> PromptAsset:
    """读取并渲染提示词。首次调用读盘，之后走缓存。"""
    global _asset
    if _asset is None:
        _asset = _load()
    return _asset


def reset_cache() -> None:
    """仅供测试与非默认目录切换后使用。"""
    global _asset
    _asset = None


def prompt_version() -> str:
    return load_asset().version


def render_system_prompt() -> str:
    return load_asset().system


def render_user_prompt(text: str, user_conditions: tuple[str, ...] = ()) -> str:
    """拼用户消息。用户手写的条件必须全部纳入，且权重不得低于画像自动解析出的同维度标准。"""
    conditions = [item.strip() for item in user_conditions if item.strip()]
    if conditions:
        lines = "\n".join(f"- {item}" for item in conditions)
        block = (
            "\n用户手动补充的判断条件（每行一条，**必须全部纳入标准，不得省略**）：\n"
            f"{lines}\n\n"
        )
    else:
        block = "\n"

    return Template(load_asset().user_template).substitute(
        query=text.strip(),
        conditions_block=block,
    )


# ── 内部实现 ──────────────────────────────────────────────────────────────

_asset: PromptAsset | None = None


def _load() -> PromptAsset:
    directory = prompt_dir()
    contract = load_contract()
    _check_contract_consistency(contract, directory)

    system_template = _read_text(directory / _SYSTEM_TEMPLATE)
    user_template = _read_text(directory / _USER_TEMPLATE)

    return PromptAsset(
        version=contract.version,
        system=_render_system(system_template, contract),
        user_template=user_template,
        contract=contract,
        directory=directory,
    )


def _render_system(template: str, contract: PromptContract) -> str:
    """把契约与运行态取值填进 system 模板。

    契约表由 `contract.json` 生成，而不是在 markdown 里手写一遍——
    手写的表会与枚举漂移，而漂移的后果是判定器解析不了模型输出。
    """
    rows = "\n".join(
        f"| {item.name} | {item.tokens_hint} | "
        f"{Template(item.expected_hint).substitute(enum_values='、'.join(item.enum_values))} |"
        for item in contract.categories
    )

    return Template(template).substitute(
        category_count=len(contract.categories),
        category_list=" / ".join(contract.category_names),
        default_weights="、".join(f"{name}={weight}" for name, weight in CATEGORY_WEIGHTS.items()),
        contract_table=rows,
        per_category_rule=_describe_per_category_rule(contract),
        lenient_categories=_join_names(contract.lenient_names),
        hard_weight_threshold=HARD_WEIGHT_THRESHOLD,
        min_criteria=contract.min_criteria,
        max_criteria=contract.max_criteria,
    )


def _describe_per_category_rule(contract: PromptContract) -> str:
    """由每维度上限生成硬性规则第 2 条，避免这条规则与契约表说的不是一回事。"""
    multi = [item for item in contract.categories if item.max_count > 1]
    if not multi:
        return "每个 category 最多一条。"
    limit = max(item.max_count for item in multi)
    return f"每个 category 最多一条；只有 {_join_names([item.name for item in multi])} 允许各最多 {limit} 条。"


def _join_names(names: list[str] | tuple[str, ...]) -> str:
    """中文并列：两个用「 与 」，三个及以上用「、」并留最后一项用「与」。"""
    items = list(names)
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} 与 {items[1]}"
    return "、".join(items[:-1]) + f" 与 {items[-1]}"


def _check_contract_consistency(contract: PromptContract, directory: Path) -> None:
    """契约文件与规则引擎的表必须逐项一致。

    两边都由人维护，改一处忘另一处会表现为「模型按新契约输出、判定器按旧契约拒绝」——
    看起来像模型故障，实际是配置漂移。这里让它加载时就失败。
    """
    declared = set(contract.category_names)
    if declared != set(_LLM_CATEGORIES):
        raise PromptAssetError(
            f"{directory / _CONTRACT_FILE} 的维度枚举与 criteria._LLM_CATEGORIES 不一致："
            f"相差 {sorted(declared ^ set(_LLM_CATEGORIES))}"
        )

    # funding 的取值集必须与规则引擎认识的融资阶段一致：不一致时模型会按契约输出
    # 一个判定器根本不认识的阶段，表现为「标准被逐条拒绝 → 整批降级」，
    # 看起来像模型故障，实际是契约漂移。
    funding = contract.spec("funding")
    if funding is not None and funding.expected_kind == "enum":
        known_stages = tuple(dict.fromkeys(stage for _keys, stage in FUNDING_KEYWORDS))
        if tuple(funding.enum_values) != known_stages:
            raise PromptAssetError(
                f"{directory / _CONTRACT_FILE} 中 funding.enum_values 与 "
                f"criteria.FUNDING_KEYWORDS 不一致：{funding.enum_values} vs {known_stages}"
            )

    for item in contract.categories:
        expected_max = _MAX_PER_CATEGORY.get(item.name, _DEFAULT_MAX_PER_CATEGORY)
        if item.max_count != expected_max:
            raise PromptAssetError(
                f"{directory / _CONTRACT_FILE} 中 {item.name} 的 max={item.max_count} "
                f"与 criteria._MAX_PER_CATEGORY 的 {expected_max} 不一致"
            )


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise PromptAssetError(
            f"提示词资产缺失：{path}。"
            f"它属于仓库文件而不是外部依赖，缺失说明检出损坏；"
            f"若用了 AIGET_LLM_PROMPT_DIR，请确认指向的目录里有 {_SYSTEM_TEMPLATE} 等文件。"
        )
    return path.read_text(encoding="utf-8").rstrip("\n")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PromptAssetError(f"提示词契约缺失：{path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PromptAssetError(f"{path} 不是合法 JSON：{error}") from error
    if not isinstance(raw, dict):
        raise PromptAssetError(f"{path} 的顶层必须是 JSON 对象")
    return raw


def _require_str(raw: dict[str, Any], key: str, path: Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PromptAssetError(f"{path} 缺少非空字符串字段 {key}")
    return value


def _require_int(raw: dict[str, Any], key: str, path: Path) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PromptAssetError(f"{path} 的 {key} 必须是整数")
    return value


def _require_bool(raw: dict[str, Any], key: str, path: Path) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise PromptAssetError(f"{path} 的 {key} 必须是布尔值")
    return value


def _require_list(raw: dict[str, Any], key: str, path: Path) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list) or not value:
        raise PromptAssetError(f"{path} 缺少非空数组字段 {key}")
    return value
