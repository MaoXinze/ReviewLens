import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Modal,
  message,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { getErrorMessage } from '../../api/client';
import type { AnalysisRun, ModelInfo, PublishCriteria } from '../../api/models';
import * as modelApi from '../../api/models';
import { usePolling } from '../../hooks/usePolling';

const { Title, Paragraph } = Typography;

const PUBLISH_COLORS: Record<string, string> = {
  evaluation_only: 'default',
  published: 'green',
  archived: 'orange',
};
const STATUS_TAGS: Record<string, string> = {
  succeeded: 'success',
  running: 'processing',
  failed: 'error',
  queued: 'default',
};

export default function ModelsPage() {
  const [current, setCurrent] = useState<ModelInfo | null>(null);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [criteriaMap, setCriteriaMap] = useState<Record<string, PublishCriteria>>({});

  async function load() {
    setLoading(true);
    try {
      const [history, cur, runsResp] = await Promise.all([
        modelApi.listModelHistory(),
        modelApi.getCurrentModel(),
        modelApi.listAnalysisRuns({ page, page_size: 20 }),
      ]);
      setRuns(runsResp.items ?? history.items ?? []);
      setTotal(runsResp.total ?? history.total ?? 0);
      setCurrent(cur);
    } finally {
      setLoading(false);
    }
  }

  async function loadCriteria(runId: string) {
    try {
      const c = await modelApi.getPublishCriteria(runId);
      setCriteriaMap((m) => ({ ...m, [runId]: c }));
    } catch {
      /* 门槛接口失败不阻断列表 */
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // 存在运行中/排队中的训练时，每 5s 轮询直到全部落定
  const hasRunning = runs.some((r) => r.status === 'running' || r.status === 'queued');
  usePolling(load, 5000, hasRunning);

  async function onPublish(run: AnalysisRun) {
    Modal.confirm({
      title: '确认发布模型',
      content: `确定将模型 ${run.model_version || run.id} 发布为生产模型吗？发布后该模型将用于线上推理。`,
      okText: '确认发布',
      cancelText: '取消',
      onOk: async () => {
        try {
          const resp = await modelApi.publishModel(run.id);
          message.success(resp.message || '发布成功');
          await load();
        } catch (e: unknown) {
          message.error(getErrorMessage(e, '发布失败'));
        }
      },
    });
  }

  async function onRollback(run: AnalysisRun) {
    Modal.confirm({
      title: '确认回滚模型',
      content: `确定回滚到 ${run.model_version || run.id} 吗？回滚后该模型将替换当前生产模型。`,
      okText: '确认回滚',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const resp = await modelApi.rollbackModel(run.id);
          message.success(resp.message || '回滚成功');
          await load();
        } catch (e: unknown) {
          message.error(getErrorMessage(e, '回滚失败'));
        }
      },
    });
  }

  const columns: ColumnsType<AnalysisRun> = [
    {
      title: '模型版本',
      dataIndex: 'model_version',
      render: (v: string, row) => (
        <Space>
          <Typography.Text code>{v || '-'}</Typography.Text>
          {row.publish_status === 'published' && <Badge status="success" text="生产" />}
        </Space>
      ),
    },
    { title: '数据集版本', dataIndex: 'dataset_version' },
    {
      title: '算法',
      dataIndex: 'algorithm',
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Macro-F1',
      dataIndex: 'macro_f1',
      sorter: (a, b) => (a.macro_f1 ?? -1) - (b.macro_f1 ?? -1),
      render: (v: number | null) => (v ?? '-'),
    },
    {
      title: '测试样本',
      dataIndex: 'test_samples',
      sorter: (a, b) => a.test_samples - b.test_samples,
    },
    {
      title: '状态',
      dataIndex: 'status',
      render: (v: string) => <Badge status={(STATUS_TAGS[v] as 'success') ?? 'default'} text={v} />,
    },
    {
      title: '发布状态',
      dataIndex: 'publish_status',
      render: (v: string) => <Tag color={PUBLISH_COLORS[v]}>{v}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, row) => {
        const criteria = criteriaMap[row.id];
        const gates = [
          (criteria?.macro_f1_ok ?? true) && (criteria?.test_samples_ok ?? true) && (criteria?.coverage_ok ?? true),
        ][0];
        const publishable = row.status === 'succeeded' && criteria?.can_publish !== false && gates;
        return (
          <Space>
            <Button
              size="small"
              onClick={() => loadCriteria(row.id)}
            >
              检查门槛
            </Button>
            <Button
              size="small"
              type="primary"
              disabled={!publishable}
              onClick={() => onPublish(row)}
            >
              发布
            </Button>
            <Button size="small" danger disabled={row.publish_status !== 'published'} onClick={() => onRollback(row)}>
              回滚
            </Button>
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><span className="grad-text">模型训练与评测</span></Title>
      <Paragraph type="secondary">管理模型发布、回滚与版本历史。发布需同时满足 F1≥0.70、测试样本≥1000、审核覆盖率≥80%。</Paragraph>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic title="当前生产模型" value={current?.model_version ?? '—'} valueStyle={{ fontSize: 18 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="算法" value={current?.algorithm ?? '—'} valueStyle={{ fontSize: 18 }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="Macro-F1" value={current?.macro_f1 ?? '—'} valueStyle={{ fontSize: 18 }} precision={4} />
          </Card>
        </Col>
      </Row>

      {current?.publish_status === 'no_model' && (
        <Alert type="info" showIcon style={{ marginBottom: 16 }} message="尚未发布任何模型" description="完成训练并通过门槛后即可发布。" />
      )}

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={runs}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: (p) => setPage(p),
        }}
      />
    </div>
  );
}