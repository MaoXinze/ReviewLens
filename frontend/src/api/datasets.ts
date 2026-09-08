import client from './client';

// ---------- 类型 ----------

export interface DatasetImportResult {
  job_id?: string | null;
  status: string;
  message: string;
  dataset_version?: string | null;
  reused?: boolean;
}

export interface Dataset {
  dataset_version: string;
  source_filename: string;
  file_sha256: string;
  total_rows: number;
  valid_rows: number;
  rejected_rows: number;
  quality_report?: Record<string, unknown> | null;
  status: string;
  error_message?: string | null;
  created_at: string;
}

export interface DatasetListResponse {
  items: Dataset[];
  total: number;
  page: number;
  page_size: number;
}

export interface DatasetReview {
  id: string;
  review_id: string;
  product_id: string;
  product_group_id?: string | null;
  review_title?: string | null;
  review_text: string;
  rating?: number | null;
  reviewed_at: string;
  reviewer_id?: string | null;
  helpful_votes: number;
  verified_purchase: boolean;
  language: string;
}

export interface DatasetReviewListResponse {
  items: DatasetReview[];
  total: number;
  page: number;
  page_size: number;
}

export interface QualityReport {
  rejection_reasons: Record<string, number>;
  reasons_detail: Record<string, string[]>;
}

// ---------- API ----------

export function listDatasets(params?: { page?: number; page_size?: number }) {
  return client
    .get<{ data: DatasetListResponse }>('/api/v1/datasets', { params })
    .then((r) => r.data.data);
}

export function getDataset(version: string) {
  return client
    .get<{ data: Dataset }>(`/api/v1/datasets/${version}`)
    .then((r) => r.data.data);
}

export function getQualityReport(version: string) {
  return client
    .get<{ data: QualityReport }>(`/api/v1/datasets/${version}/quality-report`)
    .then((r) => r.data.data);
}

export function listDatasetReviews(
  version: string,
  params?: { page?: number; page_size?: number },
) {
  return client
    .get<{ data: DatasetReviewListResponse }>(
      `/api/v1/datasets/${version}/reviews`,
      { params },
    )
    .then((r) => r.data.data);
}

export function importDataset(file: File, fieldMapping?: Record<string, string>) {
  const formData = new FormData();
  formData.append('file', file);
  if (fieldMapping && Object.keys(fieldMapping).length) {
    formData.append('field_mapping', JSON.stringify(fieldMapping));
  }
  return client
    .post<{ data: DatasetImportResult }>('/api/v1/datasets/imports', formData)
    .then((r) => r.data.data);
}