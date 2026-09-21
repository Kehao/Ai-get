"""实体发现 agent（当前位于 `app/agents/`，开发阶段）。

一句画像进去，一批补全后的档案出来：

```
① 检索网页  →  ② 提炼实体  →  ③ 逐级深挖补全
```

## 模块导览（`common/` 为跨 agent 共享，`discovery/` 为实体发现 agent）

| 模块 | 职责 |
| --- | --- |
| `common.protocols` | 三个依赖协议：`WebSearch` / `PageFetcher` / `JsonLlm` |
| `common.builtin` | 内置实现：OpenAI 兼容 LLM 客户端 + 标准库网页抓取器 |
| `common.domains` | 注册域提取与「非实体官网」站点清单 |
| `company_discovery.spec` | 配置模型（`DiscoverySpec` / 字段表 / 预算），配置在 `company_discovery/configs/` |
| `company_discovery.prompts` | 提示词模板（`prompts/*.md` 随代码走）与渲染 |
| `company_discovery.extract` | ② 提炼：从网页里认出实体并初判 |
| `company_discovery.deep_dive` | ③ 深挖：三级递进补全（抓已知页 → 搜官网 → 按缺口定向检索） |
| `company_discovery.agent` | ①+②+③ 的串联编排与步骤日志 |
| `company_discovery.cli` | 命令行（`python -m app.agents.discovery.cli`） |
| `company_discovery.adapters` | **本项目的适配器**：把百度搜索 / DeepSeek / 抓取接进协议（唯一对外部的依赖点） |

## 三个依赖协议

搜索、抓取、模型都通过 `Protocol` 注入——不必继承基类、不必 import 本包：

| 协议 | 失败时 | 为什么 |
| --- | --- | --- |
| `WebSearch` | **抛异常** | 检索是链路前提，「源挂了」不能伪装成「没搜到」 |
| `PageFetcher` | 返回空串 | 抓取只是补材料，少一页不该整条失败 |
| `JsonLlm` | **抛异常** | 「模型挂了」与「模型说没有」必须可区分 |

**不内置搜索**：各家 API 差别太大，造「通用适配层」只会假装通用。

## 两段式入口

| 段 | 函数 | 说明 |
| --- | --- | --- |
| ①+② | `discover_entities(profile, documents=None, …)` | 检索 + 提炼，产出候选清单 |
| ③ | `deepen_entity(profile, name, documents, …)` | 对一家实体补全档案，参数＝名字 + 原始网页 |
| 串联 | `run_discovery_agent(profile, …)` | ①②③一口气跑完，带 steps 日志 |

## ⚠️ 命名注意

这里的 "agent" 是技术意义上的自主流程；`routers/agents.py` 与
`repositories/agents.py` 里的「训练智能体」是产品话术里的**销售智能体**，
两者不是一回事，只是英文词撞了。

## 成熟后的独立路径

本目录的模块刻意保持**零内部依赖**（不 import `app.*` 的其它部分——唯一的例外
是 `adapters.py`，它本来就是项目与包之间的耦合层），配置与提示词都随目录走。
成熟后整体拷出、补一份 `pyproject.toml` 即可成为独立包，`adapters.py` 留在项目里当耦合层。
"""

from __future__ import annotations

from .company_discovery.adapters import (
    BaiduWebSearch,
    ProjectJsonLlm,
    ProjectPageFetcher,
    deepen_project_entity,
    discover_project_entities,
    load_project_spec,
)
from .company_discovery.agent import AgentStep, DiscoveryRun, discover_entities, run_discovery_agent
from .common.builtin import HttpFetcher, LlmError, OpenAiCompatibleLlm
from .company_discovery.deep_dive import deepen_entity
from .common.domains import extract_domain, is_skippable, registrable_domain
from .company_discovery.extract import extract_entities
from .common.protocols import JsonLlm, PageFetcher, WebSearch
from .company_discovery.spec import Budget, DiscoverySpec, FieldSpec, SpecError, load_spec, read_spec

__version__ = "0.2.0.dev"

__all__ = [
    "AgentStep",
    "Budget",
    "BaiduWebSearch",
    "DiscoveryRun",
    "DiscoverySpec",
    "FieldSpec",
    "HttpFetcher",
    "JsonLlm",
    "LlmError",
    "OpenAiCompatibleLlm",
    "PageFetcher",
    "ProjectJsonLlm",
    "ProjectPageFetcher",
    "SpecError",
    "WebSearch",
    "__version__",
    "deepen_entity",
    "deepen_project_entity",
    "discover_entities",
    "discover_project_entities",
    "extract_domain",
    "extract_entities",
    "is_skippable",
    "load_project_spec",
    "load_spec",
    "read_spec",
    "registrable_domain",
    "run_discovery_agent",
]
