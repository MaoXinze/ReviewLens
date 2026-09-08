import { lazy, Suspense } from 'react';
import { ConfigProvider, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { themeConfig } from './theme';
import ErrorBoundary from './components/ErrorBoundary';
import RequireAuth from './components/RequireAuth';
import AppLayout from './layouts/AppLayout';

// 路由级代码分割：每个页面独立 chunk
const LoginPage = lazy(() => import('./pages/Login'));
const RegisterPage = lazy(() => import('./pages/Register'));
const NotFoundPage = lazy(() => import('./pages/NotFound'));
const DashboardPage = lazy(() => import('./pages/Dashboard'));
const DatasetsPage = lazy(() => import('./pages/Datasets'));
const SearchPage = lazy(() => import('./pages/Search'));
const ReviewTasksPage = lazy(() => import('./pages/ReviewTasks'));
const InsightsPage = lazy(() => import('./pages/Insights'));
const ModelsPage = lazy(() => import('./pages/Models'));
const IssuesPage = lazy(() => import('./pages/Issues'));
const AlertsPage = lazy(() => import('./pages/Alerts'));
const UsersPage = lazy(() => import('./pages/Users'));
const ProfilePage = lazy(() => import('./pages/Profile'));

function PageFallback() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '40vh' }}>
      <Spin size="large" />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ConfigProvider locale={zhCN} theme={themeConfig}>
        <BrowserRouter>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route
                element={
                  <RequireAuth>
                    <AppLayout />
                  </RequireAuth>
                }
              >
                <Route path="/dashboard" element={<DashboardPage />} />
                <Route path="/datasets" element={<DatasetsPage />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/review-tasks" element={<ReviewTasksPage />} />
                <Route path="/insights" element={<InsightsPage />} />
                <Route path="/models" element={<ModelsPage />} />
                <Route path="/issues" element={<IssuesPage />} />
                <Route path="/alerts" element={<AlertsPage />} />
                <Route path="/users" element={<UsersPage />} />
                <Route path="/profile" element={<ProfilePage />} />
              </Route>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ConfigProvider>
    </ErrorBoundary>
  );
}
