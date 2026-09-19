#!/usr/bin/env python3
"""「画像 → 加权判定标准」输出的白名单校验器。

为什么必须有这一层：下游判定器会**直接解析**结构化字段（`expected` 拿去 split、
`tokens` 拿去做子串匹配）。模型偶尔会把 `size.expected` 写成「50 人以下」这种
人类友好但机器解析不了的值——不在这里拦下来，就会在很远的地方崩，且难以定位。

契约从 `contract.json` 读（与本技能目录的提示词渲染同源），所以**改契约只改那一个文件**，
提示词与校验器不会各说各话。

用法：
    python3 validate_criteria.py criteria.json
    cat criteria.json | python3 validate_criteria.py
    python3 validate_criteria.py criteria.json --json
    python3 validate_criteria.py criteria.json --contract /path/to/contract.json

退出码：0 = 全部合规；1 = 存在不合规项（逐条报到 stderr）；2 = 输入或契约不可读。
纯标准库、无网络、无副作用。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# 契约默认与脚本同目录的上一级（scripts/ → 技能根）。
_DEFAULT_CONTRACT = Path(__file__).resolve().parents[1] / "contract.json"

MAX_NAME_CHARS = 22
MAX_QUESTION_CHARS = 80
MAX_NOTE_CHARS = 60
MAX_TOKEN_CHARS = 30
MAX_TOKENS = 20

_RANGE_RE = re.compile(r"^(\d+):(\d+)$")


class ContractError(RuntimeError):
    """契约文件缺失或格式不对。"""


class Contract:
    """契约的只读视图。移植到新领域时改 `contract.json`，不碰这个类。"""

    def __init__(self, raw: dict[str, Any], path: Path) -> None:
        self.path = path
        self.version = str(raw.get("version", "")) or "(未声明)"
        self.min_criteria = self._int(raw, "min_criteria", path)
        self.max_criteria = self._int(raw, "max_criteria", path)

        categories = raw.get("categories")
        if not isinstance(categories, list) or not categories:
            raise ContractError(f"{path} 缺少非空 categories 数组")
        self.categories: list[dict[str, Any]] = []
        for index, item in enumerate(categories):
            if not isinstance(item, dict) or not item.get("name"):
                raise ContractError(f"{path} 的 categories[{index}] 缺少 name")
            self.categories.append(item)

        self.by_name = {str(item["name"]): item for item in self.categories}

    @staticmethod
    def _int(raw: dict[str, Any], key: str, path: Path) -> int:
        value = raw.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ContractError(f"{path} 的 {key} 必须是整数")
        return value

    def all_category_names(self) -> list[str]:
        return [str(item["name"]) for item in self.categories]

    def load(path: Path) -> "Contract":
        if not path.is_file():
            raise ContractError(f"读不到契约文件：{path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ContractError(f"{path} 不是合法 JSON：{error}") from error
        if not isinstance(raw, dict):
            raise ContractError(f"{path} 的顶层必须是 JSON 对象")
        return Contract(raw, path)


def _is_int(value: object) -> bool:
    """bool 是 int 的子类，必须显式排除，否则 True 会被当成 weight=1。"""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_one(index: int, item: object, contract: Contract) -> list[str]:
    """校验单条标准。返回错误消息列表（空列表 = 合规）。"""
    where = f"criteria[{index}]"
    if not isinstance(item, dict):
        return [f"{where}: 必须是对象，实际是 {type(item).__name__}"]

    errors: list[str] = []
    category = item.get("category")
    spec = contract.by_name.get(str(category))
    if spec is None:
        return [
            f"{where}.category: 必须是 {'/'.join(contract.all_category_names())} 之一，"
            f"实际是 {category!r}"
        ]

    where = f"{where}({category})"
    lenient_required = bool(spec.get("lenient", False))

    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{where}.name: 必须是非空字符串")
    elif len(name) > MAX_NAME_CHARS:
        errors.append(f"{where}.name: 超过 {MAX_NAME_CHARS} 字（实际 {len(name)}）：{name!r}")

    question = item.get("question")
    if not isinstance(question, str) or not question.strip():
        errors.append(f"{where}.question: 必须是非空字符串")
    elif not question.rstrip().endswith(("?", "？")):
        errors.append(f"{where}.question: 必须以问号结尾：{question!r}")
    elif len(question) > MAX_QUESTION_CHARS:
        errors.append(f"{where}.question: 超过 {MAX_QUESTION_CHARS} 字（实际 {len(question)}）")

    weight = item.get("weight")
    if not _is_int(weight) or not 1 <= weight <= 5:
        errors.append(f"{where}.weight: 必须是 1-5 的整数，实际是 {weight!r}")

    lenient = item.get("lenient")
    if not isinstance(lenient, bool):
        errors.append(f"{where}.lenient: 必须是布尔值，实际是 {lenient!r}")
    elif lenient_required and not lenient:
        errors.append(
            f"{where}.lenient: {category} 必须为 true"
            "（公开资料没写到 ≠ 该特征不成立，判成「不符合」会让冷门领域集体掉档）"
        )
    elif not lenient_required and lenient:
        errors.append(f"{where}.lenient: {category} 必须为 false")

    errors.extend(_check_tokens(where, spec, item.get("tokens")))
    errors.extend(_check_expected(where, spec, item.get("expected")))

    note = item.get("note", "")
    if not isinstance(note, str):
        errors.append(f"{where}.note: 必须是字符串，实际是 {type(note).__name__}")
    elif len(note) > MAX_NOTE_CHARS:
        errors.append(f"{where}.note: 超过 {MAX_NOTE_CHARS} 字（实际 {len(note)}）")

    return errors


def _check_tokens(where: str, spec: dict[str, Any], tokens: object) -> list[str]:
    category = spec["name"]
    if not isinstance(tokens, list):
        return [f"{where}.tokens: 必须是数组，实际是 {type(tokens).__name__}"]

    if spec.get("tokens_must_be_empty"):
        if tokens:
            return [
                f"{where}.tokens: {category} 用结构化取值表达，必须为空数组 []，"
                f"实际有 {len(tokens)} 项"
            ]
        return []

    if not tokens:
        return [f"{where}.tokens: {category} 依赖子串匹配，必须给出至少一个关键词"]

    errors: list[str] = []
    if len(tokens) > MAX_TOKENS:
        errors.append(f"{where}.tokens: 最多 {MAX_TOKENS} 个，实际 {len(tokens)} 个")
    for position, token in enumerate(tokens):
        if not isinstance(token, str) or not token.strip():
            errors.append(f"{where}.tokens[{position}]: 必须是非空字符串，实际是 {token!r}")
        elif len(token) > MAX_TOKEN_CHARS:
            errors.append(
                f"{where}.tokens[{position}]: 单条关键词超过 {MAX_TOKEN_CHARS} 字"
                f"（不要写句子）：{token!r}"
            )
    return errors


def _check_expected(where: str, spec: dict[str, Any], expected: object) -> list[str]:
    category = spec["name"]
    kind = str(spec.get("expected_kind", "text"))

    if not isinstance(expected, str):
        return [f"{where}.expected: 必须是字符串，实际是 {type(expected).__name__}"]

    if kind == "enum":
        allowed = [str(value) for value in (spec.get("enum_values") or [])]
        if not allowed:
            return [f"{where}.expected: 契约里 {category} 声明为 enum 但没给 enum_values"]
        if expected not in allowed:
            return [f"{where}.expected: 必须是「{'、'.join(allowed)}」之一，实际是 {expected!r}"]
        return []

    if kind == "range":
        matched = _RANGE_RE.match(expected.strip())
        if matched is None:
            return [
                f"{where}.expected: 必须是「最小值:最大值」用**英文**冒号连接的两个整数"
                f"（如 '0:50'），实际是 {expected!r}"
            ]
        low, high = int(matched.group(1)), int(matched.group(2))
        if low > high:
            return [f"{where}.expected: 下界大于上界（{expected!r}）"]
        return []

    if kind == "empty":
        if expected != "":
            return [f"{where}.expected: {category} 的取值必须为空字符串 \"\"，实际是 {expected!r}"]
        return []

    # kind == "text"：取值是给展示用的名称，非空即可
    if not expected.strip():
        return [f"{where}.expected: {category} 必须给出取值名称（不能为空）"]
    return []


def validate(payload: object, contract: Contract) -> list[str]:
    """校验整批输出，返回全部错误消息。"""
    if not isinstance(payload, dict):
        return [f"顶层必须是 JSON 对象，实际是 {type(payload).__name__}"]

    items = payload.get("criteria")
    if not isinstance(items, list):
        return ["顶层缺少 criteria 数组"]

    errors: list[str] = []
    if not contract.min_criteria <= len(items) <= contract.max_criteria:
        errors.append(
            f"标准条数必须在 {contract.min_criteria}~{contract.max_criteria} 之间，"
            f"实际 {len(items)} 条"
        )

    for index, item in enumerate(items):
        errors.extend(_check_one(index, item, contract))

    # 每维度条数上限。放在逐条校验之后，这样单条的错误先报，读起来更清楚。
    counts: dict[str, int] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("category"), str):
            counts[item["category"]] = counts.get(item["category"], 0) + 1
    for category, count in counts.items():
        spec = contract.by_name.get(category)
        if spec is None:
            continue
        limit = int(spec.get("max", 1))
        if count > limit:
            errors.append(f"category={category} 最多 {limit} 条，实际 {count} 条")

    return errors


def _load_payload(source: str | None) -> object:
    if source is None:
        return json.load(sys.stdin)
    with open(source, encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str]) -> int:
    args = argv[1:]
    as_json = "--json" in args
    args = [item for item in args if item != "--json"]

    contract_path = _DEFAULT_CONTRACT
    if "--contract" in args:
        position = args.index("--contract")
        if position + 1 >= len(args):
            print("--contract 后面要跟一个路径", file=sys.stderr)
            return 2
        contract_path = Path(args[position + 1]).expanduser().resolve()
        del args[position : position + 2]

    try:
        contract = Contract.load(contract_path)
    except ContractError as error:
        print(f"契约不可用：{error}", file=sys.stderr)
        return 2

    try:
        payload = _load_payload(args[0] if args else None)
    except FileNotFoundError:
        print(f"读不到文件：{args[0]}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"输入不是合法 JSON：{error}", file=sys.stderr)
        return 2

    errors = validate(payload, contract)

    if as_json:
        print(
            json.dumps(
                {"ok": not errors, "version": contract.version, "errors": errors},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif errors:
        for message in errors:
            print(f"✗ {message}", file=sys.stderr)
    else:
        total = len(payload.get("criteria", [])) if isinstance(payload, dict) else 0
        print(f"✓ {total} 条标准全部合规（契约 {contract.version}）")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
