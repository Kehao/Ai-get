"""静态目录数据：推荐策略、智能体模板、渠道清单、知识库问答模板与商机语料。"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import COMPANY_COUNT_OPTIONS
from ..models import AgentTemplate, Channel, CountOption, SearchMode, Strategy

STRATEGIES: tuple[Strategy, ...] = (
    Strategy(id="strategy-beijing-ai-b", text="在北京/上海/深圳的 AI B2B 公司，B 轮融资，员工 50-200 人"),
    Strategy(id="strategy-saas-funding", text="近 6 个月完成融资的 SaaS 公司，提供订阅制服务"),
    Strategy(id="strategy-hiring-north-america", text="正在招聘北美地区销售负责人的中国软件公司"),
    Strategy(id="strategy-english-site", text="近一年发布英文版官网的 B2B 科技公司"),
    Strategy(id="strategy-outbound-blog", text="持续更新博客且话题与「Outbound Sales」相关的公司"),
    Strategy(id="strategy-webinar", text="定期举办网络研讨会 (Webinar) 的 B2B SaaS 品牌"),
)

# 找人模式问的是「什么职位 + 在什么样的公司」，与找公司那组要圈的实体不同，提示词也完全不同
# （参考站两种模式各有一组，这里按同样口径给出中文版）。
PEOPLE_STRATEGIES: tuple[Strategy, ...] = (
    Strategy(id="strategy-people-vp-sales", text="正在全球扩张的 SaaS 公司的销售副总裁或 CRO"),
    Strategy(id="strategy-people-bizdev", text="AI 工具厂商的商务拓展负责人"),
    Strategy(id="strategy-people-cmo", text="云安全初创公司的 CMO 或市场总监"),
    Strategy(id="strategy-people-growth", text="正在招聘付费获客岗位的 AI 初创公司的增长负责人"),
)

STRATEGIES_BY_MODE: dict[SearchMode, tuple[Strategy, ...]] = {
    "company": STRATEGIES,
    "people": PEOPLE_STRATEGIES,
}

COUNT_OPTIONS: tuple[CountOption, ...] = tuple(CountOption(value=value) for value in COMPANY_COUNT_OPTIONS)

RESEARCH_QUESTIONS: tuple[str, ...] = (
    "帮我对 Cargill 进行贸易背调",
    "分析 Trafigura 的贸易网络、主要品类与合规风险",
    "查询 Li & Fung 的供应商网络、采购区域与贸易线索",
)

AGENT_TEMPLATES: tuple[AgentTemplate, ...] = (
    AgentTemplate(
        id="template-default",
        emoji="🧠",
        name="Ai-get 默认销售智能体",
        badge="默认",
        status_label="已发布",
        description="覆盖所有渠道的标准 B2B 销售智能体，支持首轮破冰触达与自动回复。",
        mode_label="智能体模式 · 破冰触达",
        channels=["LinkedIn", "WhatsApp", "邮件"],
        source_label="系统模板 · 三渠道通用",
    ),
    AgentTemplate(
        id="template-linkedin",
        emoji="💼",
        name="LinkedIn 智能体",
        badge="默认",
        status_label="已发布",
        description="面向 LinkedIn 站内触达的专用智能体，偏职业化表达，适合首轮连接与一对一商务沟通。",
        mode_label="智能体模式 · 破冰触达",
        channels=["LinkedIn"],
        source_label="系统模板 · LinkedIn",
    ),
    AgentTemplate(
        id="template-whatsapp",
        emoji="💬",
        name="WhatsApp 智能体",
        badge="默认",
        status_label="已发布",
        description="面向即时通讯场景的专用智能体，适合自然口语化开场、快速响应与多轮短消息推进。",
        mode_label="智能体模式 · 破冰触达",
        channels=["WhatsApp"],
        source_label="系统模板 · WhatsApp",
    ),
    AgentTemplate(
        id="template-email",
        emoji="✉️",
        name="邮件智能体",
        badge="默认",
        status_label="已发布",
        description="面向邮件渠道的专用智能体，擅长度量清晰的冷启动序列与基于回复的自动跟进。",
        mode_label="智能体模式 · 破冰触达",
        channels=["邮件"],
        source_label="系统模板 · 邮件",
    ),
)

EMAIL_CHANNEL = Channel(
    id="email-smtp",
    name="Email（SMTP/IMAP）",
    group="邮箱渠道",
    description="通过你的邮件服务器收发邮件",
    icon="mail",
    state="available",
    account_label=None,
)

SOCIAL_CHANNELS: tuple[Channel, ...] = (
    Channel(
        id="linkedin",
        name="LinkedIn",
        group="社媒渠道",
        description="访问职业资料、公司数据与消息能力",
        icon="linkedin",
        state="available",
        account_label=None,
    ),
    Channel(
        id="whatsapp",
        name="WhatsApp",
        group="社媒渠道",
        description="发送消息并管理联系人",
        icon="message-circle",
        state="available",
        account_label=None,
    ),
)

COMING_SOON_CHANNELS: tuple[Channel, ...] = (
    Channel(
        id="instagram",
        name="Instagram",
        group="即将支持",
        description="访问帖子、Stories 与互动数据",
        icon="instagram",
        state="coming_soon",
        account_label=None,
    ),
    Channel(
        id="telegram",
        name="Telegram",
        group="即将支持",
        description="管理频道、群组与机器人",
        icon="send",
        state="coming_soon",
        account_label=None,
    ),
)


@dataclass(frozen=True, slots=True)
class QaTemplate:
    question: str
    answer: str


KNOWLEDGE_QA_TEMPLATES: tuple[QaTemplate, ...] = (
    QaTemplate(
        question="你们主要解决什么问题？",
        answer="我们帮助 B2B 团队用 AI 销售智能体发现匹配的客户、完成企业调研，并执行多渠道触达，"
        "把从目标市场到会议预约的中间环节自动化。",
    ),
    QaTemplate(
        question="和传统线索数据库有什么不同？",
        answer="传统数据库依赖静态索引，记录每年衰减明显。我们基于实时公开信息检索与富化，"
        "并用自然语言描述客户画像，而不是让人在固定筛选器里做选择题。",
    ),
    QaTemplate(
        question="支持哪些触达渠道？",
        answer="支持邮件、LinkedIn 与 WhatsApp 三条渠道，并且共用一条对话主线，"
        "让每一次沟通都建立在上一次互动的基础上。",
    ),
    QaTemplate(
        question="需要多长时间才能看到效果？",
        answer="完成账号关联与智能体训练后，通常当天即可产出第一批潜客列表；"
        "触达效果取决于目标客群与开场内容，我们会根据回复数据持续调整序列。",
    ),
    QaTemplate(
        question="数据安全如何处理？",
        answer="客户列表与调研结果仅用于当前工作空间，导出的联系人数据由客户自行管理，"
        "我们不会把客户数据用于训练公共模型。",
    ),
    QaTemplate(
        question="可以先小范围试用吗？",
        answer="可以。建议先在单一细分行业或单一城市范围内跑一轮挖掘与触达，"
        "确认线索质量和回复率后再扩大范围。",
    ),
    QaTemplate(
        question="如何评估线索质量？",
        answer="每条企业记录都会给出匹配结论（明确符合 / 可能符合 / 待确认）与 AI 摘要，"
        "并可对任意字段发起重新富化，保证销售在跟进前拿到可判断的依据。",
    ),
    QaTemplate(
        question="是否支持把线索同步到 CRM？",
        answer="支持导出 CSV，也可以通过集成把富化后的线索推送到 HubSpot、Salesforce 等系统，"
        "让销售团队在原有工作流里继续跟进。",
    ),
)


@dataclass(frozen=True, slots=True)
class OpportunitySeed:
    company_name: str
    contact_name: str
    channel: str
    signal: str
    level: str
    summary: str


OPPORTUNITY_SEEDS: tuple[OpportunitySeed, ...] = (
    OpportunitySeed(
        "杭州云栖智能科技有限公司",
        "王志远",
        "邮件",
        "对方回复询问报价区间",
        "建议跟进",
        "首轮邮件发出 4 小时后收到回复，对方主动询问按坐席计费的价格区间，属于明确采购意向信号。",
    ),
    OpportunitySeed(
        "上海澜途数据科技有限公司",
        "李雅静",
        "LinkedIn",
        "接受了连接请求并查看了资料",
        "建议跟进",
        "对方接受连接请求后浏览了产品页两次，建议在 24 小时内发送带行业案例的跟进消息。",
    ),
    OpportunitySeed(
        "深圳前海智仓供应链有限公司",
        "张海涛",
        "邮件",
        "邮件被转发给同事",
        "初步信号",
        "邮件被转发给另一位同事，说明信息已进入内部流转，可在 3 天后补充一份方案摘要。",
    ),
    OpportunitySeed(
        "苏州恒芯半导体材料有限公司",
        "刘文博",
        "WhatsApp",
        "对方已读未回",
        "初步信号",
        "消息已读但未回复，建议调整开场角度，从交付周期而非功能切入。",
    ),
    OpportunitySeed(
        "合肥兆芯新能源科技有限公司",
        "陈思琪",
        "LinkedIn",
        "对方点赞了产品动态",
        "初步信号",
        "对方对产品动态进行了点赞互动，可先评论对方近期内容再发起连接请求。",
    ),
    OpportunitySeed(
        "成都蜀味调味品有限公司",
        "杨俊杰",
        "邮件",
        "退信，邮箱不可达",
        "暂无信号",
        "邮箱投递失败，建议改用官网联系方式挖掘获取新的对接人邮箱后重试。",
    ),
    OpportunitySeed(
        "无锡江南智造工业软件有限公司",
        "黄晓峰",
        "LinkedIn",
        "连接请求被忽略",
        "暂无信号",
        "连接请求超过 7 天未响应，建议更换触达角色，从业务负责人转向信息化负责人。",
    ),
    OpportunitySeed(
        "武汉光谷视界科技有限公司",
        "周梦琳",
        "邮件",
        "对方询问是否有同行案例",
        "建议跟进",
        "对方索要与自身行业匹配的落地案例，属于评估阶段的典型问题，建议直接约 30 分钟会议。",
    ),
    OpportunitySeed(
        "厦门鹭岛文创设计有限公司",
        "吴嘉伟",
        "邮件",
        "打开邮件 3 次",
        "初步信号",
        "同一邮件被多次打开但未回复，说明内容相关度尚可，建议补充一份更具体的价值说明。",
    ),
    OpportunitySeed(
        "青岛蓝湾海洋生物科技有限公司",
        "徐雨萌",
        "WhatsApp",
        "对方回复了第一条消息",
        "建议跟进",
        "对方用中文回复了首条消息并询问合作方式，建议立即补充公司介绍与下一步安排。",
    ),
    OpportunitySeed(
        "佛山陶瓷云科技有限公司",
        "孙振宇",
        "邮件",
        "进入报价沟通阶段",
        "建议跟进",
        "已完成需求澄清，对方要求提供年度方案报价，属于高优先级商机。",
    ),
    OpportunitySeed(
        "郑州麦丰农业科技有限公司",
        "马国栋",
        "LinkedIn",
        "未产生互动",
        "暂无信号",
        "触达 5 天无任何互动，建议暂缓该账号，把资源转向同行业其他匹配企业。",
    ),
)
