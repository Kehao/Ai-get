// 应用入口：全局 Provider 与路由表。
// 营销页对外可访问；控制台页面统一由 RequireAuth 校验登录态。

import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { ToastProvider } from '@/components/Toast';
import { CONSOLE_ENTRY, ROUTES } from '@/constants/routes';
import ConsoleLayout from '@/layouts/ConsoleLayout';
import MarketingLayout from '@/layouts/MarketingLayout';
import SignInPage from '@/pages/auth/SignInPage';
import SignUpPage from '@/pages/auth/SignUpPage';
import AccountPage from '@/pages/console/AccountPage';
import AgentConfigPage from '@/pages/console/AgentConfigPage';
import ConnectPage from '@/pages/console/ConnectPage';
import KnowledgeDetailPage from '@/pages/console/KnowledgeDetailPage';
import KnowledgePage from '@/pages/console/KnowledgePage';
import OpportunitiesPage from '@/pages/console/OpportunitiesPage';
import ResearchDetailPage from '@/pages/console/ResearchDetailPage';
import ResearchPage from '@/pages/console/ResearchPage';
import SettingsPage from '@/pages/console/SettingsPage';
import TargetDetailPage from '@/pages/console/TargetDetailPage';
import TargetsPage from '@/pages/console/TargetsPage';
import DocsPage from '@/pages/marketing/DocsPage';
import HomePage from '@/pages/marketing/HomePage';
import PrivacyPage from '@/pages/marketing/PrivacyPage';
import TermsPage from '@/pages/marketing/TermsPage';
import RequireAuth from '@/router/RequireAuth';
import { AuthProvider } from '@/store/auth';
import { PreferencesProvider } from '@/store/preferences';

const App = (): JSX.Element => (
  <BrowserRouter>
    <PreferencesProvider>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route element={<MarketingLayout />}>
              <Route path={ROUTES.home} element={<HomePage />} />
              <Route path={ROUTES.docs} element={<DocsPage />} />
              <Route path={ROUTES.terms} element={<TermsPage />} />
              <Route path={ROUTES.privacy} element={<PrivacyPage />} />
            </Route>

            <Route path={ROUTES.signIn} element={<SignInPage />} />
            <Route path={ROUTES.signUp} element={<SignUpPage />} />

            <Route element={<RequireAuth />}>
              <Route path="/console" element={<ConsoleLayout />}>
                <Route index element={<Navigate to={CONSOLE_ENTRY} replace />} />
                <Route path="targets" element={<TargetsPage />} />
                <Route path="targets/:listId" element={<TargetDetailPage />} />
                <Route path="company-research" element={<ResearchPage />} />
                <Route path="company-research/:recordId" element={<ResearchDetailPage />} />
                <Route path="agent-config" element={<AgentConfigPage />} />
                <Route path="connect" element={<ConnectPage />} />
                <Route path="knowledge" element={<KnowledgePage />} />
                <Route path="knowledge/:knowledgeBaseId" element={<KnowledgeDetailPage />} />
                <Route path="opportunities" element={<OpportunitiesPage />} />
                <Route path="account" element={<AccountPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to={ROUTES.home} replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </PreferencesProvider>
  </BrowserRouter>
);

export default App;
