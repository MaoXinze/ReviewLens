import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { getErrorMessage } from '../../api/client';
import type { ReviewSummary, ReviewTask, Sentiment } from '../../api/reviewTasks';
import * as taskApi from '../../api/reviewTasks';

const { Title, Paragraph, Text } = Typography;

const STATUS_TAGS: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'blue', text: '已通过' },
  rejected: { color: 'red', text: '已拒绝' },
  awaiting_second_review: { color: 'purple', text: '待复核' },
  verified: { color: 'green', text: '已复核通过' },
  cancelled: { color: 'default', text: '已取消' },
};

const SENTIMENT_TAGS: Record<string, string> = {
  positive: 'green',
  neutral: 'blue',
  negative: 'red',
};

export default function ReviewTasksPage() {
  const [tasks, setTasks] = useState<ReviewTask[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [current, setCurrent] = useState<ReviewTask | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [secondOpen, setSecondOpen] = useState(false);
  const [secondTarget, setSecondTarget] = useState<ReviewTask | null>(null);
  const [secondForm] = Form.useForm<{ status: 'approved' | 'rejected'; review_note?: string }>();
  const [secondLoading, setSecondLoading] = useState(false);

  const [genForm] = Form.useForm<{ dataset_version: string; count: number }>();
  const [genOpen, setGenOpen] = useState(false);
  const [genLoading, setGenLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const resp = await taskApi.listReviewTasks({
        page,
        page_size: 20,
        status: statusFilter,
      });
      setTasks(resp.items ?? []);
      setTotal(resp.total ?? 0);
    } finally {
      setLoading(false);
    }
  }

  async function loadSummary() {
    try {
      const s = await taskApi.getSummary();
      setSummary(s);
    } catch {
      // 汇总非关键，静默
    }
  }

  async function loadNext() {
    try {
      const t = await taskApi.getNextTask();
      setCurrent(t);
    } catch {
      setCurrent(null);
    }
  }

  useEffect(() => {
    load();
    loadSummary();
    loadNext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter]);

  async function onOpenGenerate() {
    genForm.resetFields();
    setGenOpen(true);
  }

  async function onGenerate() {
    try {
      const values = await genForm.validateFields();
      setGenLoading(true);
      const resp = await taskApi.generateTasks({
        dataset_version: values.dataset_version,
        count: values.count ?? 50,
      });
      message.success(`已生成 ${resp.created} 条任务（跳过 ${resp.skipped}）`);
      setGenOpen(false);
      await load();
      await loadSummary();
      await loadNext();
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '生成失败'));
    } finally {
      setGenLoading(false);
    }
  }

  async function onSubmitDecision(decision: 'approved' | 'rejected') {
    if (!current) return;
    setReviewing(true);
    try {
      const reviewer_sentiment: Sentiment =
        decision === 'approved'
          ? (current.system_sentiment as Sentiment) ?? 'neutral'
          : 'neutral';
      await taskApi.submitReview(current.id, {
        status: decision,
        reviewer_sentiment,
        review_reason: 'confirm_prediction',
      });
      message.success('已提交审核结果');
      await loadNext();
      await loadSummary();
      await load();
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '提交失败'));
    } finally {
      setReviewing(false);
    }
  }

  async function onOpenSecond(task: ReviewTask) {
    setSecondTarget(task);
    secondForm.resetFields();
    setSecondOpen(true);
  }

  async function onSecond() {
    if (!secondTarget) return;
    try {
      const values = await secondForm.validateFields();
      setSecondLoading(true);
      await taskApi.secondReview(secondTarget.id, values);
      message.success('二次复核已完成');
      setSecondOpen(false);
      await load();
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '复核失败'));
    } finally {
      setSecondLoading(false);
    }
  }

  const columns: ColumnsType<ReviewTask> = [
    { title: '任务 ID', dataIndex: 'id', ellipsis: true, width: 230 },
    { title: '数据集', dataIndex: 'dataset_version', ellipsis: true, width: 150 },
    { title: '采样组', dataIndex: 'sampling_group', width: 110 },
    {
      title: '系统情感',
      dataIndex: 'system_sentiment',
      width: 110,
      render: (v: string | null) =>
        v ? <Tag color={SENTIMENT_TAGS[v] ?? 'default'}>{v}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: '审核结果',
      dataIndex: 'status',
      width: 130,
      render: (v: string) => {
        const meta = STATUS_TAGS[v] ?? { color: 'default', text: v };
        return <Tag color={meta.color}>{meta.text}</Tag>;
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, row) => (
        <Space>
          <Button size="small" disabled={row.status !== 'pending'} onClick={() => setCurrent(row)}>
            审核
          </Button>
          {row.status === 'approved' && (
            <Button size="small" onClick={() => onOpenSecond(row)}>
              复核
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><span className="grad-text">人工审核</span></Title>
      <Paragraph type="secondary">
        对 NLP 预测结果进行抽样人工标注。先生成审核任务，再逐条核对系统情感判断，二次复核由分析师确认。
      </Paragraph>

      {/* 汇总统计 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={5}>
          <Card size="small">
            <Statistic title="任务总数" value={summary?.total ?? 0} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="已完成" value={summary?.done ?? 0} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic title="待处理" value={summary?.pending ?? 0} />
          </Card>
        </Col>
        <Col span={9}>
          <Card size="small">
            <div style={{ marginBottom: 4 }}>
              <Text type="secondary">审核覆盖率 {((summary?.completion_rate ?? 0) * 100).toFixed(0)}%</Text>
            </div>
            <Progress percent={Math.round((summary?.completion_rate ?? 0) * 100)} status="active" />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Card
            title="审核工作台"
            extra={
              <Space>
                <Button onClick={loadNext}>下一条</Button>
                <Button type="primary" onClick={onOpenGenerate}>
                  生成任务
                </Button>
              </Space>
            }
          >
            {current ? (
              <Row gutter={16}>
                <Col span={15}>
                  <Card size="small" title="待审核评论">
                    {current.review_title && <Text strong>{current.review_title}</Text>}
                    <div style={{ margin: '8px 0' }}>
                      <Text>{current.review_text ?? '（原文缺失）'}</Text>
                    </div>
                    <Space wrap>
                      {current.rating && <Tag>★{current.rating}</Tag>}
                      <Text type="secondary">review_id: {current.review_id}</Text>
                    </Space>
                  </Card>
                  <div style={{ textAlign: 'center', marginTop: 16 }}>
                    <Space size="large">
                      <Button
                        type="primary"
                        danger
                        loading={reviewing}
                        onClick={() => onSubmitDecision('rejected')}
                      >
                        拒绝（重判）
                      </Button>
                      <Button
                        type="primary"
                        loading={reviewing}
                        onClick={() => onSubmitDecision('approved')}
                      >
                        通过（认同预测）
                      </Button>
                    </Space>
                  </div>
                </Col>
                <Col span={9}>
                  <Card size="small" title="系统预测">
                    <Row gutter={8}>
                      <Col span={12}>
                        <Text type="secondary">情感</Text>
                        <div>
                          <Tag color={SENTIMENT_TAGS[current.system_sentiment ?? ''] ?? 'default'}>
                            {current.system_sentiment ?? '—'}
                          </Tag>
                        </div>
                      </Col>
                      <Col span={12}>
                        <Text type="secondary">置信度</Text>
                        <div style={{ fontSize: 16, fontWeight: 600 }}>
                          {((current.system_confidence ?? 0) * 100).toFixed(0)}%
                        </div>
                      </Col>
                    </Row>
                    {current.system_aspects?.length ? (
                      <div style={{ marginTop: 12 }}>
                        {current.system_aspects.map((a, i) => (
                          <div key={i}>
                            <Text code>{(a as { aspect?: string }).aspect ?? 'aspect'}</Text>
                            <Tag
                              color={SENTIMENT_TAGS[(a as { sentiment?: string }).sentiment ?? ''] ?? 'default'}
                            >
                              {(a as { sentiment?: string }).sentiment ?? '—'}
                            </Tag>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Text type="secondary">无属性预测</Text>
                    )}
                  </Card>
                </Col>
              </Row>
            ) : (
              <Paragraph type="secondary" style={{ textAlign: 'center', margin: 24 }}>
                暂无待审核任务，点击「生成任务」从预测结果抽取。
              </Paragraph>
            )}
          </Card>
        </Col>
      </Row>

      <Row justify="space-between" align="middle" style={{ marginBottom: 8 }}>
        <Space>
          <Text>状态</Text>
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 160 }}
            value={statusFilter}
            onChange={(v) => {
              setPage(1);
              setStatusFilter(v);
            }}
            options={Object.entries(STATUS_TAGS).map(([k, v]) => ({ value: k, label: v.text }))}
          />
        </Space>
      </Row>

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={tasks}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: (p) => setPage(p),
        }}
      />

      {/* 生成任务 */}
      <Modal
        title="生成审核任务"
        open={genOpen}
        onOk={onGenerate}
        confirmLoading={genLoading}
        onCancel={() => setGenOpen(false)}
      >
        <Form form={genForm} layout="vertical">
          <Form.Item
            name="dataset_version"
            label="数据集版本"
            rules={[{ required: true, message: '必填' }]}
          >
            <Input placeholder="如 ds-a1b2c3d4" />
          </Form.Item>
          <Form.Item name="count" label="抽样数量" initialValue={50} rules={[{ required: true }]}>
            <InputNumber min={1} max={5000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 二次复核 */}
      <Modal
        title="二次复核"
        open={secondOpen}
        onOk={onSecond}
        confirmLoading={secondLoading}
        onCancel={() => setSecondOpen(false)}
      >
        {secondTarget && (
          <Card size="small" style={{ marginBottom: 16 }}>
            <Text type="secondary">评论：</Text>
            <Text>{secondTarget.review_text ?? '（原文缺失）'}</Text>
          </Card>
        )}
        <Form form={secondForm} layout="vertical">
          <Form.Item name="status" label="复核结论" rules={[{ required: true }]}>
            <Radio.Group
              options={[
                { value: 'approved', label: '通过' },
                { value: 'rejected', label: '驳回' },
              ]}
            />
          </Form.Item>
          <Form.Item name="review_note" label="复核说明">
            <Input.TextArea rows={3} placeholder="复核意见" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}