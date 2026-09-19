"""OpenAI 兼容的 Chat Completions 客户端。

## 为什么用标准库 urllib 而不是 httpx / openai SDK

这一层只做一件事：发一个 JSON POST、取回一个 JSON。用标准库换来两个好处——
**不新增依赖**，以及**降级路径不依赖第三方库的健康状况**。
真需要流式或异步时再换 httpx，接口形状（`complete_json`）不用变。

## 错误分类学

调用方需要据此决定「该重试、该降级，还是该提示用户改配置」，所以错误必须分类，
不能只抛一个笼统的 Exception。沿用 `providers.SourceError` 的同一套思路：

| kind | 含义 | 可重试 | 调用方的合理反应 |
| --- | --- | --- | --- |
| `not_configured` | 没开开关或没填密钥 | 否 | 直接用规则引擎 |
| `auth_failed` | 401/403，密钥无效 | 否 | 提示用户改配置 |
| `quota` | 402／余额不足 | 否 | 提示用户充值 |
| `invalid_request` | 400，模型名或参数不合法 | 否 | 提示用户改配置（响应体会带上服务端原话） |
| `rate_limited` | 429 | 是 | 稍后重试或降级 |
| `timeout` | 超时 | 是 | 降级 |
| `upstream` | 5xx | 是 | 降级 |
| `invalid_response` | 返回体不是预期的 JSON 形状 | 否 | 降级 |

**任何一条路径都不会把 api_key 写进异常或日志。**
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .config import get_settings

_MAX_ERROR_BODY = 300

# 解析失败时带进异常的内容预览长度。JSON 模式下解析失败只有两种原因——
# 被 max_tokens 截断，或模型在 JSON 外面裹了话——两者靠 finish_reason 与
# 开头几个字符就能区分，所以预览取开头就够，没必要整段灌进日志。
_MAX_CONTENT_PREVIEW = 160

_RETRYABLE_KINDS = frozenset({"rate_limited", "timeout", "upstream"})


@dataclass(frozen=True, slots=True)
class Completion:
    """一次成功调用：解析好的 JSON 对象 + 实际模型名 + 用量。

    用量必须带出来——「成本有界」这条约束要能观测才成立，
    不能在这一层丢掉再去反查。
    """

    data: dict[str, Any]
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        value = self.usage.get("total_tokens")
        return int(value) if isinstance(value, (int, float)) else 0

    @property
    def cached_tokens(self) -> int:
        """命中前缀缓存的 token 数。命中部分通常便宜一个数量级。"""
        value = self.usage.get("prompt_cache_hit_tokens")
        return int(value) if isinstance(value, (int, float)) else 0


class LlmError(RuntimeError):
    """一次 LLM 调用的失败。`kind` 是稳定的分类，`message` 面向开发者。"""

    def __init__(
        self,
        message: str,
        *,
        kind: str,
        status: int | None = None,
        details: str = "",
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.details = details

    @property
    def retryable(self) -> bool:
        return self.kind in _RETRYABLE_KINDS


def complete_json(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> Completion:
    """发一次对话补全并要求返回 JSON 对象。

    使用 `response_format={"type": "json_object"}` 做结构化输出约束——
    这是「LLM 输出必须可校验」的前置条件：拿到自由文本再正则抠 JSON 是不可靠的。
    """
    settings = get_settings()
    if not settings.enabled:
        raise LlmError("LLM 未开启（AIGET_LLM_ENABLED=false）", kind="not_configured")
    if not settings.configured:
        raise LlmError("LLM 已开启但缺少 AIGET_LLM_API_KEY", kind="not_configured")

    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens or settings.max_tokens,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        settings.endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
            "Accept": "application/json",
        },
    )

    raw = _send(request, settings.timeout_seconds)
    usage = raw.get("usage")
    return Completion(
        data=_extract_json(raw),
        model=str(raw.get("model") or ""),
        usage=usage if isinstance(usage, dict) else {},
    )


def _send(request: urllib.request.Request, timeout: int) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = _read_error_body(error)
        kind, status = _classify_http(error.code)
        raise LlmError(
            f"LLM 调用失败（HTTP {status}）：{details or error.reason}",
            kind=kind,
            status=status,
            details=details,
        ) from error
    except urllib.error.URLError as error:
        # URLError 会把 socket 超时也包进来，必须再分辨一次，
        # 否则超时会被误报成网络不可达，调用方就不会去重试。
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise LlmError(f"LLM 调用超时（>{timeout}s）", kind="timeout") from error
        raise LlmError(f"LLM 网络不可达：{error.reason}", kind="upstream") from error
    except (socket.timeout, TimeoutError) as error:
        raise LlmError(f"LLM 调用超时（>{timeout}s）", kind="timeout") from error
    except json.JSONDecodeError as error:
        raise LlmError("LLM 返回体不是合法 JSON", kind="invalid_response") from error


def _read_error_body(error: urllib.error.HTTPError) -> str:
    try:
        text = error.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — 读取错误响应体失败不应掩盖原始错误
        return ""
    text = text.strip()
    if not text:
        return ""
    # 服务端的 invalid_request 消息会直接列出可用的模型名，对排查极有价值，
    # 因此保留原文；但要截断，避免超长 HTML 错误页灌进日志。
    return text[:_MAX_ERROR_BODY]


def _classify_http(status: int) -> tuple[str, int]:
    if status in (401, 403):
        return "auth_failed", status
    if status == 402:
        return "quota", status
    if status == 429:
        return "rate_limited", status
    if status == 400:
        return "invalid_request", status
    if status >= 500:
        return "upstream", status
    return "invalid_request", status


def _extract_json(raw: dict[str, Any]) -> dict[str, Any]:
    """从补全响应里取出 message.content 并解析成 JSON 对象。

    解析失败时把 `finish_reason` 与内容开头一并写进异常：这两种信息决定了
    调用方该做什么——`length` 要调大 `AIGET_LLM_MAX_TOKENS`，
    其它值要去看 prompt 是否没约束住输出形状。没有它们，运维只能靠猜。
    """
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmError("LLM 返回体缺少 choices", kind="invalid_response")

    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        # 推理型模型偶尔会把内容全放进 reasoning_content 而 content 为空，
        # 这种返回对调用方毫无用处，归类为形状错误而不是「没匹配到」。
        raise LlmError(
            f"LLM 返回内容为空（finish_reason={first.get('finish_reason')}）",
            kind="invalid_response",
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        finish = first.get("finish_reason")
        hint = "，疑因输出被 max_tokens 截断" if finish == "length" else ""
        raise LlmError(
            f"LLM 返回的 content 不是合法 JSON（finish_reason={finish}{hint}）"
            f"：{content[:_MAX_CONTENT_PREVIEW]}",
            kind="invalid_response",
        ) from error

    if not isinstance(parsed, dict):
        raise LlmError("LLM 返回的 JSON 不是对象", kind="invalid_response")
    return parsed
