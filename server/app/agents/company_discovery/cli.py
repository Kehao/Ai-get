"""命令行入口。

```bash
discovery-agent configs                    # 列出可用配置
discovery-agent show company-discovery     # 看某份配置的字段表与预算
discovery-agent run "近 6 个月完成融资的 SaaS 公司" \
    --search my_project.search:build_search \
    --llm-base-url https://api.deepseek.com \
    --llm-model deepseek-chat \
    --llm-api-key "$DEEPSEEK_KEY"
```

⚠️ `--search` 指向**你自己的**搜索实现，格式是 `模块:工厂函数`。
本包不含搜索服务，理由见 `protocols` 里 `WebSearch` 的说明——
各家搜索 API 差别太大，造一个「通用适配层」只会假装通用。

LLM 的三项也可以通过环境变量给：`DISCOVERY_AGENT_LLM_BASE_URL` /
`DISCOVERY_AGENT_LLM_MODEL` / `DISCOVERY_AGENT_LLM_API_KEY`。
配置文件目录用 `DISCOVERY_AGENT_CONFIGS` 覆盖。
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .agent import run_discovery_agent
from ..common.builtin import HttpFetcher, OpenAiCompatibleLlm
from .spec import DEFAULT_SPEC_NAME, SpecError, candidate_dirs, load_spec


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="discovery-agent",
        description="配置驱动的实体发现 agent：检索网页 → 提炼实体 → 逐级补全档案。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("configs", help="列出可用配置")

    show = sub.add_parser("show", help="查看一份配置的字段表与预算")
    show.add_argument("name", nargs="?", default=DEFAULT_SPEC_NAME)

    run = sub.add_parser("run", help="跑一次发现")
    run.add_argument("profile", help="画像，例如「近 6 个月完成融资的 SaaS 公司」")
    run.add_argument("--spec", default=DEFAULT_SPEC_NAME, help="配置名或路径")
    run.add_argument(
        "--search",
        required=True,
        metavar="模块:工厂函数",
        help="你的搜索实现。工厂函数会被无参调用，返回一个 WebSearch",
    )
    run.add_argument(
        "--llm-base-url", default=os.environ.get("DISCOVERY_AGENT_LLM_BASE_URL", "")
    )
    run.add_argument("--llm-model", default=os.environ.get("DISCOVERY_AGENT_LLM_MODEL", ""))
    run.add_argument("--llm-api-key", default=os.environ.get("DISCOVERY_AGENT_LLM_API_KEY", ""))
    run.add_argument("--llm-timeout", type=float, default=60.0)
    run.add_argument("--output", help="把完整结果写成 JSON 到这个文件（默认打到 stdout）")

    args = parser.parse_args(argv)

    if args.command == "configs":
        return _list_configs()
    if args.command == "show":
        return _show_spec(args.name)
    return _run(args)


def _list_configs() -> int:
    seen: set[str] = set()
    for directory in candidate_dirs():
        if not directory.is_dir():
            continue
        print(f"# {directory}")
        for path in sorted(directory.glob("*.json")):
            mark = " " if path.stem in seen else "*"
            seen.add(path.stem)
            print(f"  {mark} {path.stem}")
    if not seen:
        print("（没有找到任何配置；用 DISCOVERY_AGENT_CONFIGS 指定目录）")
    return 0


def _show_spec(name: str) -> int:
    try:
        spec = load_spec(name)
    except SpecError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    print(f"配置：{spec.name}　实体：{spec.entity}　字段 {len(spec.fields)} 个")
    print("\n字段表：")
    for item in spec.fields:
        flags = []
        if item.required:
            flags.append("必填")
        if item.is_list:
            flags.append("多值")
        hint = f"　检索词「{item.search_hint}」" if item.search_hint else ""
        print(f"  {item.name:<18} {item.label:<12} {'／'.join(flags) or '可选'}{hint}")
    print("\n预算：")
    # 用 dataclasses.fields 而不是 vars()：Budget 是 slots dataclass，根本没有 __dict__。
    for item in dataclasses.fields(spec.budget):
        print(f"  {item.name:<22} {getattr(spec.budget, item.name)}")
    if spec.query:
        print(f"\n固定查询：{spec.query}")
    if spec.site:
        print(f"限定站点：{spec.site}")
    if spec.skip_hosts:
        print(f"额外跳过：{'、'.join(spec.skip_hosts)}")
    return 0


def _run(args: argparse.Namespace) -> int:
    if not args.llm_base_url or not args.llm_model:
        print(
            "错误：需要 --llm-base-url 与 --llm-model（或用 DISCOVERY_AGENT_LLM_* 环境变量）",
            file=sys.stderr,
        )
        return 2

    try:
        spec = load_spec(args.spec)
    except SpecError as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2

    try:
        search = _load_factory(args.search)()
    except Exception as error:  # noqa: BLE001 — 启动期的错误要给出可操作的提示
        print(f"错误：无法构造搜索实现（{args.search}）：{error}", file=sys.stderr)
        return 2

    llm = OpenAiCompatibleLlm(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout=args.llm_timeout,
    )

    try:
        run = run_discovery_agent(
            args.profile, llm=llm, search=search, fetcher=HttpFetcher(), spec=spec
        )
    except Exception as error:  # noqa: BLE001 — 顶层把异常转成退出码，别甩一屏堆栈
        print(f"运行失败：{error}", file=sys.stderr)
        return 1

    payload = run.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=list)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"已写入 {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


def _load_factory(path: str) -> Callable[[], Any]:
    module_name, _, attr = path.partition(":")
    if not module_name or not attr:
        raise ValueError(f"要写成「模块:工厂函数」，收到 {path!r}")
    module = importlib.import_module(module_name)
    factory = getattr(module, attr, None)
    if factory is None:
        raise ValueError(f"{module_name} 里没有 {attr}")
    if not callable(factory):
        raise ValueError(f"{path} 不是可调用的工厂函数")
    return factory


if __name__ == "__main__":
    raise SystemExit(main())
