import { useMemo, useState } from 'react';
import { Button, Form, Input, Progress, Segmented, Typography, message } from 'antd';
import { Link, useNavigate } from 'react-router-dom';

import * as authApi from '../../api/auth';
import { IconArrowRight, IconCheckCircle, IconLock, IconMail, IconUser, ReviewLensLogo } from '../../components/icons';

const { Title, Text } = Typography;

type RegisterMode = 'email' | 'phone';

interface RegisterForm {
  identifier: string;
  full_name?: string;
  password: string;
  confirm: string;
}

/** 密码强度：0-4（长度 + 字符类别） */
function passwordScore(pwd: string): number {
  if (!pwd) return 0;
  let score = 0;
  if (pwd.length >= 8) score += 1;
  if (pwd.length >= 12) score += 1;
  if (/[a-zA-Z]/.test(pwd) && /\d/.test(pwd)) score += 1;
  if (/[^a-zA-Z0-9]/.test(pwd)) score += 1;
  return score;
}

const STRENGTH = [
  { label: '过短', color: '#ff4d4f' },
  { label: '弱', color: '#ff7a45' },
  { label: '一般', color: '#faad14' },
  { label: '强', color: '#52c41a' },
  { label: '很强', color: '#389e0d' },
];

export default function RegisterPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<RegisterMode>('email');
  const [password, setPassword] = useState('');
  // 注册成功后展示自动生成的账号名
  const [created, setCreated] = useState<{ username: string | null; account: string } | null>(null);

  const score = useMemo(() => passwordScore(password), [password]);
  const strength = STRENGTH[score];

  const onFinish = async (values: RegisterForm) => {
    setLoading(true);
    try {
      const body: authApi.RegisterBody = {
        password: values.password,
        full_name: values.full_name || undefined,
      };
      const account = values.identifier.trim();
      if (mode === 'email') body.email = account;
      else body.phone = account;

      const resp = await authApi.register(body);
      setCreated({ username: resp.username, account });
      message.success('注册成功');
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '注册失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  // 注册成功：展示自动生成的账号名，引导去登录
  if (created) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          position: 'relative',
        }}
      >
        <div className="rl-bg" />
        <div className="glass-card" style={{ width: 420, maxWidth: '100%', padding: '36px 32px', textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
            <IconCheckCircle size={44} style={{ color: '#52c41a' }} />
          </div>
          <Title level={4} style={{ marginTop: 0 }}>
            注册成功
          </Title>
          <Text type="secondary" style={{ display: 'block', marginBottom: 18 }}>
            系统已为你的账号（{created.account}）生成登录账号名：
          </Text>
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: '#1677ff',
              background: '#f0f7ff',
              border: '1px dashed #91caff',
              borderRadius: 8,
              padding: '10px 16px',
              marginBottom: 8,
              letterSpacing: 0.5,
            }}
          >
            {created.username}
          </div>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 20 }}>
            请妥善保存。之后可用邮箱/手机号/账号名 + 密码登录。
          </Text>
          <Button type="primary" block size="large" className="gradient-btn" onClick={() => navigate('/login')}>
            去登录
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        position: 'relative',
      }}
    >
      <div className="rl-bg" />
      <div style={{ width: 420, maxWidth: '100%', position: 'relative' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 10 }}>
            <ReviewLensLogo size={46} />
          </div>
          <Title
            level={2}
            style={{
              margin: 0,
              fontWeight: 800,
              background: 'var(--rl-grad-text)',
              WebkitBackgroundClip: 'text',
              backgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            创建账号
          </Title>
          <Text type="secondary">加入 ReviewLens，开始数据驱动的体验优化</Text>
        </div>

        <div className="glass-card" style={{ padding: '26px 28px' }}>
          <Segmented
            block
            value={mode}
            onChange={(v) => setMode(v as RegisterMode)}
            options={[
              { label: '邮箱注册', value: 'email' },
              { label: '手机号注册', value: 'phone' },
            ]}
            style={{ marginBottom: 18 }}
          />

          <Form<RegisterForm> layout="vertical" onFinish={onFinish} requiredMark={false}>
            <Form.Item
              name="identifier"
              label={mode === 'email' ? '邮箱' : '手机号'}
              rules={[
                { required: true, message: mode === 'email' ? '请输入邮箱' : '请输入手机号' },
                ...(mode === 'email'
                  ? [{ type: 'email' as const, message: '邮箱格式不正确' }]
                  : [{ pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确' }]),
              ]}
            >
              <Input
                prefix={
                  <IconMail size={15} style={{ color: 'var(--rl-text-faint)' }} />
                }
                placeholder={mode === 'email' ? 'you@example.com' : '用于登录和找回账号'}
                size="large"
              />
            </Form.Item>
            <Form.Item name="full_name" label="姓名">
              <Input
                prefix={<IconUser size={15} style={{ color: 'var(--rl-text-faint)' }} />}
                placeholder="您的姓名（可选）"
                size="large"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, message: '密码至少 8 位' },
              ]}
            >
              <div>
                <Input.Password
                  prefix={<IconLock size={15} style={{ color: 'var(--rl-text-faint)' }} />}
                  placeholder="至少 8 位"
                  size="large"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                {password && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                    <Progress
                      percent={(score / 4) * 100}
                      showInfo={false}
                      strokeColor={strength.color}
                      style={{ flex: 1, margin: 0 }}
                      size={['100%', 4]}
                    />
                    <Text style={{ fontSize: 12, color: strength.color, whiteSpace: 'nowrap' }}>
                      {strength.label}
                    </Text>
                  </div>
                )}
              </div>
            </Form.Item>
            <Form.Item
              name="confirm"
              label="确认密码"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次输入的密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password
                prefix={<IconLock size={15} style={{ color: 'var(--rl-text-faint)' }} />}
                placeholder="再次输入密码"
                size="large"
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 8 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                size="large"
                loading={loading}
                className="gradient-btn"
              >
                注 册
                {!loading && <IconArrowRight size={15} style={{ marginLeft: 6 }} />}
              </Button>
            </Form.Item>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', textAlign: 'center' }}>
              注册后系统会自动生成一个登录账号名，邮箱 / 手机号 / 账号名均可登录
            </Text>
          </Form>
          <div style={{ textAlign: 'center', marginTop: 14 }}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              已有账号？<Link to="/login">去登录</Link>
            </Text>
          </div>
        </div>
      </div>
    </div>
  );
}
