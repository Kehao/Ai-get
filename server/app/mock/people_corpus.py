"""找人模式用的虚拟职业档案语料。

与 `company_corpus.py` 是两份**互不相同的语料**：一份是机构画像，一份是自然人档案，
字段与检索维度都不一样，所以不共用一个 dataclass。

数据仅用于演示产品流程，**全部为虚构人物**，姓名、雇主、档案地址与履历均不对应任何真实主体，
也不指向任何真实存在的社交主页。演示「按人名找人」这类用法时，查不到匹配是**正常结果**，
召回层会照常返回候选、由判定层标成「待确认」——这正是产品该有的形态，
不要把真人数据填进来让演示好看。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonSeed:
    """一条人物职业档案。

    `name` 是档案上的展示名（海外职业档案多为拼音或英文写法），
    `name_local` 是中文姓名，`aliases` 收录同一人的其他写法。
    姓名匹配只认这三处，**不由上层猜拼音**——正序/倒序/缩写的组合太多了。
    """

    name: str
    company: str
    company_domain: str
    title: str
    name_local: str
    location: str
    summary: str
    source_label: str
    source_handle: str
    aliases: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    contact_email: str = ""


PERSON_SEEDS: tuple[PersonSeed, ...] = (
    PersonSeed(
        "Kehang Chen",
        "云枢出海科技",
        "yunshu-global.com",
        "VP of Sales",
        "陈可航",
        "上海",
        "陈可航是云枢出海科技的销售副总裁，负责中国 SaaS 厂商出海业务的直销与渠道体系搭建。"
        "他此前在两家跨境电商服务商担任销售负责人，主导过从零搭建海外销售团队与合作伙伴网络，"
        "擅长订阅制产品的定价策略、续费管理与大客户谈判。",
        "领英",
        "kehang-chen",
        ("Chen Kehang", "Kehang C.", "陈可航"),
        ("SaaS", "出海", "订阅制", "销售管理", "渠道体系"),
        "kehang.chen@example.com",
    ),
    PersonSeed(
        "Shuhe Lin",
        "澜舟智能",
        "lanzhou-ai.com",
        "Chief Revenue Officer",
        "林书禾",
        "深圳",
        "林书禾现任澜舟智能首席营收官，统管市场、销售与客户成功三条线。"
        "她有十余年企业级软件商业化经验，曾帮助两家 AI 公司在三年内把年度经常性收入做到亿元规模，"
        "熟悉从产品试用到规模化续约的完整漏斗。",
        "领英",
        "shuhe-lin",
        ("Lin Shuhe", "Shuhe L.", "林书禾"),
        ("AI", "企业服务", "营收管理", "客户成功", "商业化"),
        "shuhe.lin@example.com",
    ),
    PersonSeed(
        "Yanbo Su",
        "智绘工坊",
        "zhihui-tools.com",
        "Head of Business Development",
        "苏彦博",
        "北京",
        "苏彦博负责智绘工坊的商务拓展，主营面向设计团队的 AI 协作工具，"
        "他建立了与设计软件生态、内容平台及行业媒体的合作矩阵，"
        "并主导过面向企业客户的批量授权与联合营销项目。",
        "领英",
        "yanbo-su",
        ("Su Yanbo", "Yanbo S.", "苏彦博"),
        ("AI", "设计工具", "商务拓展", "渠道合作", "企业授权"),
        "yanbo.su@example.com",
    ),
    PersonSeed(
        "Naiqing Gu",
        "磐石云安全",
        "panshi-sec.com",
        "CMO",
        "顾乃青",
        "杭州",
        "顾乃青是磐石云安全的市场总监，负责品牌定位、产品市场与行业活动。"
        "她此前在两家安全厂商负责市场体系从零搭建，主导过面向金融与政企客户的行业峰会与白皮书项目，"
        "擅长把技术能力翻译成可被采购决策层理解的价值语言。",
        "领英",
        "naiqing-gu",
        ("Gu Naiqing", "Naiqing G.", "顾乃青"),
        ("云安全", "市场营销", "品牌", "行业活动", "产品市场"),
        "naiqing.gu@example.com",
    ),
    PersonSeed(
        "Yilang Zheng",
        "微光智能",
        "weiguang-ai.com",
        "Growth Lead",
        "郑亦朗",
        "北京",
        "郑亦朗在微光智能负责增长，主攻自助注册产品的获客与激活漏斗。"
        "他以 SEO、内容矩阵与产品内引导为主要手段，把小团队的增长实验做成了每周可复盘的流程，"
        "曾把试用转化率提升逾一倍。",
        "领英",
        "yilang-zheng",
        ("Zheng Yilang", "Yilang Z.", "郑亦朗"),
        ("AI", "增长", "获客", "转化率", "内容营销"),
        "yilang.zheng@example.com",
    ),
    PersonSeed(
        "Wenjun Pei",
        "磐石云安全",
        "panshi-sec.com",
        "销售总监",
        "裴文珺",
        "杭州",
        "裴文珺负责磐石云安全华东区的直销业务，客户以金融与制造业为主。"
        "她带领的团队以行业解决方案切入，近两年在多家城商行完成替换类项目落地。",
        "公司团队页",
        "wenjun-pei",
        ("Pei Wenjun", "Wenjun P.", "裴文珺"),
        ("云安全", "直销", "金融行业", "解决方案"),
    ),
    PersonSeed(
        "Zhiqiao Xia",
        "云枢出海科技",
        "yunshu-global.com",
        "出海业务负责人",
        "夏知乔",
        "上海",
        "夏知乔负责云枢出海科技的海外市场开拓，长期驻东南亚与中东地区，"
        "熟悉当地渠道体系与合规要求，主导过多个本地化交付项目。",
        "会议嘉宾页",
        "zhiqiao-xia",
        ("Xia Zhiqiao", "Zhiqiao X.", "夏知乔"),
        ("出海", "东南亚", "国际化", "本地化", "渠道"),
    ),
    PersonSeed(
        "Ruoxi Duan",
        "澜舟智能",
        "lanzhou-ai.com",
        "产品市场总监",
        "段若曦",
        "深圳",
        "段若曦负责澜舟智能的产品市场工作，包括竞品研究、定价与新品上市节奏。"
        "她有咨询与 SaaS 双边背景，习惯用客户访谈驱动定位决策。",
        "领英",
        "ruoxi-duan",
        ("Duan Ruoxi", "Ruoxi D.", "段若曦"),
        ("AI", "产品市场", "定价", "竞品分析", "新品上市"),
        "ruoxi.duan@example.com",
    ),
    PersonSeed(
        "Heng Xiao",
        "智绘工坊",
        "zhihui-tools.com",
        "Staff Software Engineer",
        "肖珩",
        "北京",
        "肖珩是智绘工坊的资深工程师，负责图形渲染与协作编辑内核。"
        "他在实时协同算法与前端性能优化方面有多年积累，持有多项图形处理相关专利。",
        "专利发明人页",
        "heng-xiao",
        ("Xiao Heng", "Heng X.", "肖珩"),
        ("软件工程", "图形渲染", "协同编辑", "专利", "性能优化"),
    ),
    PersonSeed(
        "Jiaran Mu",
        "微光智能",
        "weiguang-ai.com",
        "Head of Product",
        "穆迦然",
        "北京",
        "穆迦然负责微光智能的产品线规划，主导了从单点工具向工作流产品的转型。"
        "她偏好小而快的验证循环，坚持每个版本只解决一个明确的客户问题。",
        "领英",
        "jiaran-mu",
        ("Mu Jiaran", "Jiaran M.", "穆迦然"),
        ("AI", "产品管理", "工作流", "用户研究"),
        "jiaran.mu@example.com",
    ),
    PersonSeed(
        "Yuecheng Hua",
        "磐石云安全",
        "panshi-sec.com",
        "Head of Security Research",
        "花岳成",
        "杭州",
        "花岳成带领磐石云安全的研究团队，负责漏洞挖掘与威胁情报。"
        "他常在行业安全会议做技术分享，并在多所高校担任校外导师。",
        "会议嘉宾页",
        "yuecheng-hua",
        ("Hua Yuecheng", "Yuecheng H.", "花岳成"),
        ("云安全", "漏洞挖掘", "威胁情报", "技术演讲"),
    ),
    PersonSeed(
        "Zhenning Lou",
        "恒达工业软件",
        "hengda-mes.com",
        "销售负责人",
        "娄振宁",
        "无锡",
        "娄振宁负责恒达工业软件的销售体系，客户集中在汽车零部件与电子装配行业。"
        "他从实施顾问转做销售，擅长把产线痛点翻译成可量化的交付方案。",
        "公司团队页",
        "zhenning-lou",
        ("Lou Zhenning", "Zhenning L.", "娄振宁"),
        ("工业软件", "智能制造", "销售管理", "项目实施"),
    ),
    PersonSeed(
        "Yiran Feng",
        "光谷视界",
        "ov-vision.com",
        "市场总监",
        "冯一然",
        "武汉",
        "冯一然负责光谷视界的市场工作，聚焦工业质检场景的行业教育与客户案例传播。"
        "她主导过面向新能源电池厂商的技术开放日活动。",
        "领英",
        "yiran-feng",
        ("Feng Yiran", "Yiran F.", "冯一然"),
        ("机器视觉", "工业质检", "市场营销", "行业活动"),
        "yiran.feng@example.com",
    ),
    PersonSeed(
        "Kaixuan Nie",
        "澜舟智能",
        "lanzhou-ai.com",
        "Chief Technology Officer",
        "聂恺轩",
        "深圳",
        "聂恺轩是澜舟智能的联合创始人兼首席技术官，负责模型推理平台与工程效率。"
        "他此前在大型互联网公司负责基础设施，长期关注推理成本与稳定性。",
        "公司团队页",
        "kaixuan-nie",
        ("Nie Kaixuan", "Kaixuan N.", "聂恺轩"),
        ("AI", "技术管理", "推理平台", "基础设施", "成本优化"),
    ),
    PersonSeed(
        "Shuran Bai",
        "清源环保",
        "qingyuan-env.com",
        "副总经理",
        "柏舒然",
        "苏州",
        "柏舒然负责清源环保的工程与运维业务，管理工业园区废水处理项目的交付。"
        "她在水处理工艺与项目成本控制上有十余年经验。",
        "公司团队页",
        "shuran-bai",
        ("Bai Shuran", "Shuran B.", "柏舒然"),
        ("环保", "水处理", "工程项目", "运维"),
    ),
    PersonSeed(
        "Zimo Yan",
        "浙江大学环境与资源学院",
        "zju-env.edu.cn",
        "副教授",
        "严子墨",
        "杭州",
        "严子墨是环境工程方向的副教授，研究工业废水深度处理与资源化利用。"
        "他主持过多项省部级课题，并常为地方环保部门提供技术评审支持。",
        "学术主页",
        "zimo-yan",
        ("Yan Zimo", "Zimo Y.", "严子墨"),
        ("环保", "学术研究", "水处理", "技术评审"),
    ),
    PersonSeed(
        "Yueqing Sang",
        "启明艺术培训",
        "qiming-art.com",
        "校长",
        "桑悦清",
        "郑州",
        "桑悦清是启明艺术培训的创办人，负责校区运营与课程体系。"
        "她把到店试听与家长口碑作为主要招生渠道，近年尝试用社群活动提升续费率。",
        "公司团队页",
        "yueqing-sang",
        ("Sang Yueqing", "Yueqing S.", "桑悦清"),
        ("教育培训", "校区运营", "招生", "社群运营"),
    ),
    PersonSeed(
        "Chengyu Rong",
        "邻里优选",
        "linli-mart.com",
        "运营总监",
        "荣承宇",
        "杭州",
        "荣承宇负责邻里优选的门店运营与社群团购业务，管理二十余家社区门店。"
        "他以到店客流与复购频次为核心指标，推动门店会员体系线上化。",
        "公司团队页",
        "chengyu-rong",
        ("Rong Chengyu", "Chengyu R.", "荣承宇"),
        ("零售", "门店运营", "社群团购", "会员体系"),
    ),
)

# 人物档案的来源 → 面向用户的一句话说明（用在证据条目里）。
# 档案地址由「来源 + 句柄」在数据源层拼装（见 `providers/mock_source._source_url`）——
# 语料里只存句柄，避免同一段域名在几十条记录里各写一遍、改一处漏一处。
SOURCE_DESCRIPTIONS: dict[str, str] = {
    "领英": "领英职业档案",
    "公司团队页": "官方团队页",
    "会议嘉宾页": "会议官网",
    "学术主页": "院校官网",
    "专利发明人页": "专利检索站",
    "行业论坛": "行业社区",
}
