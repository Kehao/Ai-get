"""网页结果映射规则（`web_mapping`）的单元测试。

取名规则的每一条都来自实测踩坑，所以要逐条钉住：标语标题、导航残留、
目录页后缀、与域名互证——退化与丢弃的分界必须稳定，否则两个源的行为会悄悄漂移。
"""

from __future__ import annotations

import pytest

from app.providers.web_mapping import (
    extract_domain,
    is_directory_domain,
    is_non_company_domain,
    name_from_domain,
    name_from_title,
    registrable_domain,
)


# ── 域名 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.yunshan.net/about", "yunshan.net"),
        ("http://YunShan.NET/", "yunshan.net"),
        ("https://aiqicha.baidu.com/detail_1", "aiqicha.baidu.com"),
        ("https://intranet-host/page", ""),  # 没有 "." 的 netloc 当不成企业域名
        ("", ""),
    ],
)
def test_extract_domain(url, expected):
    assert extract_domain(url) == expected


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("36kr.com", True),
        ("www.36kr.com", True),  # 注册域匹配：子域同样命中
        ("news.mydrivers.com", True),
        ("yunshan.net", False),
        ("aiqicha.baidu.com", True),  # 归属 baidu.com 这条媒体规则
    ],
)
def test_non_company_domain(domain, expected):
    assert is_non_company_domain(domain) is expected


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("aiqicha.baidu.com", True),
        ("qcc.com", True),
        ("a.qcc.com", True),
        ("notqcc.com", False),  # 后缀匹配不能误伤同名注册域
        ("yunshan.net", False),
    ],
)
def test_directory_domain(domain, expected):
    assert is_directory_domain(domain) is expected


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("saas.360.cn", "360.cn"),
        ("ent.online.360.cn", "360.cn"),  # 不同子域必须归到同一注册域
        ("yunshan.net", "yunshan.net"),
        ("foo.com.cn", "foo.com.cn"),  # 二级后缀国家码：退三层
        ("localhost", "localhost"),
    ],
)
def test_registrable_domain(domain, expected):
    assert registrable_domain(domain) == expected


# ── 取名：像企业名的才采信 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "domain", "expected"),
    [
        # 组织形式词收尾：直接采信，「站点名 - 标题」的前半截先被切出来。
        ("山东浪潮云安全科技有限公司 - 爱企查", "", "山东浪潮云安全科技有限公司"),
        ("Acme Security Inc. | 官网", "acme.com", "Acme Security Inc."),
        # 目录页后缀（「常见问题与解答」）挂在企业名后面时截到组织形式词为止。
        (
            "中汇云安全科技(上海)有限公司常见问题与解答_爱企查",
            "",
            "中汇云安全科技(上海)有限公司",
        ),
        # 短且含行业词：不带「公司」二字的中文企业名靠这条通过。
        ("云杉网络 - 企业云安全服务", "yunshan.net", "云杉网络"),
        ("青云科技", "", "青云科技"),
        # 与域名主体互证：拉丁品牌名的通道。
        ("Idc4", "idc4.com", "Idc4"),
        # 整句标语、导航残留、句读标点：一律不采信（调用方将退化到域名主体）。
        ("智能云安全整体解决方案与服务提供商", "datacloudsec.com", ""),
        ("News", "news.mydrivers.com", ""),
        ("New", "new.qq.com", ""),  # 域名主体太短，不足以为标题作证
        ("企业版WorkClaw, 好用不折腾,安全又可控", "qingteng.cn", ""),
        ("陈华", "", ""),  # 法人页面：目录站记录没有域名可退化，靠这条丢弃
        ("", "yunshan.net", ""),
    ],
)
def test_name_from_title(title, domain, expected):
    assert name_from_title(title, domain) == expected


def test_name_from_domain_is_the_fallback():
    assert name_from_domain("datacloudsec.com") == "Datacloudsec"
    assert name_from_domain("yun-shan.net") == "Yun shan"
    # 子域第一段（m、news）不能当公司名，要取注册域主段。
    assert name_from_domain("m.tensorsecurity.cn") == "Tensorsecurity"
    assert name_from_domain("news.mydrivers.com") == "Mydrivers"
    assert name_from_domain("") == ""


def test_sentence_marks_block_long_names():
    """含句读的长名即使挂着行业词也不采信——它是一句话，不是一个名字。"""
    assert name_from_title("云安全、数据安全与身份认证平台", "x.com") == ""
