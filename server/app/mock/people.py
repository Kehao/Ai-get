"""企业关键联系人的虚拟数据。

姓名按「姓 + 名」的拼音形式同时存储，便于生成形如 `wang.zhiyuan@example.com` 的邮箱。
"""

from __future__ import annotations

from ..models import Contact

SURNAMES: tuple[tuple[str, str], ...] = (
    ("王", "wang"),
    ("李", "li"),
    ("张", "zhang"),
    ("刘", "liu"),
    ("陈", "chen"),
    ("杨", "yang"),
    ("黄", "huang"),
    ("周", "zhou"),
    ("吴", "wu"),
    ("徐", "xu"),
    ("孙", "sun"),
    ("马", "ma"),
    ("朱", "zhu"),
    ("胡", "hu"),
    ("林", "lin"),
    ("何", "he"),
)

GIVEN_NAMES: tuple[tuple[str, str], ...] = (
    ("志远", "zhiyuan"),
    ("雅静", "yajing"),
    ("海涛", "haitao"),
    ("文博", "wenbo"),
    ("思琪", "siqi"),
    ("俊杰", "junjie"),
    ("晓峰", "xiaofeng"),
    ("梦琳", "menglin"),
    ("嘉伟", "jiawei"),
    ("雨萌", "yumeng"),
    ("振宇", "zhenyu"),
    ("露露", "lulu"),
    ("国栋", "guodong"),
    ("清扬", "qingyang"),
    ("子涵", "zihan"),
    ("慧敏", "huimin"),
)

TITLES: tuple[str, ...] = (
    "创始人 & CEO",
    "采购总监",
    "供应链负责人",
    "市场负责人",
    "品牌总监",
    "商务拓展经理",
    "运营总监",
    "信息化负责人",
    "行政与采购经理",
    "技术负责人",
)

_PHONE_PREFIXES: tuple[str, ...] = ("138", "139", "156", "176", "188", "133", "159", "182")


def build_contacts(seed: int, domain: str, count: int) -> list[Contact]:
    """按种子确定性生成联系人，同一企业每次得到相同结果。"""
    contacts: list[Contact] = []
    for offset in range(count):
        index = seed * 7 + offset * 13
        surname_cn, surname_py = SURNAMES[index % len(SURNAMES)]
        given_cn, given_py = GIVEN_NAMES[(index // 3) % len(GIVEN_NAMES)]
        title = TITLES[(index // 5) % len(TITLES)]
        phone_prefix = _PHONE_PREFIXES[index % len(_PHONE_PREFIXES)]
        contacts.append(
            Contact(
                id=f"contact-{seed}-{offset}",
                name=f"{surname_cn}{given_cn}",
                title=title,
                email=f"{surname_py}.{given_py}@{domain}",
                linkedin=f"linkedin.com/in/{surname_py}-{given_py}-{(index % 90) + 10}",
                phone=f"{phone_prefix}****{(index * 37) % 10000:04d}",
                confidence=70 + (index % 30),
            )
        )
    return contacts
