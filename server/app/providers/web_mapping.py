"""网页检索结果 → 企业记录的共享映射规则。

Tavily 与百度 AI 搜索返回的都是「网页结果列表」（title / url / content）。
把网页结果折算成 `CompanyRecord` 的规则——域名提取、标题取名、站点类型过滤——
属于**检索域的常识**，不属于某一家供应商。放在这里共用，避免两份实现慢慢漂移：
一个源补了过滤清单而另一个没补，同一批网页在两个源里就会被判成不同的东西。

各源只保留自己的**检索策略**（查什么、查几次、站点限定怎么加、怎么计费）。

## 站点三分类

网页检索的召回难点是「这条结果属于企业的哪一面」：

- **企业站点**：域名就是企业的对外身份，可直接当去重键与触达入口；
- **工商目录站**（爱企查、企查查…）：页面内容有价值（企业全名、注册资本、
  法定代表人），但**域名是目录站自己的**，不能当企业域名——留着会污染去重键
  与联系人链路。所以这类结果保留记录、把域名留空（去重退化到名称）；
- **媒体、UGC、招聘站**：页面讲的是「关于企业的事」而不是企业本身，
  且标题里的主体往往是写稿人。整条丢弃——召回宁缺毋滥。

三类的判定表放在这里，两个源共用。

## 名字从哪里来

**标题不是可靠的名字来源**，这是实测出来的：百度泛搜索返回的标题里出现过
「News」「New」「Idc4」以及「智能云安全整体解决方案与服务提供商」这样的整句标语。
采信它们等于往列表里塞假公司。所以 `name_from_title` 走保守通道，
只有「像企业名」的三类标题才被采信，其余一律返回空串，由调用方**退化到域名主体**
（`datacloudsec.com` → `Datacloudsec`，至少不是错的）。中文企业名很少与拼音域名
互证，所以中文侧靠「组织形式词」与「行业词」两条通道兜住，不靠域名。

工商目录站的记录没有域名可退化，取名失败即整条丢弃——名单里出现「陈华」
（法定代表人页面）这种，就是靠这条挡下的。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# 媒体 / UGC / 招聘 / 代码托管：整条丢弃。按**注册域**匹配（含子域），
# 所以 en.wikipedia.org 同样命中 wikipedia.org。
NON_COMPANY_DOMAINS = frozenset(
    {
        # 通用示例域（防止假数据混进真实召回）
        "example.com",
        "example.net",
        "example.org",
        # 百科 / UGC / 博客平台
        "wikipedia.org",
        "baike.com",
        "zhihu.com",
        "csdn.net",
        "jianshu.com",
        "github.com",
        "gitee.com",
        "medium.com",
        "wordpress.com",
        "blogspot.com",
        # 社交媒体
        "linkedin.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "weibo.com",
        "douban.com",
        # 媒体门户：出现频率高但主体不是企业本身
        "sohu.com",
        "sina.com.cn",
        "163.com",
        "qq.com",
        "ifeng.com",
        "36kr.com",
        "tmtpost.com",
        "iyiou.com",
        "cena.com.cn",
        "mydrivers.com",
        "ithome.com",
        "cnbeta.com.tw",
        "leiphone.com",
        "geekpark.net",
        "huxiu.com",
        "thepaper.cn",
        "caixin.com",
        "yicai.com",
        # 财经媒体与资讯门户：中文网页检索里最大的噪声源，
        # 它们几乎占满了「行业 + 融资 + 公司」这类查询的头部结果。
        "ce.cn",
        "nbd.com.cn",
        "huanqiu.com",
        "stcn.com",
        "cls.cn",
        "jiemian.com",
        "21jingji.com",
        "eeo.com.cn",
        "hexun.com",
        "jrj.com.cn",
        "xinhuanet.com",
        "people.com.cn",
        "chinanews.com.cn",
        "cyzone.cn",
        "donews.com",
        "techweb.com.cn",
        "zhiding.cn",
        "chinastarmarket.cn",
        # 招聘平台：标题主体是职位，不是公司
        "zhipin.com",
        "lagou.com",
        "liepin.com",
        "51job.com",
        "maimai.cn",
        # 搜索 / 导航站
        "baidu.com",
        "so.com",
        "bing.com",
        "sogou.com",
    }
)

# 工商目录站：**保留记录但域名留空**。按完整 host 后缀匹配——不用注册域，
# 否则 aiqicha.baidu.com 会把整个 baidu.com 拖进「目录站」分支。
DIRECTORY_DOMAINS = frozenset(
    {
        "aiqicha.baidu.com",
        "aiqicha.com",
        "qcc.com",
        "tianyancha.com",
        "qixin.com",
        "qiye.qianzhan.com",
        "xbiao.com",
        "qiyezhishi.com",
        "shuidi.cn",
        "riskbird.com",
    }
)

# 标题里常见的「页面标题 + 站点名」分隔符。切出第一段作为企业名的候选。
# 半角与全角都要留：中文站点的全角横线、竖线同样常见。
TITLE_SEPARATORS = (" | ", " - ", " — ", " – ", "_", "｜", "－", "·", "—")

NAME_MAX_CHARS = 40

# 拉丁标题按空格分词超过这个数，更像「Shop SaaS Tools Online」这类页面标语
# 而不是公司名——此时不采用标题，退化到域名主体。中文公司名无空格不受影响。
NAME_MAX_WORDS = 3

# 中文标题长于这个字数且没有组织形式词收尾，就不再当企业名——
# 「智能云安全整体解决方案与服务提供商」这类标语正是靠这条挡下的。
NAME_MAX_CJK_CHARS = 12

# 组织形式词（**尾部结构**）：出现在标题里就截到它结尾，后面跟着的
# 「常见问题与解答」这类页面后缀自然被切掉。
ORG_STRONG_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "有限公司",
    "集团公司",
    "总公司",
    "分公司",
    "集团",
    "公司",
    "研究院",
    "研究所",
    "事务所",
    "中心",
    "工厂",
    "医院",
    "学校",
    "银行",
)

# 行业词（**中间词，不截断**）：只用来判断「这串字像不像企业名」。
# 「云杉网络」「青云科技」这类不带「公司」二字的企业名靠它通过。
ORG_WEAK_TERMS = (
    "科技",
    "网络",
    "信息",
    "技术",
    "软件",
    "数据",
    "智能",
    "电子",
    "实业",
    "股份",
    "通信",
    "半导体",
    "生物",
    "医药",
    "能源",
    "环保",
    "机械",
    "装备",
    "材料",
    "化工",
    "食品",
    "汽车",
    "建设",
    "物流",
    "贸易",
    "教育",
    "传媒",
    "文化",
    "旅游",
    "农业",
    "地产",
    "咨询",
    "设计",
    "安全",
)

# 拉丁企业名后缀。用词边界匹配，免得 "Co" 命中 "Cloud" 的中间。
_LATIN_ORG_TAIL = re.compile(
    r"\b(?:Inc|Ltd|LLC|Corp|GmbH|Co|Limited|Holdings|Group|Technologies|Technology|"
    r"Systems|Solutions|Industries|Partners)\b\.?",
    re.IGNORECASE,
)

# 企业名里不会出现的句读标点。出现即判定为「一句话」而不是一个名字，
# 例如「企业版WorkClaw, 好用不折腾,安全又可控」。
# **括号不算**：中文企业名里带地名的括号很常见（「中汇云安全科技(上海)有限公司」）。
_SENTENCE_MARKS = frozenset(",，。;；、！!？?")

# 二级后缀国家码：`xxx.com.cn` 的主段要再往前退一层，否则会取到 "com"。
_SECOND_LEVEL_SUFFIXES = frozenset({"com", "net", "org", "gov", "edu", "co", "ac"})
_COUNTRY_TLDS = frozenset({"cn", "uk", "jp", "au", "hk", "tw", "sg"})


def extract_domain(url: str) -> str:
    """从 URL 取企业域名（去掉 www.）。没有 "." 的 netloc 当不成企业域名，返回空串。"""
    netloc = urlparse(url).netloc.strip().lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc if "." in netloc else ""


def registrable_domain(domain: str) -> str:
    """注册域：`ent.online.360.cn` → `360.cn`，`finance.sina.com.cn` → `sina.com.cn`。

    两个用途，都必须走它：**去掉子域**（同一家公司的 `saas.360.cn` 与
    `ent.online.360.cn` 曾在列表里占两行）与**查站点名单**（最后两段在
    `.com.cn` 域名上是 `com.cn`，拿它查表等于整份名单失效——实测漏过一批媒体站）。
    """
    parts = [part for part in domain.lower().split(".") if part]
    if len(parts) <= 2:
        return ".".join(parts)
    if parts[-1] in _COUNTRY_TLDS and parts[-2] in _SECOND_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_non_company_domain(domain: str) -> bool:
    """域名（或其注册域）命中媒体/UGC/招聘清单。"""
    return _matches_registrable(domain, NON_COMPANY_DOMAINS)


def is_directory_domain(domain: str) -> bool:
    """域名是工商目录站（内容可用，但域名不是企业的）。"""
    return _matches_host(domain, DIRECTORY_DOMAINS)


def _matches_registrable(domain: str, table: frozenset[str]) -> bool:
    """按**注册域**匹配。必须复用 `registrable_domain` 而不是自取最后两段：

    `finance.sina.com.cn` 的最后两段是 `com.cn`，拿它查表永远不会命中，
    于是整份名单在 `.com.cn` / `.cn` 域名上集体失效——实测漏掉了新浪财经、
    中国经济网、每日经济新闻等一大批媒体站。
    """
    return registrable_domain(domain) in table


def _matches_host(domain: str, table: frozenset[str]) -> bool:
    """完整 host 后缀匹配：`a.qcc.com` 命中 `qcc.com`，但 `notqcc.com` 不命中。"""
    return any(domain == host or domain.endswith("." + host) for host in table)


def name_from_title(title: str, domain: str = "") -> str:
    """网页标题 → 企业名。**不像企业名时返回空串**，由调用方决定退化还是丢弃。

    网页标题的两种失败模式都见过了：整句标语（「智能云安全整体解决方案与服务提供商」）
    与导航残留（「News」「New」）。所以取名的准入走保守通道，三选一：

    1. 含组织形式词收尾 → 截到该词结尾（顺手去掉「常见问题与解答」这类页面后缀）；
    2. 短（≤ `NAME_MAX_CJK_CHARS`）且含行业词 → 中文品牌名多数落在这一档；
    3. 与域名主体互证 → 拉丁品牌名（`Idc4` 对 `idc4.com`）。

    都不满足就返回空串：宁可退回域名主体（至少不是错的），也不把标语当公司名。
    """
    segment = _first_segment(title)
    if not segment or len(segment) > NAME_MAX_CHARS or len(segment.split()) > NAME_MAX_WORDS:
        return ""
    if any(mark in segment for mark in _SENTENCE_MARKS):
        return ""

    trimmed = _trim_at_org_suffix(segment)
    if trimmed:
        return trimmed
    if len(segment) <= NAME_MAX_CJK_CHARS and any(term in segment for term in ORG_WEAK_TERMS):
        return segment
    if _agrees_with_domain(segment, domain):
        return segment
    return ""


def name_from_domain(domain: str) -> str:
    """域名主体当名称的兜底：`yunshan.net` → `Yunshan`。没有更好的来源时才用。

    取**注册域**主段而不是子域第一段：`m.tensorsecurity.cn` 的第一段是 `m`，
    当公司名显然是坏的（实测踩过）。
    """
    root = _registrable_label(domain)
    return root[:NAME_MAX_CHARS].replace("-", " ").strip().capitalize() or domain


def _first_segment(title: str) -> str:
    """按常见分隔符切出第一段——「站点名 - 页面标题」的前半截通常是主体。"""
    for separator in TITLE_SEPARATORS:
        if separator in title:
            title = title.split(separator, 1)[0]
            break
    return title.strip()

def _trim_at_org_suffix(segment: str) -> str:
    """截到最后一个组织形式词的结尾；没有这类词时返回空串。

    取**最后一个**：`股份有限公司` 比 `有限公司` 晚，`集团公司` 比 `集团` 晚，
    这样才能切出「山东浪潮云安全科技有限公司」的完整名字而不是「山东浪潮集团」。
    """
    best_end = 0
    for suffix in ORG_STRONG_SUFFIXES:
        index = segment.rfind(suffix)
        if index >= 0:
            best_end = max(best_end, index + len(suffix))
    for match in _LATIN_ORG_TAIL.finditer(segment):
        best_end = max(best_end, match.end())
    if best_end == 0:
        return ""
    trimmed = segment[:best_end].strip()
    return trimmed if len(trimmed) >= 2 else ""


def _agrees_with_domain(segment: str, domain: str) -> bool:
    """标题里的名字与域名主体互证——拉丁品牌名的最后一道通道。

    主体取**注册域**（倒数第二段）而不是子域第一段：`news.mydrivers.com` 的第一段
    恰好是 `news`，拿它当证据就会让标题「News」通过——实测踩过这个坑。
    """
    root = _registrable_label(domain)
    if len(root) < 4:  # 太短的域名主体（new、qq、idc）不足以当证据
        return False
    flattened = re.sub(r"[^0-9a-z\u4e00-\u9fa5]", "", segment.lower())
    return bool(flattened) and (root in flattened or flattened in root)


def _registrable_label(domain: str) -> str:
    """注册域的主段：`idc4.com` → `idc4`，`xxx.com.cn` → `xxx`。"""
    return registrable_domain(domain).split(".", 1)[0]
