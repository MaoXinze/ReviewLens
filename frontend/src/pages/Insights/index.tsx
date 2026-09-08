import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  Breadcrumb,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Input,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { Column } from '@ant-design/charts';
import dayjs, { type Dayjs } from 'dayjs';
import * as insightApi from '../../api/insights';
import PageHeader from '../../components/PageHeader';

const { Paragraph, Text } = Typography;
import type {
  AspectRate,
  EvidenceItem,
  SkuStat,
} from '../../api/insights';
import {
  IconAlert,
  IconDatabase,
  IconInsights,
  IconRocket,
} from '../../components/icons';


// 趋势分层：month=全年12月 / week=月内周 / day=周内7天
type TrendUnit = 'month' | 'week' | 'day';

interface TrendDatum {
  bucket: string;
  label: string;
  rate: number;
  total: number;
  negative: number;
}

const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}月`,
}));

const WEEKDAY_LABELS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

function pad2(n: number) {
  return n.toString().padStart(2, '0');
}

/** 根据粒度格式化 bucket 为可读标签 */
function formatBucket(bucket: string, unit: TrendUnit): string {
  const d = dayjs(bucket);
  if (!d.isValid()) return bucket;
  if (unit === 'month') return `${d.month() + 1}月`;
  if (unit === 'week') return `${d.format('MM-DD')}周`;
  return `${d.format('MM-DD')} ${WEEKDAY_LABELS[d.day() === 0 ? 6 : d.day() - 1]}`;
}

/** tooltip 用的完整时间标题 */
function fullBucketTitle(bucket: string, unit: TrendUnit): string {
  const d = dayjs(bucket);
  if (!d.isValid()) return bucket;
  if (unit === 'month') return `${d.year()}年${d.month() + 1}月`;
  if (unit === 'week') return `${d.year()}年${d.month() + 1}月 · ${d.format('MM-DD')} 起`;
  return `${d.format('YYYY-MM-DD')} ${WEEKDAY_LABELS[d.day() === 0 ? 6 : d.day() - 1]}`;
}

function ChangeTag({ change }: { change?: number | null }) {
  if (change == null) return <Tag>—</Tag>;
  const up = change > 0;
  const color = up ? 'red' : 'green';
  const arrow = up ? '↑' : '↓';
  return <Tag color={color}>{arrow} {(Math.abs(change) * 100).toFixed(1)}%</Tag>;
}

interface EvidenceDrawerState {
  open: boolean;
  aspect?: string;
  items: EvidenceItem[];
  total: number;
  loading: boolean;
}

export default function InsightsPage() {
  const [datasets, setDatasets] = useState<insightApi.DatasetOption[]>([]);
  const [datasetVersion, setDatasetVersion] = useState<string>('');
  const [productId, setProductId] = useState<string>('');
  const [period, setPeriod] = useState<string>('');
  const [ranking, setRanking] = useState<AspectRate[]>([]);

  const [trendUnit, setTrendUnit] = useState<TrendUnit>('month');
  const [trendYear, setTrendYear] = useState<number | null>(null); // null = 未初始化
  const [trendMonth, setTrendMonth] = useState<number>(new Date().getMonth() + 1);
  const [trendDate, setTrendDate] = useState<Dayjs>(dayjs());
  const [trendAspect, setTrendAspect] = useState<string>('');
  const [trendItems, setTrendItems] = useState<insightApi.TrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(true);

  const [skuProducts, setSkuProducts] = useState<
    { product_id: string; review_count: number }[]
  >([]);
  const [skuList, setSkuList] = useState<string[]>([]);
  const [skuAspect, setSkuAspect] = useState<string>('');
  const [skuResult, setSkuResult] = useState<SkuStat[]>([]);

  const [evidence, setEvidence] = useState<EvidenceDrawerState>({
    open: false,
    items: [],
    total: 0,
    loading: false,
  });
  const [evPage, setEvPage] = useState(1);

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
    insightApi
      .getAspectRanking({ dataset_version: datasetVersion, product_id: productId || undefined, period: period || undefined })
      .then((resp) => setRanking(resp.ranking ?? []))
      .catch(() => setRanking([]));
  }, [datasetVersion, productId, period]);

  // 趋势窗口参数：month='2025' / week='2025-08' / day='2025-08-11'（年份未初始化时传全量）
  const trendPeriod = useMemo(() => {
    if (trendYear == null) return undefined;
    if (trendUnit === 'month') return `${trendYear}`;
    if (trendUnit === 'week') return `${trendYear}-${pad2(trendMonth)}`;
    return `${trendYear}-${pad2(trendMonth)}-${pad2(trendDate.date())}`;
  }, [trendUnit, trendYear, trendMonth, trendDate]);

  // 初始化：用 year 粒度全量推断数据最晚年份作为默认下钻起点
  useEffect(() => {
    if (!datasetVersion || trendYear != null) return;
    insightApi
      .getTrends({ dataset_version: datasetVersion, granularity: 'year' })
      .then((resp) => {
        const items = (resp.items ?? []) as insightApi.TrendPoint[];
        if (items.length) {
          const years = items.map((t) => dayjs(t.bucket).year()).filter((y) => y > 0);
          setTrendYear(years.length ? Math.max(...years) : new Date().getFullYear());
        } else {
          setTrendYear(new Date().getFullYear());
        }
      })
      .catch(() => setTrendYear(new Date().getFullYear()));
  }, [datasetVersion, trendYear]);

  useEffect(() => {
    if (!datasetVersion || trendYear == null) return;
    setTrendLoading(true);
    insightApi
      .getTrends({
        dataset_version: datasetVersion,
        granularity: trendUnit,
        aspect: trendAspect || undefined,
        period: trendPeriod,
      })
      .then((resp) => setTrendItems(resp.items ?? []))
      .catch(() => setTrendItems([]))
      .finally(() => setTrendLoading(false));
  }, [datasetVersion, trendUnit, trendAspect, trendPeriod, trendYear]);

  // 数据集变化时拉取 SKU 列表，并默认选中评论量前二的商品
  useEffect(() => {
    setSkuList([]);
    setSkuResult([]);
    if (!datasetVersion) {
      setSkuProducts([]);
      return;
    }
    insightApi
      .getDatasetProducts(datasetVersion, 50)
      .then((items) => {
        setSkuProducts(items);
        if (items.length > 0) setSkuList(items.slice(0, 2).map((i) => i.product_id));
      })
      .catch(() => setSkuProducts([]));
  }, [datasetVersion]);

  const loadSku = useCallback(async () => {
    if (!datasetVersion || skuList.length === 0) {
      setSkuResult([]);
      return;
    }
    try {
      const resp = await insightApi.getSkuComparison({
        dataset_version: datasetVersion,
        skus: skuList.join(','),
        aspect: skuAspect || undefined,
      });
      setSkuResult(resp.skus ?? []);
    } catch {
      setSkuResult([]);
    }
  }, [datasetVersion, skuList, skuAspect]);

  useEffect(() => {
    loadSku();
  }, [loadSku]);

  const openEvidence = useCallback(
    (aspect?: string) => {
      if (!datasetVersion) return;
      const params = {
        dataset_version: datasetVersion,
        page_size: 20,
        product_id: productId || undefined,
        aspect,
        sentiment: 'negative',
        period: period || undefined,
      };
      setEvPage(1);
      setEvidence({ open: true, aspect, items: [], total: 0, loading: true });
      insightApi.getEvidence(params).then((resp) => {
        setEvidence({ open: true, aspect, items: resp.items ?? [], total: resp.total ?? 0, loading: false });
      }).catch(() => setEvidence((s) => ({ ...s, loading: false })));
    },
    [datasetVersion, productId, period],
  );

  const loadEvidencePage = useCallback(
    async (page: number) => {
      if (!datasetVersion) return;
      setEvidence((s) => ({ ...s, loading: true }));
      const resp = await insightApi.getEvidence({
        dataset_version: datasetVersion,
        page,
        page_size: 20,
        product_id: productId || undefined,
        aspect: evidence.aspect,
        sentiment: 'negative',
        period: period || undefined,
      });
      setEvPage(page);
      setEvidence((s) => ({ ...s, items: resp.items ?? [], total: resp.total ?? 0, loading: false }));
    },
    [datasetVersion, productId, period, evidence.aspect],
  );

  const rankingColumns: ColumnsType<AspectRate> = [
    { title: '属性', dataIndex: 'aspect' },
    { title: '评论数', dataIndex: 'total', sorter: (a, b) => a.total - b.total },
    { title: '差评数', dataIndex: 'negative', sorter: (a, b) => a.negative - b.negative },
    {
      title: '差评率',
      dataIndex: 'negative_rate',
      sorter: (a, b) => a.negative_rate - b.negative_rate,
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      title: '环比',
      dataIndex: 'change',
      render: (_, row) => <ChangeTag change={row.change} />,
    },
    {
      title: '证据',
      key: 'evidence',
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => openEvidence(row.aspect)}>
          查看差评证据
        </Button>
      ),
    },
  ];

  const skuColumns: ColumnsType<SkuStat> = [
    { title: '商品', dataIndex: 'product_id' },
    { title: '评论数', dataIndex: 'total' },
    { title: '差评数', dataIndex: 'negative' },
    { title: '差评率', dataIndex: 'negative_rate', render: (v: number) => `${(v * 100).toFixed(1)}%` },
    {
      title: '差评属性 TOP',
      dataIndex: 'top_aspects',
      render: (top: AspectRate[]) => (
        <Space size={4} wrap>
          {top.slice(0, 3).map((a) => (
            <Button key={a.aspect} type="link" size="small" onClick={() => openEvidence(a.aspect)}>
              {a.aspect} {`${(a.negative_rate * 100).toFixed(0)}%`}
            </Button>
          ))}
        </Space>
      ),
    },
  ];

  // ----- SKU 分组柱状图：横轴属性、系列为 SKU、纵轴差评率 -----
  const skuAspects = useMemo(() => {
    const set = new Set<string>();
    skuResult.forEach((s) => s.top_aspects.forEach((a) => set.add(a.aspect)));
    return [...set];
  }, [skuResult]);

  const skuChartData = useMemo(() => {
    const rows: { aspect: string; sku: string; rate: number }[] = [];
    skuAspects.forEach((asp) => {
      skuResult.forEach((s) => {
        const hit = s.top_aspects.find((a) => a.aspect === asp);
        rows.push({
          aspect: asp,
          sku: s.product_id,
          rate: hit ? +(hit.negative_rate * 100).toFixed(1) : 0,
        });
      });
    });
    return rows;
  }, [skuAspects, skuResult]);

  const SKU_COLORS = ['#1677ff', '#722ed1', '#faad14', '#52c41a', '#eb2f96', '#13c2c2'];
  const skuChartConfig = {
    data: skuChartData,
    xField: 'aspect',
    yField: 'rate',
    colorField: 'sku',
    // 同一属性下多 SKU 并列（分组柱）
    transform: [{ type: 'dodgeX' }],
    height: 320,
    scale: { color: { range: SKU_COLORS } },
    interaction: { tooltip: { crosshairs: true } },
    axis: {
      x: {
        labelFill: '#8a9099',
        labelFontSize: 11,
        line: true,
        lineStroke: 'rgba(0, 0, 0, 0.12)',
        tick: false,
      },
      y: {
        labelFill: '#8a9099',
        labelFontSize: 11,
        grid: true,
        gridStroke: 'rgba(0, 0, 0, 0.06)',
        line: false,
        labelFormatter: (v: number) => `${v}%`,
      },
    },
    legend: { color: { position: 'top' } },
    labels: [
      {
        text: (d: { rate: number }) => (d.rate > 0 ? `${d.rate}%` : ''),
        position: 'top',
        dy: -6,
        fontSize: 10,
        fill: '#3b4652',
        transform: [{ type: 'overlapHide' }],
      },
    ],
  } as unknown as Record<string, unknown>;

  const rankTable = (
    <Card
      className="glass-card"
      title="属性差评率排行"
      extra={
        <Space>
          <Select
            style={{ width: 220 }}
            value={datasetVersion || undefined}
            placeholder="数据集"
            onChange={setDatasetVersion}
            options={datasets.map((d) => ({ label: d.dataset_version, value: d.dataset_version }))}
          />
          <Input.Search placeholder="商品 ID" allowClear style={{ width: 160 }} onSearch={(v) => setProductId(v.trim())} />
          <Input placeholder="月份 e.g. 2025-08" allowClear style={{ width: 160 }} onPressEnter={(e) => setPeriod((e.target as HTMLInputElement).value.trim())} />
        </Space>
      }
    >
      <Table rowKey="aspect" size="small" pagination={false} columns={rankingColumns} dataSource={ranking} />
    </Card>
  );

  // ----- 趋势：统计概览 -----
  const trendStats = useMemo(() => {
    if (!trendItems.length) return null;
    const rates = trendItems.map((t) => t.negative_rate);
    const avg = (rates.reduce((a, b) => a + b, 0) / rates.length) * 100;
    const peakItem = trendItems.reduce((a, b) => (b.negative_rate > a.negative_rate ? b : a));
    const totalReviews = trendItems.reduce((a, t) => a + t.total, 0);
    const last = trendItems[trendItems.length - 1];
    const prev = trendItems.length > 1 ? trendItems[trendItems.length - 2] : null;
    const change = prev ? (last.negative_rate - prev.negative_rate) * 100 : null;
    return { avg, peakItem, totalReviews, change };
  }, [trendItems]);

  const trendChartData: TrendDatum[] = trendItems.map((t) => ({
    bucket: t.bucket,
    label: formatBucket(t.bucket, trendUnit),
    rate: +(t.negative_rate * 100).toFixed(1),
    total: t.total,
    negative: t.negative,
  }));

  // 柱体样式：G2 v5 用 style 键（columnStyle 是 G2Plot 旧写法，charts v2 下被忽略）
  const columnStyle: Record<string, unknown> = {
    // 柱宽比 0.45（12 个月 / 7 天视图比例适中）
    columnWidthRatio: 0.45,
    // 蓝色渐变柱体：浅蓝 → AntD 主蓝（浅色底上清晰沉稳）
    fill: 'linear-gradient(to bottom, #4096ff, #1677ff)',
    radiusTopLeft: 4,
    radiusTopRight: 4,
  };
  // 周视图只有 4~5 个数据点，按比例拉伸会变成又宽又空的柱子 → 用 maxWidth 封顶
  if (trendUnit === 'week') {
    columnStyle.maxWidth = 48;
    columnStyle.minWidth = 8;
  }
  // 可点击下钻提示：柱体显示手型光标
  columnStyle.cursor = 'pointer';

  const trendConfig = {
    data: trendChartData,
    xField: 'label',
    yField: 'rate',
    height: 380,
    // 顶部留白：为柱体外侧数值标签预留空间
    padding: [56, 32, 40, 40],
    style: columnStyle,
    // 悬停柱体加深 + 提示十字线
    interaction: { tooltip: { crosshairs: true } },
    state: {
      hover: { style: { fill: '#0958d9', cursor: 'pointer' } },
    },
    // 浅色主题下的坐标轴：中灰文字 + 淡网格
    axis: {
      x: {
        labelFill: '#8a9099',
        labelFontSize: 11,
        line: true,
        lineStroke: 'rgba(0, 0, 0, 0.12)',
        tick: false,
      },
      y: {
        labelFill: '#8a9099',
        labelFontSize: 11,
        grid: true,
        gridStroke: 'rgba(0, 0, 0, 0.06)',
        line: false,
        labelFormatter: (v: number) => `${v}%`,
      },
    },
    tooltip: {
      title: (d: TrendDatum) => fullBucketTitle(d.bucket, trendUnit),
      items: [
        (d: TrendDatum) => ({ name: '差评率', value: `${d.rate}%` }),
        (d: TrendDatum) => ({ name: '评论数', value: d.total.toLocaleString() }),
        (d: TrendDatum) => ({ name: '差评数', value: d.negative.toLocaleString() }),
      ],
    },
    // 柱顶外侧数值标签：深灰文字 + 白色描边底，浅色底上高可读；
    // transform 自动防重叠 / 防越界
    labels: [
      {
        text: (d: TrendDatum) => (d.rate > 0 ? `${d.rate}%` : ''),
        position: 'top',
        dy: -8,
        fontSize: 12,
        fontWeight: 600,
        fill: '#3b4652',
        background: {
          fill: 'rgba(255, 255, 255, 0.85)',
          radius: 4,
          padding: [2, 5],
        },
        transform: [{ type: 'overlapHide' }, { type: 'exceedAdjust' }],
      },
    ],
    // 均值参考线（琥珀色虚线，浅色底用深一档的琥珀）
    ...(trendStats
      ? {
          annotations: [
            {
              type: 'lineY',
              yField: +trendStats.avg.toFixed(1),
              style: { stroke: '#d48806', lineDash: [4, 4], lineWidth: 1 },
              label: {
                text: `均值 ${trendStats.avg.toFixed(1)}%`,
                position: 'right',
                dy: -4,
                fill: '#d48806',
                fontSize: 11,
              },
            },
          ],
        }
      : {}),
  } as unknown as Record<string, unknown>;

  /** 点击柱体下钻：月→周→天 */
  function drillTrend(datum: { bucket?: string } | null | undefined) {
    if (!datum?.bucket) return;
    const d = dayjs(datum.bucket);
    if (!d.isValid()) return;
    if (trendUnit === 'month') {
      setTrendMonth(d.month() + 1);
      setTrendUnit('week');
    } else if (trendUnit === 'week') {
      setTrendDate(d);
      setTrendUnit('day');
    }
  }

  // 关键：onReady 只在图表首次创建时执行一次，内部闭包会捕获旧 state。
  // 用 ref 保存最新 drillTrend，事件回调始终读取最新版本。
  const drillRef = useRef<(d: { bucket?: string } | null | undefined) => void>(() => {});
  drillRef.current = drillTrend;

  const unitLabel: Record<TrendUnit, string> = {
    month: '年',
    week: '月',
    day: '日',
  };

  // 面包屑：当前下钻路径（可点回上层）
  const weekOfMonth = Math.ceil(trendDate.date() / 7);
  const crumbStyle = (active: boolean): CSSProperties => ({
    cursor: 'pointer',
    color: active ? 'var(--rl-text)' : 'var(--rl-cyan)',
    fontWeight: active ? 600 : 400,
  });
  const trendBreadcrumbItems = [
    {
      title: (
        <span onClick={() => setTrendUnit('month')} style={crumbStyle(trendUnit === 'month')}>
          {trendYear ?? '…'} 年
        </span>
      ),
    },
    ...(trendUnit !== 'month'
      ? [
          {
            title: (
              <span onClick={() => setTrendUnit('week')} style={crumbStyle(trendUnit === 'week')}>
                {trendMonth} 月
              </span>
            ),
          },
        ]
      : []),
    ...(trendUnit === 'day'
      ? [
          {
            title: (
              <span style={{ color: 'var(--rl-text)', fontWeight: 600 }}>
                第 {weekOfMonth} 周
              </span>
            ),
          },
        ]
      : []),
  ];

  const trendStatCards = trendStats
    ? [
        {
          label: '平均差评率',
          value: `${trendStats.avg.toFixed(1)}%`,
          color: '#1677ff',
          icon: <IconInsights size={15} />,
        },
        {
          label: `峰值 · ${formatBucket(trendStats.peakItem.bucket, trendUnit)}`,
          value: `${(trendStats.peakItem.negative_rate * 100).toFixed(1)}%`,
          color: '#cf1322',
          icon: <IconAlert size={15} />,
        },
        {
          label: '样本评论',
          value: trendStats.totalReviews.toLocaleString(),
          color: '#7c3aed',
          icon: <IconDatabase size={15} />,
        },
        {
          label: '环比上一期',
          value:
            trendStats.change == null
              ? '—'
              : `${trendStats.change >= 0 ? '+' : ''}${trendStats.change.toFixed(1)} pp`,
          color:
            trendStats.change != null && trendStats.change >= 0 ? '#cf1322' : '#389e0d',
          icon: <IconRocket size={15} />,
        },
      ]
    : [];

  const trend = (
    <Card
      className="glass-card"
      title="属性差评率趋势"
      extra={
        <Space wrap size={8}>
          <Select
            style={{ width: 170 }}
            value={datasetVersion || undefined}
            placeholder="数据集"
            onChange={setDatasetVersion}
            options={datasets.map((d) => ({ label: d.dataset_version, value: d.dataset_version }))}
          />
          <Input.Search placeholder="属性（留空=整体）" allowClear style={{ width: 160 }} onSearch={(v) => setTrendAspect(v.trim())} />
        </Space>
      }
    >
      {/* 面包屑 + 粒度/时间导航 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <Space size={12} wrap>
          <Breadcrumb items={trendBreadcrumbItems} />
          {trendAspect && (
            <Tag color="geekblue" closable onClose={() => setTrendAspect('')}>
              {trendAspect}
            </Tag>
          )}
        </Space>

        <Space wrap size={8}>
          <Segmented
            value={trendUnit}
            onChange={(v) => setTrendUnit(v as TrendUnit)}
            options={(['month', 'week', 'day'] as TrendUnit[]).map((u) => ({
              label: unitLabel[u],
              value: u,
            }))}
          />

          {/* 年份导航 */}
          <Space.Compact>
            <Button disabled={trendYear == null} onClick={() => setTrendYear((y) => (y ?? 0) - 1)}>‹</Button>
            <Input
              value={trendYear != null ? `${trendYear}年` : '…'}
              readOnly
              style={{ width: 70, textAlign: 'center', background: 'rgba(148,163,184,0.06)' }}
            />
            <Button disabled={trendYear == null} onClick={() => setTrendYear((y) => (y ?? 0) + 1)}>›</Button>
          </Space.Compact>

          {/* 月/日联动选择 */}
          {trendUnit !== 'month' && (
            <Select
              style={{ width: 80 }}
              value={trendMonth}
              onChange={setTrendMonth}
              options={MONTH_OPTIONS}
            />
          )}
          {trendUnit === 'day' && (
            <DatePicker
              value={trendDate}
              onChange={(d) => d && setTrendDate(d)}
              placeholder="选周内任一天"
              style={{ width: 150 }}
            />
          )}
        </Space>
      </div>

      {/* 统计概览条 */}
      {trendStatCards.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: 12,
            marginBottom: 16,
          }}
        >
          {trendStatCards.map((s) => (
            <div key={s.label} className="stat-card">
              <div className="stat-label">
                <span style={{ color: s.color, display: 'inline-flex', alignItems: 'center' }}>{s.icon}</span>
                <span>{s.label}</span>
              </div>
              <div className="stat-value" style={{ color: s.color, fontSize: 22 }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 图表主体 */}
      {trendLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 380 }}>
          <Spin size="large" />
        </div>
      ) : trendChartData.length > 0 ? (
        <Column
          {...trendConfig}
          onReady={(chartInst: unknown) => {
            // @ant-design/plots 的 Plot 包装器转发 G2 事件时只用 e.type（原生名 'click'），
            // 语义事件 'element:click' 只存在于内部 G2 实例上，在包装器上注册永远不触发
            //（EventEmitter 静默注册，无报错）→ 必须绑定 wrapper.chart（内部 G2 实例）。
            // 回调经 drillRef 读取最新下钻逻辑，避免闭包捕获首帧 state。
            const handleElementClick = (e: unknown) => {
              const ev = e as { data?: unknown };
              // G2 v5: e.data = { data: <原始记录> }（见 interaction/event.js）
              let raw: unknown = ev.data;
              if (
                raw &&
                typeof raw === 'object' &&
                'data' in (raw as Record<string, unknown>)
              ) {
                raw = (raw as { data: unknown }).data;
              }
              if (Array.isArray(raw)) raw = raw[0];
              drillRef.current(raw as { bucket?: string } | null | undefined);
            };
            type ClickEmitter = {
              on?: (evt: string, cb: (e: unknown) => void) => void;
            };
            const wrapper = chartInst as { chart?: ClickEmitter } | undefined;
            const fallback = (chartInst as ClickEmitter).on;
            if (wrapper?.chart?.on) {
              wrapper.chart.on('element:click', handleElementClick);
            } else if (fallback) {
              // 兜底：未来版本若内部实例不可达，退回包装器（仅能感知点击，无 element 语义）
              fallback.call(chartInst, 'element:click', handleElementClick);
            }
          }}
        />
      ) : (
        <div style={{ textAlign: 'center', padding: '70px 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 14 }}>
            <IconInsights size={44} style={{ color: 'var(--rl-purple)' }} />
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--rl-text)', marginBottom: 6 }}>
            该时间段暂无数据
          </div>
          <div style={{ color: 'var(--rl-text-secondary)', fontSize: 13 }}>
            试试切换年份 / 月份，或返回上一层级
          </div>
          {trendUnit !== 'month' && (
            <Button
              size="small"
              style={{ marginTop: 14, background: 'rgba(148,163,184,0.08)', borderColor: 'var(--rl-border)' }}
              onClick={() => setTrendUnit(trendUnit === 'day' ? 'week' : 'month')}
            >
              返回上一层级
            </Button>
          )}
        </div>
      )}

      {/* 下钻提示 */}
      {trendUnit !== 'day' && trendChartData.length > 0 && !trendLoading && (
        <div style={{ textAlign: 'center', marginTop: 8, color: 'var(--rl-text-faint)', fontSize: 12 }}>
          点击柱体可下钻到更细粒度
        </div>
      )}
    </Card>
  );

  const sku = (
    <Card
      className="glass-card"
      title="SKU 属性对比"
      extra={
        <Space wrap size={8}>
          <Select
            style={{ width: 220 }}
            value={datasetVersion || undefined}
            placeholder="数据集"
            onChange={setDatasetVersion}
            options={datasets.map((d) => ({ label: d.dataset_version, value: d.dataset_version }))}
          />
          <Input.Search
            placeholder="属性（可选）"
            allowClear
            style={{ width: 150 }}
            onSearch={(v) => setSkuAspect(v.trim())}
          />
        </Space>
      }
    >
      <Paragraph type="secondary" style={{ marginBottom: 14 }}>
        SKU 对比用于把多个商品放在同一把尺子下：横比它们在<b>相同属性</b>（物流、品质、外观等）上的差评率，
        快速定位「哪个商品 × 哪个属性」最拖后腿，为改进排优先级。
      </Paragraph>

      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          mode="multiple"
          allowClear
          placeholder="选择要对比的 SKU（默认评论量前二）"
          style={{ minWidth: 320, flex: 1 }}
          value={skuList}
          onChange={setSkuList}
          maxTagCount="responsive"
          options={skuProducts.map((p) => ({
            label: `${p.product_id}（${p.review_count.toLocaleString()} 条评论）`,
            value: p.product_id,
          }))}
        />
        {skuList.length > 4 && (
          <Tag color="orange">建议对比不超过 4 个 SKU，过多会降低可读性</Tag>
        )}
      </div>

      {skuChartData.length > 0 ? (
        <Column {...skuChartConfig} />
      ) : (
        <div style={{ textAlign: 'center', padding: '48px 24px', color: 'var(--rl-text-secondary)' }}>
          {skuList.length === 0
            ? '请先在上方选择要对比的 SKU'
            : '所选 SKU 暂无属性分析数据（需先完成批量推理）'}
        </div>
      )}

      <Divider style={{ margin: '18px 0 14px' }} plain>
        <Text type="secondary" style={{ fontSize: 12 }}>明细数据</Text>
      </Divider>
      <Table rowKey="product_id" size="small" pagination={false} columns={skuColumns} dataSource={skuResult} />
    </Card>
  );

  return (
    <div style={{ padding: 24 }}>
      <PageHeader
        title="体验洞察"
        description="属性排行、趋势与 SKU 对比，每个数字可下钻到证据评论；趋势图支持点击柱体逐层下钻（年 → 月 → 日）。"
      />

      <Tabs
        items={[
          { key: 'ranking', label: '属性排行', children: rankTable },
          { key: 'trends', label: '趋势', children: trend },
          { key: 'sku', label: 'SKU 对比', children: sku },
        ]}
      />

      <Drawer
        title={evidence.aspect ? `差评证据：${evidence.aspect}` : '差评证据'}
        width={640}
        open={evidence.open}
        onClose={() => setEvidence((s) => ({ ...s, open: false }))}
      >
        <Table
          rowKey="review_id"
          size="small"
          loading={evidence.loading}
          dataSource={evidence.items}
          pagination={{
            current: evPage,
            pageSize: 20,
            total: evidence.total,
            onChange: (p) => loadEvidencePage(p),
          }}
          columns={[
            { title: '商品', dataIndex: 'product_id', width: 80 },
            { title: '评分', dataIndex: 'rating', width: 60 },
            {
              title: '内容',
              dataIndex: 'review_text',
              ellipsis: true,
            },
            {
              title: '时间',
              dataIndex: 'reviewed_at',
              width: 110,
              render: (v?: string) => (v ? v.slice(0, 10) : '—'),
            },
          ]}
          expandable={{
            expandedRowRender: (r) => (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="属性">
                  {r.aspects.map((a) => `${a.aspect}:${a.sentiment}`).join('，') || '—'}
                </Descriptions.Item>
                <Descriptions.Item label="完整评论">{r.review_text}</Descriptions.Item>
              </Descriptions>
            ),
          }}
        />
      </Drawer>
    </div>
  );
}