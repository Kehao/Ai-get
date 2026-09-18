// 路由常量集中管理，避免路径字符串散落在组件中。

export const ROUTES = {
  home: '/',
  signIn: '/auth/signin',
  signUp: '/auth/signup',
  terms: '/terms-of-service',
  privacy: '/privacy-policy',
  docs: '/docs',

  consoleTargets: '/console/targets',
  consoleTargetDetail: (listId: string) => `/console/targets/${listId}`,
  consoleResearch: '/console/company-research',
  consoleResearchDetail: (recordId: string) => `/console/company-research/${recordId}`,
  consoleAgents: '/console/agent-config',
  consoleChannels: '/console/connect',
  consoleKnowledge: '/console/knowledge',
  consoleKnowledgeDetail: (knowledgeBaseId: string) => `/console/knowledge/${knowledgeBaseId}`,
  consoleOpportunities: '/console/opportunities',
  consoleAccount: '/console/account',
  consoleSettings: '/console/settings',
} as const;

/** 登录后默认进入的主功能页。 */
export const CONSOLE_ENTRY = ROUTES.consoleTargets;
