"""L0 资格标准引擎：把一段自然语言画像解析成一组**带权重的判断标准**。

「标准」才是挖掘产品真正的核心产物——它同时决定了**召回什么**、**判定什么**，
以及结果为什么可解释。Ai-get 把这一步放在服务端自动完成，并在 SKILL.md 里
明确要求用户不要写过度指定的清单，原因就在这里。

## 两条实现路径：LLM 优先，规则兜底

`build_criteria()` 会**先尝试 LLM**（`app.llm`），失败则回退到这里的规则引擎。
两条路径产出**同一个 `Criterion` 结构**，所以判定器、状态机、接口层完全无感。

- **LLM 路径**负责语义归一化：把「消费品与旅游行业小微商家」这类说法映射到有限的维度上，
  并展开同义检索词。这是规则表永远覆盖不全的部分。
- **规则路径**保障可用性：LLM 未开启、超时、密钥失效、输出不合 schema 时，
  功能只会「标准糙一些」，不会「不可用」。也正因为它是默认路径，
  别人 clone 下来跑不会产生任何外部请求与费用。

**LLM 的输出必须过白名单校验**（`_criterion_from_llm`）才会被采纳：类别必须 ∈ 枚举、
权重必须 ∈ 1..5、`size` 的 `expected` 必须能解析成 `最小:最大` 两个整数……
理由是判定器（`judge.py`）**直接解析这些字段**，一个格式错的值会让判定静默失效。
校验不通过就整体降级到规则引擎，绝不把半可信的标准放进去。

## 为什么权重是固定的而不是让模型自由发挥

`CATEGORY_WEIGHTS` 是一张**按维度固定**的表。让模型自由给权重看似更"聪明"，
但会让「同一份画像两次生成的标准权重不同」，标准就不再可复核。
维度的相对重要性是产品决策，不是每次调用的即兴判断。

## 标准分类与权重

| 分类 | 权重 | 判定依据 | 未命中时的态度 |
| --- | --- | --- | --- |
| `geo` 地域 | 5 | 企业所在地区 | 硬性，不符合即扣分 |
| `industry` 行业 | 5 | 主营业务 | 硬性，不符合即扣分 |
| `size` 规模 | 3 | 员工人数区间 | 硬性 |
| `funding` 融资阶段 | 3 | 融资轮次 | 硬性 |
| `business` 业务特征 | 3 | 公开资料表述 | **lenient**：无法证伪，命中不了只记不确定 |
| `signal` 意向信号 | 2 | 公开资料线索 | **lenient**：同上 |
| `reachability` 可触达性 | 1 | 是否有可用联系方式 | 硬性 |

`lenient` 这一栏是有意为之：**无法从公开信息证伪的条件，不应该被算成失败**。
把「没查到」当成「不符合」，会让所有冷门行业的结果集体掉档。
"""

from __future__ import annotations

import logging
import re
import zlib
from dataclasses import dataclass
from typing import Literal, Sequence, get_args

from ..mock.synth import CITIES
from ..models import CriteriaSource

logger = logging.getLogger(__name__)

CriterionCategory = Literal[
    "geo",
    "industry",
    "size",
    "funding",
    "business",
    "signal",
    "reachability",
]

# **会社模式**各维度的权重。人物模式有自己的一份（`person_criteria.PERSON_CATEGORY_WEIGHTS`），
# 两套维度不重叠，因此不是同一张表的两个分支，而是两张表。
# 名字保持 `CATEGORY_WEIGHTS` 是因为它已经被 L0 提示词渲染器与契约校验器引用，
# 改名会牵动仓库资产里的断言表，收益只有「看起来更整齐」。
CATEGORY_WEIGHTS: dict[CriterionCategory, int] = {
    "geo": 5,
    "industry": 5,
    "size": 3,
    "funding": 3,
    "business": 3,
    "signal": 2,
    "reachability": 1,
}

# 达到「明确符合」的总分阈值；以及「判定为硬性条件」的权重分界线。
# 分界值取 3 而不是 4：地域、行业、规模、融资这四类都是画像里**明确写出来的要求**，
# 任何一条不满足都不该拿到「明确符合」——权重 4 会让「要 A 轮的未融资企业」蒙混过关。
FULL_SCORE_THRESHOLD = 0.75
PARTIAL_SCORE_THRESHOLD = 0.45
HARD_WEIGHT_THRESHOLD = 3

# 区域关键词 → 该区域包含的城市。用于「长三角/华南」这类没有点名的画像。
REGION_CITIES: dict[str, tuple[str, ...]] = {
    "长三角": ("上海", "苏州", "南京", "杭州", "宁波", "无锡", "合肥"),
    "珠三角": ("广州", "深圳", "佛山", "东莞"),
    "京津冀": ("北京", "天津"),
    "成渝": ("成都", "重庆"),
    "华中": ("武汉", "长沙", "郑州"),
    "华南": ("广州", "深圳", "佛山", "东莞", "厦门", "福州"),
    "华东": ("上海", "杭州", "苏州", "南京", "青岛", "宁波", "无锡", "合肥", "济南"),
    "华北": ("北京", "天津", "青岛"),
    "西南": ("成都", "重庆", "昆明", "贵阳"),
    "西北": ("西安",),
}

# 行业族：一族包含若干同义或上下游关键词。查询词与语料行业都用同一份词表做子串匹配，
# 因为两边都是中文短语，一个词表就够；不需要维护「查询词 → 语义 ID」的映射表。
#
# 词表刻意**不含**「渠道」「门店」「私域」「内容」这类通用词：它们既可能是目标行业，
# 也可能是画像对企业的能力要求（「要求具备线上渠道」），放进来会把能力要求误判成行业，
# 凭空多出一条硬性标准，把整批结果的得分压下去。
INDUSTRY_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("消费品与零售", ("消费品", "快消", "零售", "日用品", "生鲜", "食品", "餐饮", "调味", "坚果", "服装", "时尚", "电商", "电子商务")),
    ("文旅与本地服务", ("文旅", "旅游", "康养", "酒店", "景区", "文创", "文化创意", "品牌设计", "传媒", "内容营销", "美容", "美业", "本地生活", "本地服务")),
    ("企业服务与软件", ("企业服务", "SaaS", "saas", "软件", "云计算", "云安全", "信息安全", "产业互联网", "信息化", "政企", "外包", "数据服务", "商业智能", "人工智能", "AI", "机器视觉", "网络安全")),
    ("智能制造与工业", ("智能制造", "工业设备", "装备制造", "自动化", "工业软件", "MES", "工业质检", "精密制造", "模具", "工业品", "机械", "暖通", "半导体", "材料", "3C", "汽车零部件", "智能装备")),
    ("贸易与供应链", ("贸易", "跨境", "进出口", "供应链", "物流", "仓储", "货运", "分销", "外贸")),
    ("医疗与健康", ("医疗", "器械", "生物科技", "保健品", "健康", "康复", "医药", "皮肤管理")),
    ("新能源与环保", ("新能源", "储能", "电池", "光伏", "环保", "节能", "双碳")),
    ("教育与培训", ("教育", "培训", "职业", "人才发展", "企业内训", "在线教育")),
    ("农业与食品供应链", ("农业", "农资", "种植", "养殖", "订单农业", "海洋食品")),
    ("建筑与工程", ("建筑", "建材", "工程", "机电", "装修", "陶瓷", "检测", "实验室", "地理信息", "测绘")),
)

# 规模关键词 → 员工人数目标区间。用「区间是否有交集」判定，避免依赖语料里
# 「1-10 人」与「40-120 人」这类不统一的写法。
SIZE_BANDS: tuple[tuple[tuple[str, ...], tuple[int, int], str], ...] = (
    # 「中小」排在「小微」之前：写成「中小微企业」时应当按更宽松的中小口径处理，
    # 而「小微企业」不含「中小」，仍会落到更严格的小微口径上。
    (("中小", "中型"), (0, 200), "中小企业（200 人以下）"),
    (("小微", "微型", "初创", "小店", "个体"), (0, 50), "小微（50 人以下）"),
    (("大型", "规模化", "集团"), (200, 10**6), "中大型（200 人以上）"),
    (("300 人以上", "300人以上", "500 人以上", "500人以上"), (300, 10**6), "300 人以上"),
    (("100 人以上", "100人以上"), (100, 10**6), "100 人以上"),
    (("50 人以上", "50人以上"), (50, 10**6), "50 人以上"),
)

FUNDING_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("未融资", "无融资", "不融资"), "未融资"),
    (("天使",), "天使轮"),
    (("a 轮", "a轮", "A 轮", "A轮"), "A轮"),
    (("b 轮", "b轮", "B 轮", "B轮"), "B轮"),
    (("c 轮", "c轮", "C 轮", "C轮", "上市", "ipo"), "C轮"),
)

SIGNAL_KEYWORDS: tuple[str, ...] = (
    "数字化",
    "信息化",
    "招投标",
    "中标",
    "扩张",
    "出海",
    "跨境",
    "招聘",
    "线上",
    "私域",
    "微信小程序",
    "小程序",
    "自动化",
    "降本",
    "增效",
    "新建",
    "投产",
    "改造",
)
# 注意：SIGNAL_KEYWORDS 里刻意不含「融资」。语料摘要中每家都会写「当前融资阶段为 X」，
# 把它当意向信号等于给所有企业白送一条命中标准，信号标准就失去了区分度。

_SEGMENT_SEPARATORS = ("，", ",", "；", ";", "。", "、", "\n", "。", "！", "?", "？")
_MIN_SEGMENT_LENGTH = 4
_NAME_LIMIT = 22

# 从画像片段里剔除的意图词与虚词：它们描述「我要找什么」，不描述企业的特征。
_INTENT_WORDS: tuple[str, ...] = (
    "寻找",
    "找一找",
    "找",
    "我要",
    "我想",
    "需要",
    "希望",
    "要求",
    "具备",
    "拥有",
    "以及",
    "并且",
    "同时",
    "公司",
    "企业",
    "商家",
    "客户",
    "画像",
    "目标",
    "潜客",
    "行业",
    "融资",
    "这些",
    "以下",
    "左右",
    "以内",
    "以上",
    # 偏好类虚词：只表达「更希望」而不是企业的客观特征。留在残句里会让
    # 「最好有微信小程序」在信号标准之外再生成一条业务特征标准，同一句话被计两次。
    "最好",
    "尽量",
    "优先",
    "偏向",
    "倾向",
)
_FILLER_CHARS = " 的了与和及或和之其有无"

_EMPLOYEE_RANGE = re.compile(r"(\d+)\s*(?:[-\u2013~至]\s*(\d+))?")


@dataclass(frozen=True, slots=True)
class Criterion:
    """一条判断标准。

    字段刻意保持「一段 JSON 就能表达」的形状，使换用 LLM 生成时不需要改任何下游代码。
    企业与人物两套标准**共用这个形状**：权重的相对大小、`lenient` 的语义、
    硬性条件的一票否决都是同一套口径（见 `scoring.py`），
    不同的只是「有哪些维度」以及每个维度怎么判。
    """

    id: str
    name: str
    question: str
    # 取值来自**当前模式的维度词表**：会社模式见本模块的 `CriterionCategory`，
    # 人物模式见 `person_criteria.PersonCriterionCategory`。
    #
    # 这里刻意不写成两者的 `Literal` 联合类型：那样两套词表就得放进同一个模块，
    # 而「人物维度」一旦在会社模块里可见，迟早会有人把它加进 `_LLM_CATEGORIES`，
    # 于是会社模式的 LLM 会开始产出「姓名」标准。词表分开放，越界更早被发现。
    category: str
    weight: int
    tokens: tuple[str, ...] = ()
    expected: str = ""
    rationale: str = ""
    lenient: bool = False

    @property
    def is_hard(self) -> bool:
        """硬性条件：一旦判定为「不符合」，就不允许结论落到「明确符合」。"""
        return self.weight >= HARD_WEIGHT_THRESHOLD and not self.lenient


# ── 对外入口 ──────────────────────────────────────────────────────────────

SOURCE_LABELS: dict[str, str] = {
    "llm": "LLM 生成",
    "rule": "内置规则引擎",
}


@dataclass(frozen=True, slots=True)
class CriteriaBuild:
    """一次标准生成的完整结果，含可追溯的元信息。

    元信息不是装饰：标准会被**冻结**进任务记录，只有知道它由哪条路径、
    哪版 prompt、哪个模型产出，日后才解释得清「为什么这批结论是这样」。
    """

    criteria: tuple[Criterion, ...]
    source: CriteriaSource
    label: str
    prompt_version: str = ""
    model: str = ""
    # 降级原因。`source == "rule"` 时如果这里有值，说明是 LLM 失败导致的降级，
    # 而不是配置里就没开 LLM——这两种情况的运维动作完全不同。
    fallback_reason: str = ""


def build_criteria(
    text: str,
    *,
    user_conditions: Sequence[str] = (),
) -> list[Criterion]:
    """把画像正文与用户手写的判断条件合并成一份标准清单。"""
    return list(build_criteria_detailed(text, user_conditions=user_conditions).criteria)


def build_criteria_detailed(
    text: str,
    *,
    user_conditions: Sequence[str] = (),
) -> CriteriaBuild:
    """LLM 优先、规则兜底的标准生成。**任何情况下都会返回一份可用的标准。**

    顺序稳定：地域 → 行业 → 规模 → 融资 → 业务特征 → 意向信号 → 可触达性 → 用户补充。
    顺序稳定意味着 id 稳定，前端条件行的色条与勾选状态才不会在刷新后跳位。
    """
    llm_build = _criteria_from_llm(text, user_conditions)
    if llm_build is not None:
        return llm_build

    criteria = _criteria_from_text(text)
    for raw in user_conditions:
        criteria = _merge_user_condition(criteria, raw)

    return CriteriaBuild(
        criteria=tuple(_with_reachability(criteria)),
        source="rule",
        label=SOURCE_LABELS["rule"],
        fallback_reason=_last_llm_failure(),
    )


def _last_llm_failure() -> str:
    """取最近一次 LLM 失败的原因，用于区分「没开」与「开了但失败」。"""
    from ..llm import stats as llm_stats

    detail = llm_stats()
    return f"{detail.last_error_kind}: {detail.last_error_message}" if detail.last_error_kind else ""


# ── LLM 路径：调用 + 白名单校验 ────────────────────────────────────────────

# LLM 允许产出的维度。刻意不含 reachability——它与画像内容无关，
# 由 `_with_reachability` 统一补，避免模型自作主张地漏掉或改写。
_LLM_CATEGORIES: frozenset[str] = frozenset(get_args(CriterionCategory)) - {"reachability"}

# 各维度允许的最大条数。business / signal 允许并列多条（画像里可能有多个并列特征）。
_MAX_PER_CATEGORY: dict[str, int] = {"business": 3, "signal": 3}
_DEFAULT_MAX_PER_CATEGORY = 1

# LLM 输出里各字段的长度上限。超过即判为不合格——
# 这些上限同时也是「不要把整句话塞进 tokens」的兜底（prompt 里已要求，但模型会漂）。
_MAX_NAME_CHARS = 40
_MAX_QUESTION_CHARS = 80
_MAX_TOKEN_CHARS = 30
_MAX_TOKENS = 20
_MAX_RATIONALE_CHARS = 120

# LLM 至少要产出这么多条有效标准，否则整批弃用。
# 定在 2 而不是 1：只剩一条标准时「加权得分」失去意义，还不如走规则引擎。
_MIN_ACCEPTED = 2

_SIZE_EXPECTED = re.compile(r"^(\d+):(\d+)$")

_KNOWN_FUNDING_STAGES: frozenset[str] = frozenset(stage for _keys, stage in FUNDING_KEYWORDS)


def _criteria_from_llm(
    text: str,
    user_conditions: Sequence[str],
) -> CriteriaBuild | None:
    """尝试用 LLM 生成标准。未开启、失败或校验不通过时返回 None（交由规则引擎接手）。"""
    # 局部导入：`app.llm.prompts` 在模块层反向依赖本模块的词汇表，
    # 在函数内导入才能保证本模块已经完整加载，从而不产生循环导入。
    from ..llm import LlmError, generate_criteria, get_settings, prompt_version

    settings = get_settings()
    if not settings.usable:
        return None

    conditions = tuple(item.strip() for item in user_conditions if item.strip())

    try:
        result = generate_criteria(text, conditions)
    except LlmError as error:
        # 不抛给调用方：LLM 是「会失败的外部依赖」，失败只应降低标准质量。
        logger.warning("L0 标准生成降级到规则引擎：%s", error)
        return None
    except Exception:  # noqa: BLE001 — 兜底：绝不让 LLM 的任何异常冒泡成 5xx
        logger.exception("L0 标准生成出现未预期异常，降级到规则引擎")
        return None

    accepted, rejected = _validate_llm_items(result.criteria)
    if len(accepted) < _MIN_ACCEPTED:
        logger.warning(
            "L0 LLM 输出通过校验的条目不足（通过 %d / 拒绝 %d），整批弃用并降级",
            len(accepted),
            rejected,
        )
        return None

    # 用户手写的条件绝不能被模型漏掉：模型没覆盖到的由规则逻辑补齐。
    # 这是「宁可重复一条，也不静默丢掉用户明确写下的要求」的取舍。
    for raw in conditions:
        accepted = _merge_user_condition(accepted, raw)

    return CriteriaBuild(
        criteria=tuple(_with_reachability(accepted)),
        source="llm",
        label=f"LLM · {result.prompt_version} · {result.model}",
        prompt_version=result.prompt_version or prompt_version(),
        model=result.model,
    )


def _validate_llm_items(items: Sequence[dict]) -> tuple[list[Criterion], int]:
    """把 LLM 输出的 dict 逐个校验成 `Criterion`，返回 (通过项, 被拒条数)。

    逐条校验而不是整批要么全过要么全废：一条越界的标准不该毁掉其余合理的标准。
    但**通过数量不足**时（见 `_MIN_ACCEPTED`）仍然整批弃用——半份标准比没有更危险。
    """
    accepted: list[Criterion] = []
    per_category: dict[str, int] = {}
    rejected = 0

    for item in items:
        criterion = _criterion_from_llm(item)
        if criterion is None:
            rejected += 1
            continue

        cap = _MAX_PER_CATEGORY.get(criterion.category, _DEFAULT_MAX_PER_CATEGORY)
        if per_category.get(criterion.category, 0) >= cap:
            rejected += 1
            continue

        per_category[criterion.category] = per_category.get(criterion.category, 0) + 1
        accepted.append(criterion)

    return accepted, rejected


def _criterion_from_llm(item: dict) -> Criterion | None:
    """单条标准的白名单校验与构造。任一硬性契约不满足即返回 None。"""
    category = item.get("category")
    if not isinstance(category, str) or category not in _LLM_CATEGORIES:
        return None

    name = _clean_text(item.get("name"), _MAX_NAME_CHARS)
    if not name:
        return None

    weight = item.get("weight")
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        return None
    weight = int(weight)
    if not 1 <= weight <= 5:
        return None

    tokens = _clean_tokens(item.get("tokens"))
    expected = _clean_text(item.get("expected"), _MAX_NAME_CHARS)

    # 每类维度的硬性契约。判定器直接解析 expected / tokens，这里必须挡住格式错误的值。
    if category == "size":
        match = _SIZE_EXPECTED.match(expected)
        if match is None:
            return None
        low, high = int(match.group(1)), int(match.group(2))
        if low > high:
            return None
        tokens = ()
    elif category == "funding":
        if expected not in _KNOWN_FUNDING_STAGES:
            return None
        tokens = tokens or (expected,)
    elif not tokens:
        # geo / industry / business / signal 全靠 tokens 做子串匹配，缺了就无法判定。
        return None

    # business 与 signal 强制 lenient：这是打分模型的安全不变量，不是模型的自由选项。
    # 公开资料没写到某项特征，不等于这项特征不成立。
    lenient = True if category in ("business", "signal") else False

    question = _clean_text(item.get("question"), _MAX_QUESTION_CHARS) or f"公开资料是否体现了「{name}」？"

    return Criterion(
        # 用 CRC32 而不是内置 hash：内置 hash 对字符串按进程随机加盐，
        # 会让同一条标准在服务重启后换 id，前端条件行的色条随之跳位。
        id=f"criterion-{category}-{zlib.crc32(f'{name}|{expected}'.encode()) % 10**6}",
        name=name,
        question=question,
        category=category,  # type: ignore[arg-type] — 已由 _LLM_CATEGORIES 校验
        weight=weight,
        tokens=tokens,
        expected=expected,
        rationale=_clean_text(item.get("note"), _MAX_RATIONALE_CHARS) or "由 LLM 依据画像推导。",
        lenient=lenient,
    )


def _clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _clean_tokens(value: object) -> tuple[str, ...]:
    """规整 tokens：只保留非空短字符串，去重并限长。

    限长是必须的——模型偶尔会把整句话塞进 tokens，那种值做子串匹配永远命中不了，
    还会让前端条件行显示出一大段文字。
    """
    if not isinstance(value, list):
        return ()
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if not token or len(token) > _MAX_TOKEN_CHARS:
            continue
        if token not in cleaned:
            cleaned.append(token)
        if len(cleaned) >= _MAX_TOKENS:
            break
    return tuple(cleaned)


def detect_city(text: str) -> str | None:
    """识别画像里的城市。先看点名城市，再看区域名（长三角、华南这类）。"""
    for city in CITIES:
        if city in text:
            return city
    return None


def detect_region(text: str) -> str | None:
    return next((region for region in REGION_CITIES if region in text), None)


def industry_hints(text: str) -> tuple[str, ...]:
    """把画像里提到的行业展开成一组**匹配词**，交给数据源优化召回。

    返回的是展开后的词而不是族名，因为数据源的语料词表与这里的族名并不一致
    （语料写「食品」「电子商务」，合成模板写「消费品牌」「电商零售」），
    只有词才能两边都匹配上。

    真实数据源可以完全忽略这个提示；内置演示源用它来保证结果不跑偏——
    否则「找消费品企业」会返回一堆无关行业，让判定层集体落空，
    那是**召回层的问题**，不该由判定层背。

    ⚠️ **召回不要用这个函数**：标准一旦冻结，提示就必须从标准派生
    （见 `company_hints`），重新解析画像会把用户改过的条件冲掉。
    这里的入参是**画像原文**，因此只适用于还没有标准的场合。
    """
    tokens: list[str] = []
    for _family, family_tokens in INDUSTRY_FAMILIES:
        if any(token in text for token in family_tokens):
            tokens.extend(family_tokens)
    return tuple(dict.fromkeys(tokens))


@dataclass(frozen=True, slots=True)
class CompanyHints:
    """会社模式的召回提示。**从已冻结的标准派生**，不是再读一遍画像。

    与 `PersonHints` 存在同样的理由，但两者维度不重叠，所以是两份而不是一份：
    会社要的是「地域 + 行业」，人物要的是「姓名 + 职位 + 公司特征」。
    """

    city: str | None = None
    industry_hints: tuple[str, ...] = ()


def company_hints(criteria: Sequence[Criterion]) -> CompanyHints:
    """把会社标准里的可比对取值摊平成召回提示。

    与 `industry_hints(画像)` 的分工要说清楚：那个函数是「画像 → 匹配词」，
    只适用于**还没有标准**的场合（如策略文案预览）。召回必须走这条路径，
    否则用户手动补充的地域/行业条件传不到数据源——标准里有「地域：上海」、
    召回却按画像里的（可能根本没有）城市去捞，判定层再按上海筛，
    结果就是整批系统性落空。

    **刻意不做同族扩展**（人物侧做了，见 `_expand_industry_tokens`）：
    规则引擎产出的行业标准，tokens 本来就是整个族；LLM 产出的 tokens 是它
    收敛过的词，再扩回族等于把模型的理解丢掉。这些 tokens 随查询下发后只算
    **提示**（数据源可自行选用，判定层也要用），不再拼进检索查询本身。
    """
    city: str | None = None
    industry: list[str] = []

    for criterion in criteria:
        if criterion.category == "geo" and city is None:
            city = criterion.expected or (criterion.tokens[0] if criterion.tokens else None)
        elif criterion.category == "industry":
            industry.extend(criterion.tokens)

    return CompanyHints(city=city, industry_hints=tuple(dict.fromkeys(industry)))


# ── 内部：从正文派生标准 ──────────────────────────────────────────────────


def _criteria_from_text(text: str) -> list[Criterion]:
    stripped = text.strip()
    if not stripped:
        return []

    criteria: list[Criterion] = []
    consumed: list[str] = []

    city = detect_city(stripped)
    if city:
        criteria.append(_geo_criterion(city, source="画像中点名的城市"))
        consumed.append(city)
    else:
        region = detect_region(stripped)
        if region:
            cities = REGION_CITIES[region]
            criteria.append(
                Criterion(
                    id="criterion-geo",
                    name=f"地域：{region}",
                    question=f"企业是否位于{region}（{'、'.join(cities[:5])} 等）？",
                    category="geo",
                    weight=CATEGORY_WEIGHTS["geo"],
                    tokens=cities,
                    expected=region,
                    rationale=f"画像提到区域「{region}」，展开为其覆盖的主要城市。",
                )
            )
            consumed.append(region)

    families = _matched_families(stripped)
    if families:
        # 多个行业族合并成**一条**行业标准，按「命中任一即可」判定。
        # 画像里写「消费品与旅游行业」指的是目标客群覆盖这两个行业，
        # 而不是要求某一家企业同时做这两个行业；拆成两条硬性标准会让符合条件的企业
        # 集体被判成「可能符合」，反而是错的。
        names = [family for family, _tokens in families]
        tokens: list[str] = []
        for _family, family_tokens in families:
            tokens.extend(family_tokens)
        label = names[0] if len(names) == 1 else f"{'／'.join(names)}（任一）"
        criteria.append(
            Criterion(
                id="criterion-industry",
                name=f"行业：{label}",
                question=(
                    f"企业主营业务是否属于{names[0]}？"
                    if len(names) == 1
                    else f"企业主营业务是否属于{_join_names(names)}中的任一方向？上下游与渠道环节也算命中。"
                ),
                category="industry",
                weight=CATEGORY_WEIGHTS["industry"],
                tokens=tuple(dict.fromkeys(tokens)),
                expected="／".join(names),
                rationale="由画像中的行业关键词推导。",
            )
        )
        for _family, family_tokens in families:
            consumed.extend(token for token in family_tokens if token in stripped)

    size = _detect_size(stripped)
    if size:
        label, low, high, size_keyword = size
        criteria.append(
            Criterion(
                id="criterion-size",
                name=f"规模：{label}",
                question=f"企业员工人数是否落在 {low}–{high} 人的区间内？",
                category="size",
                weight=CATEGORY_WEIGHTS["size"],
                expected=f"{low}:{high}",
                rationale="由画像中的规模表述推导。",
            )
        )
        if size_keyword in stripped:
            consumed.append(size_keyword)

    funding = _detect_funding(stripped)
    if funding:
        stage, funding_keyword = funding
        criteria.append(
            Criterion(
                id="criterion-funding",
                name=f"融资阶段：{stage}",
                question=f"企业当前融资阶段是否为「{stage}」？",
                category="funding",
                weight=CATEGORY_WEIGHTS["funding"],
                tokens=(stage,),
                expected=stage,
                rationale="由画像中的融资阶段表述推导。",
            )
        )
        if funding_keyword in stripped:
            consumed.append(funding_keyword)

    signals = _longest_match([token for token in SIGNAL_KEYWORDS if token in stripped])
    if signals:
        criteria.append(
            Criterion(
                id="criterion-signal",
                name=f"意向信号：{'、'.join(signals[:3])}",
                question=f"公开资料中是否出现与「{'、'.join(signals[:3])}」相关的动作或表述？",
                category="signal",
                weight=CATEGORY_WEIGHTS["signal"],
                tokens=tuple(signals),
                rationale="由画像中的意向信号词推导，用于判断是否有可跟进的时机。",
                lenient=True,
            )
        )
        consumed.extend(signals)

    for index, segment in enumerate(_leftover_segments(stripped, consumed)):
        criteria.append(
            Criterion(
                id=f"criterion-business-{index}",
                name=f"业务特征：{_shorten(segment)}",
                question=f"公开资料是否体现了「{segment}」这一业务特征？",
                category="business",
                weight=CATEGORY_WEIGHTS["business"],
                tokens=(segment,),
                rationale="画像中未能归入地域/行业/规模的其他限定语。",
                lenient=True,
            )
        )

    return criteria


def _matched_families(text: str) -> list[tuple[str, tuple[str, ...]]]:
    matched: list[tuple[str, tuple[str, ...]]] = []
    for family, tokens in INDUSTRY_FAMILIES:
        if any(token in text for token in tokens):
            matched.append((family, tokens))
    return matched


def _detect_size(text: str) -> tuple[str, int, int, str] | None:
    for keywords, (low, high), label in SIZE_BANDS:
        matched = next((keyword for keyword in keywords if keyword in text), None)
        if matched:
            return label, low, high, matched
    return None


def _detect_funding(text: str) -> tuple[str, str] | None:
    lowered = text.lower().replace(" ", "")
    for keywords, stage in FUNDING_KEYWORDS:
        for keyword in keywords:
            if keyword.lower().replace(" ", "") in lowered:
                return stage, keyword
    return None


def _longest_match(tokens: Sequence[str]) -> list[str]:
    """去掉被更长关键词包含的短词。

    命中「微信小程序」后不必再单独记一条「小程序」：否则信号标准会自己和自己重复，
    而且短词先被消费掉之后，残句里会留下「微信」这种碎片，又生成一条多余的业务特征标准。
    """
    return [token for token in tokens if not any(token != other and token in other for other in tokens)]


def _join_names(names: Sequence[str]) -> str:
    """把多个行业族名拼成可读的并列短语，超过三个时用「等」收尾。"""
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return "、".join(names)
    return f"{'、'.join(names[:3])} 等"


def _leftover_segments(text: str, consumed: Sequence[str]) -> list[str]:
    """切出未能归类的画像片段，作为「业务特征」标准。

    先剔掉已经被地域/行业/规模消费掉的词，再剔掉「寻找」「要求」这类**意图词**——
    否则「寻找杭州的消费品与旅游行业小微商家」整句都会被当成一条业务特征，
    凭空多出一条永远判不确定的标准。
    """
    normalized = text
    for separator in _SEGMENT_SEPARATORS:
        normalized = normalized.replace(separator, "|")

    segments: list[str] = []
    for raw in normalized.split("|"):
        segment = raw.strip()
        if len(segment) < _MIN_SEGMENT_LENGTH:
            continue
        residue = segment
        # 长词先剔除：先删「小程序」会让「微信小程序」剩下「微信」碎片，
        # 碎片又会被当成一条业务特征标准。
        for token in sorted(consumed, key=len, reverse=True):
            residue = residue.replace(token, "")
        for word in sorted(_INTENT_WORDS, key=len, reverse=True):
            residue = residue.replace(word, "")
        residue = residue.strip(_FILLER_CHARS)
        if len(residue) < _MIN_SEGMENT_LENGTH:
            continue
        segments.append(segment)

    return segments[:2]


# 可触达性这条标准的名称。`_with_reachability` 与「回传的条件名要跳过」两处共用一份字面量：
# 名字对不上时，条件面板回传的「可触达性」会被当成新条件，多出一条重复的宽松标准。
REACHABILITY_LABEL = "可触达性"


def _appears(term: str, text: str) -> bool:
    """词是否出现在正文里。拉丁词大小写不敏感，与人物侧同一口径。"""
    if term.isascii() and term.isalpha():
        return term.lower() in text.lower()
    return term in text


def _is_round_tripped_label(text: str, criteria: list[Criterion]) -> bool:
    """判断这条「用户条件」是不是引擎自己下发、又被前端原样回传的条件名。

    条件面板把当前生效的条件名（「地域：杭州」「行业：企业服务与软件」「可触达性」……）
    一并回传，它们**不是用户新增的条件**；若不识别，每条都会再被包成一条宽松标准，
    权重表凭空翻倍、结论随之漂移。只跳过能对上已有标准的：带未知取值的同类条件
    （如「行业：必须有 ISO 认证」）仍然按用户条件收下，不会被静默丢掉。
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


# 「类别前缀」的形状：不超过 6 个字、不含空白与冒号的短词 + 中文冒号。
# 只按形状剥开头反复出现的前缀段（「业务特征：业务特征：X」→「X」），
# 条件本体不受影响；剥完为空（文本只有前缀）时由调用方放弃这条。
_LABEL_HEAD = re.compile(r"^[^：\s]{1,6}：")


def _strip_name_prefixes(text: str) -> str:
    """剥掉条件文本开头已经包过的类别前缀，保证包装是幂等的。

    「业务特征：业务特征：订阅制」→「订阅制」，随后只会再包一层，
    名字回到「业务特征：订阅制」并从此稳定——无论 LLM 每次用什么前缀词。
    """
    stripped = text.strip()
    while True:
        match = _LABEL_HEAD.match(stripped)
        if match is None:
            return stripped
        stripped = stripped[match.end() :].lstrip()


def _merge_user_condition(criteria: list[Criterion], raw: str) -> list[Criterion]:
    """把用户手写的一条判断条件并入标准清单。

    能归类就归类（地域/行业/规模/融资），归不了就作为一条宽松的业务特征标准——
    **手工补充的条件几乎不可能被公开资料证伪，因此不能参与扣分**。
    """
    text = raw.strip()
    if not text:
        return criteria

    if _is_round_tripped_label(text, criteria):
        return criteria

    # 条件面板回传的文本可能已经包过类别前缀。不剥掉就再包一层，
    # 每次保存都会出现「业务特征：业务特征：…」。按形状剥（LLM 每次起的
    # 前缀词可能不同，词表靠不住），剥完的才是条件本体。
    text = _strip_name_prefixes(text)
    if not text:
        return criteria

    # 剥完前缀后按**内容**去重：「意向信号：正在招聘」和「动态：正在招聘」
    # 是同一条条件，不能各包一层变成两条重复标准。
    if any(_appears(text, item.name) for item in criteria):
        return criteria

    lowered = {item.name for item in criteria}

    city = detect_city(text)
    if city:
        name = f"地域：{city}"
        if name not in lowered:
            return [*criteria, _geo_criterion(city, source="用户手动补充的判断条件")]
        return criteria

    families = _matched_families(text)
    existing_industry = next((item for item in criteria if item.category == "industry"), None)
    if families:
        names = [family for family, _tokens in families]
        if existing_industry is not None:
            # 已经有行业标准时把它并进去，而不是再起一条——行业是一个维度，不该重复计分。
            merged_tokens: list[str] = list(existing_industry.tokens)
            for _family, family_tokens in families:
                merged_tokens.extend(family_tokens)
            merged_names = list(dict.fromkeys([*existing_industry.expected.split("／"), *names]))
            replacement = Criterion(
                id=existing_industry.id,
                name=f"行业：{'／'.join(merged_names)}{'（任一）' if len(merged_names) > 1 else ''}",
                question=f"企业主营业务是否属于{_join_names(merged_names)}中的任一方向？上下游与渠道环节也算命中。",
                category="industry",
                weight=existing_industry.weight,
                tokens=tuple(dict.fromkeys(merged_tokens)),
                expected="／".join(merged_names),
                rationale="由画像与用户手动补充的判断条件共同推导。",
            )
            return [replacement if item is existing_industry else item for item in criteria]

        tokens: list[str] = []
        for _family, family_tokens in families:
            tokens.extend(family_tokens)
        label = names[0] if len(names) == 1 else f"{'／'.join(names)}（任一）"
        return [
            *criteria,
            Criterion(
                id="criterion-industry-user",
                name=f"行业：{label}",
                question=f"企业主营业务是否属于{_join_names(names)}中的任一方向？上下游与渠道环节也算命中。",
                category="industry",
                weight=CATEGORY_WEIGHTS["industry"],
                tokens=tuple(dict.fromkeys(tokens)),
                expected="／".join(names),
                rationale="用户手动补充的判断条件。",
            ),
        ]

    name = f"业务特征：{_shorten(text)}"
    if name in lowered:
        return criteria
    return [
        *criteria,
        Criterion(
            # 用 CRC32 而不是内置 hash：内置 hash 对字符串按进程随机加盐，
            # 会让同一条条件在服务重启后换 id，条件行的色条随之跳位。
            id=f"criterion-user-{zlib.crc32(text.encode()) % 10**6}",
            name=name,
            question=f"公开资料是否体现了「{text}」？",
            category="business",
            weight=CATEGORY_WEIGHTS["business"],
            tokens=(text,),
            rationale="用户手动补充的判断条件，无法证伪时不参与扣分。",
            lenient=True,
        ),
    ]


def _geo_criterion(city: str, *, source: str) -> Criterion:
    return Criterion(
        id="criterion-geo",
        name=f"地域：{city}",
        question=f"企业是否位于{city}？",
        category="geo",
        weight=CATEGORY_WEIGHTS["geo"],
        tokens=(city,),
        expected=city,
        rationale=f"{source}。",
    )


def _with_reachability(criteria: list[Criterion]) -> list[Criterion]:
    """可触达性永远参与评估：找不到联系人，再匹配的企业也进不了触达序列。"""
    if any(item.category == "reachability" for item in criteria):
        return criteria
    return [
        *criteria,
        Criterion(
            id="criterion-reachability",
            name=REACHABILITY_LABEL,
            question="是否能获取到可用的公开联系方式？",
            category="reachability",
            weight=CATEGORY_WEIGHTS["reachability"],
            rationale="任何画像都适用的通用标准：无法触达的企业不应占用触达序列名额。",
        ),
    ]


def _shorten(text: str, limit: int = _NAME_LIMIT) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= limit else f"{stripped[:limit]}…"


def employee_range(raw: str) -> tuple[int, int] | None:
    """把语料里的员工规模表述解析成区间。

    语料同时存在「1-10 人」「40-120 人」「500 人以上」三种写法，
    因此统一按数值区间处理，用「区间是否有交集」判定规模是否匹配。
    """
    match = _EMPLOYEE_RANGE.search(raw or "")
    if match is None:
        return None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else low
    if "以上" in raw or "上" in raw:
        return low, 10**6
    return min(low, high), max(low, high)
