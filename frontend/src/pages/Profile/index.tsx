import { useEffect, useState } from 'react';
import { Avatar, Button, Card, Col, Descriptions, Divider, Form, Input, Row, Space, Tag, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';

import * as authApi from '../../api/auth';
import { useAuthStore } from '../../store/auth';
import {
  IconCheckCircle,
  IconLogout,
  IconMail,
  IconUser,
  ReviewLensLogo,
} from '../../components/icons';

const { Title, Text } = Typography;

const ROLE_TAG_COLOR: Record<string, string> = {
  admin: 'purple',
  analyst: 'blue',
  operator: 'green',
};

const ROLE_DESC: Record<string, string> = {
  admin: '管理员 · 全部权限',
  analyst: '分析师 · 分析/审核/告警',
  operator: '运营 · 常规操作',
};

const ROLE_MATRIX: { role: string; label: string; color: string; abilities: string[] }[] = [
  { role: 'admin', label: '管理员', color: 'purple', abilities: ['全部权限', '用户与角色管理', '模型发布'] },
  { role: 'analyst', label: '分析师', color: 'blue', abilities: ['数据导入与搜索', '人工审核', '告警规则创建'] },
  { role: 'operator', label: '运营', color: 'green', abilities: ['常规操作', '问题卡流转', '告警处理'] },
];

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, initialized, fetchMe, signOut } = useAuthStore();
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<{ full_name: string }>();

  useEffect(() => {
    if (initialized && !user) {
      navigate('/login');
      return;
    }
    if (user) form.setFieldsValue({ full_name: user.full_name ?? '' });
  }, [initialized, user, form, navigate]);

  if (!user) return null;

  const displayName = user.full_name || user.email.split('@')[0];
  const joinedDate = new Date(user.created_at);

  const onSave = async (values: { full_name: string }) => {
    setSaving(true);
    try {
      await authApi.updateMe({ full_name: values.full_name || undefined });
      await fetchMe();
      message.success('保存成功');
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      message.error(detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 880, margin: '0 auto' }}>
      <Title level={3}>
        <span className="grad-text">个人设置</span>
      </Title>

      {/* 用户横幅：头像 + 信息 + 快捷操作 */}
      <div
        className="gradient-card"
        style={{
          padding: '22px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 18,
          marginBottom: 18,
          justifyContent: 'space-between',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <Avatar
            size={68}
            style={{
              background: 'linear-gradient(135deg, #22d3ee, #6366f1, #a78bfa)',
              fontWeight: 800,
              fontSize: 28,
              color: '#fff',
              boxShadow: 'var(--rl-glow)',
              flexShrink: 0,
            }}
          >
            {displayName.slice(0, 1).toUpperCase()}
          </Avatar>
          <div style={{ minWidth: 0 }}>
            <Space align="center" size={10}>
              <span style={{ fontSize: 21, fontWeight: 700, color: 'var(--rl-text)' }}>{displayName}</span>
              <Tag color={ROLE_TAG_COLOR[user.role] ?? 'default'} style={{ marginInlineEnd: 0 }}>
                {user.role}
              </Tag>
            </Space>
            <div style={{ marginTop: 4, color: 'var(--rl-text-secondary)', fontSize: 13 }}>
              {ROLE_DESC[user.role] ?? user.role}
            </div>
          </div>
        </div>
        <Button
          icon={<IconLogout size={15} />}
          onClick={() => {
            signOut();
            navigate('/login');
          }}
          style={{ background: 'rgba(148,163,184,0.08)', borderColor: 'var(--rl-border)' }}
        >
          退出登录
        </Button>
      </div>

      <Row gutter={18}>
        {/* 账号信息 */}
        <Col xs={24} md={10}>
          <Card className="glass-card" title="账号信息" style={{ height: '100%', marginBottom: 18 }}>
            <Descriptions column={1} size="small" colon={false} labelStyle={{ color: 'var(--rl-text-secondary)', width: 76 }}>
              <Descriptions.Item label="邮箱" contentStyle={{ display: 'block' }}>
                <Space size={6}>
                  <IconMail size={14} style={{ color: 'var(--rl-text-faint)' }} />
                  <span style={{ wordBreak: 'break-all' }}>{user.email}</span>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="角色">
                <Space size={6}>
                  <IconCheckCircle size={14} style={{ color: 'var(--rl-cyan)' }} />
                  <span>{user.role}</span>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="账号 ID">
                <Text type="secondary" style={{ fontSize: 12 }}>{user.id.slice(0, 16)}…</Text>
              </Descriptions.Item>
              <Descriptions.Item label="加入时间">
                {joinedDate.toLocaleDateString('zh-CN')}
              </Descriptions.Item>
            </Descriptions>
            <Divider style={{ borderColor: 'var(--rl-border)', margin: '16px 0' }} />
            <div style={{ color: 'var(--rl-text-faint)', fontSize: 12 }}>
              账号创建于 {joinedDate.toLocaleDateString('zh-CN')}，当前状态：正常
            </div>
          </Card>
        </Col>

        {/* 编辑资料 */}
        <Col xs={24} md={14}>
          <Card className="glass-card" title="编辑资料" style={{ height: '100%', marginBottom: 18 }}>
            <Form form={form} layout="vertical" onFinish={onSave}>
              <Form.Item name="full_name" label="姓名" rules={[{ max: 100, message: '姓名不能超过 100 字' }]}>
                <Input
                  prefix={<IconUser size={15} />}
                  placeholder="请输入姓名"
                  size="large"
                  style={{ background: 'rgba(148,163,184,0.06)' }}
                />
              </Form.Item>
              <Form.Item label="邮箱" extra="邮箱用于登录，暂不支持修改">
                <Input value={user.email} disabled size="large" style={{ background: 'rgba(148,163,184,0.04)' }} />
              </Form.Item>
              {user.phone && (
                <Form.Item label="手机号" extra="手机号可用于登录，暂不支持修改">
                  <Input value={user.phone} disabled size="large" style={{ background: 'rgba(148,163,184,0.04)' }} />
                </Form.Item>
              )}
              {user.username && (
                <Form.Item label="账号名" extra="注册时自动生成，可用于登录，暂不支持修改">
                  <Input value={user.username} disabled size="large" style={{ background: 'rgba(148,163,184,0.04)' }} />
                </Form.Item>
              )}
              <Button type="primary" htmlType="submit" loading={saving} className="gradient-btn">
                保存修改
              </Button>
            </Form>
          </Card>
        </Col>
      </Row>

      {/* 角色权限说明 */}
      <Card className="glass-card" title="角色权限说明">
        <Row gutter={16}>
          {ROLE_MATRIX.map((r) => (
            <Col xs={24} md={8} key={r.role}>
              <div
                style={{
                  padding: '14px 16px',
                  borderRadius: 12,
                  background: 'rgba(148,163,184,0.05)',
                  border: '1px solid var(--rl-border)',
                  marginBottom: 12,
                }}
              >
                <Space size={8} style={{ marginBottom: 8 }}>
                  <Tag color={r.color}>{r.label}</Tag>
                  <Text code style={{ fontSize: 12 }}>{r.role}</Text>
                </Space>
                <div>
                  {r.abilities.map((a) => (
                    <div key={a} style={{ color: 'var(--rl-text-secondary)', fontSize: 13, padding: '2px 0' }}>
                      · {a}
                    </div>
                  ))}
                </div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>

      <div
        style={{
          textAlign: 'center',
          marginTop: 30,
          color: 'var(--rl-text-faint)',
          fontSize: 12,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <ReviewLensLogo size={16} />
        ReviewLens · 让每一条评论都被看见
      </div>
    </div>
  );
}
