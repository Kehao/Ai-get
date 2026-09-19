"""姓名匹配：判断「档案上的名字」与「画像里写的名字」是不是同一个人。

放在这里而不是放在数据源或判定层里，是因为它**被两侧同时需要**：
- 召回层（`providers/mock_source`）用它决定谁排前面；
- 判定层（`qualification/person_judge`）用它给出「姓名是否匹配」这一条结论。

两侧分属不同层，谁 import 谁都会形成环，所以归一化与匹配规则必须落在两者之下。

## 匹配等级，而不是布尔值

同一个人的名字在公开档案里会写成 `Ke-Hao R.A. Chiu`、`Kehao Qiu`、`QIU Kehao`、`陈可航`
等多种形态，所以「命中」本身也分程度：

| 等级 | 含义 | 例子 |
| --- | --- | --- |
| `full` | 整个名字对上了 | 条件写「陈可航」，档案写 `Kehang Chen / 陈可航` |
| `partial` | 只对上了名字的一段 | 条件写「陈」，或写「陈可」（只写了姓或半个名） |
| `none` | 没有对上 | 条件写「陈」，档案是 `花岳成 / Yuecheng Hua` |

区分两者的原因是判定口径：`full` 才可以判「符合」，`partial` 只能判「不确定」——
「姓陈」不足以认定就是这个人，但也**不能算作不符合**。

## 两条规则按字符集分开

- **中文**：允许子串（`陈可` ⊂ `陈可航`）。中文信息密度高，两个字已经足够指向一个人。
- **拉丁**：不做子串，只认「从两端连续取词再拼接」的结果。拉丁字母密度低，
  `chen` 在 `yuecheng hua` 的任意一段里都可能出现，子串命中会把「按人名找人」
  这种唯一答案式检索变成一堆噪声。

单字提示（`陈`、`l`）整体跳过：中文单字命中率过低，会把姓名条件变成噪声。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence

NameMatchLevel = Literal["full", "partial", "none"]

# 名字里允许出现的分隔符：空格、连字符、点号、间隔号。它们不该影响「是不是同一个人」。
_NAME_NOISE = re.compile(r"[\s\-_.·・]+")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")

# 低于这个长度的提示一律不作为姓名依据。
MIN_HINT_LENGTH = 2


@dataclass(frozen=True, slots=True)
class NameMatch:
    """一次姓名匹配的结果，带上「是谁对上的」，便于结论文案直接引用。"""

    level: NameMatchLevel = "none"
    hint: str = ""
    form: str = ""

    @property
    def matched(self) -> bool:
        return self.level != "none"

    @property
    def is_full(self) -> bool:
        return self.level == "full"


@dataclass(frozen=True, slots=True)
class NameForms:
    """一条档案上所有可用来比对的姓名形态。"""

    # 归一化后的中文写法与拉丁全名（整名相等即可判定 full）
    full: frozenset[str]
    # 拉丁写法里的单个词（姓或名），命中只算 partial
    tokens: frozenset[str]


def normalize_name(value: str) -> str:
    """姓名比对前的归一化：去掉分隔符再统一小写。"""
    return _NAME_NOISE.sub("", value).lower()


def _latin_tokens(value: str) -> list[str]:
    return [token.lower() for token in _LATIN_WORD.findall(value)]


def name_forms(values: Sequence[str]) -> NameForms:
    """把一条档案上的若干姓名写法展开成可比对的形态集合。"""
    full: set[str] = set()
    tokens: set[str] = set()

    for value in values:
        if not value or not value.strip():
            continue
        if _CJK.search(value):
            full.add(normalize_name(value))

        words = _latin_tokens(value)
        if not words:
            continue
        tokens.update(words)
        # 从两端连续取词拼接：`Ke-Hao R.A. Chiu` 的 `kehao`、`Chen Kehang` 的 `chenkehang`
        # 都能命中，而 `yuecheng hua` 里的一段 `chen` 不会。
        for size in range(2, len(words) + 1):
            full.add("".join(words[:size]))
            full.add("".join(words[-size:]))
        # 倒序全名：档案写 `Kehao Qiu`、条件写 `Qiu Kehao` 时仍然算同一个人。
        full.add("".join(reversed(words)))

    return NameForms(full=frozenset(full), tokens=frozenset(tokens))


def match_name(values: Sequence[str], hints: Sequence[str]) -> NameMatch:
    """在一条档案的若干姓名写法里查这些提示，返回**最高**的匹配等级。

    任何一个提示完整命中就直接返回——`full` 不会被后一个提示的 `partial` 覆盖。
    """
    forms = name_forms(values)
    best = NameMatch()

    for hint in hints:
        needle = normalize_name(hint)
        if len(needle) < MIN_HINT_LENGTH:
            continue

        if _CJK.search(needle):
            if needle in forms.full:
                return NameMatch("full", hint, needle)
            if best.level == "none":
                form = next((item for item in forms.full if needle in item), None)
                if form is not None:
                    best = NameMatch("partial", hint, form)
            continue

        if needle in forms.full:
            return NameMatch("full", hint, needle)
        if best.level == "none" and needle in forms.tokens:
            best = NameMatch("partial", hint, needle)

    return best
