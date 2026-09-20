"""LLM 接入层。

## 这一层负责什么

只负责**把外部模型变成一个会说结构化 JSON 的、会失败的外部依赖**：

- `config`：全部开关从 `server/.env` 读，默认关闭（不产生外部请求）。
- `client`：OpenAI 兼容的最小客户端（标准库实现，零新增依赖）+ 错误分类学。
- `prompts`：版本化的 L0 prompt，约束输出结构。
- `generator`：生成 + 缓存 + 统计。

## 这一层刻意不负责什么

**不构造业务对象、不做 schema 校验。** 输出校验放在 `qualification/criteria.py`，
因为那里才是 `Criterion` 的定义处，校验规则的单一来源不能散落。

调用的开关与降级策略由调用方决定——`criteria.build_criteria_detailed()` 在失败时
回退到规则引擎，所以 LLM 不可用只会让标准「差一些」，不会让功能「不可用」。

## 怎么打开

1. 在 `server/.env` 里设 `AIGET_LLM_ENABLED=true` 与 `AIGET_LLM_API_KEY=...`（见 `.env.example`）；
2. 重启后端。`.env` 只被 `app.config` 在导入时读一次，改完不重启不会生效。

模型名必须用服务端认可的名字。DeepSeek 目前只认 `deepseek-flash` 与 `deepseek-v4-pro`
（`deepseek-chat` 是 `deepseek-flash` 的别名）；写错时服务端会在错误体里回一份可用列表，
`client` 会原样保留这段信息，所以报错时看日志最后一行就能知道该填什么。
"""

from __future__ import annotations

from .client import Completion, LlmError, complete_json
from .config import LlmSettings, get_settings, reset_settings
from .generator import GenerationResult, GenerationStats, generate_criteria, stats
from .prompts import (
    PromptAsset,
    PromptAssetError,
    PromptContract,
    load_asset,
    prompt_dir,
    prompt_dir_label,
    prompt_version,
    render_system_prompt,
    render_user_prompt,
)


def person_prompt_dir_label() -> str:
    """人物契约目录的可读标识（状态接口用）。"""
    return prompt_dir_label("people")


def person_prompt_version() -> str:
    """人物契约的版本号（状态接口用）。"""
    return prompt_version("people")

__all__ = [
    "Completion",
    "GenerationResult",
    "GenerationStats",
    "LlmError",
    "LlmSettings",
    "PromptAsset",
    "PromptAssetError",
    "PromptContract",
    "complete_json",
    "generate_criteria",
    "get_settings",
    "load_asset",
    "person_prompt_dir_label",
    "person_prompt_version",
    "prompt_dir",
    "prompt_dir_label",
    "prompt_version",
    "render_system_prompt",
    "render_user_prompt",
    "reset_settings",
    "stats",
]
