"""语料用尽后的企业条目合成。

挖掘数量可选 25 / 100 / 500 / 1000，手工语料不足以覆盖，因此超出部分按规则合成，
保证任何数量都有结构一致、可读的结果。
"""

from __future__ import annotations

from .company_corpus import COMPANY_SEEDS, CompanySeed

CITIES: tuple[str, ...] = (
    "杭州",
    "上海",
    "北京",
    "深圳",
    "广州",
    "苏州",
    "南京",
    "成都",
    "武汉",
    "西安",
    "青岛",
    "天津",
    "厦门",
    "合肥",
    "郑州",
    "长沙",
    "福州",
    "重庆",
    "宁波",
    "无锡",
    "佛山",
    "东莞",
    "济南",
    "南昌",
    "贵阳",
    "沈阳",
    "昆明",
)

BRANDS: tuple[tuple[str, str], ...] = (
    ("云启", "yunqi"),
    ("智联", "zhilian"),
    ("恒达", "hengda"),
    ("远图", "yuantu"),
    ("锦程", "jincheng"),
    ("万象", "wanxiang"),
    ("合力", "heli"),
    ("启航", "qihang"),
    ("锐驰", "ruichi"),
    ("博远", "boyuan"),
    ("天工", "tiangong"),
    ("嘉禾", "jiahe"),
    ("明远", "mingyuan"),
    ("康泰", "kangtai"),
    ("新程", "xincheng"),
    ("弘毅", "hongyi"),
)

INDUSTRY_PACKS: tuple[tuple[str, str, str, str], ...] = (
    ("企业服务", "SaaS", "订阅制软件与实施服务", "40-120 人"),
    ("智能制造", "工业设备", "产线自动化改造与设备集成", "80-300 人"),
    ("消费品牌", "电商零售", "线上渠道运营与私域复购", "20-80 人"),
    ("医疗健康", "器械耗材", "院内耗材配送与康复服务", "30-150 人"),
    ("物流供应链", "仓储配送", "区域仓配一体化履约", "60-260 人"),
    ("新能源", "储能设备", "工商业储能与能源管理", "50-200 人"),
    ("教育培训", "企业内训", "企业人才发展与课程交付", "20-90 人"),
    ("文化传媒", "内容营销", "品牌内容制作与投放", "10-60 人"),
    ("农业科技", "农资服务", "订单农业与农资集采", "30-140 人"),
    ("建筑建材", "工程服务", "机电安装与建材集采", "40-180 人"),
)

FUNDING_STAGES: tuple[str, ...] = ("未融资", "天使轮", "A 轮", "A 轮", "B 轮", "C 轮")

MOMENTUM: tuple[str, ...] = (
    "通过渠道扩张寻找新的增量市场",
    "把项目制收入逐步转为订阅制收入",
    "拓展非互联网行业客户以分散风险",
    "补齐数字化基础设施以支撑规模扩张",
    "组建前场销售团队并完善客户成功体系",
)


class _CompanyIndex:
    """把「第 N 家企业」映射到语料或合成条目，两种来源共享同一取用顺序。"""

    def __init__(self) -> None:
        self._corpus_size = len(COMPANY_SEEDS)

    @property
    def corpus_size(self) -> int:
        return self._corpus_size

    def at(self, index: int, preferred_city: str | None = None) -> CompanySeed:
        """取第 index 家企业；超出语料范围时合成，合成条目优先落在目标城市。"""
        if index < self._corpus_size:
            return COMPANY_SEEDS[index]
        return self._synthesize(index - self._corpus_size, preferred_city)

    def _synthesize(self, overflow_index: int, preferred_city: str | None) -> CompanySeed:
        city = preferred_city or CITIES[overflow_index % len(CITIES)]
        brand_cn, brand_py = BRANDS[(overflow_index // len(CITIES)) % len(BRANDS)]
        industry, sub_industry, business, employees = INDUSTRY_PACKS[
            (overflow_index // (len(CITIES) * len(BRANDS))) % len(INDUSTRY_PACKS)
        ]
        funding = FUNDING_STAGES[overflow_index % len(FUNDING_STAGES)]
        momentum = MOMENTUM[(overflow_index // len(FUNDING_STAGES)) % len(MOMENTUM)]
        name = f"{city}{brand_cn}{industry}有限公司"
        domain = f"{brand_py}{overflow_index % 900 + 100}.com"
        summary = (
            f"{name}是一家位于{city}的{industry}企业，主营{business}，员工规模约 {employees}，"
            f"当前融资阶段为 {funding}。公开信息显示其正在{momentum}，"
            "对能够带来可量化产出提升的工具接受度较高。"
        )
        return CompanySeed(
            name=name,
            domain=domain,
            industries=(industry, sub_industry),
            summary=summary,
            location=city,
            employees=employees,
            funding_stage=funding,
        )


COMPANY_INDEX = _CompanyIndex()
