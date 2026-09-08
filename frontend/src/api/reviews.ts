import client from './client';

// ---------- 类型 ----------

export type SortBy = 'relevance' | 'date' | 'helpful';
export type GroupBy = 'aspect' | 'rating' | 'date' | 'sentiment';
export type DateHistogram = 'day' | 'week' | 'month';

export interface SearchFilters {
  dataset_version?: string | null;
  product_id?: string | null;
  product_group_id?: string | null;
  rating_min?: number | null;
  rating_max?: number | null;
  date_from?: string | null;
  date_to?: string | null;
  language?: string | null;
  overall_sentiment?: string | null;
  aspect?: string | null;
}

export interface SearchResponse {
  items: SearchHit[];
  total: number;
  page: number;
  page_size: number;
  took_ms: number;
}

export interface SearchHit {
  review_id: string;
  product_id: string;
  product_group_id?: string | null;
  review_title?: string | null;
  review_text: string;
  rating?: number | null;
  reviewed_at?: string | null;
  language?: string | null;
  helpful_votes: number;
  verified_purchase: boolean;
  overall_sentiment?: string | null;
  highlight: string[];
}

export interface AggregateResponse {
  buckets: AggregateBucket[];
  total_docs: number;
  took_ms: number;
}

export interface AggregateBucket {
  key: string;
  doc_count: number;
  negative_count: number;
  negative_rate: number;
  positive_count?: number | null;
  neutral_count?: number | null;
  avg_confidence?: number | null;
}

// ---------- API ----------

export function searchReviews(body: {
  query?: string;
  filters?: SearchFilters;
  page?: number;
  page_size?: number;
  sort_by?: SortBy;
}) {
  return client
    .post<{ data: SearchResponse }>('/api/v1/reviews/search', body)
    .then((r) => r.data.data);
}

export function aggregateReviews(body: {
  dataset_version?: string | null;
  group_by?: GroupBy;
  date_histogram?: DateHistogram;
  filters?: {
    product_id?: string | null;
    product_group_id?: string | null;
    rating_min?: number | null;
    rating_max?: number | null;
    date_from?: string | null;
    date_to?: string | null;
    language?: string | null;
  };
}) {
  return client
    .post<{ data: AggregateResponse }>('/api/v1/reviews/aggregate', body)
    .then((r) => r.data.data);
}