"""第 ③ 步：对一家实体做四级递进补全（v2）。

| 级别 | 手段 | 成本 |
| --- | --- | --- |
| L1 | 抓取检索结果里指向该实体的页面正文 | 每页一次抓取 |
| L2 | 搜「<名称> 官网」→ 定位站点 → 抓首页 | 一次检索 + 一次抓取 |
| L2.5 | 从首页抽同域链接 → 挑子页（关于/产品/招聘…）→ 抓正文 | 每页一次抓取（**免费**） |
| L3 | 按缺失字段定向检索 → 再整理 | 一次检索 + 若干抓取（**花钱**） |

L2.5 是 v2 相对 v1 的唯一新增：首页常常只有简介，成立时间、规模、产品清单这类
信息住在「关于我们」「加入我们」子页里。子页抓取免费，所以**排在花钱的 L3 之前**
——子页能补上的缺口，就不必再花检索的钱。抓取器不提供 `fetch_links` 或
`budget.max_subpages = 0` 时自动跳过，行为退回 v1。

每一级结束都让模型整理一次（`organize`），`missing` 空了就不再往下走。

## 只有 required 字段驱动补缺

`missing_required` 只认 `required: true` 的字段。全设成必填等于让循环永远追不完——
每轮都在为「还缺某个次要字段」花钱。非必填字段照样会被尽力抽取，只是不再触发补缺检索。

## 失败语义：全静默降级

整理失败、检索失败、抓取失败都只是**少一路材料**：档案照旧产出，只是字段少几个、
`missing` 长一点。调用方拿到的一定是一份结构完整的档案——这条链路上没有「整批失败」，
唯一的例外由调用方（`agent`）在提炼那一步把关。

失败原因走 `logging`，宿主可以决定要不要看见它。
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from . import prompts
from ..common.domains import extract_domain, is_skippable, registrable_domain
from .extract import as_bool
from ..common.protocols import JsonLlm, PageFetcher, WebSearch
from .spec import DiscoverySpec

logger = logging.getLogger(__name__)

_MAX_OUTPUT_TOKENS = 4096


def deepen_entity(
    profile: str,
    name: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    llm: JsonLlm,
    search: WebSearch,
    fetcher: PageFetcher,
    spec: DiscoverySpec,
    domain: str = "",
) -> dict:
    """对**已知的**一家实体做深挖。

    「已知身份」是这条路径与 `agent` 那套「先提炼再深挖」的区别：调用方已经知道要补谁
    （比如用户点开了某一行），再提炼一次既多花一次调用，又可能让模型把名字改掉、
    结果对不回原来那条记录。

    `documents` 用该条记录已有的证据构造即可（`title` / `url` / `content`）——
    L1 会按 url 重新抓全文，片段足够用来定位与判定。
    """
    profile = profile.strip()
    name = name.strip()
    if not profile or not name:
        return fallback_dossier({"name": name}, spec)

    brief = {
        "name": name,
        "domain": domain.strip(),
        "matched": True,
        "reason": "",
        "evidence_url": str(documents[0].get("url", "")) if documents else "",
    }
    pages = known_pages(documents, spec, fetcher)
    return _deepen(profile, brief, pages, llm=llm, search=search, fetcher=fetcher, spec=spec)


def known_pages(
    documents: Sequence[Mapping[str, Any]], spec: DiscoverySpec, fetcher: PageFetcher
) -> list[dict]:
    """L1 的材料：把已知 URL 抓成正文。

    抓不到就保留检索结果里的 `content`——搜索引擎给的正文主体往往已经够用，
    比空着强，也比让整条链路失败强。
    """
    pages: list[dict] = []
    for item in documents[: spec.budget.max_pages]:
        url = str(item.get("url", "")).strip()
        text = fetcher.fetch(url, max_chars=spec.budget.page_chars) if url else ""
        pages.append({**item, "content": text or str(item.get("content", ""))})
    return pages


def locate_homepage(name: str, *, spec: DiscoverySpec, search: WebSearch) -> str:
    """L2：搜「<名称> 官网」，从结果里挑一个像官网的注册域。

    只做排除法：剔掉搜索引擎、百科、社交平台、招聘站与媒体门户，剩下的交给模型
    在整理时确认。在字符串层面做同名实体消歧没有可靠手段，假装精确只会写错域名。
    """
    if not name:
        return ""
    try:
        items = search.search(f"{name} 官网", top_k=spec.budget.homepage_top_k)
    except Exception:  # noqa: BLE001 — 检索失败只是少一路材料，不该中断深挖
        logger.warning("定位官网的检索失败：%s", name, exc_info=True)
        return ""
    for item in items:
        host = extract_domain(str(item.get("url", "")))
        if not host or is_skippable(host, spec.skip_hosts):
            continue
        return registrable_domain(host)
    return ""


def search_gaps(
    name: str,
    gaps: Sequence[str],
    *,
    spec: DiscoverySpec,
    search: WebSearch,
    fetcher: PageFetcher,
) -> list[dict]:
    """L3：按第一个缺失字段定向检索并抓页，供下一轮整理使用。

    检索词取自配置的 `search_hint`——它写的是「官网」而不是「域名」，
    直译字段名会让这一轮检索白跑。
    """
    keyword = spec.search_hint(gaps[0])
    try:
        items = search.search(f"{name} {keyword}", top_k=spec.budget.gap_top_k)
    except Exception:  # noqa: BLE001
        logger.warning("补缺检索失败：%s %s", name, keyword, exc_info=True)
        return []
    pages: list[dict] = []
    for item in items[: spec.budget.gap_pages_per_round]:
        url = str(item.get("url", "")).strip()
        text = fetcher.fetch(url, max_chars=spec.budget.page_chars) if url else ""
        if text:
            pages.append({**item, "content": text})
    return pages


# 子页挑选的关键词分组。命中任意一组记 1 分——按「信息密度」排序，
# 关于我们（成立时间/规模）与产品页最值钱，招聘页次之（规模线索），其余兜底。
_SUBPAGE_KEYWORDS: tuple[tuple[str, ...], ...] = (
    ("about", "关于", "简介", "介绍", "profile"),
    ("product", "产品", "服务", "方案", "solution", "business"),
    ("join", "career", "招聘", "job", "人才"),
    ("contact", "联系"),
    ("news", "动态", "新闻", "media", "资讯"),
)

# 这些扩展名的链接是文件不是页面，抓回来也抽不出正文。
_SUBPAGE_ASSET_SUFFIXES = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".zip", ".rar", ".7z", ".mp4", ".mp3", ".exe", ".apk", ".css", ".js",
)


def pick_subpages(
    links: Sequence[str], *, home_domain: str, max_subpages: int
) -> list[str]:
    """从首页链接里挑出值得抓的同域子页（纯函数，自检覆盖）。

    三道闸：同注册域（外链一律不要）→ 非资源文件 → 关键词打分
    （得分高在前，同分路径短在前——路径短通常是层级更高的页面）。
    """
    home = registrable_domain(home_domain)
    if not home or max_subpages <= 0:
        return []

    scored: list[tuple[int, int, str]] = []
    for link in links:
        clean = link.split("?", 1)[0].split("#", 1)[0].rstrip("/").lower()
        if registrable_domain(clean) != home:
            continue
        parts = clean.split("/")  # https: / "" / host / path...
        path = parts[3] if len(parts) > 3 else ""
        if not path or clean.endswith(_SUBPAGE_ASSET_SUFFIXES):
            continue  # 首页自身没有路径；资源文件抓不出正文
        score = sum(1 for group in _SUBPAGE_KEYWORDS if any(word in path for word in group))
        scored.append((-score, len(path), clean))
    scored.sort()
    return [link for _, _, link in scored[:max_subpages]]


def explore_subpages(
    home_url: str,
    name: str,
    *,
    fetch_links: Any,
    fetcher: PageFetcher,
    spec: DiscoverySpec,
) -> list[dict]:
    """L2.5：抓首页链接 → 挑子页 → 抓正文。抓取器不支持链接时静默跳过。"""
    try:
        links = list(fetch_links(home_url, max_links=60))
    except Exception:  # noqa: BLE001 — 与其它抓取同口径：失败只是少一路材料
        logger.warning("首页链接抽取失败：%s", home_url, exc_info=True)
        return []
    if not links:
        return []

    pages: list[dict] = []
    for url in pick_subpages(
        links, home_domain=extract_domain(home_url), max_subpages=spec.budget.max_subpages
    ):
        text = fetcher.fetch(url, max_chars=spec.budget.page_chars)
        if text:
            pages.append({"title": f"{name} 官网子页", "url": url, "content": text})
    return pages


def organize(
    profile: str,
    name: str,
    materials: Sequence[Mapping[str, Any]],
    *,
    llm: JsonLlm,
    spec: DiscoverySpec,
) -> dict | None:
    """让模型依据材料整理出档案。失败（含无材料）返回 None，由调用方退回上一版。"""
    if not materials:
        return None
    try:
        completion = llm.complete_json(
            prompts.render(
                "deepdive.system.md",
                entity=spec.entity,
                field_table=spec.field_table(),
                json_fields=spec.json_fields(),
            ),
            prompts.render(
                "deepdive.user.md",
                entity=spec.entity,
                entity_name=name,
                profile=profile,
                materials=render_materials(materials, spec),
            ),
            temperature=0.0,
            max_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception:  # noqa: BLE001 — 整理失败退回上一版，不让整批结果受影响
        logger.warning("整理档案失败：%s", name, exc_info=True)
        return None
    return parse_dossier(completion, fallback_name=name, materials=materials, spec=spec)


def parse_dossier(
    data: Mapping[str, Any],
    *,
    fallback_name: str,
    materials: Sequence[Mapping[str, Any]],
    spec: DiscoverySpec,
) -> dict | None:
    """校验模型输出并归一化。形状不对时返回 None（调用方退回上一版）。

    档案的键**由配置的字段表决定**：加一个字段只需要改 JSON，
    校验、检索词、提示词会一起跟上。
    """
    raw = data.get("entity")
    if raw is None:
        raw = data.get("company")  # 兼容旧版提示词的输出键
    if not isinstance(raw, dict):
        return None

    dossier: dict[str, Any] = {"name": str(raw.get("name", "")).strip() or fallback_name}
    for item in spec.fields:
        value = raw.get(item.name)
        if item.is_list:
            dossier[item.name] = (
                tuple(str(part).strip() for part in value if str(part).strip())
                if isinstance(value, list)
                else ()
            )
        else:
            dossier[item.name] = str(value or "").strip()

    dossier["matched"] = as_bool(raw.get("matched"))
    dossier["reason"] = str(raw.get("reason", "")).strip()
    dossier["missing"] = missing_required(raw, spec)
    # materials 允许为空（直接调用与自检都会走到），不能想当然取第 0 条。
    dossier["evidence_url"] = str(materials[0].get("url", "")) if materials else ""
    return dossier


def fallback_dossier(brief: Mapping[str, Any], spec: DiscoverySpec) -> dict:
    """整理失败时的降级档案：保住「是谁、判没判过」，其余字段按配置如实留空。"""
    dossier: dict[str, Any] = {
        "name": str(brief.get("name", "")).strip(),
        "matched": as_bool(brief.get("matched")),
        "reason": str(brief.get("reason", "")).strip(),
        "missing": spec.required_names,
        "evidence_url": str(brief.get("evidence_url", "")),
    }
    for item in spec.fields:
        dossier[item.name] = () if item.is_list else ""
    return dossier


def missing_required(record: Mapping[str, Any], spec: DiscoverySpec) -> list[str]:
    """取档案里仍缺、且**值得再花一次检索去找**的字段名。

    只有 `required` 的字段会驱动补缺检索；不在册的取值一律剔除，
    免得模型写出「风险等级」这类字段就把一轮检索勾出去。
    """
    raw = record.get("missing")
    if not isinstance(raw, list):
        return []
    allowed = set(spec.required_names)
    return [name for name in (str(item).strip() for item in raw) if name in allowed]


def render_materials(materials: Sequence[Mapping[str, Any]], spec: DiscoverySpec) -> str:
    lines: list[str] = []
    for index, page in enumerate(materials[: spec.budget.max_materials], start=1):
        title = str(page.get("title", "")).strip()
        url = str(page.get("url", "")).strip()
        body = " ".join(str(page.get("content", "")).split())
        lines.append(f"[{index}] {title}\n    URL：{url}\n    正文：{body}")
    return "\n".join(lines)


def to_url(domain: str) -> str:
    return domain if domain.startswith(("http://", "https://")) else f"https://{domain}"


def _deepen(
    profile: str,
    brief: Mapping[str, Any],
    pages: Sequence[Mapping[str, Any]],
    *,
    llm: JsonLlm,
    search: WebSearch,
    fetcher: PageFetcher,
    spec: DiscoverySpec,
) -> dict:
    """补全一家实体。任何一步失败都退回上一版档案，不让整批结果受影响。"""
    budget = spec.budget
    name = str(brief.get("name", "")).strip()
    materials = [page for page in pages if _mentions(page, name)]

    # L2：先看有没有现成域名，没有再搜「官网」定位。
    domain = str(brief.get("domain", "")).strip() or locate_homepage(
        name, spec=spec, search=search
    )
    if domain:
        url = to_url(domain)
        text = fetcher.fetch(url, max_chars=budget.page_chars)
        if text:
            materials.append({"title": f"{name} 官网", "url": url, "content": text})

    record = organize(profile, name, materials, llm=llm, spec=spec) or fallback_dossier(
        brief, spec
    )

    # L2.5（v2）：官网子页探索——免费（HTTP 抓取），所以排在花钱的 L3 之前：
    # 子页能补上的缺口就不必再花检索的钱。抓取器不提供 fetch_links 或预算为 0
    # 时自动跳过，行为退回 v1。首轮整理已把字段填满时同样不抓（零成本才是真省）。
    if budget.max_subpages > 0 and domain and missing_required(record, spec):
        fetch_links = getattr(fetcher, "fetch_links", None)
        if callable(fetch_links):
            extra = explore_subpages(
                to_url(domain), name, fetch_links=fetch_links, fetcher=fetcher, spec=spec
            )
            if extra:
                materials.extend(extra)
                refined = organize(profile, name, materials, llm=llm, spec=spec)
                if refined is not None:
                    record = refined

    # L3：档案仍报缺必填字段就定向检索一轮；检索不到就停，不做无谓的重复。
    for _ in range(budget.max_gap_rounds):
        gaps = missing_required(record, spec)
        if not gaps:
            break
        extra = search_gaps(name, gaps, spec=spec, search=search, fetcher=fetcher)
        if not extra:
            break
        materials.extend(extra)
        refined = organize(profile, name, materials, llm=llm, spec=spec)
        if refined is None:
            break
        record = refined

    # Logo：模型读不了图片、材料又是纯文本，这步只能由抓取层确定性直取
    # （apple-touch-icon / rel=icon / og:image / favicon.ico，逐个验证可加载）。
    # **不进字段表**——写进去模型只会对着正文编 URL。抓取器不支持时静默跳过。
    if domain:
        fetch_icon = getattr(fetcher, "fetch_icon_url", None)
        if callable(fetch_icon):
            try:
                logo_url = str(fetch_icon(to_url(domain)) or "")
            except Exception:  # noqa: BLE001 — 与其它抓取同口径：失败只是少个 logo
                logger.warning("抓取企业 logo 失败：%s", domain, exc_info=True)
            else:
                if logo_url:
                    record["logo"] = logo_url

    return record


def _mentions(page: Mapping[str, Any], name: str) -> bool:
    if not name:
        return False
    return name in f"{page.get('title', '')} {page.get('content', '')}"


if __name__ == "__main__":
    # 自检：不联网、不调模型（`python -m discovery_agent.deep_dive`）。
    from .spec import FieldSpec

    spec = DiscoverySpec(
        name="test",
        entity="公司",
        fields=(
            FieldSpec("domain", "官网", required=True, search_hint="官网"),
            FieldSpec("summary", "简介", required=True, search_hint="公司简介"),
            FieldSpec("products", "产品", kind="list"),
        ),
    )

    assert to_url("acme.com") == "https://acme.com"
    assert to_url("https://acme.com") == "https://acme.com"
    assert _mentions({"title": "甲获投", "content": ""}, "甲")
    assert not _mentions({"title": "无关", "content": "正文"}, "甲")

    # v2 子页挑选：同域过滤 + 资源过滤 + 关键词打分 + 上限
    picked = pick_subpages(
        [
            "https://acme.com/",                       # 首页自身，不要
            "https://acme.com/about",                  # 得分 1，路径短在前
            "https://acme.com/about/team",             # 得分 2（about+team? team 不在词表）→ about 命中 1
            "https://acme.com/product/a.png",          # 资源文件，不要
            "https://other.com/about",                 # 外域，不要
            "https://www.acme.com/join",               # 同注册域（www 剥掉），得分 1
            "https://acme.com/news?id=9",              # query 剥掉后命中 news，得分 1
        ],
        home_domain="acme.com",
        max_subpages=3,
    )
    # 同分时按路径长度升序：join/news（4 字）排在 about（5 字）前
    assert picked == ["https://acme.com/news", "https://www.acme.com/join",
                      "https://acme.com/about"], picked
    assert pick_subpages(["https://acme.com/about"], home_domain="", max_subpages=3) == []
    assert pick_subpages(["https://acme.com/about"], home_domain="acme.com", max_subpages=0) == []

    # 只有 required 驱动补缺：非必填的 products 与不在册的字段都不该勾出检索
    gaps = missing_required({"missing": ["domain", "products", "风险等级", "summary", 7]}, spec)
    assert gaps == ["domain", "summary"], gaps
    assert missing_required({"missing": "domain"}, spec) == [], "非数组一律视为无缺口"

    dossier = parse_dossier(
        {
            "entity": {
                "name": "",
                "domain": "acme.com",
                "products": ["甲", " ", "乙"],
                "matched": "false",
                "missing": ["domain"],
            }
        },
        fallback_name="兜底名",
        materials=[{"url": "https://acme.com"}],
        spec=spec,
    )
    assert dossier is not None
    assert dossier["name"] == "兜底名", "名字缺失时回落到候选名"
    assert dossier["products"] == ("甲", "乙"), dossier["products"]
    assert dossier["matched"] is False, '字符串 "false" 不能被当成真'
    assert dossier["evidence_url"] == "https://acme.com"

    legacy = parse_dossier(
        {"company": {"domain": "b.com"}}, fallback_name="x", materials=[], spec=spec
    )
    assert legacy is not None and legacy["domain"] == "b.com", "旧输出键仍要认"
    assert parse_dossier({}, fallback_name="x", materials=[], spec=spec) is None

    fallback = fallback_dossier({"name": "甲"}, spec)
    assert fallback["missing"] == spec.required_names, "降级档案要报必填字段全缺"
    assert fallback["products"] == (), "列表字段降级后是空元组而不是空串"

    print("deep_dive 自检通过")
