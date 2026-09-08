import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

import { getErrorMessage } from '../../api/client';
import type { SearchHit, SearchResponse, SortBy } from '../../api/reviews';
import * as reviewApi from '../../api/reviews';
import { IconSearch, IconSpark } from '../../components/icons';

const { Title, Paragraph, Text } = Typography;

const SENTIMENT_TAGS: Record<string, string> = {
  positive: 'green',
  neutral: 'blue',
  negative: 'red',
};

const SUGGESTED_QUERIES = ['电池续航', 'shipping badly', 'battery life', 'screen'];

interface SearchFormValues {
  query?: string;
  dataset_version?: string;
  rating_min?: number;
  rating_max?: number;
  overall_sentiment?: string;
  date_from?: dayjs.Dayjs;
  date_to?: dayjs.Dayjs;
}

// ES 高亮用 <em> 包裹命中词；先转义全文再去掉 JSX 无关标签，避免 XSS
function escapeHtml(s: string) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderHighlight(hit: SearchHit) {
  if (hit.highlight && hit.highlight.length) {
    return (
      <div>
        <Text type="secondary">摘要：</Text>
        {hit.highlight.map((hl, i) => (
          <span
            key={i}
            dangerouslySetInnerHTML={{
              __html: (
                i < hit.highlight.length - 1 ? `${escapeHtml(hl)}…` : escapeHtml(hl)
              ).replace(/&lt;em&gt;/g, '<em>').replace(/&lt;\/em&gt;/g, '</em>'),
            }}
          />
        ))}
      </div>
    );
  }
  return <Text>{hit.review_text}</Text>;
}

export default function SearchPage() {
  const [form] = Form.useForm<SearchFormValues>();
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [tookMs, setTookMs] = useState(0);
  const [sortBy, setSortBy] = useState<SortBy>('relevance');
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  async function doSearch(resetPage = false) {
    const values = form.getFieldsValue();
    const body = {
      query: values.query ?? '',
      sort_by: sortBy,
      page: resetPage ? 1 : page,
      page_size: 10,
      filters: {
        dataset_version: values.dataset_version || null,
        rating_min: values.rating_min ?? null,
        rating_max: values.rating_max ?? null,
        overall_sentiment: values.overall_sentiment || null,
        date_from: values.date_from ? values.date_from.format('YYYY-MM-DD') : null,
        date_to: values.date_to ? values.date_to.format('YYYY-MM-DD') : null,
      },
    };
    if (resetPage && page !== 1) {
      setPage(1);
    }
    setLoading(true);
    try {
      const resp: SearchResponse = await reviewApi.searchReviews(body);
      setHits(resp.items ?? []);
      setTotal(resp.total ?? 0);
      setTookMs(resp.took_ms ?? 0);
      setSearched(true);
    } catch (e: unknown) {
      message.error(getErrorMessage(e, '搜索失败（可能 ES 未就绪）'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (searched) {
      doSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, sortBy]);

  function applySuggestion(q: string) {
    form.setFieldsValue({ query: q });
    doSearch(true);
  }

  const columns: ColumnsType<SearchHit> = [
    {
      title: '评论内容',
      dataIndex: 'review_text',
      render: (_, hit) => (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          {hit.review_title && <Text strong>{hit.review_title}</Text>}
          {renderHighlight(hit)}
          <Space size={8} wrap>
            <Text type="secondary">ID: {hit.review_id}</Text>
            {hit.rating && <Tag color={hit.rating >= 4 ? 'green' : hit.rating === 3 ? 'gold' : 'red'}>★{hit.rating}</Tag>}
            {hit.overall_sentiment && (
              <Tag color={SENTIMENT_TAGS[hit.overall_sentiment] ?? 'default'}>
                {hit.overall_sentiment}
              </Tag>
            )}
            {hit.verified_purchase && <Tag>已购</Tag>}
            {hit.helpful_votes > 0 && <Text type="secondary">有用 {hit.helpful_votes}</Text>}
          </Space>
        </Space>
      ),
    },
    { title: '产品 ID', dataIndex: 'product_id', width: 130, ellipsis: true },
    { title: '时间', dataIndex: 'reviewed_at', width: 150 },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Title level={3}><span className="grad-text">评论搜索</span></Title>
      <Paragraph type="secondary">
        基于 Elasticsearch 的 IK 中文分词全文检索，支持评分、时间、情感等过滤条件，结果带关键词高亮。
      </Paragraph>

      {/* 筛选区（玻璃卡片） */}
      <Card className="glass-card" style={{ marginBottom: 16 }}>
        <Form
          form={form}
          layout="inline"
          onFinish={() => doSearch(true)}
          style={{ display: 'flex', flexWrap: 'wrap', gap: 12, rowGap: 16 }}
        >
          <Form.Item name="query" label="关键词" style={{ marginBottom: 0, minWidth: 210 }}>
            <Input placeholder="如：电池续航、shipping badly" allowClear style={{ width: 210 }} />
          </Form.Item>
          <Form.Item name="dataset_version" label="数据集" style={{ marginBottom: 0 }}>
            <Input placeholder="datasets 版本号" style={{ width: 170 }} allowClear />
          </Form.Item>
          <Form.Item name="overall_sentiment" label="情感" style={{ marginBottom: 0 }}>
            <Select
              allowClear
              placeholder="全部"
              style={{ width: 120 }}
              options={Object.keys(SENTIMENT_TAGS).map((v) => ({ value: v }))}
            />
          </Form.Item>
          <Form.Item label="评分" style={{ marginBottom: 0 }}>
            <Space.Compact>
              <Form.Item name="rating_min" noStyle>
                <InputNumber min={1} max={5} placeholder="最低" style={{ width: 74 }} />
              </Form.Item>
              <span style={{ padding: '0 8px', color: 'var(--rl-text-faint)', display: 'inline-flex', alignItems: 'center' }}>~</span>
              <Form.Item name="rating_max" noStyle>
                <InputNumber min={1} max={5} placeholder="最高" style={{ width: 74 }} />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item label="时间" style={{ marginBottom: 0 }}>
            <Space.Compact>
              <Form.Item name="date_from" noStyle>
                <DatePicker placeholder="开始" />
              </Form.Item>
              <span style={{ padding: '0 8px', color: 'var(--rl-text-faint)', display: 'inline-flex', alignItems: 'center' }}>~</span>
              <Form.Item name="date_to" noStyle>
                <DatePicker placeholder="结束" />
              </Form.Item>
            </Space.Compact>
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, marginLeft: 'auto' }}>
            <Button type="primary" htmlType="submit" loading={loading} className="gradient-btn">
              搜索
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {/* 结果统计行 */}
      {searched && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 12,
          }}
        >
          <Space>
            <Text type="secondary">排序</Text>
            <Select
              style={{ width: 130 }}
              value={sortBy}
              onChange={setSortBy}
              options={[
                { value: 'relevance', label: '相关度' },
                { value: 'date', label: '时间' },
                { value: 'helpful', label: '有用数' },
              ]}
            />
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="命中" labelStyle={{ color: 'var(--rl-text-faint)' }}>
                {total} 条
              </Descriptions.Item>
              <Descriptions.Item label="耗时" labelStyle={{ color: 'var(--rl-text-faint)' }}>
                {tookMs} ms
              </Descriptions.Item>
            </Descriptions>
          </Space>
        </div>
      )}

      {/* 结果区 / 空状态 */}
      {!searched ? (
        <EmptyState
          icon={<IconSearch size={52} style={{ color: 'var(--rl-purple)' }} />}
          title="开启你的评论洞察"
          desc="输入关键词或组合筛选条件，从海量评论中找到值得关注的信号"
        >
          <div style={{ marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 13 }}>试试搜索：</Text>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginTop: 12 }}>
              {SUGGESTED_QUERIES.map((q) => (
                <Button key={q} size="small" onClick={() => applySuggestion(q)} style={{ background: 'rgba(148,163,184,0.08)', borderColor: 'var(--rl-border)' }}>
                  {q}
                </Button>
              ))}
            </div>
          </div>
        </EmptyState>
      ) : hits.length === 0 ? (
        <EmptyState
          icon={<IconSpark size={48} style={{ color: 'var(--rl-text-faint)' }} />}
          title="未找到匹配评论"
          desc="当前条件过于严格，试试放宽评分范围、缩短时间跨度或更换关键词"
        />
      ) : (
        <Table
          rowKey="review_id"
          loading={loading}
          columns={columns}
          dataSource={hits}
          pagination={{
            current: page,
            pageSize: 10,
            total,
            onChange: (p) => setPage(p),
            showTotal: (t) => `共 ${t} 条`,
          }}
        />
      )}
    </div>
  );
}

function EmptyState({
  icon,
  title,
  desc,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  children?: React.ReactNode;
}) {
  return (
    <Card className="glass-card">
      <div style={{ textAlign: 'center', padding: '48px 24px' }}>
        <div style={{ marginBottom: 16 }}>{icon}</div>
        <div style={{ fontSize: 17, fontWeight: 600, color: 'var(--rl-text)', marginBottom: 8 }}>{title}</div>
        <div style={{ color: 'var(--rl-text-secondary)', maxWidth: 380, margin: '0 auto', fontSize: 13 }}>{desc}</div>
        {children}
      </div>
    </Card>
  );
}
