"""网页抓取：把一个 URL 变成可读文本。

## 为什么召回链路一直不需要它，现在却需要

百度源的 `content` 字段本来就是**正文主体**（中位 483~1031 字），所以召回从来
不必爬原网页。但「按企业深挖」是另一回事：企业官网首页、关于我们页里的信息
（成立时间、规模、业务线、客户案例）根本不在那 20 条检索结果里，只能抓。

## 边界

- 只抓公开页面：不执行 JS、不解析非 HTML 内容、不带登录态。
- **抓取失败是常态，不是异常**：反爬、超时、非 200、编码错乱一律返回空串。
  少一个信息源而已，不该让整条链路失败。这与「源失败不得伪装成空结果」不冲突
  ——那条纪律针对的是**召回**（用户会以为市场上没有这类企业）；这里是锦上添花的信息补全。
- 用标准库 `html.parser` 抽文本，不引入解析器依赖：我们需要的是「去掉标签」，
  不是「查询 DOM」。
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

_TIMEOUT_SECONDS = 15
_MAX_BYTES = 400_000
_DEFAULT_MAX_CHARS = 3000
_DEFAULT_MAX_LINKS = 60

# 这些标签的**内容**不该进正文（脚本是代码、样式是 CSS），要整段跳过。
_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "head", "template"})

# 块级标签的边界补一个换行，让抽出来的文本保留段落感而不是糊成一行。
_BLOCK_TAGS = frozenset(
    {
        "p", "div", "br", "li", "tr", "td", "th", "section", "article",
        "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr",
    }
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _download(url: str, *, html_only: bool = False) -> str:
    """抓取 `url` 并解码成 HTML；任何失败都返回空串。

    `html_only=True` 时连 `text/*` 也不要——那是给「抽链接/图标」用的：
    把纯文本响应当 HTML 解析只会产出垃圾候选。
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return ""

    raw = b""
    charset = ""
    try:
        with requests.get(url, headers=_HEADERS, timeout=_TIMEOUT_SECONDS, stream=True) as response:
            if response.status_code != 200:
                return ""
            content_type = response.headers.get("Content-Type", "").lower()
            allowed = ("html", "text/") if not html_only else ("html",)
            if not any(kind in content_type for kind in allowed):
                return ""
            charset = response.encoding or ""
            # 边读边截：正文只需要前几百 KB，遇到大文件不必下完。
            raw = response.raw.read(_MAX_BYTES, decode_content=True)
    except Exception:  # noqa: BLE001 — 抓取失败不区分原因，统一降级成「没抓到」
        return ""

    return _decode(raw, charset)


def fetch_page_text(url: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """抓取 `url` 并抽成纯文本；任何失败都返回空串。"""
    return _extract_text(_download(url))[:max_chars]


def fetch_page_links(url: str, *, max_links: int = _DEFAULT_MAX_LINKS) -> list[str]:
    """抓取 `url` 并抽出页面里的链接（绝对 URL，按出现顺序去重）；失败返回空列表。

    服务于深挖 v2 的「官网子页探索」：从首页 HTML 里拿候选子页地址。
    只抽 `<a href>` 并解析成绝对 URL，**不做同域过滤**——那是调用方的事
    （深挖层拿着注册域比对，抓取层不该懂业务）。
    """
    return _extract_links(_download(url, html_only=True), url)[:max_links]


class _LinkExtractor(HTMLParser):
    """只收集 `<a href>`，与正文抽取共用 skip 逻辑避免把导航里的噪音放大。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value and value.strip():
                self.hrefs.append(value.strip())


def _extract_links(html: str, base_url: str) -> list[str]:
    """href → 绝对 URL。丢掉锚点/脚本/邮件协议，出现顺序去重。"""
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


class _IconExtractor(HTMLParser):
    """收集 `<link rel~=icon>` 与 `<meta property=og:image>` 的候选地址。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[tuple[str, str]] = []  # (kind, href) kind: link / og

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        pairs = {name.lower(): (value or "").strip() for name, value in attrs}
        if tag == "link" and "icon" in pairs.get("rel", "").lower() and pairs.get("href"):
            self.candidates.append(("link", pairs["href"]))
        elif tag == "meta" and pairs.get("property", "").lower() == "og:image" and pairs.get("content"):
            self.candidates.append(("og", pairs["content"]))


def fetch_page_icon(url: str) -> str:
    """抓取 `url` 的 HTML，挑出一个**可用的** logo 图标地址；失败返回空串。

    候选顺序：`<link rel=…icon…>`（apple-touch-icon 通常是最大最好看的一张，
    排最前）→ `og:image` → 兜底的 `/favicon.ico`。每个候选都做一次轻量
    HEAD 校验（200 + image/*），**只返回真加载得出来的**——给前端一个坏地址
    比不给更糟。服务于企业档案的 logo 展示，模型读不了图片，这步必须确定性直取。
    """
    html = _download(url, html_only=True)
    if not html:
        return ""

    parser = _IconExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — 半截 HTML 也能用
        pass

    candidates: list[str] = []
    for kind, href in parser.candidates:
        # og:image 常是分享封面图而非 logo，只当第二梯队
        if kind == "link" and "apple-touch" in href.lower():
            candidates.insert(0, href)
        elif kind == "link":
            candidates.append(href)
        else:
            candidates.append(href)

    base = url.strip()
    root = urljoin(base, "/")
    candidates.append("favicon.ico")  # 事实标准兜底：站点根目录
    for href in candidates:
        absolute = urljoin(base, href).split("#", 1)[0]
        if not absolute.startswith(("http://", "https://")):
            continue
        if _icon_loadable(absolute):
            return absolute
    return ""


def _icon_loadable(url: str) -> bool:
    """轻量校验：HEAD（不行就 GET 少读）拿状态与类型，确认是张真图。"""
    for method in ("HEAD", "GET"):
        try:
            with requests.request(
                method, url, headers=_HEADERS, timeout=_TIMEOUT_SECONDS, stream=True
            ) as response:
                if response.status_code != 200:
                    continue
                content_type = response.headers.get("Content-Type", "").lower()
                if "image/" not in content_type:
                    continue
                if method == "GET":
                    response.raw.read(1024, decode_content=True)  # 少读，别整张下
                return True
        except Exception:  # noqa: BLE001 — 校验失败换下一个候选
            continue
    return False


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


def _extract_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 — 半截 HTML 也能用，能抽多少抽多少
        pass
    return parser.text()


def _decode(raw: bytes, charset: str) -> str:
    """按「响应头声明 → UTF-8 → 中文常见编码」的顺序试，全失败就宽松解码。

    中文站点里 GBK/GB18030 仍然常见，只按 UTF-8 解会得到一片乱码，
    而乱码喂给 LLM 比不喂更糟——它会煞有介事地"总结"出错误内容。
    """
    for candidate in (charset, "utf-8", "gb18030"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


if __name__ == "__main__":
    # 自检：不联网，只验证 HTML → 文本的抽取行为（`python -m app.providers.web_fetch`）。
    sample = """
    <html><head><title>示例</title><style>body{color:red}</style></head>
    <body><script>var a = 1;</script><h1>标题</h1><p>第一段</p><p>第二段</p></body></html>
    """
    text = _extract_text(sample)
    assert "标题" in text and "第一段" in text and "第二段" in text, text
    assert "var a" not in text, "脚本内容不该进正文"
    assert "color:red" not in text, "样式内容不该进正文"
    assert "示例" not in text, "title 不应重复出现在正文里"
    assert fetch_page_text("ftp://example.com") == "", "非 http(s) 直接返回空"
    assert _decode("<p>中文</p>".encode("gb18030"), "") == "<p>中文</p>", "GBK 兜底解码"
    assert fetch_page_links("ftp://example.com") == [], "链接抓取同样只认 http(s)"

    sample_links = """
    <a href="/about">关于</a><a href="https://a.com/x#top">外链</a>
    <a href="/about">重复</a><a href="javascript:void(0)">脚本</a>
    <a href="mailto:a@b.c">邮件</a><a href="#top">锚点</a><a>无 href</a>
    """
    links = _extract_links(sample_links, "https://a.com/home/")
    assert links == ["https://a.com/about", "https://a.com/x"], links

    icon_html = """
    <head>
      <link rel="icon" href="/favicon.png">
      <link rel="apple-touch-icon" href="/touch.png">
      <meta property="og:image" content="https://cdn.a.com/cover.jpg">
    </head>
    """
    icons = _IconExtractor()
    icons.feed(icon_html)
    assert icons.candidates == [("link", "/favicon.png"), ("link", "/touch.png"),
                                ("og", "https://cdn.a.com/cover.jpg")], icons.candidates
    assert fetch_page_icon("ftp://example.com") == "", "图标抓取同样只认 http(s)"
    print("web_fetch 自检通过")
