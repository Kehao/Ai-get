// 控制台侧边栏导航结构。子菜单只描述结构，渲染由 ConsoleLayout 完成。

import { Building2, Crosshair, LineChart, Share2, type LucideIcon } from 'lucide-react';

import { ROUTES } from './routes';

export interface ConsoleNavChild {
  label: string;
  path: string;
}

export interface ConsoleNavItem {
  key: string;
  label: string;
  icon: LucideIcon;
  path?: string;
  children?: ConsoleNavChild[];
}

export const CONSOLE_NAV: ConsoleNavItem[] = [
  {
    key: 'targets',
    label: '潜客挖掘',
    icon: Crosshair,
    path: ROUTES.consoleTargets,
  },
  {
    key: 'research',
    label: '企业背调',
    icon: Building2,
    path: ROUTES.consoleResearch,
  },
  {
    key: 'agents',
    label: '智能体',
    icon: Share2,
    children: [
      { label: '训练智能体', path: ROUTES.consoleAgents },
      { label: '关联账号', path: ROUTES.consoleChannels },
      { label: '知识库', path: ROUTES.consoleKnowledge },
    ],
  },
  {
    key: 'opportunities',
    label: '商机洞察',
    icon: LineChart,
    path: ROUTES.consoleOpportunities,
  },
];
