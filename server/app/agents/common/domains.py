"""域名工具：注册域提取 + 「明显不是实体官网」的站点清单。

## 为什么只做排除法

定位官网时**不做判断，只做排除**：剔掉搜索引擎、百科、社交平台、招聘站、媒体门户，
剩下的交给模型在整理时确认（提示词要求「只有材料本身就是官网时才填 domain」）。

硬做同名实体消歧没有可靠手段——「云杉网络」和「邢台云杉网络科技」在字符串上无法区分，
假装精确只会把错误域名写进档案。

## 按注册域匹配，不是按后缀

`finance.sina.com.cn` 的最后两段是 `com.cn`，拿它查表永远不会命中——
一份清单会在所有 `.com.cn` 站点上集体失效。所以统一先取注册域再比。
"""

from __future__ import annotations

# 二级后缀：这些国家的注册域要取三段，而不是两段。
_SECOND_LEVEL_SUFFIXES = frozenset(
    {
        "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
        "co.uk", "org.uk", "ac.uk", "gov.uk",
        "co.jp", "or.jp", "ne.jp", "ac.jp",
        "com.hk", "com.tw", "com.sg", "com.au", "com.my", "co.kr",
    }
)

# 常见的「不是实体官网」站点。只列出现频率高到会污染结果的，不求穷尽——
# 清单再长也总有漏网，真正的把关在整理那一步。
DEFAULT_SKIP_HOSTS = frozenset(
    {
        # 搜索引擎
        "google.com", "bing.com", "baidu.com", "sogou.com", "so.com", "sm.cn",
        "yandex.com", "duckduckgo.com",
        # 百科 / 问答 / 博客 / 技术社区
        "wikipedia.org", "baike.com", "zhihu.com", "douban.com", "jianshu.com",
        "csdn.net", "cnblogs.com", "segmentfault.com", "v2ex.com", "juejin.cn",
        "reddit.com", "quora.com", "medium.com", "substack.com", "wordpress.com",
        "blogspot.com", "notion.site",
        # 社交 / 视频 / 直播
        "weibo.com", "linkedin.com", "facebook.com", "twitter.com", "x.com",
        "instagram.com", "youtube.com", "bilibili.com", "douyin.com",
        "xiaohongshu.com", "tiktok.com", "kuaishou.com",
        # 媒体门户（出现频率极高，但主体不是报道里的实体本身）
        "sina.com.cn", "sina.cn", "sohu.com", "163.com", "qq.com", "ifeng.com",
        "thepaper.cn", "jiemian.com", "yicai.com", "caixin.com", "cls.cn",
        "eastmoney.com", "jrj.com.cn", "hexun.com", "stcn.com", "chinastarmarket.cn",
        "36kr.com", "huxiu.com", "iyiou.com", "cyzone.cn", "tmtpost.com", "pedaily.cn",
        "techcrunch.com", "reuters.com", "bloomberg.com", "forbes.com", "wsj.com",
        # 招聘 / 工商目录
        "zhipin.com", "liepin.com", "51job.com", "lagou.com", "zhaopin.com",
        "qcc.com", "tianyancha.com", "aiqicha.baidu.com", "qixin.com",
        # 代码托管
        "github.com", "gitee.com", "gitlab.com", "bitbucket.org",
    }
)


def extract_domain(url: str) -> str:
    """从 URL 里取出主机名（含端口会去掉）。拿不到就返回空串。"""
    text = url.strip()
    if "//" in text:
        text = text.split("//", 1)[1]
    host = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    return host.split("@")[-1].split(":")[0].strip().lower()


def registrable_domain(host: str, *, strip_www: bool = True) -> str:
    """取注册域：`www.a.example.com.cn` → `example.com.cn`。"""
    clean = extract_domain(host) if "//" in host else host.strip().lower()
    clean = clean.split(":")[0]
    if strip_www and clean.startswith("www."):
        clean = clean[4:]
    parts = [part for part in clean.split(".") if part]
    if len(parts) <= 2:
        return ".".join(parts)
    if ".".join(parts[-2:]) in _SECOND_LEVEL_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_skippable(host: str, extra: frozenset[str] | set[str] | tuple[str, ...] = ()) -> bool:
    """这个主机名是否该在「找官网」时跳过。

    在注册域层面比对，所以 `finance.sina.com.cn` 能命中清单里的 `sina.com.cn`。
    `extra` 是调用方追加的站点（注册域形式）。
    """
    domain = registrable_domain(host)
    if not domain:
        return True
    if domain in DEFAULT_SKIP_HOSTS:
        return True
    return any(registrable_domain(item) == domain for item in extra if str(item).strip())


if __name__ == "__main__":
    # 自检：不联网（`python -m discovery_agent.domains`）。
    assert extract_domain("https://a.example.com/x?y=1") == "a.example.com"
    assert extract_domain("http://user@Host.COM:8080/p") == "host.com"
    assert extract_domain("不是网址") == "不是网址", "拿不到就原样返回，由注册域那层兜底"

    assert registrable_domain("www.example.com") == "example.com"
    assert registrable_domain("a.b.example.co.uk") == "example.co.uk"
    assert registrable_domain("finance.sina.com.cn") == "sina.com.cn"
    assert registrable_domain("x.com.cn") == "x.com.cn", "两段就是注册域"
    assert registrable_domain("localhost") == "localhost"

    # 关键用例：中文站点的 .com.cn 必须在清单里命中，否则整份清单会在那一类站上失效
    assert is_skippable("finance.sina.com.cn"), "媒体子域要按注册域命中"
    assert is_skippable("baike.baidu.com")
    assert not is_skippable("acme.com")
    assert is_skippable("acme.com", extra=("acme.com",)), "调用方追加的站点也要拦"
    assert is_skippable("", extra=()), "取不出域名时视为不可用"

    print(f"domains 自检通过（内置跳过清单 {len(DEFAULT_SKIP_HOSTS)} 条）")
