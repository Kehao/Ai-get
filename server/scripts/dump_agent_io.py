"""把 discovery-agent 每一步的输入输出落盘留档。

用途有两个：

1. **生成留档**：手工分步执行 agent 的三段，把每步的输入与输出原样写成 JSON，
   落到 `server/data/agent-run/`。想看「agent 每步吃什么吐什么」、想对比改动前后的
   数据形状，跑它。
2. **补注说明**（`--annotate`）：给已经落盘的文件注入 `_meta` 说明块（数据本身不动）。
   适合「数据是旧的、说明是后来才写的」这种场面。

⚠️ 会覆盖 `server/data/agent-run/` 下的同名文件；真实调用百度与 DeepSeek，
跑一次约 40 秒、几分钱。跑之前想留旧数据，先拷目录。

用法：

    # 生成留档（覆盖式）
    .venv/bin/python scripts/dump_agent_io.py

    # 只给已有文件补说明，不重新生成
    .venv/bin/python scripts/dump_agent_io.py --annotate
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.adapters import (  # noqa: E402
    BaiduWebSearch,
    ProjectJsonLlm,
    ProjectPageFetcher,
    load_project_spec,
)
from discovery_agent.deep_dive import deepen_entity  # noqa: E402
from discovery_agent.extract import extract_entities  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "agent-run"
PROFILE = "近 6 个月完成融资的 SaaS 公司"

# 每个文件的「户口」：是什么、哪来的、给谁用。生成与补注共用这一份，保证口径一致。
FILE_NOTES: dict[str, dict[str, str]] = {
    "01-search-input.json": {
        "是什么": "agent 第①步「检索」的输入参数",
        "哪来的": "由 dump_agent_io.py 构造：query 就是用户画像原文，top_k 来自 agent 配置的 budget.search_top_k",
        "给谁用": "WebSearch 协议的实现。本项目里是 BaiduWebSearch → 百度千帆 /v2/ai_search/chat/completions（纯搜索模式）",
    },
    "01-search-output.json": {
        "是什么": "第①步「检索」的输出：一批原始网页（本次 20 条）",
        "哪来的": "百度千帆 /v2/ai_search/chat/completions 的返回，原样落盘（18 个字段全部保留）",
        "给谁用": "② 提炼的输入（见 02-extract-input.json）；③ 深挖的 L1 也会按 url 重新抓全文",
        "注意": "整条链路只实际使用 title / url / content / website / date 五个字段，其余是百度自己的元数据",
    },
    "02-extract-input.json": {
        "是什么": "agent 第②步「提炼」的输入 = 用户画像 + 第①步的全部网页",
        "哪来的": "dump_agent_io.py 组装（documents 原样透传自 01 的输出）",
        "给谁用": "JsonLlm 协议的实现。本项目里是 DeepSeek deepseek-flash；system 提示词来自独立包的 prompts/extract.system.md",
        "注意": "这是整条链路成本的大头：66KB 正文全靠模型读",
    },
    "02-extract-output.json": {
        "是什么": "第②步「提炼」的输出：从 20 条网页里认出的实体清单（本次 12 家）",
        "哪来的": "模型输出（entities 数组），经 parse_entities 校验归一化",
        "给谁用": "调用方据此决定深挖哪几家（默认取前 max_entities=3 家）；深挖的 name/domain 初始值也来自这里",
        "注意": "matched 为 false 的记录**有意保留**——它们解释了为什么某些网页没产出候选",
    },
    "03-deepen-input.json": {
        "是什么": "agent 第③步「深挖」的输入 = 画像 + 目标实体名 + 现有域名 + 同一批网页",
        "哪来的": "dump_agent_io.py 组装（取提炼结果的第 1 家；documents 原样透传）",
        "给谁用": "deepen_entity：L1 抓已知页、L2 搜「<名> 官网」、L3 按缺口定向检索，全部从这份材料出发",
        "注意": "深挖**不吃**提炼的二手结论，回原始材料找线索——所以它能发现提炼阶段漏掉的官网等信息，代价是同一批材料被模型读两次",
    },
    "03-deepen-output.json": {
        "是什么": "第③步「深挖」的输出：一份补全后的完整档案（本次是江苏领健智能科技有限公司）",
        "哪来的": "模型整理输出，经 parse_dossier 按字段表校验归一化；L2 搜到官网后实体名会变成工商全称",
        "给谁用": "调用方。本项目里写入 TargetCompany 的对应字段并落库（domain→website、summary→ai_summary、…）",
        "注意": "档案的键由配置的字段表决定；加字段只需改 server/agent-configs/company-discovery.json",
    },
}


def _meta(name: str, *, generated_at: str | None = None) -> dict:
    note = dict(FILE_NOTES[name])
    note["生成时间"] = generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note["生成脚本"] = "server/scripts/dump_agent_io.py"
    return note


def _write(path: Path, name: str, payload, *, generated_at: str) -> None:
    # 统一包一层：`_meta` 是户口说明，`data` 才是真实数据。
    # 不直接把 `_meta` 并进顶层，是因为检索与提炼的输出顶层本来就是数组。
    document = {"_meta": _meta(name, generated_at=generated_at), "data": payload}
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, default=list), encoding="utf-8"
    )
    print(f"    {name:<30} {path.stat().st_size:>7,} 字节")


def dump_all() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    spec = load_project_spec()
    llm = ProjectJsonLlm()
    search = BaiduWebSearch()
    fetcher = ProjectPageFetcher()

    print(f"画像：{PROFILE}\n")

    print("① 检索（走 WebSearch 协议 → 百度）")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write(
        OUT_DIR / "01-search-input.json",
        "01-search-input.json",
        {"query": PROFILE, "top_k": spec.budget.search_top_k, "site": spec.site or None},
        generated_at=generated,
    )
    documents = search.search(PROFILE, top_k=spec.budget.search_top_k)
    documents = list(documents)
    _write(
        OUT_DIR / "01-search-output.json", "01-search-output.json", documents,
        generated_at=generated,
    )

    print("② 提炼（走 JsonLlm 协议 → DeepSeek）")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write(
        OUT_DIR / "02-extract-input.json",
        "02-extract-input.json",
        {"profile": PROFILE, "documents": documents},
        generated_at=generated,
    )
    entities = extract_entities(PROFILE, documents, llm=llm, spec=spec)
    entities = list(entities)
    _write(
        OUT_DIR / "02-extract-output.json", "02-extract-output.json", entities,
        generated_at=generated,
    )

    print("③ 深挖（三个协议一起）")
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    first = entities[0]
    _write(
        OUT_DIR / "03-deepen-input.json",
        "03-deepen-input.json",
        {
            "profile": PROFILE,
            "name": first["name"],
            "domain": first["domain"],
            "documents": documents,
        },
        generated_at=generated,
    )
    dossier = deepen_entity(
        PROFILE,
        first["name"],
        documents,
        llm=llm,
        search=search,
        fetcher=fetcher,
        spec=spec,
        domain=str(first.get("domain", "")),
    )
    _write(
        OUT_DIR / "03-deepen-output.json", "03-deepen-output.json", dossier,
        generated_at=generated,
    )


def annotate_existing() -> None:
    """给已落盘的文件补 `_meta`，数据本身一个字节不动。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"给 {OUT_DIR} 下的文件补说明（数据不动，只加 _meta）：")
    for name in FILE_NOTES:
        path = OUT_DIR / name
        if not path.is_file():
            print(f"    跳过 {name}（文件不存在）")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.pop("_meta", None)  # 重复注入时剥掉旧的说明，避免嵌套
        document = {"_meta": _meta(name, generated_at=now), "data": data}
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, default=list), encoding="utf-8"
        )
        print(f"    已注入 {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--annotate",
        action="store_true",
        help="只给已有文件补 _meta 说明，不重新生成数据",
    )
    args = parser.parse_args()

    if args.annotate:
        annotate_existing()
    else:
        dump_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
