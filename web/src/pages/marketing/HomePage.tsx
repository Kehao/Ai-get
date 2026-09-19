// 落地页：Hero、多渠道序列、核心功能、客户反馈。
// Hero 里的产品截图用纯样式还原控制台界面，避免依赖图片资源。

import { useNavigate } from 'react-router-dom';
import {
  Building2,
  Crosshair,
  Mail,
  MessageCircle,
  Plug,
  Search,
  Sparkles,
  Star,
} from 'lucide-react';

import Button from '@/components/Button';
import Tag from '@/components/Tag';
import { CONSOLE_ENTRY } from '@/constants/routes';

import styles from './HomePage.module.less';

const CHANNELS = [
  { icon: Mail, label: 'Email' },
  { icon: Plug, label: 'LinkedIn' },
  { icon: MessageCircle, label: 'WhatsApp' },
];

const SEQUENCE = [
  { day: '第 1 天', title: '暖场邮件', detail: '基于公司背景和意向信号发送个性化开场' },
  { day: '第 2 天', title: 'LinkedIn：点赞内容', detail: '先互动对方最近内容，让名字自然出现' },
  { day: '第 3 天', title: 'LinkedIn：发送连接请求', detail: '带着上下文发送连接请求' },
  { day: '第 5 天', title: 'WhatsApp 跟进', detail: '基于前面所有上下文继续自然跟进' },
  { day: '第 7 天', title: '会议已预约', detail: '对方在通话前已经对你建立熟悉感' },
];

const SEQUENCE_STATS = [
  { value: '3×', label: '相比纯邮件更高的回复率' },
  { value: '5 个触点', label: '全程无需人工操作' },
  { value: '1 条', label: '统一的对话主线' },
];

const FEATURES = [
  {
    icon: Crosshair,
    title: '潜客挖掘',
    subtitle: '实时数据，而非过时数据库',
    detail: '描述你的 ICP，基于实时市场信号发现匹配的企业和关键决策人，让每一次触达都建立在当下正在发生的市场变化之上。',
  },
  {
    icon: Search,
    title: '智能调研',
    subtitle: '一键找到关键决策人',
    detail: '输入目标企业，自动识别关键决策人，包括买家、采购负责人及业务联系人，并提供经过验证的联系人资料。',
  },
  {
    icon: Building2,
    title: '企业背调',
    subtitle: '触达之前，先深入了解客户',
    detail: '分析企业信息、业务背景和市场信号，构建清晰的目标企业画像，把分散的公开信息转化为可执行的销售洞察。',
  },
  {
    icon: Sparkles,
    title: '智能体',
    subtitle: '基于买家研究，生成个性化触达',
    detail: '学习你的公司信息、销售目标和沟通风格，结合对每个客户的理解，自动生成并执行个性化、多渠道触达。',
  },
  {
    icon: Plug,
    title: '关联账号',
    subtitle: '在客户常用的渠道建立联系',
    detail: '连接 Email、LinkedIn、WhatsApp 等客户常用渠道，自动维护跨渠道对话，让每一次沟通都建立在上一轮互动的基础上。',
  },
];

const TESTIMONIALS = [
  {
    quote:
      '我们把线索数据库和单独的邮件工具都换掉了。Ai-get 同时完成这三件事，多渠道序列带来的回复数是过去纯邮件活动的 3 倍。',
    name: 'Nate H.',
    role: 'B2B SaaS 增长负责人',
  },
  {
    quote: '原本以为扩大 outbound 之前得先再招一个 SDR，现在第一批合格线索当天就跑出来了。',
    name: '林哲',
    role: '营收运营负责人',
  },
  {
    quote: '最有用的是每条线索都带匹配结论和背调摘要，销售不用再自己判断值不值得跟。',
    name: '周敏',
    role: '华东区销售总监',
  },
];

const HomePage = (): JSX.Element => {
  const navigate = useNavigate();
  const goConsole = (): void => navigate(CONSOLE_ENTRY);

  return (
    <div className={styles.page}>
      <section className={styles.hero}>
        <span className={styles.heroBadge}>AI B2B 销售智能体</span>
        <h1 className={styles.heroTitle}>
          使用 <span className={styles.heroBrand}>Ai-get</span> 找到并触达真实客户
        </h1>

        <div className={styles.channelRow}>
          {CHANNELS.map(({ icon: Icon, label }) => (
            <span key={label} className={styles.channelChip}>
              <Icon size={15} />
              {label}
            </span>
          ))}
        </div>

        <p className={styles.heroLead}>
          Ai-get 会找到有购买意向的买家，完成调研，并运行完整触达活动。你只需要在对方准备购买时介入。
        </p>

        <div className={styles.heroActions}>
          <Button variant="gradient" size="lg" onClick={goConsole} leadingIcon={<span aria-hidden>👋</span>}>
            免费雇用 REVOR
          </Button>
          <a className={styles.ghostLink} href="#how">
            查看工作原理 ↓
          </a>
        </div>

        <div className={styles.previewWrapper}>
          <div className={styles.preview}>
            <div className={styles.previewSidebar}>
              <span className={styles.previewBrand}>Ai-get</span>
              {['潜客挖掘', '企业背调', '智能体', '商机洞察'].map((item, index) => (
                <span
                  key={item}
                  className={[styles.previewNavItem, index === 0 ? styles.previewNavItemActive : '']
                    .filter(Boolean)
                    .join(' ')}
                >
                  {item}
                </span>
              ))}
            </div>
            <div className={styles.previewBody}>
              <div className={styles.previewToolbar}>
                <span className={styles.previewPill}>找公司</span>
                <span className={styles.previewPillMuted}>找人</span>
                <span className={styles.previewSearch}>描述你的目标客户画像…</span>
                <span className={styles.previewButton}>开始挖掘潜客</span>
              </div>
              {['杭州优能达食品有限公司', '杭州韩绮绣文化创意有限公司', '杭州安厨电子商务有限公司'].map((name) => (
                <div key={name} className={styles.previewRow}>
                  <span className={styles.previewCellName}>{name}</span>
                  <Tag tone="success" size="sm">
                    明确符合
                  </Tag>
                  <span className={styles.previewCellMuted}>已获取联系人</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className={styles.section} id="how">
        <header className={styles.sectionHeader}>
          <span className={styles.sectionEyebrow}>多渠道序列</span>
          <h2 className={styles.sectionTitle}>一个目标 三个渠道 一条对话主线</h2>
          <p className={styles.sectionLead}>
            你的智能体不是只会群发邮件，而是会编排一套更接近真实关系建立方式的多触点沟通流程。
          </p>
        </header>

        <ol className={styles.timeline}>
          {SEQUENCE.map((step) => (
            <li key={step.title} className={styles.timelineItem}>
              <span className={styles.timelineDay}>{step.day}</span>
              <h3 className={styles.timelineTitle}>{step.title}</h3>
              <p className={styles.timelineDetail}>{step.detail}</p>
            </li>
          ))}
        </ol>

        <div className={styles.statRow}>
          {SEQUENCE_STATS.map((stat) => (
            <div key={stat.label} className={styles.stat}>
              <strong>{stat.value}</strong>
              <span>{stat.label}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.sectionAlt}>
        <header className={styles.sectionHeader}>
          <span className={styles.sectionEyebrow}>核心功能</span>
          <h2 className={styles.sectionTitle}>REVOR 如何工作？</h2>
          <p className={styles.sectionLead}>从目标市场到已预约会议，中间的工作交给你的 AI 销售智能体。</p>
        </header>

        <div className={styles.featureGrid}>
          {FEATURES.map(({ icon: Icon, title, subtitle, detail }) => (
            <article key={title} className={styles.featureCard}>
              <span className={styles.featureIcon}>
                <Icon size={18} />
              </span>
              <h3 className={styles.featureTitle}>{title}</h3>
              <p className={styles.featureSubtitle}>{subtitle}</p>
              <p className={styles.featureDetail}>{detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <header className={styles.sectionHeader}>
          <span className={styles.sectionEyebrow}>客户反馈</span>
          <h2 className={styles.sectionTitle}>B2B 营收团队怎么评价</h2>
        </header>

        <div className={styles.testimonialGrid}>
          {TESTIMONIALS.map((item) => (
            <figure key={item.name} className={styles.testimonial}>
              <div className={styles.stars} aria-label="五星评价">
                {Array.from({ length: 5 }, (_, index) => (
                  <Star key={index} size={14} fill="currentColor" />
                ))}
              </div>
              <blockquote>{item.quote}</blockquote>
              <figcaption>
                <strong>{item.name}</strong>
                <span>{item.role}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

    </div>
  );
};

export default HomePage;
