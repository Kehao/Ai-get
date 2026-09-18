// 服务条款页。

import { Link } from 'react-router-dom';

import { ROUTES } from '@/constants/routes';

import LegalPage, { type LegalSection } from './LegalPage';

const UPDATED_AT = '2026 年 9 月 19 日';

const SECTIONS: LegalSection[] = [
  {
    heading: '服务说明',
    paragraphs: [
      'Ai-get 是一套面向 B2B 团队的 AI 销售智能体平台，提供潜客挖掘、企业背调、智能体训练与商机洞察能力。',
      '本站为参考站点复刻的演示环境，所有企业信息、联系人与互动记录均为虚拟数据，不代表任何真实主体。',
    ],
  },
  {
    heading: '账户与登录',
    paragraphs: ['你需使用有效邮箱注册账户，并对账户下的全部操作负责。请不要将账户凭据分享给他人。'],
    list: [
      '注册时提供的信息应真实、准确，并在变更后及时更新。',
      '如发现账户被未经授权使用，请立即联系我们冻结账户。',
      '演示环境不接数据库，服务重启后新建的账户与数据会被清空。',
    ],
  },
  {
    heading: '数据来源与使用边界',
    paragraphs: [
      '平台的公开信息检索能力仅用于合法的商业沟通准备。你承诺不将本服务用于骚扰、欺诈或违反当地法律法规的用途。',
      '我们对展示的公开信息准确性不作担保，使用前请自行核实。',
    ],
  },
  {
    heading: '智能体行为',
    paragraphs: [
      '智能体按照你配置的渠道与话术风格执行触达。你是智能体对外沟通内容的最终责任人。',
      '请确保触达内容不包含虚假陈述、误导性承诺或侵犯第三方权益的信息。',
    ],
  },
  {
    heading: '服务变更与终止',
    paragraphs: [
      '我们可能调整功能范围或接口行为。对于影响使用的重大变更，会在页面显著位置提前说明。',
      '如你违反本条款，我们有权暂停或终止对应的账户访问。',
    ],
  },
  {
    heading: '免责声明',
    paragraphs: ['本服务按现状提供。在法律允许的最大范围内，我们不对因使用本服务产生的间接损失承担责任。'],
  },
];

const TermsPage = (): JSX.Element => (
  <LegalPage
    title="服务条款"
    updatedAt={UPDATED_AT}
    intro="欢迎使用 Ai-get。本条款说明你在使用本平台时的权利与义务，请在使用前仔细阅读。"
    sections={SECTIONS}
    footer={
      <>
        如对本条款有疑问，可通过 <Link to={ROUTES.home}>首页</Link> 联系方式与我们沟通。
      </>
    }
  />
);

export default TermsPage;
