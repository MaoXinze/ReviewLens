import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Modal,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import type { RcFile } from 'antd/es/upload';
import type { ColumnsType } from 'antd/es/table';

import { getErrorMessage } from '../../api/client';
import type { Dataset, QualityReport } from '../../api/datasets';
import * as datasetApi from '../../api/datasets';
import { usePolling } from '../../hooks/usePolling';

const { Title, Paragraph } = Typography;

const STATUS_TAGS: Record<string, { color: string; text: string }> = {
  processing: { color: 'processing', text: '导入中' },
  queued: { color: 'default', text: '排队中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
  reused: { color: 'blue', text: '复用缓存' },
};

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const [reportVersion, setReportVersion] = useState<string | null>(null);
  const [report, setReport] = useState<QualityReport | null>(null);
  const [reportOpen, setReportOpen] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const resp = await datasetApi.listDatasets({ page, page_size: 20 });
      setDatasets(resp.items ?? []);
      setTotal(resp.total ?? 0);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  // 存在导入中的数据集时，每 5s 轮询列表直到全部落定
  const hasRunning = datasets.some((d) => d.status === 'queued' || d.status === 'processing');
  usePolling(load, 5000, hasRunning);

  async function onUpload(file: RcFile): Promise<boolean> {
    try {
      const result = await datasetApi.importDataset(file);
      if (result.status === 'queued' || result.status === 'processing') {
        message.info(`导入任务已提交：${result.dataset_version ?? result.message}`);
      } else {
        message.success(result.message);
      }
      setTimeout(load, 800);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '导入失败'));
    }
    return false; // 阻止 antd 默认上传动作，我们手动发送
  }

  async function onShowReport(dataset: Dataset) {
    try {
      const qr = await datasetApi.getQualityReport(dataset.dataset_version);
      setReport(qr);
      setReportVersion(dataset.dataset_version);
      setReportOpen(true);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '加载质量报告失败'));
    }
  }

  const columns: ColumnsType<Dataset> = [
    { title: '数据集版本', dataIndex: 'dataset_version', ellipsis: true },
    { title: '源文件', dataIndex: 'source_filename', ellipsis: true },
    { title: '总行数', dataIndex: 'total_rows', width: 90, sorter: (a, b) => a.total_rows - b.total_rows },
    { title: '有效行', dataIndex: 'valid_rows', width: 90, sorter: (a, b) => a.valid_rows - b.valid_rows },
    { title: '拒绝行', dataIndex: 'rejected_rows', width: 90, sorter: (a, b) => a.rejected_rows - b.rejected_rows },
    { title: '文件 SHA256', dataIndex: 'file_sha256', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: string) => {
        const meta = STATUS_TAGS[v] ?? { color: 'default', text: v };
        return <Tag color={meta.color}>{meta.text}</Tag>;
      },
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, row) => (
        <Button size="small" disabled={row.rejected_rows > 0} onClick={() => onShowReport(row)}>
          质量报告
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><span className="grad-text">数据导入</span></Title>
      <Paragraph type="secondary">
        上传 Amazon Reviews 2023 的 CSV/JSONL 评论文件触发异步导入。系统会对文件做格式校验、按数据集去重并生成质量报告。
      </Paragraph>

      <Card style={{ marginBottom: 16 }}>
        <Upload.Dragger accept=".csv,.jsonl,.json" multiple={false} beforeUpload={onUpload}>
          <p style={{ fontSize: 16 }}>点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint">支持 CSV / JSONL / JSON，单文件上传</p>
        </Upload.Dragger>
      </Card>

      <Table
        rowKey="dataset_version"
        loading={loading}
        columns={columns}
        dataSource={datasets}
        pagination={{
          current: page,
          pageSize: 20,
          total,
          onChange: (p) => setPage(p),
        }}
      />

      {/* 质量报告 */}
      <Modal
        title={`质量报告 — ${reportVersion ?? ''}`}
        open={reportOpen}
        onCancel={() => setReportOpen(false)}
        footer={null}
        width={640}
      >
        {report && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Row gutter={16}>
              <Col span={12}>
                <Card size="small">
                  <Statistic title="拒绝原因分类" value={Object.keys(report.rejection_reasons ?? {}).length} suffix="类" />
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small">
                  <Statistic title="拒绝总条数" value={Object.values(report.rejection_reasons ?? {}).reduce((a, b) => a + b, 0)} />
                </Card>
              </Col>
            </Row>
            {Object.entries(report.rejection_reasons ?? {}).map(([reason, count]) => (
              <Card key={reason} size="small" title={`${reason}（${count} 条）`}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  {(report.reasons_detail?.[reason] ?? []).slice(0, 10).map((sample, i) => (
                    <Descriptions key={i} size="small" column={1}>
                      <Descriptions.Item>{sample}</Descriptions.Item>
                    </Descriptions>
                  ))}
                  {(report.reasons_detail?.[reason] ?? []).length === 0 && (
                    <Typography.Text type="secondary">无样例</Typography.Text>
                  )}
                </Space>
              </Card>
            ))}
          </Space>
        )}
      </Modal>
    </div>
  );
}