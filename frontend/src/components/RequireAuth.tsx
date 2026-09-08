import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';

import { getToken } from '../api/client';
import { useAuthStore } from '../store/auth';
import { useEffect } from 'react';

export default function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { user, initialized, fetchMe } = useAuthStore();
  const hasToken = Boolean(getToken());

  useEffect(() => {
    if (hasToken && !initialized) {
      fetchMe();
    }
  }, [hasToken, initialized, fetchMe]);

  // 未登录 → 跳登录页并记录来源
  if (!hasToken) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 已有 token 但用户信息尚未拉取到，先显示加载
  if (!initialized || !user) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '60vh',
        }}
      >
        {/* tip 仅在嵌套/全屏模式生效，包一层容器以正确显示提示文案 */}
        <Spin size="large" tip="加载中...">
          <div style={{ minHeight: 120 }} />
        </Spin>
      </div>
    );
  }

  return <>{children}</>;
}
