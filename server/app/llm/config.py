"""LLM 接入的集中配置。

所有开关都从环境变量读取，而环境变量的来源统一是 `server/.env`
（由 `app.config` 在导入时加载）。新增开关时**只改这一个文件**，
业务代码一律通过 `get_settings()` 拿值，不要在别处直接读 `os.environ`。

## 两个状态需要区分

- `enabled`：配置里是否显式打开了 LLM。默认 **false**——安全默认是「不产生外部请求」，
  这样别人 clone 下来跑不会因为漏配 key 而每个请求都超时。
- `configured`：是否真的填了 API key。
- `usable` = 两者同时成立。业务代码只判断 `usable`。

分开的理由：`enabled=true` 但忘了填 key 是最常见的配置错误，
把它和「没开」区分开，才能在界面上给出「已开启但缺少密钥」这种可操作的提示。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

# 仅为触发 `app.config` 里的 .env 加载。顺序很重要：必须先加载，再读 os.environ。
from .. import config as _app_config  # noqa: F401

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_SECONDS = 30
# 4096 而不是更省的值：max_tokens 是**上限不是目标**，正常输出用不到它，
# 只有 JSON 被截断时才会触顶。实测过一次长画像触发 2000 截断导致整批标准降级，
# 而截断的代价（标准质量下滑且静默）远大于把上限留宽一点。
DEFAULT_MAX_TOKENS = 4096


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int, *, low: int, high: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(float(raw))
    except ValueError:
        return default
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class LlmSettings:
    """一次进程生命周期内不变的 LLM 配置快照。"""

    enabled: bool
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int
    max_tokens: int
    judge_enabled: bool

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def usable(self) -> bool:
        """真正可以发起调用：既打开了开关，也填了密钥。"""
        return self.enabled and self.configured

    @property
    def endpoint(self) -> str:
        """补齐到 `/chat/completions`。允许用户只填到域名。"""
        base = self.base_url.strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def describe(self) -> dict[str, object]:
        """对外可安全暴露的自描述。**永远不包含 api_key**。"""
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "usable": self.usable,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            # 输出上限要暴露：诊断「为什么这批标准降级了」时，
            # 第一件要看的就是它——JSON 被截断是 JSON 模式最主要的失败原因。
            "max_tokens": self.max_tokens,
            "judge_enabled": self.judge_enabled,
        }


def load_settings() -> LlmSettings:
    settings = LlmSettings(
        enabled=_flag("AIGET_LLM_ENABLED", False),
        base_url=os.environ.get("AIGET_LLM_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        model=os.environ.get("AIGET_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
        api_key=os.environ.get("AIGET_LLM_API_KEY", ""),
        timeout_seconds=_int("AIGET_LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, low=3, high=180),
        max_tokens=_int("AIGET_LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS, low=256, high=16000),
        judge_enabled=_flag("AIGET_LLM_JUDGE_ENABLED", False),
    )
    if settings.judge_enabled:
        # 这个开关目前**没有被任何代码读取**：L3 判定仍是纯规则的。
        # 显式告警而不是静默忽略——打开它却什么都不发生，比没有这个开关更坏。
        logger.warning(
            "AIGET_LLM_JUDGE_ENABLED=true，但 L3 的 LLM 判定路径尚未实现，本次仍走规则判定"
        )
    return settings


_settings: LlmSettings | None = None


def get_settings() -> LlmSettings:
    """进程内缓存。改 .env 需要重启，这与项目「内存单例」的整体约定一致。"""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """仅供测试：丢弃缓存，使下一次 `get_settings()` 重读环境变量。"""
    global _settings
    _settings = None
