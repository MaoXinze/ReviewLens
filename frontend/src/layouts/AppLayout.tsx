import { useCallback, useEffect, useState } from 'react';
import { Avatar, Badge, Breadcrumb, Button, Dropdown, Layout, Menu, Space, Tag } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../store/auth';
import { listAlerts } from '../api/alerts';
import {
  IconAlert,
  IconBell,
  IconDashboard,
  IconDatabase,
  IconInsights,
  IconIssue,
  IconLogout,
  IconMenu,
  IconModel,
  IconReview,
  IconSearch,
  IconSettings,
  IconUsers,
  ReviewLensLogo,
} from '../components/icons';

const { Header, Sider, Content } = Layout;

const ROLE_TAG_COLOR: Record<string, string> = {
  admin: 'purple',
  analyst: 'blue',
  operator: 'green',
};

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': '体验总览',
  '/datasets': '数据集',
  '/search': '评论搜索',
  '/review-tasks': '审核任务',
  '/insights': '体验洞察',
  '/models': '模型中心',
  '/issues': '问题卡',
  '/alerts': '告警中心',
  '/users': '用户管理',
  '/profile': '个人设置',
};

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);
  const [alertCount, setAlertCount] = useState(0);

  // 轮询未处理告警数（60s）
  useEffect(() => {
    let cancelled = false;
    async function loadAlertCount() {
      try {
        const resp = await listAlerts({ status: 'active', page: 1, page_size: 1 });
        if (!cancelled) setAlertCount(resp.total ?? 0);
      } catch {
        /* 忽略告警数加载失败 */
      }
    }
    loadAlertCount();
    const timer = window.setInterval(loadAlertCount, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const handleMenuClick = useCallback(
    ({ key }: { key: string }) => {
      navigate(key);
    },
    [navigate],
  );

  const currentPath = '/' + (location.pathname.split('/')[1] || 'dashboard');
  const pageTitle = PAGE_TITLES[currentPath] ?? '';

  // 菜单（含自制图标）
  const menuItems = [
    { key: '/dashboard', icon: <IconDashboard size={17} />, label: '体验总览' },
    { key: '/datasets', icon: <IconDatabase size={17} />, label: '数据集' },
    { key: '/search', icon: <IconSearch size={17} />, label: '评论搜索' },
    { key: '/review-tasks', icon: <IconReview size={17} />, label: '审核任务' },
    { key: '/insights', icon: <IconInsights size={17} />, label: '体验洞察' },
    { key: '/models', icon: <IconModel size={17} />, label: '模型中心' },
    { key: '/issues', icon: <IconIssue size={17} />, label: '问题卡' },
    { key: '/alerts', icon: <IconAlert size={17} />, label: '告警中心' },
  ];
  if (user?.role === 'admin') {
    menuItems.push({ key: '/users', icon: <IconUsers size={17} />, label: '用户管理' });
  }

  const userMenuItems = [
    { key: 'profile', icon: <IconSettings size={15} />, label: '个人设置' },
    { type: 'divider' as const },
    { key: 'logout', icon: <IconLogout size={15} />, label: '退出登录' },
  ];

  const handleUserMenu = ({ key }: { key: string }) => {
    if (key === 'profile') navigate('/profile');
    if (key === 'logout') {
      signOut();
      navigate('/login');
    }
  };

  const displayName = user?.full_name || user?.email?.split('@')[0] || 'RL';
  const avatarBg =
    'linear-gradient(135deg, #22d3ee, #6366f1, #a78bfa)';

  return (
    <>
      <div className="rl-bg" />
      <Layout style={{ minHeight: '100vh' }}>
        <Sider
          collapsible
          collapsed={collapsed}
          trigger={null}
          width={224}
          style={{
            background: '#ffffff',
            borderRight: '1px solid #f0f0f0',
          }}
        >
          {/* Logo */}
          <div
            style={{
              height: 64,
              margin: '12px 16px 8px',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              overflow: 'hidden',
            }}
          >
            <ReviewLensLogo size={collapsed ? 28 : 32} />
            {!collapsed && (
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 800,
                  letterSpacing: 0.5,
                  background: 'var(--rl-grad-text)',
                  WebkitBackgroundClip: 'text',
                  backgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  whiteSpace: 'nowrap',
                }}
              >
                ReviewLens
              </span>
            )}
          </div>

          <Menu
            mode="inline"
            selectedKeys={[currentPath]}
            items={menuItems}
            onClick={handleMenuClick}
            style={{ background: 'transparent', paddingTop: 8 }}
          />
        </Sider>

        <Layout>
          <Header
            style={{
              background: 'rgba(255, 255, 255, 0.85)',
              backdropFilter: 'blur(10px)',
              padding: '0 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid #f0f0f0',
              height: 60,
              lineHeight: '60px',
            }}
          >
            <Space>
              <Button
                type="text"
                icon={<IconMenu size={18} />}
                onClick={() => setCollapsed(!collapsed)}
                style={{ color: 'var(--rl-text-secondary)' }}
              />
              <Breadcrumb
                items={[
                  { title: <span style={{ color: 'var(--rl-text-faint)' }}>首页</span> },
                  { title: <span className="grad-text" style={{ fontWeight: 600 }}>{pageTitle || '页面'}</span> },
                ]}
              />
            </Space>

            <Space size="middle">
              <Badge count={alertCount} size="small" overflowCount={99}>
                <Button
                  type="text"
                  shape="circle"
                  icon={<IconBell size={19} />}
                  onClick={() => navigate('/alerts')}
                  style={{ color: 'var(--rl-text-secondary)', fontSize: 18 }}
                />
              </Badge>

              <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenu }} placement="bottomRight">
                <Space style={{ cursor: 'pointer', padding: '4px 8px', borderRadius: 10 }} size={10}>
                  <Avatar size={30} style={{ background: avatarBg, fontWeight: 700, color: '#fff' }}>
                    {displayName.slice(0, 1).toUpperCase()}
                  </Avatar>
                  <span style={{ color: 'var(--rl-text)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {displayName}
                  </span>
                  {user?.role && <Tag color={ROLE_TAG_COLOR[user.role] ?? 'default'} style={{ marginInlineEnd: 0 }}>{user.role}</Tag>}
                </Space>
              </Dropdown>
            </Space>
          </Header>

          <Content style={{ margin: '0 auto', width: '100%', maxWidth: 1440 }}>
            {/* page-fade：路由切换入场动画（见 global.css） */}
            <div className="page-fade" key={currentPath}>
              <Outlet />
            </div>
          </Content>
        </Layout>
      </Layout>
    </>
  );
}
