"""内置实现：标准库版的网页抓取器，与 OpenAI 兼容的 LLM 客户端。

**它们不是必需品**——三个依赖都是协议，宿主可以换成自己的。提供内置实现只是为了让
「开箱能跑」成立：

- **抓取**与**LLM** 有通用协议可循（HTTP 取文本；OpenAI 的 `/chat/completions` 已是事实标准）；
- **搜索没有**通用协议（各家 API 的请求体、鉴权、返回结构差别太大），
  所以 `WebSearch` 必须由宿主提供。这不是偷懒，是拒绝造一个假装通用的适配层。

零第三方依赖：`urllib` + `json` + `html.parser` 就够。
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from typing import Any, Mapping
from urllib.parse import urljoin

# ── 网页抓取 ──────────────────────────────────────────────────────────────

_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "head", "template"})

# 块级标签的边界补一个换行，让抽出来的文本保留段落感而不是糊成一行。
_BLOCK_TAGS = frozenset(
    {
        "p", "div", "br", "li", "tr", "td", "th", "section", "article",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr",
    }
)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class HttpFetcher:
    """标准库实现的网页抓取器：取 HTML、去标签、返回纯文本。

    实现 `PageFetcher` 协议——**失败返回空串**，不抛。
    另提供 `fetch_links`（可选扩展）：抽页面里的链接，供深挖 v2 做子页探索。
    """

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_bytes: int = 400_000,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.headers = {**_DEFAULT_HEADERS, **(headers or {})}

    def fetch(self, url: str, *, max_chars: int) -> str:
        return extract_text(self._download(url))[:max_chars]

    def fetch_links(self, url: str, *, max_links: int = 60) -> list[str]:
        return extract_links(self._download(url, html_only=True), url)[:max_links]

    def _download(self, url: str, *, html_only: bool = False) -> str:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return ""

        raw = b""
        charset = ""
        try:
            request = urllib.request.Request(url, headers=dict(self.headers))
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if getattr(response, "status", 200) != 200:
                    return ""
                content_type = str(response.headers.get("Content-Type", "")).lower()
                allowed = ("html",) if html_only else ("html", "text/")
                if not any(kind in content_type for kind in allowed):
                    return ""
                charset = response.headers.get_content_charset() or ""
                # 边读边截：正文只需要前几百 KB，遇到大文件不必下完。
                raw = response.read(self.max_bytes)
        except Exception:  # noqa: BLE001 — 抓取失败不区分原因，统一降级成「没抓到」
            return ""

        return decode(raw, charset)


class _TextExtractor(HTMLParser):
    """把 HTML 抽成文本。只认标签边界，不做 DOM 树。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        lines = (line.strip() for line in "".join(self._chunks).splitlines())
        return "\n".join(line for line in lines if line)


def extract_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — 半截 HTML 也能用，能抽多少抽多少
        pass
    return parser.text()


class _LinkExtractor(HTMLParser):
    """只收集 `<a href>`。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value and value.strip():
                self.hrefs.append(value.strip())


def extract_links(html: str, base_url: str) -> list[str]:
    """href → 绝对 URL：丢掉锚点/脚本/邮件协议，按出现顺序去重。

    不做同域过滤——那是深挖层（拿着注册域）的事，抓取层不懂业务。
    """
    parser = _LinkExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — 半截 HTML 也能用
        pass

    seen: set[str] = set()
    links: list[str] = []
    for href in parser.hrefs:
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href).split("#", 1)[0]
        if not absolute.startswith(("http://", "https://")) or absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


def decode(raw: bytes, charset: str = "") -> str:
    """按「响应头声明 → UTF-8 → 中文常见编码」的顺序试，全失败就宽松解码。

    中文站点里 GBK/GB18030 仍然常见，只按 UTF-8 解会得到一片乱码，
    而**乱码喂给模型比不喂更糟**——它会煞有介事地「总结」出错误内容。
    """
    for candidate in (charset, "utf-8", "gb18030"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


# ── OpenAI 兼容客户端 ────────────────────────────────────────────────────

_RETRYABLE_KINDS = frozenset({"rate_limited", "timeout", "upstream"})
_MAX_ERROR_BODY = 300
_MAX_CONTENT_PREVIEW = 160


class LlmError(RuntimeError):
    """一次模型调用的失败。`kind` 是稳定分类，调用方据此决定重试还是降级。"""

    def __init__(self, message: str, *, kind: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status

    @property
    def retryable(self) -> bool:
        return self.kind in _RETRYABLE_KINDS


class OpenAiCompatibleLlm:
    """任何 OpenAI 兼容端点（`/chat/completions` + `response_format=json_object`）。

    覆盖 DeepSeek、Moonshot、通义、vLLM、Ollama 等一票服务。实现 `JsonLlm` 协议——
    **失败抛 `LlmError`**，不返回空 dict。

    ⚠️ `max_tokens` 是「输出上限」，推理型模型的自省内容也算在里面。实测输入铺得太满时
    会出现 `finish_reason=length` 且内容为空，所以要给足输出预算、别把输入堆满。
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def complete_json(
        self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 4096
    ) -> Mapping[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        return extract_json_object(self._send(request))

    def _send(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = _read_error_body(error)
            kind, status = _classify_http(error.code)
            raise LlmError(
                f"模型调用失败（HTTP {status}）：{details or error.reason}",
                kind=kind,
                status=status,
            ) from error
        except urllib.error.URLError as error:
            # URLError 会把 socket 超时也包进来，必须再分辨一次，
            # 否则超时会被误报成网络不可达，调用方就不会去重试。
            if isinstance(error.reason, (socket.timeout, TimeoutError)):
                raise LlmError(f"模型调用超时（>{self.timeout}s）", kind="timeout") from error
            raise LlmError(f"模型网络不可达：{error.reason}", kind="upstream") from error
        except (socket.timeout, TimeoutError) as error:
            raise LlmError(f"模型调用超时（>{self.timeout}s）", kind="timeout") from error
        except json.JSONDecodeError as error:
            raise LlmError("模型返回体不是合法 JSON", kind="invalid_response") from error


def extract_json_object(raw: Mapping[str, Any]) -> dict[str, Any]:
    """从补全响应里取出 `message.content` 并解析成 JSON 对象。

    解析失败时把 `finish_reason` 与内容开头一并写进异常：这两样决定了调用方该做什么
    ——`length` 要调大输出预算，其它值要去看提示词是不是没约束住输出形状。
    """
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmError("模型返回体缺少 choices", kind="invalid_response")

    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        # 推理型模型偶尔把内容全放进 reasoning_content、而 content 为空，
        # 这种返回对调用方毫无用处，归类为形状错误而不是「没匹配到」。
        raise LlmError(
            f"模型返回内容为空（finish_reason={first.get('finish_reason')}）",
            kind="invalid_response",
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        finish = first.get("finish_reason")
        hint = "，疑因输出被 max_tokens 截断" if finish == "length" else ""
        raise LlmError(
            f"模型返回的 content 不是合法 JSON（finish_reason={finish}{hint}）："
            f"{content[:_MAX_CONTENT_PREVIEW]}",
            kind="invalid_response",
        ) from error

    if not isinstance(parsed, dict):
        raise LlmError("模型返回的 JSON 不是对象", kind="invalid_response")
    return parsed


def _read_error_body(error: urllib.error.HTTPError) -> str:
    try:
        text = error.read().decode("utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 — 读错误响应体失败不应掩盖原始错误
        return ""
    # 服务端的 invalid_request 常会直接列出可用模型名，对排查极有价值，保留原文但截断，
    # 免得超长 HTML 错误页灌进日志。
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


if __name__ == "__main__":
    # 自检：不联网（`python -m discovery_agent.builtin`）。
    sample = """
    <html><head><title>示例</title><style>body{color:red}</style></head>
    <body><script>var a = 1;</script><h1>标题</h1><p>第一段</p><p>第二段</p></body></html>
    """
    text = extract_text(sample)
    assert "标题" in text and "第一段" in text and "第二段" in text, text
    assert "var a" not in text, "脚本内容不该进正文"
    assert "color:red" not in text, "样式内容不该进正文"
    assert "示例" not in text, "title 不该重复出现在正文里"
    assert HttpFetcher().fetch("ftp://example.com", max_chars=100) == "", "非 http(s) 直接返回空"
    assert decode("<p>中文</p>".encode("gb18030")) == "<p>中文</p>", "GBK 兜底解码"

    links = extract_links(
        '<a href="/a">A</a><a href="/a">重复</a><a href="mailto:x@y.z">邮</a>'
        '<a href="#top">锚</a><a href="https://b.com/p#f">外</a>',
        "https://a.com/home/",
    )
    assert links == ["https://a.com/a", "https://b.com/p"], links

    llm = OpenAiCompatibleLlm(base_url="https://api.example.com/v1/", model="m")
    assert llm.endpoint == "https://api.example.com/v1/chat/completions", "去掉多余的斜杠"

    assert extract_json_object({"choices": [{"message": {"content": '{"a":1}'}}]}) == {"a": 1}
    for bad, reason in (
        ({}, "缺 choices"),
        ({"choices": []}, "空 choices"),
        ({"choices": [{"message": {"content": "  "}}]}, "空内容"),
        ({"choices": [{"message": {"content": "不是 JSON"}}]}, "非法内容"),
        ({"choices": [{"message": {"content": "[1,2]"}}]}, "不是对象"),
    ):
        try:
            extract_json_object(bad)
        except LlmError:
            continue
        raise AssertionError(f"应当拒绝：{reason}")

    assert _classify_http(429) == ("rate_limited", 429) and _classify_http(503) == ("upstream", 503)
    assert LlmError("x", kind="timeout").retryable and not LlmError("x", kind="auth_failed").retryable

    print("builtin 自检通过（HTTP 抓取 + OpenAI 兼容客户端）")
