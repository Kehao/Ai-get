// 隐私政策页。

import { Link } from 'react-router-dom';

import { ROUTES } from '@/constants/routes';

import LegalPage, { type LegalSection } from './LegalPage';

const UPDATED_AT = '2026 年 9 月 19 日';

const SECTIONS: LegalSection[] = [
  {
    heading: '我们收集哪些信息',
    paragraphs: ['为了提供服务，我们处理的信息分为以下几类：'],
    list: [
      '账户信息：邮箱地址与登录凭据。',
      '业务内容：你创建的潜客列表、调研问题、智能体配置与知识库素材。',
      '渠道凭据：你在「关联账号」中连接的邮箱或社媒账号标识。',
      '使用记录：页面操作与接口调用日志，用于排查故障。',
    ],
  },
  {
    heading: '信息如何使用',
    paragraphs: [
      '账户信息用于身份校验；业务内容用于生成挖掘结果、调研报告与商机结论；渠道凭据仅用于代表你执行触达。',
      '我们不会把你的客户列表与调研结果用于训练公共模型。',
    ],
  },
  {
    heading: '演示环境的数据存储',
    paragraphs: [
      '本演示环境不接入数据库，全部数据保存在服务进程内存中。服务重启后，新建的账户与业务数据会被清空。',
      '这意味着演示数据不会长期留存，也不会用于任何其他用途。',
    ],
  },
  {
    heading: '信息共享',
    paragraphs: ['除以下情形外，我们不会向第三方共享你的信息：'],
    list: [
      '你明确授权或主动发起的导出、集成操作。',
      '为完成渠道触达而必须传递给你的渠道服务商。',
      '法律法规要求或司法机关依法调取。',
    ],
  },
  {
    heading: '你的权利',
    paragraphs: [
      '你可以随时查看、修改或删除自己创建的业务内容；潜客列表、调研记录与知识库均提供删除入口。',
      '如需注销账户或导出全部数据，请通过首页联系方式提交申请。',
    ],
  },
  {
    heading: '安全措施',
    paragraphs: [
      '登录令牌采用签名的无状态凭证，仅保存在浏览器会话中，关闭标签页即失效。',
      '接口访问均需携带有效令牌，未通过校验的请求会被拒绝。',
    ],
  },
];

const PrivacyPage = (): JSX.Element => (
  <LegalPage
    title="隐私政策"
    updatedAt={UPDATED_AT}
    intro="本政策说明 Ai-get 在处理你的信息时遵循的原则与实践。我们把数据最小化与用途透明作为默认设计。"
    sections={SECTIONS}
    footer={
      <>
        如需行使数据相关权利，可通过 <Link to={ROUTES.home}>首页</Link> 联系方式与我们沟通。
      </>
    }
  />
);

export default PrivacyPage;
