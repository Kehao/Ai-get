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
    # 传统线下行业包。前十个包偏 B2B，画像若落在文旅、零售、餐饮这类到店
    # 生意上，packs_matching() 一个都匹配不到，合成会退回全部包，
    # 于是「找景区民宿」的批量结果里混进半导体与工业软件。
    # 新包的 industry 字段会拼进合成企业名，要写成能自然接在「城市 + 品牌」后面的词。
    ("文旅", "景区酒店民宿", "景区门票住宿与度假预订到店核销", "10-60 人"),
    ("零售", "便利店商超", "门店零售与社群团购到店自提", "10-80 人"),
    ("餐饮", "茶饮烘焙小吃", "堂食外卖运营与会员储值复购", "20-120 人"),
    ("农产品", "生鲜食品", "产地直采与食品加工分销", "10-70 人"),
    ("环保", "节能光伏水处理", "环境治理与节能改造运维", "30-150 人"),
    ("职业培训", "艺术技能教育", "职业技能与兴趣培训交付", "20-90 人"),
    ("家居建材", "家装五金照明", "家居建材经销与工程配套", "30-180 人"),
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

    def at(self, index: int, preferred_city: str | None = None, industry_tokens: tuple[str, ...] = ()) -> CompanySeed:
        """取第 index 家企业；超出语料范围时合成，合成条目优先落在目标城市与目标行业。"""
        if index < self._corpus_size:
            return COMPANY_SEEDS[index]
        return self.synthesize(index - self._corpus_size, preferred_city, industry_tokens)

    def synthesize(
        self,
        index: int,
        preferred_city: str | None = None,
        industry_tokens: tuple[str, ...] = (),
    ) -> CompanySeed:
        """按目标城市与行业提示合成条目。

        手工语料覆盖的行业是有限的，任何稍大的数量都要靠这里补齐；`industry_tokens`
        让合成结果落在画像提到的行业里，否则「找消费品企业」的后续结果会整批跑到别的行业。
        """
        city = preferred_city or CITIES[index % len(CITIES)]
        brand_cn, brand_py = BRANDS[index % len(BRANDS)]
        packs = packs_matching(industry_tokens) or INDUSTRY_PACKS
        industry, sub_industry, business, employees = packs[(index // len(BRANDS)) % len(packs)]
        funding = FUNDING_STAGES[index % len(FUNDING_STAGES)]
        momentum = MOMENTUM[(index // len(FUNDING_STAGES)) % len(MOMENTUM)]
        name = f"{city}{brand_cn}{industry}有限公司"
        # 域名的序号段留出四位数：原来的两位序号在超过 900 条时会绕回重名。
        domain = f"{brand_py}{index % 9000 + 1000}.com"
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


def packs_matching(industry_tokens: tuple[str, ...]) -> tuple[tuple[str, str, str, str], ...]:
    """挑出行业词命中的合成模板。词表同时覆盖模板名称、细分行业与业务描述。"""
    if not industry_tokens:
        return ()
    matched = tuple(
        pack for pack in INDUSTRY_PACKS if any(token in f"{pack[0]}{pack[1]}{pack[2]}" for token in industry_tokens)
    )
    return matched


COMPANY_INDEX = _CompanyIndex()
