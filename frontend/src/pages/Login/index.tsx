import { useEffect, useState } from 'react';
import { Button, Form, Input, Segmented, Typography, message } from 'antd';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { getToken } from '../../api/client';
import * as authApi from '../../api/auth';
import { useAuthStore } from '../../store/auth';
import {
  IconArrowRight,
  IconCheckCircle,
  IconInsights,
  IconLock,
  IconMail,
  IconRocket,
  IconUser,
  ReviewLensLogo,
} from '../../components/icons';

const { Title, Text } = Typography;

type LoginMode = 'email' | 'account';

interface LoginForm {
  account: string;
  password: string;
}

/** 左侧品牌区的产品亮点 */
const HIGHLIGHTS = [
  { icon: <IconInsights size={16} />, text: '情感 × 属性双层分析，差评归因到具体维度' },
  { icon: <IconCheckCircle size={16} />, text: '每个数字可下钻到原始评论证据' },
  { icon: <IconRocket size={16} />, text: '问题卡 + 告警，驱动改进闭环' },
];

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { signIn, fetchMe } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<LoginMode>('email');

  useEffect(() => {
    // 已登录用户访问 /login 自动回到工作台（先退出登录才能看到本页）
    if (getToken()) navigate('/dashboard', { replace: true });
  }, [navigate]);

  const onFinish = async (values: LoginForm) => {
    setLoading(true);
    try {
      // 邮箱模式原样发送（后端按 @ 识别）；账号模式发送用户名或手机号
      const account =
        mode === 'email' ? values.account.trim() : values.account.trim().toLowerCase();
      const tokens = await authApi.login({ account, password: values.password });
      signIn(tokens.access_token, tokens.refresh_token);
      await fetchMe();
      const from =
        (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ||
        sessionStorage.getItem('reviewlens_from') ||
        '/dashboard';
      sessionStorage.removeItem('reviewlens_from');
      message.success('登录成功');
      navigate(from, { replace: true });
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '登录失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const emailMode = mode === 'email';

  return (
    <div style={{ minHeight: '100vh', display: 'flex', position: 'relative' }}>
      <div className="rl-bg" />

      {/* ---------- 左侧品牌叙事区（窄屏隐藏） ---------- */}
      <div
        style={{
          flex: '1 1 46%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          padding: '64px 72px',
          background: 'linear-gradient(160deg, #f0f7ff 0%, #ffffff 55%, #f9f5ff 100%)',
          borderRight: '1px solid var(--rl-border)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: -120,
            right: -120,
            width: 360,
            height: 360,
            borderRadius: '50%',
            background: 'radial-gradient(closest-side, rgba(22,119,255,0.08), transparent)',
          }}
        />
        <ReviewLensLogo size={44} />
        <Title level={2} style={{ margin: '22px 0 10px', fontWeight: 800, letterSpacing: 0.3 }}>
          把每一条差评
          <br />
          变成一次<span className="grad-text">改进决策</span>
        </Title>
        <Text type="secondary" style={{ fontSize: 15, maxWidth: 420, display: 'block' }}>
          ReviewLens 拆解商品评论，量化物流、品质、外观、服务等属性的差评率，
          帮品牌团队 3 分钟定位最严重的体验问题。
        </Text>
        <div style={{ marginTop: 36, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {HIGHLIGHTS.map((h) => (
            <div key={h.text} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 8,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#1677ff',
                  background: '#e6f4ff',
                  flexShrink: 0,
                }}
              >
                {h.icon}
              </span>
              <Text style={{ fontSize: 14 }}>{h.text}</Text>
            </div>
          ))}
        </div>
        <Text
          type="secondary"
          style={{ position: 'absolute', bottom: 28, left: 72, fontSize: 12 }}
        >
          Amazon Reviews 2023 · 真实数据闭环演示
        </Text>
      </div>

      {/* ---------- 右侧表单区 ---------- */}
      <div
        style={{
          flex: '1 1 54%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
        }}
      >
        <div style={{ width: 400, maxWidth: '100%' }}>
          {/* 窄屏才显示顶部品牌 */}
          <div style={{ textAlign: 'center', marginBottom: 26 }}>
            <div style={{ marginBottom: 12 }}>
              <span className="grad-text" style={{ fontSize: 26, fontWeight: 800 }}>
                ReviewLens
              </span>
            </div>
            <Title level={4} style={{ margin: 0 }}>
              欢迎回来
            </Title>
            <Text type="secondary">登录以继续你的体验洞察之旅</Text>
          </div>

          <Segmented
            block
            value={mode}
            onChange={(v) => setMode(v as LoginMode)}
            options={[
              { label: '邮箱登录', value: 'email' },
              { label: '手机号 / 账号', value: 'account' },
            ]}
            style={{ marginBottom: 20 }}
          />

          <Form<LoginForm> layout="vertical" onFinish={onFinish} requiredMark={false}>
            <Form.Item
              name="account"
              label={emailMode ? '邮箱' : '手机号 / 账号名'}
              rules={[
                { required: true, message: emailMode ? '请输入邮箱' : '请输入手机号或账号名' },
                ...(emailMode ? [{ type: 'email' as const, message: '邮箱格式不正确' }] : []),
              ]}
            >
              <Input
                prefix={
                  emailMode ? (
                    <IconMail size={15} style={{ color: 'var(--rl-text-faint)' }} />
                  ) : (
                    <IconUser size={15} style={{ color: 'var(--rl-text-faint)' }} />
                  )
                }
                placeholder={emailMode ? 'you@example.com' : '注册手机号或账号名'}
                size="large"
                autoComplete="username"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password
                prefix={<IconLock size={15} style={{ color: 'var(--rl-text-faint)' }} />}
                placeholder="请输入密码"
                size="large"
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 12 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                size="large"
                loading={loading}
                className="gradient-btn"
              >
                登 录
                {!loading && <IconArrowRight size={15} style={{ marginLeft: 6 }} />}
              </Button>
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'center', marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              没有账号？<Link to="/register">立即注册</Link>
            </Text>
          </div>

          <div
            style={{
              marginTop: 26,
              padding: '10px 14px',
              borderRadius: 8,
              background: '#f6f8fa',
              border: '1px solid var(--rl-border)',
              fontSize: 12,
              color: 'var(--rl-text-secondary)',
              lineHeight: 1.7,
            }}
          >
            支持三种方式登录：<b>注册邮箱</b>、<b>手机号</b>、<b>账号名</b>（注册时自动生成，
            可在个人设置中查看）。
          </div>
        </div>
      </div>
    </div>
  );
}
