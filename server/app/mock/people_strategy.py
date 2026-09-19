"""找人模式的「挖掘策略」文案生成。

与会社模式（`strategy.py`）并列，但**不共用实现**：会社给 2 组，解释「这批企业是按什么思路
圈出来的」；找人给 6 组，解释**同一个检索对象会在哪些语种、哪些地区、哪些机构语境下留下档案**。
两者的分组依据没有共同部分（一个是行业与规模，一个是语种、地区与机构类型），
硬合并只会得到一堆 `if mode == ...`。

检索对象分两类，文案跟着分两套：

* **点名找人**（画像里出现了人名，如「邱克浩」）：围绕「这个名字的拼音正序与倒序、
  中文全名在各语种站点上的写法」展开。
* **按职能找人**（如「云安全公司的 CMO 或市场总监」）：围绕「这个职称的中英文写法，
  以及同一职能在各类机构里的同类岗位」展开。

后四组（金融 / 学术创新 / 技术工业 / 教育跨境）是**主动外扩**：它们刻意不再限定原行业，
因为「同一职能换个机构语境」正是漏召的主要来源。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from ..models import StrategyGroup
from ..qualification.criteria import INDUSTRY_FAMILIES, detect_city
from ..qualification.person_criteria import build_person_criteria

_CJK_NAME = re.compile(r"[\u4e00-\u9fff]{2,4}")
_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z.\-']*")

# ── 姓名拼音 ──────────────────────────────────────────────────────────────

# 姓名用字 → 拼音。**刻意自成一份，不与 `people_synth` 的字表合并**：那份是「造语料时用的
# 姓名组件」，只覆盖造数据会抽到的字；这份要能拼**任意用户输入的姓名**（例如「邱」），
# 覆盖范围不同，合并会让任一边的需求被另一边绑住。
#
# 表是**有界**的：只收常用姓氏与常见名字用字。表外字一律不猜拼音，文案改用
# 「拼音正序 / 倒序写法」这样的描述性说法——策略文案会被用户当成检索指令，
# 给一个错的写法比不给更糟。
_PINYIN: dict[str, str] = {
    # 常用姓氏
    "张": "Zhang", "王": "Wang", "李": "Li", "赵": "Zhao", "陈": "Chen", "刘": "Liu",
    "杨": "Yang", "黄": "Huang", "周": "Zhou", "吴": "Wu", "徐": "Xu", "孙": "Sun",
    "胡": "Hu", "朱": "Zhu", "高": "Gao", "林": "Lin", "何": "He", "郭": "Guo",
    "马": "Ma", "罗": "Luo", "梁": "Liang", "宋": "Song", "郑": "Zheng", "谢": "Xie",
    "韩": "Han", "唐": "Tang", "冯": "Feng", "于": "Yu", "董": "Dong", "萧": "Xiao",
    "肖": "Xiao", "程": "Cheng", "曹": "Cao", "袁": "Yuan", "邓": "Deng", "许": "Xu",
    "傅": "Fu", "沈": "Shen", "曾": "Zeng", "彭": "Peng", "吕": "Lyu", "苏": "Su",
    "卢": "Lu", "蒋": "Jiang", "蔡": "Cai", "贾": "Jia", "丁": "Ding", "魏": "Wei",
    "薛": "Xue", "叶": "Ye", "阎": "Yan", "余": "Yu", "潘": "Pan", "杜": "Du",
    "戴": "Dai", "夏": "Xia", "钟": "Zhong", "汪": "Wang", "田": "Tian", "任": "Ren",
    "姜": "Jiang", "范": "Fan", "方": "Fang", "石": "Shi", "姚": "Yao", "谭": "Tan",
    "廖": "Liao", "邹": "Zou", "熊": "Xiong", "金": "Jin", "陆": "Lu", "郝": "Hao",
    "孔": "Kong", "白": "Bai", "崔": "Cui", "康": "Kang", "毛": "Mao", "邱": "Qiu",
    "秦": "Qin", "江": "Jiang", "史": "Shi", "顾": "Gu", "侯": "Hou", "邵": "Shao",
    "孟": "Meng", "龙": "Long", "万": "Wan", "段": "Duan", "雷": "Lei", "钱": "Qian",
    "汤": "Tang", "尹": "Yin", "黎": "Li", "易": "Yi", "常": "Chang", "武": "Wu",
    "乔": "Qiao", "贺": "He", "赖": "Lai", "龚": "Gong", "文": "Wen", "庞": "Pang",
    "樊": "Fan", "兰": "Lan", "殷": "Yin", "施": "Shi", "陶": "Tao", "洪": "Hong",
    "翟": "Zhai", "安": "An", "颜": "Yan", "倪": "Ni", "严": "Yan", "牛": "Niu",
    "温": "Wen", "季": "Ji", "俞": "Yu", "章": "Zhang", "鲁": "Lu", "葛": "Ge",
    "伍": "Wu", "韦": "Wei", "申": "Shen", "尤": "You", "毕": "Bi", "聂": "Nie",
    "焦": "Jiao", "向": "Xiang", "柳": "Liu", "骆": "Luo", "祝": "Zhu", "纪": "Ji",
    "欧": "Ou", "戚": "Qi", "解": "Xie", "强": "Qiang", "柴": "Chai", "华": "Hua",
    "车": "Che", "冉": "Ran", "房": "Fang", "边": "Bian", "吉": "Ji", "饶": "Rao",
    "刁": "Diao", "瞿": "Qu", "靳": "Jin", "管": "Guan", "甘": "Gan", "祁": "Qi",
    "翁": "Weng", "苗": "Miao", "庄": "Zhuang", "晏": "Yan", "胥": "Xu", "甄": "Zhen",
    "荣": "Rong", "桑": "Sang", "穆": "Mu", "花": "Hua", "柏": "Bai", "娄": "Lou",
    # 常见名字用字
    "伟": "Wei", "芳": "Fang", "娜": "Na", "敏": "Min", "静": "Jing", "丽": "Li",
    "磊": "Lei", "军": "Jun", "洋": "Yang", "勇": "Yong", "艳": "Yan", "杰": "Jie",
    "娟": "Juan", "涛": "Tao", "明": "Ming", "超": "Chao", "霞": "Xia", "平": "Ping",
    "刚": "Gang", "桂": "Gui", "英": "Ying", "玉": "Yu", "凤": "Feng", "春": "Chun",
    "红": "Hong", "梅": "Mei", "玲": "Ling", "燕": "Yan", "云": "Yun", "鹏": "Peng",
    "飞": "Fei", "宇": "Yu", "鑫": "Xin", "昊": "Hao", "天": "Tian", "斌": "Bin",
    "兵": "Bing", "东": "Dong", "海": "Hai", "山": "Shan", "森": "Sen", "峰": "Feng",
    "岭": "Ling", "川": "Chuan", "洲": "Zhou", "波": "Bo", "澜": "Lan", "雨": "Yu",
    "雪": "Xue", "月": "Yue", "星": "Xing", "晨": "Chen", "辰": "Chen", "曦": "Xi",
    "阳": "Yang", "光": "Guang", "辉": "Hui", "灿": "Can", "煜": "Yu", "燃": "Ran",
    "炎": "Yan", "水": "Shui", "木": "Mu", "土": "Tu", "珠": "Zhu", "宝": "Bao",
    "珍": "Zhen", "贵": "Gui", "富": "Fu", "建": "Jian", "国": "Guo", "志": "Zhi",
    "立": "Li", "新": "Xin", "世": "Shi", "界": "Jie", "和": "He", "顺": "Shun",
    "利": "Li", "兴": "Xing", "隆": "Long", "昌": "Chang", "盛": "Sheng", "泰": "Tai",
    "乐": "Le", "喜": "Xi", "福": "Fu", "才": "Cai", "学": "Xue", "问": "Wen",
    "书": "Shu", "礼": "Li", "义": "Yi", "仁": "Ren", "德": "De", "信": "Xin",
    "忠": "Zhong", "孝": "Xiao", "贤": "Xian", "良": "Liang", "正": "Zheng", "清": "Qing",
    "廉": "Lian", "勤": "Qin", "俭": "Jian", "慧": "Hui", "颖": "Ying", "睿": "Rui",
    "智": "Zhi", "哲": "Zhe", "思": "Si", "远": "Yuan", "近": "Jin", "大": "Da",
    "小": "Xiao", "中": "Zhong", "元": "Yuan", "亨": "Heng", "通": "Tong", "达": "Da",
    "克": "Ke", "浩": "Hao", "凯": "Kai", "翔": "Xiang", "毅": "Yi", "俊": "Jun",
    "豪": "Hao", "帅": "Shuai", "彬": "Bin", "楠": "Nan", "桐": "Tong", "柠": "Ning",
    "若": "Ruo", "彤": "Tong", "依": "Yi", "维": "Wei", "子": "Zi", "墨": "Mo",
    "嘉": "Jia", "禾": "He", "亦": "Yi", "彦": "Yan", "霖": "Lin", "知": "Zhi",
    "微": "Wei", "然": "Ran", "启": "Qi", "帆": "Fan", "琪": "Qi", "牧": "Mu",
    "野": "Ye", "宁": "Ning", "鹤": "He", "舟": "Zhou", "玥": "Yue", "航": "Hang",
    "婷": "Ting", "萱": "Xuan", "悦": "Yue", "蕾": "Lei", "琳": "Lin", "珊": "Shan",
    "涵": "Han", "琦": "Qi", "赫": "He", "泽": "Ze", "渊": "Yuan", "桦": "Hua",
    "榕": "Rong", "骁": "Xiao", "骏": "Jun", "骐": "Qi", "珂": "Ke", "筝": "Zheng",
    "岚": "Lan", "旭": "Xu", "昂": "Ang", "朗": "Lang", "越": "Yue", "拓": "Tuo",
    "禹": "Yu", "舜": "Shun", "尧": "Yao", "可": "Ke", "之": "Zhi", "铭": "Ming",
    "锋": "Feng", "冶": "Ye", "沁": "Qin", "洛": "Luo", "汐": "Xi", "芮": "Rui",
    "芷": "Zhi", "芊": "Qian", "梦": "Meng", "婉": "Wan", "妍": "Yan", "姝": "Shu",
}

# ── 职称 ──────────────────────────────────────────────────────────────────

# 职能概念（`person_criteria.ROLE_CONCEPTS` 的键）→ 展示用的岗位名词。
# 概念名是「检索维度」，不是「岗位名」：画像里写「市场」，文案里说「市场负责人」才读得通。
_ROLE_NOUNS: dict[str, str] = {
    "销售": "销售负责人",
    "营收": "营收负责人",
    "商务拓展": "商务拓展负责人",
    "市场": "市场负责人",
    "增长": "增长负责人",
    "产品": "产品负责人",
    "技术": "技术负责人",
    "运营": "运营负责人",
    "采购": "采购负责人",
    "人力": "人力资源负责人",
    "财务": "财务负责人",
    "设计": "设计负责人",
    "学术": "学术研究者",
}

# 英文缩写的行业惯例写法：词表里存的是小写，展示时按惯例大写。
_ACRONYM_DISPLAY: dict[str, str] = {
    "ceo": "CEO", "cmo": "CMO", "cro": "CRO", "cto": "CTO", "coo": "COO", "cfo": "CFO",
    "vp": "VP", "hr": "HR", "bd": "BD", "pr": "PR", "saas": "SaaS", "ops": "Ops",
    "ai": "AI", "b2b": "B2B", "mes": "MES", "ui": "UI", "ux": "UX",
}

_FALLBACK_EN_ROLE = "a professional in the target function"
_FALLBACK_CN_ROLE = "目标职能负责人"


def romanize_name(name: str) -> tuple[str, str] | None:
    """把中文姓名转成（名在前, 姓在前）两种拼音写法；有表外字则返回 `None`。

    返回 `None` 是**正常出口**而不是异常：调用方会退回描述性说法，
    而不是拿一个缺字或猜出来的拼音去糊弄用户。
    """
    stem = name.strip()
    if not _CJK_NAME.fullmatch(stem):
        return None
    syllables = [_PINYIN.get(char) for char in stem]
    if any(syllable is None for syllable in syllables):
        return None
    surname = syllables[0]
    # 多字名连写时只保留首字母大写（「Ke」+「Hao」→「Kehao」），
    # 与姓名拼音的通行写法一致，也让「正序 / 倒序」两种写法看起来是同一个名字。
    given = "".join(syllables[1:])
    given = f"{given[:1]}{given[1:].lower()}"
    return f"{given} {surname}", f"{surname} {given}"


# ── 检索对象 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Subject:
    """策略文案里被替换进模板的一组说法。

    姓名侧与职能侧**必须给出同一套键**：两组模板要靠同一批插槽渲染出 6 组文案，
    缺键会在 `.format()` 时炸掉（而不是悄悄少一块内容）。
    """

    slots: Mapping[str, str]


def _name_subject(name: str) -> _Subject:
    """点名找人：姓名的中英文写法。"""
    if _CJK_NAME.fullmatch(name):
        romanized = romanize_name(name)
        if romanized:
            forward, reverse = romanized
            asia_subject = f"{name} (also written {forward} or {reverse})"
        else:
            # 表外字：不展示具体拼音，改成描述「正序 / 倒序两种写法」。
            forward = f"the given-name-first Pinyin spelling of {name}"
            reverse = f"the surname-first Pinyin spelling of {name}"
            asia_subject = f"{name} (with its Pinyin spellings in both orders)"
        return _Subject(
            {
                "cjk_name": name,
                "latin_forward": forward,
                "latin_reverse": reverse,
                "asia_subject": asia_subject,
            }
        )

    # 画像里本来就是拉丁写法（如「Chen Kehang」）：直接给出两种词序，中文侧改成描述性说法。
    words = _LATIN_WORD.findall(name)
    reversed_name = " ".join(reversed(words)) if len(words) > 1 else name
    return _Subject(
        {
            "cjk_name": f"「{name}」的中文写法",
            "latin_forward": name,
            "latin_reverse": reversed_name,
            "asia_subject": f"{name} (also written {reversed_name})",
        }
    )


def _role_subject(query: str, criteria) -> _Subject:
    """按职能找人：职称与所属机构的中英文说法。"""
    title = _criterion(criteria, "title")
    company = _criterion(criteria, "company")

    concept = (title.expected or "").split("／")[0] if title else ""
    cn_role = _ROLE_NOUNS.get(concept, _FALLBACK_CN_ROLE)
    en_role = _english_role(title.tokens if title else ()) or _FALLBACK_EN_ROLE
    en_subject = _with_article(en_role)

    industry_cn = _industry_cn(company)
    industry_en = _industry_en(company)
    if industry_en:
        en_subject = f"{en_subject} at {_with_article(industry_en)} company"

    city = detect_city(query)
    return _Subject(
        {
            # 英文句子里嵌中文职能名读不通，所以后四组（英文模板）取 `en_subject`，
            # 前两组的中文模板取 `cn_subject`；两边都从同一份职称标准推导。
            "cjk_name": en_subject,
            "latin_forward": en_subject,
            "latin_reverse": en_subject,
            "asia_subject": en_subject,
            "cn_role": cn_role,
            "cn_subject": f"{industry_cn}的{cn_role}" if industry_cn else cn_role,
            "en_subject": en_subject,
            "region_cn": city or "目标地区",
            "title_aliases_en": _aliases(title.tokens if title else (), latin=True),
            "title_aliases_cn": _aliases(title.tokens if title else (), latin=False),
        }
    )


def _criterion(criteria, category: str):
    for item in criteria:
        if item.category == category:
            return item
    return None


def _english_role(tokens) -> str:
    """从职称词表里挑一个英文锚点派生出「a marketing leader」这类说法。"""
    for token in tokens:
        if token.isascii():
            return f"{_display(token)} leader"
    return ""


def _industry_cn(company) -> str:
    """行业侧只取**画像里直接写出**的词（`tokens` 就是那个集合），不拿家族名去替。"""
    if company is None or not company.tokens:
        return ""
    mentioned = [token for token in company.tokens if _LATIN_WORD.fullmatch(token)]
    return "／".join(mentioned[:2]) or "／".join(company.tokens[:2])


def _industry_en(company) -> str:
    """行业没有英文写法时，退回家族的英文锚点（如 云安全 → 企业服务与软件 → SaaS）。"""
    if company is None:
        return ""
    for token in company.tokens:
        if _LATIN_WORD.fullmatch(token):
            return _display(token)
    for family, family_tokens in INDUSTRY_FAMILIES:
        if family == company.expected:
            for token in family_tokens:
                if _LATIN_WORD.fullmatch(token):
                    return _display(token)
    return ""


def _aliases(tokens, *, latin: bool) -> str:
    """把词表里的一串说法压成展示用的别名列表，按小写去重。"""
    picked: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token.isascii() != latin:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append(_display(token) if latin else token)
    separator = " / " if latin else "、"
    return separator.join(picked[:4])


def _display(token: str) -> str:
    return _ACRONYM_DISPLAY.get(token.lower(), token)


def _with_article(phrase: str) -> str:
    """补不定冠词：`a marketing leader` / `an HR leader` / `a SaaS company`。"""
    head = phrase.partition(" ")[0]
    if head.lower() in {"a", "an", "the"}:
        return phrase
    if head[:2].isupper():
        # 全大写缩写按字母读：「HR」是「aitch-arr」→ an；「BD」是「bee-dee」→ a。
        return f"an {phrase}" if head[0].upper() in "AEFHILMNORSX" else f"a {phrase}"
    return f"an {phrase}" if head[:1].lower() in "aeiou" else f"a {phrase}"


# ── 策略分组 ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _GroupSpec:
    id: str
    title: str
    description: str
    examples: tuple[str, ...]

    def render(self, slots: Mapping[str, str]) -> StrategyGroup:
        return StrategyGroup(
            id=self.id,
            title=self.title.format(**slots),
            description=self.description.format(**slots),
            examples=[example.format(**slots) for example in self.examples],
        )


# 后四组的标题沿用参考站的英文写法（前三组用中文）：这是参考站的实际形态，
# 也对应「这组的检索会落到英文语料的站点上」。
_LATIN_GROUPS: tuple[_GroupSpec, ...] = (
    _GroupSpec(
        id="strategy-people-asia-business",
        title="Asia business and finance profiles",
        description="Targets named-professional bios in Hong Kong, China and Singapore, "
        "where this kind of role shows up most often in finance, advisory, investment, "
        "and regional business organizations.",
        examples=(
            "A public professional profile for {asia_subject} holding a current role at a "
            "financial services, investment, consulting, or corporate organization in "
            "Hong Kong, China, with a named title and career biography.",
            "A LinkedIn-style or company biography for {asia_subject}, a Singapore-based "
            "business development, investment, strategy, or advisory professional with a "
            "named employer and current responsibilities.",
            "A conference speaker, industry association, or executive biography for "
            "{asia_subject} describing a leadership, commercial, finance, or "
            "professional-services role at a specific organization in Taiwan, China.",
        ),
    ),
    _GroupSpec(
        id="strategy-people-academic",
        title="Academic and innovation affiliations",
        description="Expands beyond standard employer team pages to identifiable academic, "
        "innovation, and venture ecosystem profiles with career-relevant institutional "
        "affiliations.",
        examples=(
            "A university faculty, research center, innovation lab, or alumni professional "
            "biography for {cjk_name} that identifies a current "
            "institutional or industry role, professional specialty, and career background "
            "in mainland China.",
            "A startup accelerator, venture studio, technology incubator, or "
            "entrepreneurship program profile for {latin_forward} with a "
            "defined founder, operator, mentor, product, or investment role and a named "
            "organization.",
            "A professional association, innovation forum, or technology event speaker page "
            "for {latin_reverse} that identifies their employer, role, "
            "professional expertise, and work history in the United States.",
        ),
    ),
    _GroupSpec(
        id="strategy-people-technical",
        title="Technical and industrial professionals",
        description="Expands into identifiable engineering, manufacturing, and technology "
        "professionals through project, patent, and employer-linked biographies in new "
        "mainland China and Taiwan, China contexts.",
        examples=(
            "A public professional profile for {cjk_name}, identifying an "
            "engineering, technology, manufacturing, or R&D professional with a current "
            "employer, job title, and project or technical career background in mainland "
            "China.",
            "A patent inventor, technical conference speaker, product engineering leader, or "
            "corporate expert biography for {latin_reverse} that names a "
            "company or research organization and describes professional inventions, "
            "projects, or technical responsibilities.",
            "A company staff, leadership, or project delivery profile for "
            "{latin_forward} with a named role in industrial technology, "
            "software, infrastructure, operations, or product development and a documented "
            "professional career history.",
        ),
    ),
    _GroupSpec(
        id="strategy-people-education",
        title="Education and cross-border career profiles",
        description="Targets alumni, executive education, professional-services, and "
        "overseas career pages that can reveal a named employer and current role outside "
        "the previously emphasized finance and startup ecosystem.",
        examples=(
            "An alumni spotlight, executive education biography, or university career "
            "profile for {cjk_name} that identifies a current corporate, "
            "technology, or professional-services position and a named employer in Taiwan, "
            "China.",
            "A public LinkedIn-style profile or company biography for "
            "{latin_forward}, working in business operations, supply "
            "chain, commercial management, or international trade at a named employer in "
            "Canada.",
            "A professional association member, industry event speaker, or employer team "
            "biography for {latin_reverse} describing a current role in "
            "corporate services, logistics, technology, or business development at a named "
            "organization in Australia.",
        ),
    ),
)

_NAME_GROUPS: tuple[_GroupSpec, ...] = (
    _GroupSpec(
        id="strategy-people-latin",
        title="英文职业主页与海外履历",
        description="用姓名的拼音正序与倒序覆盖 LinkedIn、公司团队页及海外工作履历中的具体职业人物介绍。",
        examples=(
            "A professional profile for {latin_forward}, including a current job title, "
            "employer, and career background on LinkedIn or a company team page.",
            "A public professional biography for {latin_reverse} describing their current "
            "role, organization, and work experience in an English-language profile.",
            "A professional named {latin_forward} with a named employer and role, listed on "
            "a leadership, staff, or speaker biography page.",
        ),
    ),
    _GroupSpec(
        id="strategy-people-cjk",
        title="中文姓名的本地职业身份",
        description="以中文全名检索中国大陆及华语职场网站上的在职介绍、团队成员页、演讲者简介与项目署名。",
        examples=(
            "{cjk_name}的职业人物主页，包含其现任职位、所在机构与工作经历的公开个人简介。",
            "一位名为{cjk_name}的在职专业人士，在公司团队介绍、管理层页面或项目成员简介中说明其职责与雇主。",
            "{cjk_name}作为企业管理者、专业顾问、技术人员或项目负责人，在会议嘉宾简介或机构人员页面上的个人介绍。",
        ),
    ),
)

_ROLE_GROUPS: tuple[_GroupSpec, ...] = (
    _GroupSpec(
        id="strategy-people-latin",
        title="英文职称与海外雇主",
        description="用职称的英文全称与常见缩写（{title_aliases_en}）覆盖 LinkedIn、公司团队页与海外职场档案中的在职介绍。",
        examples=(
            "A professional profile for {en_subject}, including a current job title, "
            "employer, and career background on LinkedIn or a company team page.",
            "A public professional biography describing {en_subject} with their current "
            "role, organization, and work experience in an English-language profile.",
            "An English-language profile of {en_subject}, listed on a leadership, staff, or "
            "speaker biography page with a named employer.",
        ),
    ),
    _GroupSpec(
        id="strategy-people-cjk",
        title="中文职称与本地雇主",
        description="以职称的中文写法（{title_aliases_cn}）检索中国大陆及华语职场网站上的在职介绍、团队成员页、演讲者简介与项目署名。",
        examples=(
            "{cn_subject}的职业人物主页，包含其现任职位、所在机构与工作经历的公开个人简介。",
            "一位任职于{region_cn}同类机构、职级相当的{cn_role}，在公司团队介绍、管理层页面或项目成员简介中说明其职责与雇主。",
            "{cn_subject}作为企业管理者、专业顾问或项目负责人，在会议嘉宾简介或机构人员页面上的个人介绍。",
        ),
    ),
)


def build_people_strategy_groups(query: str) -> list[StrategyGroup]:
    """生成找人模式的 6 组挖掘策略。

    前三组与后三组共用一套模板，靠「检索对象是姓名还是职能」决定替换进去的说法，
    因此 6 组的组数与顺序是恒定的——前端用 `length` 直接渲染成「6组」。
    """
    criteria = build_person_criteria(query)
    name_criterion = _criterion(criteria, "name")

    if name_criterion is not None and name_criterion.tokens:
        # 点名找人：前两组讲「这个名字的两种拼音写法 + 中文全名」，
        # 后四组把中文名直接嵌进英文句子（参考站就是这么排的）。
        subject = _name_subject(name_criterion.tokens[0])
        specs = (*_NAME_GROUPS, *_LATIN_GROUPS)
    else:
        # 按职能找人：前两组讲「这个职称的中英文写法 + 本地同类岗位」。
        # 后四组刻意不再提原行业——「同一职能换个机构语境」正是漏召的主要来源。
        subject = _role_subject(query, criteria)
        specs = (*_ROLE_GROUPS, *_LATIN_GROUPS)

    return [spec.render(subject.slots) for spec in specs]
