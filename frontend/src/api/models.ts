import client from './client';

// ---------- 类型 ----------

export interface AnalysisRun {
  id: string;
  dataset_version: string;
  model_version: string;
  algorithm: string;
  random_seed: number;
  train_samples: number;
  test_samples: number;
  macro_f1: number | null;
  accuracy: number | null;
  classification_report?: Record<string, unknown> | null;
  confusion_matrix?: Record<string, unknown> | null;
  status: string;
  publish_status: string;
  error_message?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface ModelInfo {
  model_version: string | null;
  algorithm: string | null;
  macro_f1: number | null;
  publish_status: string | null;
}

export interface PublishCriteria {
  macro_f1: number | null;
  macro_f1_ok: boolean;
  test_samples: number;
  test_samples_ok: boolean;
  coverage: number | null;
  coverage_ok: boolean;
  can_publish: boolean;
  reasons: string[];
  metrics?: Record<string, unknown> | null;
}

// ---------- API ----------

export function listAnalysisRuns(params?: { dataset_version?: string; page?: number; page_size?: number }) {
  return client.get('/api/v1/analysis-runs', { params }).then((r) => r.data.data);
}

export function listModelHistory() {
  return client.get('/api/v1/models/history').then((r) => r.data.data);
}

export function getCurrentModel() {
  return client.get('/api/v1/models/current').then((r) => r.data.data);
}

export function getPublishCriteria(runId: string) {
  return client.get(`/api/v1/models/${runId}/criteria`).then((r) => r.data.data);
}

export function publishModel(runId: string) {
  return client.post(`/api/v1/analysis-runs/${runId}/publish`).then((r) => r.data.data);
}

export function rollbackModel(runId: string) {
  return client.post(`/api/v1/analysis-runs/${runId}/rollback`).then((r) => r.data.data);
}

export function createReviewedRun(body: { dataset_version: string; algorithm?: string }) {
  return client.post('/api/v1/analysis-runs/reviewed', body).then((r) => r.data.data);
}