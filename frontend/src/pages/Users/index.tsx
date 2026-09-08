import { useEffect, useState } from 'react';
import { Alert, Badge, Card, Select, Space, Table, Tag, Typography, message, Modal } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { UserOut, UserRole } from '../../api/auth';
import type { UserListResponse } from '../../api/users';
import * as userApi from '../../api/users';
import { getErrorMessage } from '../../api/client';
import { useAuthStore } from '../../store/auth';

const { Title } = Typography;

const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: 'operator', label: '运营（operator）' },
  { value: 'analyst', label: '分析师（analyst）' },
  { value: 'admin', label: '管理员（admin）' },
];

const ROLE_TAG_COLOR: Record<string, string> = {
  admin: 'purple',
  analyst: 'blue',
  operator: 'green',
};

export default function UsersPage() {
  const { user: currentUser } = useAuthStore();
  const [items, setItems] = useState<UserOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [roleUpdatingId, setRoleUpdatingId] = useState<string | null>(null);

  const isAdmin = currentUser?.role === 'admin';

  async function load() {
    setLoading(true);
    try {
      const resp: UserListResponse = await userApi.listUsers({ page, page_size: 20 });
      setItems(resp.items ?? []);
      setTotal(resp.total ?? 0);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '加载用户列表失败'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  function onChangeRole(user: UserOut, role: UserRole) {
    Modal.confirm({
      title: '修改用户角色',
      content: `确定将 ${user.email} 的角色改为「${ROLE_OPTIONS.find((o) => o.value === role)?.label}」吗？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        setRoleUpdatingId(user.id);
        try {
          await userApi.updateUserRole(user.id, role);
          message.success('角色已更新');
          await load();
        } catch (e: unknown) {
          message.error(getErrorMessage(e, '更新角色失败'));
        } finally {
          setRoleUpdatingId(null);
        }
      },
    });
  }

  const columns: ColumnsType<UserOut> = [
    { title: '邮箱', dataIndex: 'email', ellipsis: true },
    { title: '姓名', dataIndex: 'full_name', render: (v: string | null) => v || '—' },
    {
      title: '角色',
      dataIndex: 'role',
      width: 180,
      render: (v: UserRole, row) => (
        <Space size={8}>
          <Tag color={ROLE_TAG_COLOR[v] ?? 'default'}>{v}</Tag>
          <Select
            size="small"
            style={{ width: 140 }}
            value={v}
            disabled={row.id === currentUser?.id || roleUpdatingId === row.id}
            loading={roleUpdatingId === row.id}
            options={ROLE_OPTIONS}
            onChange={(nv: UserRole) => onChangeRole(row, nv)}
          />
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (v: boolean) =>
        v ? <Badge status="success" text="启用" /> : <Badge status="default" text="禁用" />,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 180 },
  ];

  if (!isAdmin) {
    return (
      <Alert
        type="warning"
        showIcon
        message="无权限访问"
        description="用户管理仅对管理员开放。"
      />
    );
  }

  return (
    <div>
      <Title level={3}><span className="grad-text">用户管理</span></Title>
      <Card>
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: (p) => setPage(p),
          }}
        />
      </Card>
    </div>
  );
}
