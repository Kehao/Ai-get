// 相关文档：从挖掘到触达的使用说明。由账户菜单在新标签页打开。

import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen } from 'lucide-react';

import Button from '@/components/Button';
import { CONSOLE_ENTRY, ROUTES } from '@/constants/routes';

import styles from './DocsPage.module.less';

interface DocStep {
  title: string;
  detail: string;
}

interface DocSection {
  id: string;
  title: string;
  summary: string;
  steps: DocStep[];
}

const SECTIONS: DocSection[] = [
  {
    id: 'quick-start',
    title: '快速开始',
    summary: '三条路径跑通「找到客户 → 摸清背景 → 发出第一封消息」。',
    steps: [
      { title: '用一句话描述目标客户', detail: '在「潜客挖掘」里写清楚行业、地区、规模与阶段，越具体线索越准。' },
      { title: '等待列表生成', detail: '挖掘是异步任务，进度会实时刷新；完成后可逐条查看企业摘要与联系人。' },
      { title: '连接渠道并触达', detail: '先在「关联账号」连接邮箱，再用「智能触达」生成多渠道序列。' },
    ],
  },
  {
    id: 'targets',
    title: '潜客挖掘',
    summary: '用自然语言描述画像，得到一份带匹配结论和联系人的企业列表。',
    steps: [
      {
        title: '画像怎么写',
        detail: '推荐句式：地区 + 行业 + 规模 + 阶段。「在广州的跨境电商 SaaS 公司，A 轮融资，员工 50-200 人」比「找客户」有效得多。',
      },
      { title: '结果怎么看', detail: '每条记录都有 AI 摘要、匹配结论（明确符合 / 可能符合 / 待确认）与两项挖掘字段。' },
      {
        title: '字段重新富化',
        detail: '任一挖掘字段失败或结果不满意时，可单独对该字段发起重新富化，不必重跑整个列表。',
      },
      { title: '自定义调研列', detail: '通过「添加智能调研」为列表增加一列，让智能体按你的问题补充信息。' },
    ],
  },
  {
    id: 'research',
    title: '企业背调',
    summary: '触达前先摸清经营、组织与采购习惯，避免在错误的角色上浪费时间。',
    steps: [
      { title: '输入主体', detail: '支持公司名或官网，推荐问题可作为起点。' },
      { title: '阅读报告', detail: '报告按核心结论、基本信息、信息缺口、建议下一步组织，并列出所用工具。' },
      { title: '把它当成起点', detail: '公开信息通常不完整，报告会明确指出待核实的项，建议在首次沟通中确认。' },
    ],
  },
  {
    id: 'agents',
    title: '智能体',
    summary: '智能体决定触达的语气、节奏与渠道，是决定回复率的关键一环。',
    steps: [
      {
        title: '训练智能体',
        detail: '可从系统模板创建，也可以完全自定义名称、图标、描述与渠道组合。',
      },
      { title: '关联账号', detail: '邮箱渠道可直接连接；社媒渠道需要对应套餐，页面会明确提示所需版本。' },
      {
        title: '知识库',
        detail: '把官网整理成问答集后，智能体在对话里会优先使用企业自身的表述，减少答非所问。',
      },
    ],
  },
  {
    id: 'opportunities',
    title: '商机洞察',
    summary: '把互动记录汇总成可判断优先级的商机列表。',
    steps: [
      { title: '看指标', detail: '互动、消息、人脉与商机四个指标随所选时间范围联动。' },
      { title: '读信号', detail: '「对方回复询问报价区间」这类信号说明进入评估阶段，应优先跟进。' },
      { title: '用结论筛选', detail: '按建议跟进 / 初步信号 / 暂无信号筛选，把精力放在高意向线索上。' },
    ],
  },
];

const DocsPage = (): JSX.Element => (
  <div className={styles.page}>
    <header className={styles.hero}>
      <span className={styles.heroIcon}>
        <BookOpen size={22} />
      </span>
      <h1 className={styles.title}>使用文档</h1>
      <p className={styles.subtitle}>
        从目标市场到已预约会议的完整链路说明。全部功能都在控制台内，无需额外配置。
      </p>
      <Link to={CONSOLE_ENTRY}>
        <Button variant="gradient" size="lg">
          进入控制台
          <ArrowRight size={15} />
        </Button>
      </Link>
    </header>

    <div className={styles.body}>
      <nav className={styles.toc} aria-label="文档目录">
        <span className={styles.tocTitle}>目录</span>
        {SECTIONS.map((section) => (
          <a key={section.id} className={styles.tocLink} href={`#${section.id}`}>
            {section.title}
          </a>
        ))}
      </nav>

      <div className={styles.content}>
        {SECTIONS.map((section) => (
          <section key={section.id} id={section.id} className={styles.section}>
            <h2 className={styles.sectionTitle}>{section.title}</h2>
            <p className={styles.sectionSummary}>{section.summary}</p>

            <ol className={styles.stepList}>
              {section.steps.map((step, index) => (
                <li key={step.title} className={styles.step}>
                  <span className={styles.stepIndex}>{index + 1}</span>
                  <div className={styles.stepBody}>
                    <h3 className={styles.stepTitle}>{step.title}</h3>
                    <p className={styles.stepDetail}>{step.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ))}

        <p className={styles.footer}>
          还有其他问题？可以回到 <Link className={styles.link} to={ROUTES.consoleSettings}>设置</Link> 调整默认行为，
          或在 <Link className={styles.link} to={ROUTES.consoleAccount}>用户中心</Link> 查看工作空间当前状态。
        </p>
      </div>
    </div>
  </div>
);

export default DocsPage;
