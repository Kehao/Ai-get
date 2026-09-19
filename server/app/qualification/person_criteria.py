"""L0 人物标准引擎：把人物画像解析成一组带权重的判断标准。

与 `criteria.py`（会社模式）**并列而不是同一个入口**：两者召回的对象不同
（机构 vs 自然人），可比对的字段也不同，标准自然不该同源。共用一套维度表的后果是
「找公司」的画像会产出姓名标准，或者「找人」的画像被要求核对员工规模。

## 维度与权重

| 维度 | 权重 | 判定依据 | 未命中时的态度 |
| --- | --- | --- | --- |
| `name` 姓名 | 5 | 档案上的展示名 / 中文本名 / 别名 | **硬性**，不是同一个人就是不符合 |
| `title` 职位 | 4 | 现任职位 | 硬性 |
| `company` 公司特征 | 4 | 所属机构的业务方向 | 硬性（档案里没写所属机构时为不确定） |
| `seniority` 职级 | 3 | 职级阶梯位置 | 硬性（相邻职级算不确定，见 `person_judge`） |
| `geo` 地域 | 3 | 个人所在城市 | 硬性（档案常缺所在地，缺了记不确定） |
| `background` 履历背景 | 3 | 公开履历表述 | **lenient**：无法证伪 |
| `signal` 意向信号 | 2 | 公开动态 | **lenient**：同上 |
| `reachability` 可触达性 | 1 | 是否有可用联系方式 | 硬性 |

姓名与职位排最高权重，是因为「找人」这件事的信息几乎全在名字与头衔里；
地域降到 3 而不是像会社模式那样给 5，是因为**个人档案里的所在地缺失率远高于企业**，
给它高权重会让人因为一个常缺的字段整批掉档。

## 什么进硬性维度、什么只进宽松维度

判据是**这条条件在人物档案上可否被证伪**：

- 所属机构做不做这门生意、职位叫不叫这个名字，都能从档案上读出来，可以证伪 → 硬性；
- 「小微企业」「A 轮」「最好有出海经验」这类条件**人物档案上根本不会写**，
  做成硬性标准只会让所有结果凭空掉一档。所以：
  - 规模与融资词在规则引擎里**只作为要剔除的干扰词**，不生成标准；
  - 用户手写补充的条件一律进 `background`（宽松）。

这与会社模式共用同一个哲学：**不可证伪的条件不参与扣分**，
只是「不可证伪」的清单在两种模式下不一样。

## 姓名：宁可少认，不可认错

姓名是一条权重 5 的硬性标准，猜错的代价是整批候选被判成「不符合」——
比漏掉一条姓名条件严重得多。所以规则引擎**只在有明确线索时才认名字**：
带引号、带称呼（`陈可航先生`）、或紧跟「名叫 / 姓名 / 联系人」这类提示词；
整段画像本身就是个名字（`找陈可航`）也算一条线索。
每个候选都要过姓氏表、虚词表、机构后缀三道校验。
没把握时不猜，宁可由用户手工补一条条件。

## 与 LLM 的关系

人物模式**目前只有规则引擎这一条路径**：L0 的提示词契约
（`skills/profile-to-weighted-criteria/contract.json`）里写的是会社模式的维度表，
装载时会逐项断言它与会社的规则表一致，不能直接拿来做人物标准。
`build_person_criteria_detailed()` 因此在 `source` 上如实报 `rule`，
且**不填 `fallback_reason`**——按约定那是「试过但失败」，而这里是从没试过。
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import Literal, Sequence

from .criteria import (
    FUNDING_KEYWORDS,
    INDUSTRY_FAMILIES,
    REGION_CITIES,
    SIZE_BANDS,
    SOURCE_LABELS,
    CriteriaBuild,
    Criterion,
    detect_city,
    detect_region,
)
from ..mock.synth import CITIES

PersonCriterionCategory = Literal[
    "name",
    "title",
    "company",
    "seniority",
    "geo",
    "background",
    "signal",
    "reachability",
]

# 人物模式各维度的权重。改动这里要同步 `person_judge` 的说明与前端条件行的顺序。
PERSON_CATEGORY_WEIGHTS: dict[PersonCriterionCategory, int] = {
    "name": 5,
    "title": 4,
    "company": 4,
    "seniority": 3,
    "geo": 3,
    "background": 3,
    "signal": 2,
    "reachability": 1,
}

# ── 姓名识别 ──────────────────────────────────────────────────────────────

# 常见姓氏（百家姓高频部分）。刻意**排除**「华」「公」「云」「杭」「支」「武」「江」这类
# 与常用词首字重合并几乎不用作姓氏的字：把它们放进来会让「华为」「公司」「云安全」
# 「杭州」「武汉」「江苏」被当成姓名。这是姓名识别里最容易出错的一环，宁可漏。
COMMON_SURNAMES: frozenset[str] = frozenset(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾萧田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦符方白邹孟熊秦邱尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃戴莫孔向汤温康施文牛樊葛邢安常易乔阎连习翟辛关岳池欧骆时卜查裴肖穆花娄聂柏桑荣"
)

# 名字里不会出现的虚词与功能字。命中即判为「这不是一个名字」。
_NAME_BLOCKERS: frozenset[str] = frozenset(
    "的了和与及或是我们个这那些有要请帮做找在中下内外吗呢吧啊就都还也把被给让对从到很更最"
)

# 机构类后缀字。候选词以它们结尾时判为机构名而不是人名（「金融行业」不会变成人名）。
_ORG_SUFFIX_CHARS: frozenset[str] = frozenset("业司团部院校店行局网站台会组队课班器件品牌表书报刊区县市省国厂场园区")

# 整词就是机构/职能词的黑名单，用于兜住上面两条规则的漏网之鱼。
_NOT_A_NAME: frozenset[str] = frozenset(
    (
        "公司", "企业", "集团", "团队", "行业", "金融", "市场", "销售", "产品", "技术",
        "运营", "增长", "渠道", "客户", "商家", "服务", "平台", "系统", "方案", "项目",
        "业务", "品牌", "教育", "医疗", "环保", "能源", "制造", "软件", "数据", "安全",
    )
)

# 明确指向「接下来是一个人名」的提示词，按长度倒序匹配。
# **不带冒号的写法留在这里，带冒号的走下面那条通用规则**（见 `detect_person_names`），
# 因为「找人：」「画像：」「目标：」这类自定义字段名穷举不完。
_NAME_TRIGGERS: tuple[str, ...] = (
    "联系人姓名是", "姓名是", "名字是", "名叫", "叫做", "本人是", "找的人是", "人选是",
)

# 名字**在称呼之前**的写法。它们与 `_NAME_TRIGGERS` 方向相反，要分开处理。
_HONORIFICS: tuple[str, ...] = ("先生", "女士", "老师", "同学", "医生", "律师", "教授")
_TRAILING_MARKERS: tuple[str, ...] = ("这个人", "此人", "本人")

# 整段画像就是一个人名的场合，允许带这些前缀（「找陈可航」）。
_NAME_PREFIXES: tuple[str, ...] = ("帮我找一下", "帮我找", "帮我查", "我想找", "我要找", "寻找", "查找", "搜一下", "找一下", "找找", "找")

# 引号里的内容优先当姓名候选（用户主动加引号 = 他明确知道自己在写一个专有名词）。
_QUOTED = re.compile(r"[「『“\"'‘]([^」』”\"'’]{1,30})[」』”\"'’]")

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z.\-']*")

# 拉丁姓名里不会出现的词——全是职能、职级、机构与行业缩写。
# 没有这道闸，「Sales VP」这种被引号包起来的职位会被认成一个人名。
_LATIN_STOPWORDS: frozenset[str] = frozenset(
    (
        "ai", "saas", "bd", "vp", "cro", "cmo", "cto", "ceo", "coo", "cfo", "hr", "pm",
        "sales", "marketing", "growth", "hacker", "product", "engineering", "design",
        "lead", "head", "director", "manager", "officer", "chief", "of", "and", "or",
        "the", "for", "group", "team", "biz", "tech", "cloud", "data", "security", "inc",
        "ltd", "co", "corp",
    )
)

# 姓名候选允许的长度：中文 2–4 字，拉丁 2–3 个词。
_MIN_CJK_NAME = 2
_MAX_CJK_NAME = 4
_MAX_LATIN_NAME_WORDS = 3

# 会被误认成人名的地名：「苏州」（苏是姓氏）、「郑州」（郑是姓氏）、「武汉」（武是姓氏）……
# 只在「整段画像就是一个名字」那条规则里用来兜底。城市表复用会社模式那一份，
# 另外补上省份与常见城市中首字撞姓氏的那些。
_KNOWN_PLACES: frozenset[str] = frozenset(
    {
        *CITIES,
        "武汉", "郑州", "常州", "温州", "泉州", "徐州", "扬州", "惠州", "柳州", "赣州",
        "石家庄", "秦皇岛", "连云港",
        "江苏", "江西", "陕西", "山西", "云南", "海南", "河南", "河北", "湖南", "湖北",
        "山东", "广东", "广西", "四川", "贵州", "甘肃", "青海", "辽宁", "吉林", "安徽",
        "福建", "浙江", "宁夏", "新疆", "西藏", "内蒙古", "台湾", "香港", "澳门",
    }
)

# ── 职位 ──────────────────────────────────────────────────────────────────

# 职能概念 → 该概念的**全部说法**（中文 + 英文）。
# 存全部说法而不是只存命中的那个词，是因为档案上的职称语言不确定：
# 画像写「销售负责人」时，档案上很可能写着 `VP of Sales`，只拿「销售」去比永远比不中。
ROLE_CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("销售", ("销售", "sales", "大客户", "直销", "客户经理", "account executive")),
    ("营收", ("营收", "revenue", "cro", "商业化", "客户成功", "customer success", "续约")),
    ("商务拓展", ("商务拓展", "商务", "bd", "business development", "渠道", "合作", "partnership", "生态")),
    ("市场", ("市场", "marketing", "品牌", "brand", "公关", "pr", "cmo", "产品市场")),
    ("增长", ("增长", "growth", "获客", "acquisition", "转化", "增长黑客", "growth hacker")),
    ("产品", ("产品", "product", "产品经理", "产品总监", "head of product")),
    ("技术", ("技术", "研发", "engineering", "cto", "架构", "算法", "algorithm", "开发")),
    ("运营", ("运营", "operations", "ops", "社区")),
    ("采购", ("采购", "procurement", "sourcing", "供应链")),
    ("人力", ("人力", "hr", "招聘负责人", "招聘经理", "招聘总监", "recruit", "talent", "组织发展")),
    ("财务", ("财务", "finance", "cfo", "会计")),
    ("设计", ("设计", "design", "ui", "ux")),
    ("学术", ("教授", "副教授", "研究员", "博士", "学术", "课题")),
)

# ── 职级 ──────────────────────────────────────────────────────────────────

# 职级阶梯，从高到低。判定器按「档案职级 ≥ 要求职级」给结论，相邻一级算不确定。
SENIORITY_LADDER: tuple[str, ...] = ("决策层", "管理层", "执行层", "一线")

SENIORITY_BANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "决策层",
        ("创始人", "联合创始人", "合伙人", "总裁", "副总裁", "总经理", "董事长", "首席",
         "vp", "vice president", "chief", "founder", "co-founder", "partner", "president",
         "ceo", "cto", "cmo", "cro", "coo", "cfo"),
    ),
    (
        "管理层",
        ("总监", "负责人", "主管", "校长", "院长", "主任", "head of", "director", "lead"),
    ),
    (
        "执行层",
        ("经理", "manager", "supervisor", "组长"),
    ),
    (
        "一线",
        ("专员", "工程师", "助理", "代表", "engineer", "specialist", "associate", "analyst", "实习生"),
    ),
)

# ── 意向信号（人物侧） ────────────────────────────────────────────────────

# 人物侧的信号与会社侧不同：会社看「数字化」「招投标」，人物看**换岗与上任**——
# 新官上任是触达窗口期，这才是「找人」的业务含义。刻意不含「融资」，
# 那是公司的状态，不是这个人的动态。
PERSON_SIGNAL_KEYWORDS: tuple[str, ...] = (
    "新上任",
    "刚加入",
    "新加入",
    "升任",
    "新任",
    "接手",
    "组建团队",
    "从零搭建",
    "扩张",
    "正在招聘",
    "招聘",
    "公开演讲",
    "受邀分享",
    "受访",
    "获奖",
    "入选",
    "负责新业务",
    "预算",
    "立项",
)

# 人物画像里的意图词与虚词。与会社模式的清单不同——「人选」「候选人」这类词
# 只在找人时出现，留在残句里会变成一条永远判不确定的履历标准。
_PERSON_INTENT_WORDS: tuple[str, ...] = (
    "帮我找一下",
    "帮我找",
    "帮我",
    "想要",
    "我要",
    "我想",
    "寻找",
    "找一找",
    "找找",
    "找",
    "需要",
    "希望",
    "要求",
    "最好是",
    "最好",
    "尽量",
    "优先",
    "偏向",
    "以及",
    "并且",
    "同时",
    "的人",
    "人选",
    "候选人",
    "联系人",
    "人物",
    "客户",
    "公司",
    "企业",
    "机构",
    "画像",
    "目标",
    "这些",
    "以下",
    "左右",
    "以内",
    "以上",
    "负责",
    "担任",
)

_PERSON_SEPARATORS: tuple[str, ...] = (
    "，", ",", "；", ";", "。", "、", "\n", "：", ":", "！", "?", "？", "（", "）", "(", ")",
)
_PERSON_FILLER_CHARS = " 的了与和及或之其有无一个人在到及"
_MIN_SEGMENT_LENGTH = 4
_NAME_LIMIT = 22


# ── 对外入口 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PersonHints:
    """从已冻结的标准里派生出的召回提示。

    派生而不是「再读一遍画像」，是因为标准才是这条任务的真源：用户改过条件、
    或 LLM 与规则引擎的理解不同时，召回必须跟着**当前生效的标准**走。
    重新解析画像会得到第三条互相矛盾的理解路径。
    """

    name_hints: tuple[str, ...] = ()
    role_hints: tuple[str, ...] = ()
    company_hints: tuple[str, ...] = ()
    city: str | None = None


def build_person_criteria(
    text: str,
    *,
    user_conditions: Sequence[str] = (),
) -> list[Criterion]:
    """把人物画像与用户手写的判断条件合并成一份标准清单。"""
    return list(build_person_criteria_detailed(text, user_conditions=user_conditions).criteria)


def build_person_criteria_detailed(
    text: str,
    *,
    user_conditions: Sequence[str] = (),
) -> CriteriaBuild:
    """人物标准的生成。目前只有规则引擎一条路径（原因见模块开头）。

    `fallback_reason` 保持为空：按约定「空 = 从没试过，有值 = 试过但失败」，
    人物模式属于前者，报成失败会让人去查一个并不存在的故障。
    """
    criteria = _criteria_from_profile(text)
    for raw in user_conditions:
        criteria = _merge_user_condition(criteria, raw)

    return CriteriaBuild(
        criteria=tuple(_with_reachability(criteria)),
        source="rule",
        label=SOURCE_LABELS["rule"],
    )


def person_hints(criteria: Sequence[Criterion]) -> PersonHints:
    """把标准里的可比对取值摊平成召回提示。

    交给数据源后**是提示不是过滤条件**：真实数据源多半只能用到姓名做精确检索，
    职位与公司特征只能当排序权重。

    行业词在这一步会被**扩展成同族的全部说法**——这是召回与判定分工的地方：
    标准里只留画像直接写出来的词（判定要严，见 `_detect_company_feature`），
    而召回要宽：「找云安全公司的人」时，一家公开资料只写了「信息安全」的公司也该被捞出来，
    再由判定层去区分它到不到位。
    """
    name_hints: list[str] = []
    role_hints: list[str] = []
    company_hints: list[str] = []
    city: str | None = None

    for criterion in criteria:
        if criterion.category == "name":
            name_hints.extend(criterion.tokens)
        elif criterion.category == "title":
            role_hints.extend(criterion.tokens)
        elif criterion.category == "company":
            company_hints.extend(_expand_industry_tokens(criterion.tokens))
        elif criterion.category == "geo" and city is None:
            city = criterion.expected or (criterion.tokens[0] if criterion.tokens else None)

    return PersonHints(
        name_hints=tuple(dict.fromkeys(name_hints)),
        role_hints=tuple(dict.fromkeys(role_hints)),
        company_hints=tuple(dict.fromkeys(company_hints)),
        city=city,
    )


def _expand_industry_tokens(tokens: Sequence[str]) -> tuple[str, ...]:
    """把行业词扩展成其所在族的全部说法。仅用于召回。"""
    expanded: list[str] = list(tokens)
    for family_tokens in (item[1] for item in INDUSTRY_FAMILIES):
        if any(token in family_tokens for token in tokens):
            expanded.extend(family_tokens)
    return tuple(dict.fromkeys(expanded))


# ── 从画像派生标准 ────────────────────────────────────────────────────────


def _criteria_from_profile(text: str) -> list[Criterion]:
    """顺序稳定：姓名 → 职位 → 职级 → 公司特征 → 地域 → 意向信号 → 履历背景。

    顺序稳定意味着 `id` 稳定，前端条件行的色条与勾选状态才不会在刷新后跳位。
    """
    stripped = text.strip()
    if not stripped:
        return []

    criteria: list[Criterion] = []
    consumed: list[str] = []

    names = detect_person_names(stripped)
    if names:
        criteria.append(
            Criterion(
                id="criterion-name",
                name=f"姓名：{'／'.join(names)}",
                question=f"候选人的姓名是否为{_join(names)}？",
                category="name",
                weight=PERSON_CATEGORY_WEIGHTS["name"],
                tokens=names,
                expected="／".join(names),
                rationale="由画像中点名的姓名推导；姓名不一致即不是要找的人。",
            )
        )
        consumed.extend(names)

    roles = _matched_roles(stripped)
    if roles:
        labels = [concept for concept, _tokens in roles]
        tokens: list[str] = []
        for _concept, concept_tokens in roles:
            tokens.extend(concept_tokens)
        label = labels[0] if len(labels) == 1 else f"{'／'.join(labels)}（任一）"
        criteria.append(
            Criterion(
                id="criterion-title",
                name=f"职位：{label}",
                question=(
                    f"候选人现任职位是否属于{labels[0]}方向？"
                    if len(labels) == 1
                    else f"候选人现任职位是否属于{_join(labels)}中的任一方向？"
                ),
                category="title",
                weight=PERSON_CATEGORY_WEIGHTS["title"],
                tokens=tuple(dict.fromkeys(tokens)),
                expected="／".join(labels),
                rationale="由画像中的职能关键词推导；档案上的职称语言可能是中文或英文，两侧都展开。",
            )
        )
        for _concept, concept_tokens in roles:
            consumed.extend(token for token in concept_tokens if _appears(token, stripped))

    seniority = _detect_seniority(stripped)
    if seniority:
        level, keyword = seniority
        criteria.append(
            Criterion(
                id="criterion-seniority",
                name=f"职级：{level}及以上",
                question=f"候选人的职级是否达到{level}？",
                category="seniority",
                weight=PERSON_CATEGORY_WEIGHTS["seniority"],
                tokens=(keyword,),
                expected=level,
                rationale=f"由画像中的「{keyword}」推导；取画像里出现的**最低**一档作为门槛，"
                "所以「CMO 或市场总监」不会把总监排除在外。",
            )
        )
        consumed.append(keyword)

    company = _detect_company_feature(stripped)
    if company:
        families, tokens = company
        label = families[0] if len(families) == 1 else f"{'／'.join(families)}（任一）"
        criteria.append(
            Criterion(
                id="criterion-company",
                name=f"公司特征：{label}",
                question=(
                    f"候选人所任职的机构是否属于{families[0]}？"
                    if len(families) == 1
                    else f"候选人所任职的机构是否属于{_join(families)}中的任一方向？"
                ),
                category="company",
                weight=PERSON_CATEGORY_WEIGHTS["company"],
                tokens=tokens,
                expected="／".join(families),
                rationale="由画像中的行业与机构关键词推导；判的是「他现在所属机构做什么」，不是他本人做什么。",
            )
        )
        for token in tokens:
            if token in stripped:
                consumed.append(token)

    city = detect_city(stripped)
    if city:
        criteria.append(
            Criterion(
                id="criterion-geo",
                name=f"地域：{city}",
                question=f"候选人是否常驻{city}？",
                category="geo",
                weight=PERSON_CATEGORY_WEIGHTS["geo"],
                tokens=(city,),
                expected=city,
                rationale="画像中点名的城市。个人档案的所在地常缺失或滞后，缺失时按不确定处理。",
            )
        )
        consumed.append(city)
    else:
        region = detect_region(stripped)
        if region:
            cities = REGION_CITIES[region]
            criteria.append(
                Criterion(
                    id="criterion-geo",
                    name=f"地域：{region}",
                    question=f"候选人是否常驻{region}（{'、'.join(cities[:5])} 等）？",
                    category="geo",
                    weight=PERSON_CATEGORY_WEIGHTS["geo"],
                    tokens=cities,
                    expected=region,
                    rationale=f"画像提到区域「{region}」，展开为其覆盖的主要城市。",
                )
            )
            consumed.append(region)

    signals = _longest_match([token for token in PERSON_SIGNAL_KEYWORDS if token in stripped])
    if signals:
        criteria.append(
            Criterion(
                id="criterion-signal",
                name=f"意向信号：{'、'.join(signals[:3])}",
                question=f"公开动态里是否出现与「{'、'.join(signals[:3])}」相关的线索？",
                category="signal",
                weight=PERSON_CATEGORY_WEIGHTS["signal"],
                tokens=tuple(signals),
                rationale="由画像中的信号词推导，用于判断现在是否有触达的窗口期。",
                lenient=True,
            )
        )
        consumed.extend(signals)

    # 规模与融资词在这里被**消费掉但不生成标准**：人物档案上不会写所属公司的员工数
    # 与融资轮次，做成标准只会让所有候选凭空掉一档（见模块开头的说明）。
    consumed.extend(_unverifiable_keywords(stripped))

    for index, segment in enumerate(_leftover_segments(stripped, consumed)):
        criteria.append(
            Criterion(
                id=f"criterion-background-{index}",
                name=f"履历背景：{_shorten(segment)}",
                question=f"公开履历是否体现了「{segment}」？",
                category="background",
                weight=PERSON_CATEGORY_WEIGHTS["background"],
                tokens=(segment,),
                rationale="画像中未能归入姓名/职位/职级/公司的其他限定语，无法证伪时不参与扣分。",
                lenient=True,
            )
        )

    return criteria


# ── 各维度的识别 ──────────────────────────────────────────────────────────


def detect_person_names(text: str) -> tuple[str, ...]:
    """从画像里挑出像人名的片段。识别不出来就返回空——**不猜**。

    四条线索：引号 > 称呼（名字在称呼之前）> 姓名提示词（名字在提示词之后）> 整段就是个名字。
    另外**任何冒号之后的开头**都试一次：`找人：陈可航`、`姓名：陈可航`、`目标：陈可航`
    是同一件事，而字段名（「画像」「目标」「城市」）是用户随手写的，穷举不完。
    每个候选都要过姓氏表、虚词表、机构后缀三道校验，最后按「长的优先」去重：
    命中「陈可航」时不再单独保留「陈可」。
    """
    candidates: list[str] = []

    for matched in _QUOTED.findall(text):
        candidates.extend(_name_candidates(matched))

    for marker in (*_HONORIFICS, *_TRAILING_MARKERS):
        for matched in re.findall(rf"([\u4e00-\u9fff]{{2,4}}){marker}", text):
            if _is_person_name(matched):
                candidates.append(matched)

    for trigger in _NAME_TRIGGERS:
        start = 0
        while True:
            index = text.find(trigger, start)
            if index < 0:
                break
            start = index + len(trigger)
            candidates.extend(_name_candidates(text[start:]))

    for piece in re.split(r"[：:]", text)[1:]:
        candidates.extend(_name_candidates(piece))

    # 整段画像就是一个人名（「找陈可航」），这是找人时最常见的用法。
    stripped = _strip_intent_prefix(text)
    if len(stripped) <= _MAX_CJK_NAME:
        candidates.extend(item for item in _name_candidates(stripped) if not _looks_like_place(item))

    return _dedupe_names(candidates)


def _name_candidates(raw: str) -> list[str]:
    """把一个片段切成姓名候选。中文与拉丁分开处理，两边的校验规则完全不同。

    中文只取片段**开头**的连续汉字，所以「陈可航（云枢出海）」不会把括号切进名字里。
    """
    found: list[str] = []
    segment = raw.strip()

    head_run = _CJK_RUN.match(segment)
    if head_run is not None:
        run = head_run.group(0)
        for size in range(min(_MAX_CJK_NAME, len(run)), _MIN_CJK_NAME - 1, -1):
            head = run[:size]
            if _is_person_name(head):
                found.append(head)
                break

    words = _LATIN_WORD.findall(segment)
    if words:
        for size in range(min(_MAX_LATIN_NAME_WORDS, len(words)), 1, -1):
            head = words[:size]
            if _is_latin_name(head):
                found.append(" ".join(head))
                break

    return found


def _strip_intent_prefix(text: str) -> str:
    """去掉「找 / 帮我找」这类前缀，让「找陈可航」也能走到整段判定。"""
    stripped = text.strip()
    for prefix in _NAME_PREFIXES:
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip(_PERSON_FILLER_CHARS)
    return stripped


def _looks_like_place(value: str) -> bool:
    """地名不是人名。「找武汉」不该被认成找一位姓武的人。"""
    return value in _KNOWN_PLACES


def _is_person_name(value: str) -> bool:
    if not (_MIN_CJK_NAME <= len(value) <= _MAX_CJK_NAME):
        return False
    if value[0] not in COMMON_SURNAMES:
        return False
    if any(char in _NAME_BLOCKERS for char in value):
        return False
    if value[-1] in _ORG_SUFFIX_CHARS:
        return False
    if value in _KNOWN_PLACES:
        return False
    return value not in _NOT_A_NAME


def _is_latin_name(words: Sequence[str]) -> bool:
    if len(words) < 2:
        return False
    for word in words:
        cleaned = word.strip(".-'").lower()
        if len(cleaned) < 2 or cleaned in _LATIN_STOPWORDS:
            return False
    return True


def _dedupe_names(candidates: Sequence[str]) -> tuple[str, ...]:
    """长的优先：命中「陈可航」时丢掉它的前缀「陈可」，两者都留会让界面显示两条姓名条件。"""
    ordered = sorted(dict.fromkeys(item for item in candidates if item), key=len, reverse=True)
    kept: list[str] = []
    for item in ordered:
        if any(item != other and item in other for other in kept):
            continue
        kept.append(item)
    return tuple(kept[:2])


def _matched_roles(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """画像里提到的职能方向，返回 (概念, 该概念的全部说法)。"""
    lowered = text.lower()
    matched: list[tuple[str, tuple[str, ...]]] = []
    for concept, tokens in ROLE_CONCEPTS:
        if any(token.lower() in lowered for token in tokens):
            matched.append((concept, tokens))
    return matched


def _detect_seniority(text: str) -> tuple[str, str] | None:
    """识别画像要求的职级，取出现过的**最低**那一档作为门槛。

    取最低而不是最高，是为了处理「CMO 或市场总监」这种并列写法：
    两个职级并列时门槛应落在低的那一档，否则总监会被判成「差一级」。
    """
    lowered = text.lower()
    matched: list[tuple[str, str]] = []
    for level, keywords in SENIORITY_BANDS:
        keyword = next((item for item in keywords if item in text or item in lowered), None)
        if keyword is not None:
            matched.append((level, keyword))

    if not matched:
        return None

    floor = max(matched, key=lambda item: SENIORITY_LADDER.index(item[0]))
    return floor


def _detect_company_feature(text: str) -> tuple[list[str], tuple[str, ...]] | None:
    """识别「对方所在的是什么公司」，复用会社模式的行业族词表。

    返回 (行业族名, **画像里直接写出来的**行业词)。**只留直接写出来的词**这一条很关键：
    行业族是一张粗表，「企业服务与软件」同时装着「云安全」与「AI」「机器视觉」，
    把整族词都塞进标准，会让「找云安全公司的市场总监」把一家人工智能公司的市场总监
    判成「明确符合」——召回宽、判定严，两件事不能混。

    同族词的扩展只发生在**召回**那一侧（见 `person_hints`）。

    只取行业，不取规模与融资：后两者在人物档案上不可验证（见模块开头）。
    """
    families: list[str] = []
    direct: list[str] = []
    for family, family_tokens in INDUSTRY_FAMILIES:
        hits = [token for token in family_tokens if token in text]
        if not hits:
            continue
        families.append(family)
        direct.extend(hits)
    if not families:
        return None
    return families, tuple(dict.fromkeys(direct))


def _unverifiable_keywords(text: str) -> list[str]:
    """规模与融资词。它们**只被剔除、不生成标准**。"""
    found: list[str] = []
    for keywords, _band, _label in SIZE_BANDS:
        found.extend(keyword for keyword in keywords if keyword in text)
    lowered = text.lower().replace(" ", "")
    for keywords, _stage in FUNDING_KEYWORDS:
        for keyword in keywords:
            if keyword.lower().replace(" ", "") in lowered:
                found.append(keyword)
                break
    return found


def _longest_match(tokens: Sequence[str]) -> list[str]:
    """去掉被更长关键词包含的短词（「正在招聘」命中后不再单独记「招聘」）。"""
    return [token for token in tokens if not any(token != other and token in other for other in tokens)]


def _join(names: Sequence[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return "、".join(names)
    return f"{'、'.join(names[:3])} 等"


def _leftover_segments(text: str, consumed: Sequence[str]) -> list[str]:
    """切出未能归类的画像片段，作为「履历背景」标准。

    与会社模式同一条思路：先剔掉已被消费的词，再剔掉意图词，剩下的残句才值得当条件。
    分句符比会社模式多一个冒号——找人时「联系人：陈可航」这种写法很常见。
    """
    normalized = text
    for separator in _PERSON_SEPARATORS:
        normalized = normalized.replace(separator, "|")

    segments: list[str] = []
    for raw in normalized.split("|"):
        segment = raw.strip()
        if len(segment) < _MIN_SEGMENT_LENGTH:
            continue
        residue = segment
        for token in sorted(consumed, key=len, reverse=True):
            residue = _remove_term(residue, token)
        for word in sorted(_PERSON_INTENT_WORDS, key=len, reverse=True):
            residue = _remove_term(residue, word)
        residue = residue.strip(_PERSON_FILLER_CHARS)
        if len(residue) < _MIN_SEGMENT_LENGTH:
            continue
        segments.append(segment)

    return segments[:2]


def _remove_term(text: str, term: str) -> str:
    """从残句里剔除一个已消费的词。

    拉丁词按**大小写不敏感**剔除：英文职称在画像里常写成大写（`CMO`、`VP`、`BD`），
    而职能词表里存的是小写。只按词表里的写法做 `replace`，正文里的 `CMO` 会原样留在
    残句里，于是「找云安全公司的 CMO」会多出一条永远判不确定的履历背景标准。
    """
    if term.isascii() and term.isalpha():
        return re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    return text.replace(term, "")


def _appears(term: str, text: str) -> bool:
    """词是否出现在正文里。与 `_remove_term` 配对的判定，大小写口径必须一致。"""
    if term.isascii() and term.isalpha():
        return term.lower() in text.lower()
    return term in text


def _merge_user_condition(criteria: list[Criterion], raw: str) -> list[Criterion]:
    """把用户手写的一条条件并入标准清单。

    除姓名外一律作为**宽松**的履历背景标准：手写的条件几乎不可能被公开履历证伪，
    因此不能参与扣分。姓名是例外——它可证伪且指向明确，值得单独成条。
    """
    text = raw.strip()
    if not text:
        return criteria

    if _is_round_tripped_label(text, criteria):
        return criteria

    existing = {item.name for item in criteria}

    names = detect_person_names(text)
    if names and not any(item.category == "name" for item in criteria):
        name = f"姓名：{'／'.join(names)}"
        if name not in existing:
            return [
                *criteria,
                Criterion(
                    id="criterion-name-user",
                    name=name,
                    question=f"候选人的姓名是否为{_join(names)}？",
                    category="name",
                    weight=PERSON_CATEGORY_WEIGHTS["name"],
                    tokens=names,
                    expected="／".join(names),
                    rationale="用户手动补充的判断条件。",
                ),
            ]

    name = f"履历背景：{_shorten(text)}"
    if name in existing:
        return criteria
    return [
        *criteria,
        Criterion(
            # CRC32 而不是内置 hash：内置 hash 对字符串按进程随机加盐，
            # 会让同一条条件在服务重启后换 id，条件行的色条随之跳位。
            id=f"criterion-user-{zlib.crc32(text.encode()) % 10**6}",
            name=name,
            question=f"公开履历是否体现了「{text}」？",
            category="background",
            weight=PERSON_CATEGORY_WEIGHTS["background"],
            tokens=(text,),
            rationale="用户手动补充的判断条件，无法证伪时不参与扣分。",
            lenient=True,
        ),
    ]


def _is_round_tripped_label(text: str, criteria: Sequence[Criterion]) -> bool:
    """判断这条「用户条件」是不是引擎自己下发、又被前端原样回传的条件名。

    条件面板会把当前生效的条件名回传（「职位：市场」「公司特征：企业服务与软件」「可触达性」……），
    它们**不是用户新增的条件**。若不识别，每条都会被包成一条宽松的「履历背景：职位：市场」，
    权重表凭空翻倍、结论随之漂移——同一份配置走「保存配置」与「重新挖掘」还会得到不同的判定。

    只跳过**能对上已有标准**的那些：带未知取值的同类条件（如「职位：必须有海外 SaaS 经验」）
    仍然按用户条件收下，不会被静默丢掉。
    """
    for item in criteria:
        if text == item.name:
            return True
    # 可触达性由引擎在合并之后才补，比对时列表里可能还没有这条，单独认它的名字。
    if text == REACHABILITY_LABEL:
        return True
    prefix, separator, remainder = text.partition("：")
    if not separator:
        return False
    for item in criteria:
        if not item.name.startswith(f"{prefix}："):
            continue
        if remainder == item.expected or _appears(remainder, item.name):
            return True
    return False


# 可触达性这条标准的名称。`_with_reachability` 与「回传的条件名要跳过」两处共用一份字面量：
# 名字对不上时，条件面板回传的「可触达性」会被当成新条件，多出一条重复的宽松标准。
REACHABILITY_LABEL = "可触达性"


def _with_reachability(criteria: list[Criterion]) -> list[Criterion]:
    """可触达性永远参与评估：拿不到任何联系方式的人进不了触达序列。"""
    if any(item.category == "reachability" for item in criteria):
        return criteria
    return [
        *criteria,
        Criterion(
            id="criterion-reachability",
            name=REACHABILITY_LABEL,
            question="是否能获取到可用的公开联系方式？",
            category="reachability",
            weight=PERSON_CATEGORY_WEIGHTS["reachability"],
            rationale="任何画像都适用的通用标准：无法触达的人不应占用触达序列名额。",
        ),
    ]


def _shorten(text: str, limit: int = _NAME_LIMIT) -> str:
    """与会社模式保持同一个截断长度，使两种模式的条件名看起来是同一种东西。"""
    stripped = text.strip()
    return stripped if len(stripped) <= limit else f"{stripped[:limit]}…"
