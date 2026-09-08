import client from './client';

// ---------- 类型 ----------

export interface SentimentBucket {
  overall_sentiment: string;
  doc_count: number;
  ratio: number;
}

export interface ReviewProgress {
  total: number;
  done: number;
  pending: number;
  approved: number;
  verified: number;
  rejected: number;
  completion_rate: number;
  agreement_rate: number;
}

export interface AspectRate {
  aspect: string;
  total: number;
  negative: number;
  negative_rate: number;
  prev_rate?: number | null;
  change?: number | null;
}

export interface InsightOverView {
  dataset_version: string;
  model_version: string | null;
  generated_at: string;
  total_reviews: number;
  sentiment_distribution: SentimentBucket[];
  top_negative_aspects: AspectRate[];
  review_progress: ReviewProgress;
}

export interface AspectRankingResponse {
  dataset_version: string;
  model_version: string | null;
  filter_conditions: Record<string, string | null | undefined>;
  ranking: AspectRate[];
}

export interface TrendPoint {
  bucket: string;
  total: number;
  negative: number;
  negative_rate: number;
}

export interface TrendsResponse {
  dataset_version: string;
  model_version: string | null;
  granularity: string;
  items: TrendPoint[];
}

export interface SkuStat {
  product_id: string;
  total: number;
  negative: number;
  negative_rate: number;
  top_aspects: AspectRate[];
}

export interface SkuComparisonResponse {
  dataset_version: string;
  model_version: string | null;
  skus: SkuStat[];
}

export interface EvidenceItem {
  review_id: string;
  product_id: string;
  review_title?: string | null;
  review_text: string;
  rating?: number | null;
  reviewed_at?: string | null;
  overall_sentiment?: string | null;
  aspects: Array<{ aspect: string; sentiment: string; confidence?: number }>;
}

export interface EvidenceResponse {
  items: EvidenceItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DatasetOption {
  dataset_version: string;
  title?: string;
}

// ---------- API ----------

export function getOverview(params: {
  dataset_version: string;
  product_id?: string;
}) {
  return client.get('/api/v1/insights/overview', { params }).then((r) => r.data.data);
}

export function getAspectRanking(params: {
  dataset_version: string;
  product_id?: string;
  period?: string;
}) {
  return client.get('/api/v1/insights/aspect-ranking', { params }).then((r) => r.data.data);
}

export function getTrends(params: {
  dataset_version: string;
  granularity: 'year' | 'month' | 'week' | 'day';
  product_id?: string;
  aspect?: string;
  /** 与 granularity 配套的窗口：month='2025' / week='2025-08' / day='2025-08-11' */
  period?: string;
}) {
  return client.get('/api/v1/insights/trends', { params }).then((r) => r.data.data);
}

export function getSkuComparison(params: {
  dataset_version: string;
  skus: string;
  aspect?: string;
}) {
  return client.get('/api/v1/insights/sku-comparison', { params }).then((r) => r.data.data);
}

/** 数据集内评论量最高的商品（SKU）列表，供 SKU 对比选择 */
export function getDatasetProducts(datasetVersion: string, limit = 50) {
  return client
    .get<{ data: { items: { product_id: string; review_count: number }[] } }>(
      `/api/v1/datasets/${datasetVersion}/products`,
      { params: { limit } },
    )
    .then((r) => r.data.data.items);
}

export function getEvidence(params: {
  dataset_version: string;
  page?: number;
  page_size?: number;
  product_id?: string;
  aspect?: string;
  sentiment?: string;
  period?: string;
}) {
  return client.get('/api/v1/insights/evidence', { params }).then((r) => r.data.data);
}

export function listDatasets(params?: { page?: number; page_size?: number }) {
  return client.get('/api/v1/datasets', { params }).then((r) => r.data.data);
}