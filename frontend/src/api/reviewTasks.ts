import client from './client';

// ---------- 类型 ----------

export type Sentiment = 'positive' | 'neutral' | 'negative';
export type ReviewTaskStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'awaiting_second_review'
  | 'verified'
  | 'cancelled';

export type ReviewReason =
  | 'confirm_prediction'
  | 'correct_sentiment'
  | 'correct_aspects'
  | 'correct_both'
  | 'invalid_text'
  | 'insufficient_info';

export interface ReviewTask {
  id: string;
  dataset_version: string;
  review_id: string;
  sampling_group: string;
  sampling_reason?: string | null;
  system_sentiment?: string | null;
  system_confidence?: number | null;
  system_aspects?: Array<Record<string, unknown>> | null;
  model_version?: string | null;
  reviewer_sentiment?: string | null;
  reviewer_aspects?: Array<Record<string, unknown>> | null;
  review_reason?: string | null;
  review_note?: string | null;
  status: string;
  reviewer_id?: string | null;
  reviewed_at?: string | null;
  second_reviewer_id?: string | null;
  second_reviewed_at?: string | null;
  created_at: string;
  // 补充的原文 quote（仅详情/next 返回）
  review_title?: string | null;
  review_text?: string | null;
  rating?: number | null;
}

export interface ReviewTaskListResponse {
  items: ReviewTask[];
  total: number;
  page: number;
  page_size: number;
}

export interface GenerateTasksResponse {
  created: number;
  dataset_version: string;
  skipped: number;
}

export interface ReviewSummary {
  dataset_version?: string | null;
  total: number;
  done: number;
  pending: number;
  approved: number;
  verified: number;
  rejected: number;
  completion_rate: number;
  agreement_rate: number;
}

// ---------- API ----------

export function listReviewTasks(params?: {
  status?: string;
  sampling_group?: string;
  dataset_version?: string;
  page?: number;
  page_size?: number;
}) {
  return client
    .get<{ data: ReviewTaskListResponse }>('/api/v1/review-tasks', { params })
    .then((r) => r.data.data);
}

export function getNextTask(datasetVersion?: string) {
  return client
    .get<{ data: ReviewTask | null }>('/api/v1/review-tasks/next', {
      params: datasetVersion ? { dataset_version: datasetVersion } : undefined,
    })
    .then((r) => r.data.data);
}

export function getSummary(datasetVersion?: string) {
  return client
    .get<{ data: ReviewSummary }>('/api/v1/review-tasks/summary', {
      params: datasetVersion ? { dataset_version: datasetVersion } : undefined,
    })
    .then((r) => r.data.data);
}

export function getReviewTask(id: string) {
  return client
    .get<{ data: ReviewTask }>(`/api/v1/review-tasks/${id}`)
    .then((r) => r.data.data);
}

export function generateTasks(body: {
  dataset_version: string;
  model_version?: string | null;
  count?: number;
}) {
  return client
    .post<{ data: GenerateTasksResponse }>('/api/v1/review-tasks/generate', body)
    .then((r) => r.data.data);
}

export function submitReview(
  id: string,
  body: {
    status: 'approved' | 'rejected';
    reviewer_sentiment?: Sentiment | null;
    reviewer_aspects?: Array<Record<string, unknown>>;
    review_reason?: ReviewReason;
    review_note?: string | null;
  },
) {
  return client
    .patch<{ data: ReviewTask }>(`/api/v1/review-tasks/${id}`, body)
    .then((r) => r.data.data);
}

export function secondReview(
  id: string,
  body: { status: 'approved' | 'rejected'; review_note?: string | null },
) {
  return client
    .post<{ data: ReviewTask }>(`/api/v1/review-tasks/${id}/second-review`, body)
    .then((r) => r.data.data);
}