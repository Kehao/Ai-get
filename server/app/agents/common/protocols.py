"""agent 只认识这三个协议，不认识任何具体实现。

这是「别人也能用」的全部秘密：换搜索服务、换 LLM、换抓取方式，只需要实现这里的
Protocol，核心逻辑一行不动——也**不会把任何宿主项目的模块拖进来**。

三个协议刻意都只有方法、没有基类。结构化类型意味着使用方**连本包都不必 import**
就能实现它们，鸭子类型天然成立。

三者对失败的要求**故意不一致**，这反映的是它们在链路里的地位：

| 协议 | 失败时 | 为什么 |
| --- | --- | --- |
| `WebSearch` | **抛异常** | 检索是链路的前提。「源挂了」被返回成空列表，会让人误判成「市面上没有」 |
| `PageFetcher` | 返回空串 | 抓取只是补材料。少一页不该让整条链路失败 |
| `JsonLlm` | **抛异常** | 「模型挂了」与「模型说没有」必须能被区分 |
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

# 检索结果的约定键。不做强类型校验，因为各家搜索 API 的返回结构千差万别，
# 强制归一化只会逼使用方写一堆适配代码。
KEY_TITLE = "title"
KEY_URL = "url"
KEY_CONTENT = "content"
KEY_SITE = "website"
KEY_DATE = "date"


@runtime_checkable
class WebSearch(Protocol):
    """网页检索。"""

    def search(
        self, query: str, *, top_k: int, site: str | None = None
    ) -> Sequence[Mapping[str, Any]]:
        """按 `query` 检索网页。

        每条结果是一个 mapping，约定键：

        | 键 | 必需 | 说明 |
        | --- | --- | --- |
        | `title` | 是 | 网页标题 |
        | `url` | 是 | 网页地址 |
        | `content` | 强烈建议 | 正文或摘要。**它直接决定提炼与深挖的质量**，只给标题的检索器会让整条链路退化成猜谜 |
        | `website` | 否 | 站点名，用于日志与你自己做过滤 |
        | `date` | 否 | 日期。注意多数搜索服务给的是**抓取时间**而非发布时间 |

        `site` 非空时限定在该站点内检索；不支持站点限定的实现可以直接忽略。

        ⚠️ 失败请**抛异常**，不要返回空列表——那会让调用方把「源挂了」误读成
        「市面上没有这类公司」。
        """
        ...


@runtime_checkable
class PageFetcher(Protocol):
    """抓取单个网页并抽成纯文本。"""

    def fetch(self, url: str, *, max_chars: int) -> str:
        """返回正文文本。

        ⚠️ **失败返回空串，不要抛**。抓不到只是少一路材料，不该让整条链路失败。
        这与 `WebSearch` 的要求相反，是有意的——抓取是锦上添花，检索才是前提。
        """
        ...


@runtime_checkable
class JsonLlm(Protocol):
    """要求模型返回 JSON 对象的对话补全。"""

    def complete_json(
        self, system: str, user: str, *, temperature: float, max_tokens: int
    ) -> Mapping[str, Any]:
        """发一次补全并返回**解析好的 JSON 对象**（不是字符串）。

        ⚠️ 失败请**抛异常**，不要返回空 dict——调用方要据此决定降级，
        「模型挂了」与「模型说没有」必须能被区分。
        """
        ...
