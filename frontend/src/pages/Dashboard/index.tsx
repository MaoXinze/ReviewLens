import { useEffect, useState } from 'react';
import { Button, Card, Col, Input, Progress, Row, Select, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Pie } from '@ant-design/charts';
import { Link } from 'react-router-dom';
import * as insightApi from '../../api/insights';
import type { AspectRate, InsightOverView, SentimentBucket } from '../../api/insights';
import PageHeader from '../../components/PageHeader';
import { IconAlert, IconCheckCircle, IconDatabase, IconModel } from '../../components/icons';

const SENTIMENT_COLORS: Record<string, string> = {
  positive: '#52c41a',
  neutral: '#faad14',
  negative: '#ff4d4f',
};

export default function DashboardPage() {
  const [datasets, setDatasets] = useState<insightApi.DatasetOption[]>([]);
  const [datasetVersion, setDatasetVersion] = useState<string>('');
  const [productId, setProductId] = useState<string>('');
  const [overview, setOverview] = useState<InsightOverView | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    insightApi.listDatasets({ page: 1, page_size: 100 }).then((resp) => {
      const items = resp.items ?? [];
      setDatasets(items);
      if (items.length > 0 && !datasetVersion) setDatasetVersion(items[0].dataset_version);
    }).catch(() => setDatasets([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!datasetVersion) return;
    setLoading(true);
    insightApi.getOverview({ dataset_version: datasetVersion, product_id: productId || undefined })
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setLoading(false));
  }, [datasetVersion, productId]);

  const sentimentData: SentimentBucket[] = overview?.sentiment_distribution ?? [];

  const distribution = sentimentData.slice().sort((a, b) => b.doc_count - a.doc_count);

  const pieData = distribution.map((d) => ({
    type: d.overall_sentiment,
    value: d.doc_count,
  }));

  const pieConfig = {
    data: pieData,
    angleField: 'value',
    colorField: 'type',
    height: 220,
    // G2 v5 用 scale.color.range 按数据顺序映射情感色（顶层 color 属性会被忽略）
    scale: {
      color: {
        range: distribution.map((d) => SENTIMENT_COLORS[d.overall_sentiment] ?? '#999'),
      },
    },
    legend: { color: { position: 'bottom' } },
  } as unknown as Record<string, unknown>;

  const aspectColumns: ColumnsType<AspectRate> = [
    { title: '属性', dataIndex: 'aspect' },
    { title: '评论数', dataIndex: 'total' },
    { title: '差评数', dataIndex: 'negative' },
    {
      title: '差评率',
      dataIndex: 'negative_rate',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
  ];

  const dp = overview?.review_progress;

  const statCards = [
    {
      label: '评论量',
      value: (overview?.total_reviews ?? 0).toLocaleString(),
      color: '#1677ff',
      icon: <IconDatabase size={15} />,
    },
    {
      label: '审核完成率',
      value: dp ? `${(dp.completion_rate * 100).toFixed(1)}%` : '—',
      color: '#389e0d',
      icon: <IconCheckCircle size={15} />,
    },
    {
      label: '审核一致率',
      value: dp ? `${(dp.agreement_rate * 100).toFixed(1)}%` : '—',
      color: '#d48806',
      icon: <IconAlert size={15} />,
    },
    {
      label: '生产模型',
      value: overview?.model_version ?? '—',
      color: '#7c3aed',
      icon: <IconModel size={15} />,
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title="体验总览"
        description="3 分钟定位当前最严重的体验问题，每个数字可下钻到证据评论。"
        extra={
          <>
            <Select
              style={{ width: 240 }}
              value={datasetVersion || undefined}
              placeholder="选择数据集版本"
              onChange={setDatasetVersion}
              options={datasets.map((d) => ({ label: d.dataset_version, value: d.dataset_version }))}
            />
            <Input.Search
              placeholder="按商品 ID 筛选（可选）"
              allowClear
              style={{ width: 220 }}
              onSearch={(v) => setProductId(v.trim())}
            />
          </>
        }
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 14,
          marginBottom: 16,
        }}
      >
        {statCards.map((s) => (
          <div key={s.label} className="stat-card">
            <div className="stat-label">
              <span style={{ color: s.color, display: 'inline-flex', alignItems: 'center' }}>{s.icon}</span>
              <span>{s.label}</span>
            </div>
            <div className="stat-value" style={{ color: s.color }}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      <Row gutter={16}>
        <Col span={8}>
          <Card className="glass-card" title="情感分布" loading={loading}>
            {pieData.length > 0 ? (
              <Pie {...pieConfig} />
            ) : (
              <Typography.Text type="secondary">暂无数据</Typography.Text>
            )}
          </Card>
        </Col>
        <Col span={8}>
          <Card className="glass-card" title="情感占比" loading={loading}>
            {distribution.map((d) => (
              <div key={d.overall_sentiment} style={{ marginBottom: 12 }}>
                <div style={{ marginBottom: 4 }}>
                  {d.overall_sentiment}
                  <span style={{ float: 'right' }}>{(d.ratio * 100).toFixed(1)}%</span>
                </div>
                <Progress
                  percent={d.ratio * 100}
                  showInfo={false}
                  strokeColor={SENTIMENT_COLORS[d.overall_sentiment]}
                />
              </div>
            ))}
          </Card>
        </Col>
        <Col span={8}>
          <Card
            className="glass-card"
            title="差评属性 TOP5"
            loading={loading}
            extra={
              <Link to="/insights">
                <Button type="link" size="small">
                  排行详情
                </Button>
              </Link>
            }
          >
            <Table
              rowKey="aspect"
              size="small"
              pagination={false}
              columns={aspectColumns}
              dataSource={overview?.top_negative_aspects ?? []}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}