import { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';

import { getErrorMessage } from '../../api/client';
import type {
  Issue,
  IssueStatus,
  RetrospectResult,
  Severity,
} from '../../api/issues';
import * as issueApi from '../../api/issues';
import * as datasetApi from '../../api/datasets';
import type { DatasetReview } from '../../api/datasets';

const { Title, Paragraph, Text } = Typography;

const STATUS_TAGS: Record<string, { color: string; text: string }> = {
  open: { color: 'orange', text: '待处置' },
  in_progress: { color: 'processing', text: '处置中' },
  pending_validation: { color: 'purple', text: '待验证' },
  closed: { color: 'success', text: '已关闭' },
};

const SEVERITY_TAGS: Record<string, string> = {
  low: 'green',
  medium: 'blue',
  high: 'orange',
  critical: 'red',
};

// 依据状态机定义当前状态可推进的目标状态
const NEXT_STATUS: Record<IssueStatus, IssueStatus[] | null> = {
  open: ['in_progress'],
  in_progress: ['open', 'pending_validation'],
  pending_validation: ['in_progress', 'closed'],
  closed: null, // 终态
};

interface IssueCreateForm {
  dataset_version: string;
  title: string;
  aspect: string;
  severity: Severity;
  source_review_ids: string[];
  description?: string;
}

export default function IssuesPage() {
  const [issues, setIssues] = useState<Issue[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const [datasets, setDatasets] = useState<datasetApi.Dataset[]>([]);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm<IssueCreateForm>();
  const [creating, setCreating] = useState(false);

  // 来源评论多选
  const [reviewPickerOpen, setReviewPickerOpen] = useState(false);
  const [reviewOptions, setReviewOptions] = useState<DatasetReview[]>([]);
  const [reviewTotal, setReviewTotal] = useState(0);
  const [reviewPage, setReviewPage] = useState(1);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [selectedReviewIds, setSelectedReviewIds] = useState<string[]>([]);

  // 处置/验证流转弹窗
  const [transitionTarget, setTransitionTarget] = useState<Issue | null>(null);
  const [transitionForm] = Form.useForm<{ note?: string }>();
  const [transitionOpen, setTransitionOpen] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  const [detail, setDetail] = useState<issueApi.IssueDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const [retrospect, setRetrospect] = useState<RetrospectResult | null>(null);
  const [retrospectOpen, setRetrospectOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const resp = await issueApi.listIssues({
        page,
        page_size: 20,
        status: statusFilter,
      });
      setIssues(resp.items ?? []);
      setTotal(resp.total ?? 0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, statusFilter]);

  // 加载数据集选项（创建表单下拉用）
  useEffect(() => {
    datasetApi
      .listDatasets({ page: 1, page_size: 100 })
      .then((resp) => setDatasets(resp.items ?? []))
      .catch(() => setDatasets([]));
  }, []);

  async function onOpenCreate() {
    createForm.resetFields();
    setSelectedReviewIds([]);
    setCreateOpen(true);
  }

  const loadReviews = useCallback(async (version: string, p: number) => {
    setReviewLoading(true);
    try {
      const resp = await datasetApi.listDatasetReviews(version, {
        page: p,
        page_size: 50,
      });
      setReviewOptions(resp.items ?? []);
      setReviewTotal(resp.total ?? 0);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '加载评论失败'));
      setReviewOptions([]);
    } finally {
      setReviewLoading(false);
    }
  }, []);

  // 打开评论选择器，拉取当前数据集的前 50 条评论
  const openReviewPicker = useCallback(async () => {
    const version = createForm.getFieldValue('dataset_version');
    if (!version) {
      message.warning('请先选择数据集版本');
      return;
    }
    setReviewPickerOpen(true);
    setReviewPage(1);
    await loadReviews(version, 1);
  }, [createForm, loadReviews]);

  async function onCreate() {
    try {
      const values = await createForm.validateFields();
      setCreating(true);
      await issueApi.createIssue({
        ...values,
        source_review_ids: values.source_review_ids ?? [],
      });
      message.success('问题卡已创建');
      setCreateOpen(false);
      createForm.resetFields();
      await load();
    } catch (e: unknown) {
      if ((e as { response?: object })?.response) {
        message.error(getErrorMessage(e, '创建失败'));
      }
      // 表单校验失败不提示
    } finally {
      setCreating(false);
    }
  }

  async function onTransition(issue: Issue, status: IssueStatus) {
    // closed 需填验证结论；open→in_progress 需填处置说明
    if (status === 'closed' || (status === 'in_progress' && issue.status === 'open')) {
      setTransitionTarget(issue);
      transitionForm.resetFields();
      setTransitionOpen(true);
      return;
    }
    // 其余流转直接执行（加轻量确认）
    Modal.confirm({
      title: '确认流转状态',
      content: `确定将问题卡「${issue.title}」流转为「${STATUS_TAGS[status]?.text ?? status}」吗？`,
      okText: '确认',
      cancelText: '取消',
      onOk: () => doTransition(issue, status),
    });
  }

  async function doTransition(issue: Issue, status: IssueStatus, note?: string) {
    try {
      const body: issueApi.IssueUpdatePayload =
        status === 'closed'
          ? { status, validation_note: note }
          : status === 'in_progress'
            ? { status, resolution_note: note }
            : { status };
      await issueApi.updateIssue(issue.id, body);
      message.success(`已流转到 ${STATUS_TAGS[status]?.text ?? status}`);
      await load();
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '流转失败'));
    }
  }

  async function onTransitionSubmit() {
    if (!transitionTarget) return;
    try {
      const values = await transitionForm.validateFields();
      setTransitioning(true);
      const targetStatus = transitionTarget.status === 'pending_validation' ? 'closed' : 'in_progress';
      await doTransition(transitionTarget, targetStatus, values.note);
      setTransitionOpen(false);
    } catch (e: unknown) {
      if ((e as { response?: object })?.response) {
        message.error(getErrorMessage(e, '流转失败'));
      }
    } finally {
      setTransitioning(false);
    }
  }

  async function onShowDetail(issue: Issue) {
    try {
      const detail = await issueApi.getIssue(issue.id);
      setDetail(detail);
      setDetailOpen(true);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '加载详情失败'));
    }
  }

  async function onRetrospect(issue: Issue) {
    try {
      const result = await issueApi.retrospectIssue(issue.id);
      setRetrospect(result);
      setRetrospectOpen(true);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '回测失败'));
    }
  }

  const columns: ColumnsType<Issue> = [
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (v: string, row) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => onShowDetail(row)}>
          {v}
        </Button>
      ),
    },
    { title: '数据集版本', dataIndex: 'dataset_version', ellipsis: true },
    { title: '属性', dataIndex: 'aspect' },
    {
      title: '严重度',
      dataIndex: 'severity',
      render: (v: Severity) => <Tag color={SEVERITY_TAGS[v]}>{v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      render: (v: IssueStatus, row) => {
        const meta = STATUS_TAGS[v] ?? { color: 'default', text: v };
        const next = NEXT_STATUS[row.status];
        return (
          <Space size={4}>
            <Badge color={meta.color} text={meta.text} />
            {next?.length && (
              <Select
                size="small"
                style={{ width: 150 }}
                placeholder="推进状态"
                value={undefined}
                onChange={(s: IssueStatus) => onTransition(row, s)}
                options={next.map((s) => ({ value: s, label: STATUS_TAGS[s as IssueStatus]?.text ?? s }))}
              />
            )}
          </Space>
        );
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => onShowDetail(row)}>详情</Button>
          <Button size="small" disabled={row.status !== 'closed'} onClick={() => onRetrospect(row)}>
            回测
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><span className="grad-text">问题卡管理</span></Title>
      <Paragraph type="secondary">
        将看板洞察转化为可追踪的改进行动。问题卡从看板创建，分派处置，验证通过后关闭，可做创建前后差评率回测。
      </Paragraph>

      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
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
        </Col>
        <Col>
          <Button type="primary" onClick={onOpenCreate}>
            新建问题卡
          </Button>
        </Col>
      </Row>

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={issues}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: (p) => setPage(p),
        }}
      />

      {/* 新建问题卡 */}
      <Modal
        title="新建问题卡"
        open={createOpen}
        onOk={onCreate}
        confirmLoading={creating}
        onCancel={() => setCreateOpen(false)}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical">
          <Form.Item name="dataset_version" label="数据集版本" rules={[{ required: true, message: '必填' }]}>
            <Select
              showSearch
              placeholder="选择数据集版本"
              optionFilterProp="label"
              options={datasets.map((d) => ({ value: d.dataset_version, label: d.dataset_version }))}
            />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 电池续航差评集中" />
          </Form.Item>
          <Form.Item name="aspect" label="属性" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="如 电池续航" />
          </Form.Item>
          <Form.Item name="severity" label="严重度" rules={[{ required: true, message: '必填' }]}>
            <Select
              placeholder="选择严重度"
              options={(['low', 'medium', 'high', 'critical'] as Severity[]).map((v) => ({ value: v }))}
            />
          </Form.Item>
          <Form.Item name="source_review_ids" label="来源评论" rules={[{ required: true, message: '请选择来源评论' }]}>
            <div>
              <Button onClick={openReviewPicker}>选择来源评论</Button>
              <div style={{ marginTop: 8 }}>
                {(selectedReviewIds.length > 0) && (
                  <Text type="secondary">已选 {selectedReviewIds.length} 条评论</Text>
                )}
              </div>
            </div>
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="问题描述" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 来源评论选择器 */}
      <Modal
        title="选择来源评论"
        open={reviewPickerOpen}
        onCancel={() => setReviewPickerOpen(false)}
        width={720}
        footer={
          <Space>
            <Button onClick={() => setReviewPickerOpen(false)}>取消</Button>
            <Button
              type="primary"
              disabled={selectedReviewIds.length === 0}
              onClick={() => {
                createForm.setFieldValue('source_review_ids', selectedReviewIds);
                setReviewPickerOpen(false);
              }}
            >
              确认选择（{selectedReviewIds.length}）
            </Button>
          </Space>
        }
      >
        <Table<DatasetReview>
          rowKey="review_id"
          size="small"
          loading={reviewLoading}
          dataSource={reviewOptions}
          pagination={{
            current: reviewPage,
            pageSize: 50,
            total: reviewTotal,
            onChange: (p) => {
              setReviewPage(p);
              loadReviews(createForm.getFieldValue('dataset_version'), p);
            },
          }}
          rowSelection={{
            selectedRowKeys: selectedReviewIds,
            onChange: (keys) => setSelectedReviewIds(keys as string[]),
          }}
          columns={[
            { title: '评论 ID', dataIndex: 'review_id', width: 200, ellipsis: true },
            { title: '评分', dataIndex: 'rating', width: 60 },
            {
              title: '内容',
              dataIndex: 'review_text',
              ellipsis: true,
            },
            { title: '时间', dataIndex: 'reviewed_at', width: 110 },
          ]}
        />
      </Modal>

      {/* 处置/验证流转 */}
      <Modal
        title={
          transitionTarget?.status === 'pending_validation'
            ? '验证并关闭问题卡'
            : '填写处置说明'
        }
        open={transitionOpen}
        onOk={onTransitionSubmit}
        confirmLoading={transitioning}
        onCancel={() => setTransitionOpen(false)}
      >
        <Form form={transitionForm} layout="vertical">
          <Form.Item
            name="note"
            label={
              transitionTarget?.status === 'pending_validation' ? '验证结论' : '处置说明'
            }
            rules={[{ required: true, message: '必填' }]}
          >
            <Input.TextArea rows={3} placeholder={transitionTarget?.status === 'pending_validation' ? '验证结论' : '处置说明'} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情 */}
      <Modal
        title="问题卡详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={640}
      >
        {detail && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Title level={4}>{detail.issue.title}</Typography.Title>
            <Space wrap>
              <Tag color={SEVERITY_TAGS[detail.issue.severity]}>{detail.issue.severity}</Tag>
              <Badge
                color={STATUS_TAGS[detail.issue.status]?.color}
                text={STATUS_TAGS[detail.issue.status]?.text ?? detail.issue.status}
              />
              <Text type="secondary">属性：{detail.issue.aspect}</Text>
            </Space>
            <Text>数据集：{detail.issue.dataset_version}</Text>
            <Text>来源评论：{(detail.issue.source_review_ids ?? []).join(', ')}</Text>
            {detail.issue.resolution_note && <Text>处置说明：{detail.issue.resolution_note}</Text>}
            {detail.issue.validation_note && <Text>验证结论：{detail.issue.validation_note}</Text>}
            <Card size="small" title="审计轨迹">
              {detail.history.length === 0 && <Text type="secondary">暂无记录</Text>}
              {detail.history.map((h, i) => (
                <div key={i} style={{ padding: '2px 0' }}>
                  <Text code>{h.field_name}</Text>
                  <Text> {h.old_value ?? '—'} → </Text>
                  <Text strong>{h.new_value ?? '—'}</Text>
                  <Text type="secondary"> · {h.reason ?? ''}</Text>
                </div>
              ))}
            </Card>
          </Space>
        )}
      </Modal>

      {/* 回测 */}
      <Modal
        title="效果回测"
        open={retrospectOpen}
        onCancel={() => setRetrospectOpen(false)}
        footer={null}
      >
        {retrospect && (
          <Row gutter={16}>
            <Col span={8}>
              <Card>
                <StatisticBlock label="创建前差评率" value={retrospect.pre_rate} />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <StatisticBlock label="当前差评率" value={retrospect.post_rate} />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <StatisticBlock
                  label="变化"
                  value={retrospect.change}
                  color={retrospect.improved ? 'green' : 'red'}
                  extra={retrospect.improved ? '改善' : '恶化'}
                />
              </Card>
            </Col>
          </Row>
        )}
      </Modal>
    </div>
  );
}

function StatisticBlock({
  label,
  value,
  color,
  extra,
}: {
  label: string;
  value: number;
  color?: string;
  extra?: string;
}) {
  return (
    <div style={{ textAlign: 'center' }}>
      <Text type="secondary">{label}</Text>
      <div style={{ fontSize: 24, fontWeight: 600, color: color ?? 'inherit' }}>
        {value.toFixed(4)}
      </div>
      {extra && <Tag color={color}>{extra}</Tag>}
    </div>
  );
}
