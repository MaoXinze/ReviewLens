import { useEffect, useState } from 'react';
import {
  Badge,
  Button,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { getErrorMessage } from '../../api/client';
import type {
  Alert,
  AlertRule,
  AlertStatus,
  ExportRecord,
  ListResponse,
  RuleStatus,
  RuleType,
} from '../../api/alerts';
import * as alertsApi from '../../api/alerts';

const { Title, Paragraph, Text } = Typography;

const RULE_STATUS_TAGS: Record<string, { color: string; text: string }> = {
  active: { color: 'success', text: '启用' },
  paused: { color: 'default', text: '暂停' },
};

const ALERT_STATUS_TAGS: Record<string, { color: string; text: string }> = {
  active: { color: 'red', text: '待处理' },
  acknowledged: { color: 'processing', text: '已确认' },
  resolved: { color: 'success', text: '已解决' },
};

// 告警状态可推进目标
const NEXT_ALERT: Record<AlertStatus, AlertStatus[] | null> = {
  active: ['acknowledged', 'resolved'],
  acknowledged: ['resolved'],
  resolved: null,
};

export default function AlertsPage() {
  // ---- 规则 ----
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [rulesTotal, setRulesTotal] = useState(0);
  const [rulesPage, setRulesPage] = useState(1);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [creating, setCreating] = useState(false);

  // ---- 告警 ----
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsTotal, setAlertsTotal] = useState(0);
  const [alertsPage, setAlertsPage] = useState(1);
  const [alertsStatus, setAlertsStatus] = useState<string | undefined>();
  const [alertsLoading, setAlertsLoading] = useState(false);

  // ---- 导出 ----
  const [exports, setExports] = useState<ExportRecord[]>([]);
  const [exportsTotal, setExportsTotal] = useState(0);
  const [exportsPage, setExportsPage] = useState(1);
  const [exportsLoading, setExportsLoading] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportForm] = Form.useForm();
  const [exporting, setExporting] = useState(false);

  async function loadRules() {
    setRulesLoading(true);
    try {
      const resp: ListResponse<AlertRule> = await alertsApi.listRules({
        page: rulesPage,
        page_size: 20,
      });
      setRules(resp.items ?? []);
      setRulesTotal(resp.total ?? 0);
    } finally {
      setRulesLoading(false);
    }
  }

  async function loadAlerts() {
    setAlertsLoading(true);
    try {
      const resp: ListResponse<Alert> = await alertsApi.listAlerts({
        page: alertsPage,
        page_size: 20,
        status: alertsStatus,
      });
      setAlerts(resp.items ?? []);
      setAlertsTotal(resp.total ?? 0);
    } finally {
      setAlertsLoading(false);
    }
  }

  async function loadExports() {
    setExportsLoading(true);
    try {
      const resp: ListResponse<ExportRecord> = await alertsApi.listExports({
        page: exportsPage,
        page_size: 20,
      });
      setExports(resp.items ?? []);
      setExportsTotal(resp.total ?? 0);
    } finally {
      setExportsLoading(false);
    }
  }

  useEffect(() => {
    loadRules();
    loadAlerts();
    loadExports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rulesPage, alertsPage, alertsStatus, exportsPage]);

  async function onCreateRule() {
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      await alertsApi.createRule(values);
      message.success('告警规则已创建');
      setCreateOpen(false);
      createForm.resetFields();
      await loadRules();
    } catch (e: unknown) {
      if ((e as { response?: object })?.response) {
        message.error(getErrorMessage(e, '创建失败'));
      }
    } finally {
      setCreating(false);
    }
  }

  async function onToggleRule(rule: AlertRule, status: RuleStatus) {
    try {
      await alertsApi.updateRuleStatus(rule.id, status);
      message.success(status === 'paused' ? '规则已暂停' : '规则已启用');
      await loadRules();
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '操作失败'));
    }
  }

  async function onAlertTransition(alert: Alert, status: AlertStatus) {
    Modal.confirm({
      title: status === 'resolved' ? '确认解决告警' : '确认告警',
      content: `确定将告警「${alert.rule_name}」标记为${ALERT_STATUS_TAGS[status]?.text ?? status}吗？`,
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        try {
          await alertsApi.updateAlertStatus(alert.id, status);
          message.success(status === 'resolved' ? '告警已解决' : '告警已确认');
          await loadAlerts();
        } catch (e: unknown) {
          message.error(getErrorMessage(e, '操作失败'));
        }
      },
    });
  }

  async function onCreateExport() {
    try {
      const values = await exportForm.validateFields();
      setExporting(true);
      await alertsApi.createExport(values);
      message.success('导出任务已提交');
      setExportOpen(false);
      exportForm.resetFields();
      await loadExports();
    } catch (e: unknown) {
      if ((e as { response?: object })?.response) {
        message.error(getErrorMessage(e, '导出失败'));
      }
    } finally {
      setExporting(false);
    }
  }

  const ruleColumns: ColumnsType<AlertRule> = [
    { title: '规则名', dataIndex: 'name' },
    {
      title: '类型',
      dataIndex: 'rule_type',
      render: (v: RuleType) => (v === 'threshold' ? <Tag>阈值</Tag> : <Tag color="blue">环比</Tag>),
    },
    { title: '属性', dataIndex: 'aspect' },
    { title: 'SKU', dataIndex: 'product_id', render: (v?: string | null) => v ?? '全部' },
    {
      title: '阈值',
      dataIndex: 'threshold_value',
      render: (v: number, row) => (row.rule_type === 'threshold' ? `${(v * 100).toFixed(1)}%` : `${(v * 100).toFixed(1)}%`),
    },
    { title: '窗口(天)', dataIndex: 'time_window_days' },
    {
      title: '状态',
      dataIndex: 'status',
      render: (v: RuleStatus, row) => (
        <Space>
          <Badge color={RULE_STATUS_TAGS[v]?.color} text={RULE_STATUS_TAGS[v]?.text ?? v} />
          <Button
            size="small"
            onClick={() => onToggleRule(row, row.status === 'active' ? 'paused' : 'active')}
          >
            {row.status === 'active' ? '暂停' : '启用'}
          </Button>
        </Space>
      ),
    },
  ];

  const alertColumns: ColumnsType<Alert> = [
    {
      title: '状态',
      dataIndex: 'status',
      render: (v: AlertStatus, row) => {
        const meta = ALERT_STATUS_TAGS[v] ?? { color: 'default', text: v };
        const next = NEXT_ALERT[row.status];
        return (
          <Space size={4}>
            <Badge color={meta.color} text={meta.text} />
            {next?.length && (
              <Select
                size="small"
                style={{ width: 110 }}
                placeholder="处理"
                value={undefined}
                onChange={(s: AlertStatus) => onAlertTransition(row, s)}
                options={next.map((s) => ({
                  value: s,
                  label: ALERT_STATUS_TAGS[s as AlertStatus]?.text ?? s,
                }))}
              />
            )}
          </Space>
        );
      },
    },
    { title: '规则', dataIndex: 'rule_name' },
    { title: '类型', dataIndex: 'rule_type', render: (v: RuleType) => (v === 'threshold' ? '阈值' : '环比') },
    { title: '属性', dataIndex: 'aspect' },
    { title: 'SKU', dataIndex: 'product_id', render: (v?: string | null) => v ?? '全部' },
    { title: '指标值', dataIndex: 'metric_value', render: (v: number) => (v * 100).toFixed(1) + '%' },
    { title: '触发阈值', dataIndex: 'trigger_value', render: (v: number) => (v * 100).toFixed(1) + '%' },
    { title: '触发时间', dataIndex: 'triggered_at', render: (v: string) => (v ? new Date(v).toLocaleString() : '') },
  ];

  const exportColumns: ColumnsType<ExportRecord> = [
    { title: '数据集版本', dataIndex: 'dataset_version' },
    {
      title: '筛选',
      dataIndex: 'filters',
      render: (f: Record<string, unknown>) => {
        const parts = Object.entries(f ?? {}).filter(([, v]) => v != null && v !== '');
        return parts.length ? parts.map(([k, v]) => `${k}=${v}`).join(' ') : '无';
      },
    },
    { title: '行数', dataIndex: 'row_count' },
    { title: '导出时间', dataIndex: 'created_at', render: (v: string) => (v ? new Date(v).toLocaleString() : '') },
    {
      title: '操作',
      key: 'action',
      render: (_, row) => (
        <Button size="small" type="primary" onClick={() => alertsApi.triggerDownload(row.id)}>
          下载
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><span className="grad-text">告警与导出</span></Title>
      <Paragraph type="secondary">
        当属性差评率超过阈值或环比增长异常时自动触发告警；同时可将筛选后的评论数据导出为 CSV 供离线分析。
      </Paragraph>

      <Tabs
        items={[
          {
            key: 'rules',
            label: '告警规则',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Row justify="end">
                  <Col>
                    <Button type="primary" onClick={() => setCreateOpen(true)}>
                      新建规则
                    </Button>
                  </Col>
                </Row>
                <Table
                  rowKey="id"
                  loading={rulesLoading}
                  columns={ruleColumns}
                  dataSource={rules}
                  pagination={{ current: rulesPage, pageSize: 20, total: rulesTotal,
                    onChange: (p) => setRulesPage(p) }}
                />
              </Space>
            ),
          },
          {
            key: 'alerts',
            label: '告警记录',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Row>
                  <Col>
                    <Text>状态</Text>
                    <Select
                      allowClear
                      placeholder="全部状态"
                      style={{ width: 160, marginLeft: 8 }}
                      value={alertsStatus}
                      onChange={(v) => {
                        setAlertsPage(1);
                        setAlertsStatus(v);
                      }}
                      options={Object.entries(ALERT_STATUS_TAGS).map(([k, v]) => ({ value: k, label: v.text }))}
                    />
                  </Col>
                </Row>
                <Table
                  rowKey="id"
                  loading={alertsLoading}
                  columns={alertColumns}
                  dataSource={alerts}
                  pagination={{ current: alertsPage, pageSize: 20, total: alertsTotal,
                    onChange: (p) => setAlertsPage(p) }}
                />
              </Space>
            ),
          },
          {
            key: 'exports',
            label: '数据导出',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size={16}>
                <Row justify="end">
                  <Col>
                    <Button type="primary" onClick={() => setExportOpen(true)}>
                      导出数据
                    </Button>
                  </Col>
                </Row>
                <Table
                  rowKey="id"
                  loading={exportsLoading}
                  columns={exportColumns}
                  dataSource={exports}
                  pagination={{ current: exportsPage, pageSize: 20, total: exportsTotal,
                    onChange: (p) => setExportsPage(p) }}
                />
              </Space>
            ),
          },
        ]}
      />

      {/* 新建规则 */}
      <Modal
        title="新建告警规则"
        open={createOpen}
        onOk={onCreateRule}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="name" label="规则名" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 电池续航差评率超阈值" />
          </Form.Item>
          <Form.Item name="rule_type" label="类型" rules={[{ required: true, message: '必填' }]}>
            <Select
              options={[
                { value: 'threshold', label: '阈值（差评率超阈值）' },
                { value: 'trend', label: '环比（差评率同比上涨）' },
              ]}
            />
          </Form.Item>
          <Form.Item name="aspect" label="属性" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 电池续航" />
          </Form.Item>
          <Form.Item name="product_id" label="SKU（可选）">
            <Input placeholder="留空表示全部 SKU" />
          </Form.Item>
          <Form.Item name="threshold_value" label="阈值（0~1）" rules={[{ required: true, message: '必填' }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.05} />
          </Form.Item>
          <Form.Item name="time_window_days" label="监控窗口(天)" initialValue={30}>
            <InputNumber style={{ width: '100%' }} min={1} max={365} />
          </Form.Item>
          <Form.Item name="dedup_days" label="去重天数" initialValue={7}>
            <InputNumber style={{ width: '100%' }} min={1} max={365} />
          </Form.Item>
          <Form.Item name="webhook_url" label="Webhook 通知地址（可选）">
            <Input placeholder="如 https://example.com/hook，触发时 POST JSON 通知" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 导出 */}
      <Modal
        title="导出评论数据"
        open={exportOpen}
        onOk={onCreateExport}
        confirmLoading={exporting}
        onCancel={() => setExportOpen(false)}
        destroyOnClose
      >
        <Form form={exportForm} layout="vertical">
          <Form.Item name="dataset_version" label="数据集版本" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 ds-a1b2c3d4" />
          </Form.Item>
          <Form.Item name="product_id" label="SKU（可选）">
            <Input placeholder="留空导出全部" />
          </Form.Item>
          <Form.Item name="sentiment" label="预测情感（可选）">
            <Select
              allowClear
              options={['positive', 'neutral', 'negative'].map((v) => ({ value: v }))}
            />
          </Form.Item>
          <Form.Item name="rating_min" label="最低评分（可选）">
            <InputNumber min={1} max={5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="rating_max" label="最高评分（可选）">
            <InputNumber min={1} max={5} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}