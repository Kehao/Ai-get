"""第 ② 步：从一批网页里认出实体，并初判是否符合画像。

## 为什么输入是**原始检索结果**，而不是别处的产出

这一步的价值恰恰在于能看见「常规过滤会丢掉的东西」：媒体页、榜单、行业综述里的实体。
喂给它经过过滤的结果，等于让它重复一遍已有的损失。

## 规模上限为什么是现在这个数

`_MAX_DOCUMENTS` / `_MAX_BODY_CHARS` 不是「越大越好」。模型的输出预算是有限的，
输入铺得越满、推理占用越多——实测出现过整批 `finish_reason=length`（内容直接为空、
一条都拿不回来）。260 字足够读出「谁、什么时候、融了多少」这类关键句，
把预算留给输出才划算。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Sequence

from . import prompts
from ..common.protocols import JsonLlm
from .spec import DiscoverySpec

logger = logging.getLogger(__name__)

_MAX_DOCUMENTS = 16
_MAX_BODY_CHARS = 260
_MAX_OUTPUT_TOKENS = 8192
_BATCH_SIZE = 5
_MAX_ROUNDS = 3
"""提炼按批走：每轮让模型只出 `_BATCH_SIZE` 家**新**实体，最多 `_MAX_ROUNDS` 轮。

为什么拆：一次要求输出 10+ 家 × 20 字段，输出预算（8192 tokens）经常撞
`finish_reason=length` 整批截断。每轮 5 家输出小而稳，还能在轮与轮之间把
已落库的行先给调用方（前端逐批显示）。轮数封顶 3 是成本闸——第 3 轮还满，
说明这批网页料很足，也到此为止。
"""


def extract_entities(
    profile: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    llm: JsonLlm,
    spec: DiscoverySpec,
    on_batch: Callable[[tuple[dict, ...]], None] | None = None,
    max_documents: int = _MAX_DOCUMENTS,
    max_rounds: int = _MAX_ROUNDS,
    batch_size: int = _BATCH_SIZE,
) -> tuple[dict, ...]:
    """把一批检索结果提炼成候选 dict 列表（**分批多轮**）。

    三个规模参数都有默认值；调用方可以按前端「结果数量」放大（见 adapters 的折算）：
    `max_documents` 读多少条网页、`max_rounds` 最多提几轮、`batch_size` 每轮几家企业。

    每轮要求模型最多认出 `batch_size` 家**新**实体（已找到的放进提示词让它避开），
    `on_batch` 在每轮结束时收到该批产出——调用方可以先把这批落库/上屏，再等下一轮。
    某轮一无所获或不足一批时提前停：模型自己表示「榨干了」，别再花一轮的钱。

    `documents` 是**原始**检索结果（`title` / `url` / `content` 等，见 `protocols`）。
    画像为空或没有网页时返回空元组，**一次模型调用都不发**。
    模型失败会把异常透出去——「模型挂了」与「这批网页里没有实体」必须能被区分。
    """
    profile = profile.strip()
    if not profile or not documents:
        return ()

    rendered = render_documents(documents, max_documents=max_documents)
    system = prompts.render(
        "extract.system.md",
        entity=spec.entity,
        field_table=spec.field_table(),
        json_fields=spec.json_fields(),
        max_output=str(batch_size),
    )
    found: list[dict] = []
    seen: set[str] = set()
    for round_index in range(max_rounds):
        found_names = "、".join(item["name"] for item in found) if found else "（暂无）"
        user = prompts.render(
            "extract.user.md",
            entity=spec.entity,
            profile=profile,
            documents=rendered,
            found_names=found_names,
        )
        # 每轮重试一次：模型偶发超时（实测 30s 档不少见）不该让整场发现清零——
        # 前几轮已到手的批次照常保留，最后一轮失败也只是少一批。
        completion = None
        for attempt in (1, 2):
            try:
                completion = llm.complete_json(
                    system, user, temperature=0.0, max_tokens=_MAX_OUTPUT_TOKENS
                )
                break
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    logger.warning(
                        "提炼第 %d 轮两次调用均失败，带着已获得的 %d 家收场",
                        round_index + 1,
                        len(found),
                        exc_info=True,
                    )
        if completion is None:
            break
        batch = tuple(
            item for item in parse_entities(completion, spec=spec) if item["name"] not in seen
        )
        if not batch:
            break
        seen.update(item["name"] for item in batch)
        found.extend(batch)
        if on_batch is not None:
            try:
                on_batch(batch)
            except Exception:  # noqa: BLE001 — 回调是调用方的上屏路径，不该打断提炼
                logger.warning("on_batch 回调失败（本批实体已保留）", exc_info=True)
        if len(batch) < batch_size:
            break
    return tuple(found)


def render_documents(
    documents: Sequence[Mapping[str, Any]],
    *,
    max_documents: int = _MAX_DOCUMENTS,
    max_body_chars: int = _MAX_BODY_CHARS,
) -> str:
    """把检索结果压成紧凑文本。序号留给模型引用，方便它说清依据来自第几条。"""
    lines: list[str] = []
    for index, item in enumerate(documents[:max_documents], start=1):
        title = str(item.get("title", "")).strip()
        site = str(item.get("website", "")).strip()
        date = str(item.get("date", "")).strip()
        url = str(item.get("url", "")).strip()
        body = " ".join(str(item.get("content", "")).split())[:max_body_chars]
        lines.append(
            f"[{index}] {title}\n    站点：{site}　日期：{date}\n    URL：{url}\n    正文：{body}"
        )
    return "\n".join(lines)


def parse_entities(data: Mapping[str, Any], *, spec: DiscoverySpec) -> tuple[dict, ...]:
    """校验输出形状并按字段表归一化。

    档案的键**由 spec.fields 决定**——配置加字段，这里的输出自动跟上。
    只丢无名记录，**不丢 `matched` 为假的记录**：后者是「否决依据」，
    带回去才能解释「为什么这批网页没有产出候选」。直接扔掉会让调用方
    分不清「没提炼出实体」和「提炼出了但都不符合」。
    """
    raw = data.get("entities")
    if raw is None:
        raw = data.get("companies")  # 兼容旧版提示词的输出键
    if not isinstance(raw, list):
        raise ValueError("提炼结果缺少 entities 数组")

    entities: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue  # 无名记录进列表只能白占一行

        candidate: dict[str, Any] = {"name": name}
        for field in spec.fields:
            value = item.get(field.name)
            if field.is_list:
                candidate[field.name] = (
                    tuple(str(part).strip() for part in value if str(part).strip())
                    if isinstance(value, list)
                    else ()
                )
            else:
                candidate[field.name] = str(value or "").strip()
        candidate["evidence_url"] = str(item.get("evidence_url", "")).strip()
        candidate["matched"] = as_bool(item.get("matched"))
        candidate["reason"] = str(item.get("reason", "")).strip()
        entities.append(candidate)
    return tuple(entities)


def as_bool(value: Any) -> bool:
    """把模型给的布尔值归一化。

    要求 JSON 输出**只保证 JSON 合法，不保证字段类型**：模型返回字符串 `"false"` 时，
    `bool("false")` 是 `True`——一条本该被否决的记录会当场变成符合项，
    而下游正是拿 `matched` 做过滤。这个坑必须在这一层堵死。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


if __name__ == "__main__":
    # 自检：不联网、不调模型（`python -m app.agents.discovery.extract`）。
    from .spec import DiscoverySpec, FieldSpec

    test_spec = DiscoverySpec(
        name="test",
        entity="公司",
        fields=(
            FieldSpec("domain", "官网", required=True),
            FieldSpec("summary", "简介", required=True),
            FieldSpec("products", "产品", kind="list"),
        ),
    )

    rendered = render_documents(({"title": "甲", "url": "https://a.com", "content": "字" * 500},))
    assert rendered.count("字") == _MAX_BODY_CHARS, rendered.count("字")

    assert as_bool("false") is False and as_bool("true") is True
    assert as_bool(True) is True and as_bool(None) is False

    parsed = parse_entities(
        {
            "entities": [
                {"name": "甲", "products": ["P1", " ", "P2"]},
                {"name": "   "},
                "不是对象",
                {"name": "乙", "matched": "true", "reason": "字符串真值"},
                {"name": "丙", "matched": "false"},
            ]
        },
        spec=test_spec,
    )
    assert [item["name"] for item in parsed] == ["甲", "乙", "丙"], parsed
    assert parsed[0]["products"] == ("P1", "P2"), "字段表驱动的列表解析"
    assert parsed[0]["summary"] == "" and parsed[0]["domain"] == "", "字段表之外/缺失的键按空处理"

    legacy = parse_entities({"companies": [{"name": "旧版"}]}, spec=test_spec)
    assert legacy[0]["name"] == "旧版", "旧输出键仍要认"
    try:
        parse_entities({}, spec=test_spec)
    except ValueError:
        pass
    else:
        raise AssertionError("缺数组时应当抛 ValueError")

    print(f"extract 自检通过（正文截断 {_MAX_BODY_CHARS} 字，解析 {len(parsed)} 条）")
