"""L0 提示词的加载与渲染（企业与个人两份契约）。

## 提示词的真源在技能目录，不在这个文件里

提示词正文与契约表放在 **`skills/`** 下的两个项目级技能目录：

- 企业模式：`skills/profile-to-company-criteria/`
- 个人模式：`skills/profile-to-person-criteria/`

这里只负责三件事：读文件、把运行时取值填进模板、缓存。
为什么不再内嵌一份 Python 副本：同一段文字有两份副本**必然漂移**，而
「这批标准是哪版 prompt 产出的」要写进任务记录——漂移会让溯源失效。

两个技能都是**自包含的通用资产**：提示词、契约、占位符填法、白名单校验规则
全部写在技能目录里，第三方不需要读本仓库任何代码即可接入任意 LLM——
本模块只是其中一个接入方。服务端的白名单校验实现在 `qualification/criteria.py`
与 `person_criteria.py`，它们与契约的一致性由加载断言保证（见下）。

## 两种模式为什么是两份契约

判机构与判自然人**回答的不是同一个问题**：企业的维度是行业/规模/融资，
个人的维度是姓名/职位/职级。共用一份契约的后果是要么个人画像产出规模标准、
要么企业画像产出姓名标准。两份契约各自与自己的规则引擎表做一致性断言。

## 两份提示词模板逐段对应

`criteria.system.md` / `criteria.user.md` 在两个技能里**结构一一对应**
（角色行、判对象声明、硬性规则 1-5 平行；中间是各自领域规则；末两条相同措辞）。
改任何一版文案时，同步检查另一版是否需要对应修改——对应关系本身也是约定。

## 取值从哪来

模板里的占位符分两类：

- **结构类**（维度枚举、每维度条数上限、宽松维度、`expected` 取值集合）来自
  各自的 `contract.json`——它是契约的单一来源，改契约只改它；
- **运行态类**（默认权重、硬性权重阈值）来自 `qualification/` 下各自的规则引擎模块。
  这些是规则引擎自己的表，不能让技能目录另存一份。

两类之间的一致性在加载时**逐项断言**（见 `_check_contract_consistency`）：
不一致就抛错。这不是防御性编程——它是「改了契约表却忘了改另一处」唯一能被立刻发现的地方。

## 输入与输出（两模式各一例）

输入是**画像原文 + 可选的手写补充条件**（由 `render_user_prompt` 拼成 user 消息，
见下方函数 docstring）；输出是模型返回的 `{"criteria": [...]}`——**不含 reachability**，
它由接入方在判定前统一补。字段含义见各技能 SKILL.md 的「输出契约」一节。

企业模式（profile-to-company-criteria）：

    输入 query：杭州的 SaaS 小微企业，员工 50 人以下

    输出（节选 3 条）：
    {"criteria": [
      {"category": "geo", "name": "地域：杭州",
       "question": "公司是否位于杭州？", "weight": 5,
       "tokens": ["杭州"], "expected": "杭州", "lenient": false, "note": ""},
      {"category": "size", "name": "规模：50人以下",
       "question": "员工规模是否不超过 50 人？", "weight": 3,
       "tokens": [], "expected": "0:50", "lenient": false, "note": ""},
      {"category": "signal", "name": "动态：正在招聘",
       "question": "近期是否有招聘、融资等公开动作？", "weight": 2,
       "tokens": ["招聘", "在招"], "expected": "", "lenient": true, "note": ""}
    ]}

    注意：size 的 tokens 必须是空数组、expected 必须是「最小:最大」（"0:50"）；
    signal 是宽松维度（lenient=true），expected 必须是空字符串。

个人模式（profile-to-person-criteria）：

    输入 query：找云安全公司的 CMO 或市场总监，最好新上任

    输出（节选 3 条）：
    {"criteria": [
      {"category": "title", "name": "职位：市场",
       "question": "现任职位是否负责市场职能？", "weight": 4,
       "tokens": ["市场", "marketing", "CMO", "品牌"], "expected": "市场", "lenient": false, "note": ""},
      {"category": "seniority", "name": "职级：管理层",
       "question": "职级是否达到管理层或更高？", "weight": 3,
       "tokens": ["总监", "head of", "director"], "expected": "管理层", "lenient": false, "note": ""},
      {"category": "signal", "name": "动态：新上任",
       "question": "近期是否有新上任的公开动态？", "weight": 2,
       "tokens": ["新上任", "履新"], "expected": "", "lenient": true, "note": ""}
    ]}

    注意：seniority 的 expected 取画像里出现的**最低**一档
    （「CMO 或市场总监」→「管理层」而不是「决策层」）；tokens 中英文都要给。

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
from typing import Any, Literal

from ..qualification.criteria import (
    CATEGORY_WEIGHTS,
    FUNDING_KEYWORDS,
    HARD_WEIGHT_THRESHOLD,
    _DEFAULT_MAX_PER_CATEGORY,
    _LLM_CATEGORIES,
    _MAX_PER_CATEGORY,
)
from ..qualification.person_criteria import (
    PERSON_CATEGORY_WEIGHTS,
    SENIORITY_LADDER,
    _DEFAULT_MAX_PER_CATEGORY as _PERSON_DEFAULT_MAX,
    _LLM_CATEGORIES as _PERSON_LLM_CATEGORIES,
    _MAX_PER_CATEGORY as _PERSON_MAX_PER_CATEGORY,
)

# 两种模式各自的默认技能目录与覆盖用环境变量。
# 企业沿用 AIGET_LLM_PROMPT_DIR（历史配置不失效）；个人用独立开关。
PromptMode = Literal["company", "people"]

DEFAULT_PROMPT_DIRS: dict[str, str] = {
    "company": "skills/profile-to-company-criteria",
    "people": "skills/profile-to-person-criteria",
}

_PROMPT_DIR_ENV_VARS: dict[str, str] = {
    "company": "AIGET_LLM_PROMPT_DIR",
    "people": "AIGET_LLM_PERSON_PROMPT_DIR",
}

# 模板文件名。改文件名要同步改对应技能的 SKILL.md。
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
    mode: str


def prompt_dir_label(mode: str = "company") -> str:
    """提示词目录的**可读标识**：配置里写的是什么就显示什么，不展开成绝对路径。

    给界面用。排查「这批标准用的哪份提示词」时，看配置值比看一长串绝对路径有用。
    """
    return os.environ.get(_PROMPT_DIR_ENV_VARS[mode], "").strip() or DEFAULT_PROMPT_DIRS[mode]


def prompt_dir(mode: str = "company") -> Path:
    """提示词目录的绝对路径，供读文件用。相对路径以仓库根为基准。"""
    path = Path(prompt_dir_label(mode))
    if not path.is_absolute():
        # app/llm/prompts.py → parents[3] 是仓库根
        path = Path(__file__).resolve().parents[3] / path
    return path


def load_contract(mode: str = "company") -> PromptContract:
    """读 `contract.json`。字段缺失或类型不对时抛出可定位的错误。"""
    path = prompt_dir(mode) / _CONTRACT_FILE
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


def load_asset(mode: str = "company") -> PromptAsset:
    """读取并渲染提示词。首次调用读盘，之后走缓存（按模式各缓存一份）。"""
    asset = _assets.get(mode)
    if asset is None:
        asset = _load(mode)
        _assets[mode] = asset
    return asset


def reset_cache() -> None:
    """仅供测试与非默认目录切换后使用。"""
    _assets.clear()


def prompt_version(mode: str = "company") -> str:
    return load_asset(mode).version


def render_system_prompt(mode: str = "company") -> str:
    return load_asset(mode).system


def render_user_prompt(text: str, user_conditions: tuple[str, ...] = (), mode: str = "company") -> str:
    """拼用户消息：画像原文 + 用户手写的补充条件。

    有手写条件时逐行列出并声明「必须全部纳入标准，不得省略」；没有时留空行，
    保持模板形状不变。⚠️ 这段条件块的文案是目前**唯一留在代码里的提示词正文**——
    `string.Template` 表达不了「有条件才出现标题」的条件分支，只能在这里拼。
    改措辞改这里，不要去改技能目录的 criteria.user.md（那边只有 $query 和
    $conditions_block 两个占位符）。
    """
    conditions = [item.strip() for item in user_conditions if item.strip()]
    if conditions:
        lines = "\n".join(f"- {item}" for item in conditions)
        block = (
            "\n用户手动补充的判断条件（每行一条，**必须全部纳入标准，不得省略**）：\n"
            f"{lines}\n\n"
        )
    else:
        block = "\n"

    return Template(load_asset(mode).user_template).substitute(
        query=text.strip(),
        conditions_block=block,
    )


# ── 内部实现 ──────────────────────────────────────────────────────────────

_assets: dict[str, PromptAsset] = {}


def _load(mode: str) -> PromptAsset:
    directory = prompt_dir(mode)
    contract = load_contract(mode)
    _check_contract_consistency(contract, directory, mode)

    system_template = _read_text(directory / _SYSTEM_TEMPLATE)
    user_template = _read_text(directory / _USER_TEMPLATE)

    return PromptAsset(
        version=contract.version,
        system=_render_system(system_template, contract, mode),
        user_template=user_template,
        contract=contract,
        directory=directory,
        mode=mode,
    )


def _render_system(template: str, contract: PromptContract, mode: str) -> str:
    """把契约与运行态取值填进 system 模板。

    契约表由 `contract.json` 生成，而不是在 markdown 里手写一遍——
    手写的表会与枚举漂移，而漂移的后果是判定器解析不了模型输出。
    默认权重来自**当前模式的规则引擎表**，不在契约里另存一份。
    """
    weights = CATEGORY_WEIGHTS if mode == "company" else PERSON_CATEGORY_WEIGHTS
    rows = "\n".join(
        f"| {item.name} | {item.tokens_hint} | "
        f"{Template(item.expected_hint).substitute(enum_values='、'.join(item.enum_values))} |"
        for item in contract.categories
    )

    return Template(template).substitute(
        category_count=len(contract.categories),
        category_list=" / ".join(contract.category_names),
        default_weights="、".join(f"{name}={weight}" for name, weight in weights.items()),
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


def _check_contract_consistency(contract: PromptContract, directory: Path, mode: str) -> None:
    """契约文件与对应模式规则引擎的表必须逐项一致。

    两边都由人维护，改一处忘另一处会表现为「模型按新契约输出、判定器按旧契约拒绝」——
    看起来像模型故障，实际是配置漂移。这里让它加载时就失败。
    """
    if mode == "people":
        _check_person_contract(contract, directory)
        return

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


def _check_person_contract(contract: PromptContract, directory: Path) -> None:
    """个人契约与 person_criteria 规则引擎表的逐项断言。思路与企业侧相同。"""
    declared = set(contract.category_names)
    if declared != set(_PERSON_LLM_CATEGORIES):
        raise PromptAssetError(
            f"{directory / _CONTRACT_FILE} 的维度枚举与 person_criteria._LLM_CATEGORIES 不一致："
            f"相差 {sorted(declared ^ set(_PERSON_LLM_CATEGORIES))}"
        )

    # seniority 的取值集必须与职级阶梯一致：阶梯改了档位名而契约没跟，
    # 模型输出的 expected 会被判定器整条拒绝，表现同企业侧的 funding 漂移。
    seniority = contract.spec("seniority")
    if seniority is not None and seniority.expected_kind == "enum":
        if tuple(seniority.enum_values) != SENIORITY_LADDER:
            raise PromptAssetError(
                f"{directory / _CONTRACT_FILE} 中 seniority.enum_values 与 "
                f"person_criteria.SENIORITY_LADDER 不一致：{seniority.enum_values} vs {SENIORITY_LADDER}"
            )

    for item in contract.categories:
        expected_max = _PERSON_MAX_PER_CATEGORY.get(item.name, _PERSON_DEFAULT_MAX)
        if item.max_count != expected_max:
            raise PromptAssetError(
                f"{directory / _CONTRACT_FILE} 中 {item.name} 的 max={item.max_count} "
                f"与 person_criteria._MAX_PER_CATEGORY 的 {expected_max} 不一致"
            )


def _read_text(path: Path) -> str:
    if not path.is_file():
        raise PromptAssetError(
            f"提示词资产缺失：{path}。"
            f"它属于仓库文件而不是外部依赖，缺失说明检出损坏；"
            f"若用了提示词目录环境变量，请确认指向的目录里有 {_SYSTEM_TEMPLATE} 等文件。"
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
