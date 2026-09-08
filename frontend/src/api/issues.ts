import client from './client';

// ---------- 类型 ----------

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type IssueStatus = 'open' | 'in_progress' | 'pending_validation' | 'closed';

export interface IssueHistoryItem {
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  changed_by: string;
  changed_at: string;
  reason: string | null;
}

export interface Issue {
  id: string;
  dataset_version: string;
  title: string;
  aspect: string;
  severity: Severity;
  status: IssueStatus;
  description?: string | null;
  source_review_ids: string[];
  assignee?: string | null;
  resolution_note?: string | null;
  validation_note?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  closed_at?: string | null;
}

export interface IssueDetail {
  issue: Issue;
  history: IssueHistoryItem[];
}

export interface IssueListResponse {
  items: Issue[];
  total: number;
  page: number;
  page_size: number;
}

export interface RetrospectResult {
  issue_id: string;
  dataset_version: string;
  aspect: string;
  pre_rate: number;
  post_rate: number;
  change: number;
  improved: boolean;
}

export interface IssueCreatePayload {
  dataset_version: string;
  title: string;
  aspect: string;
  severity: Severity;
  description?: string | null;
  source_review_ids: string[];
  assignee?: string | null;
}

export interface IssueUpdatePayload {
  status: IssueStatus;
  resolution_note?: string | null;
  validation_note?: string | null;
}

// ---------- API ----------

export function listIssues(params?: {
  status?: string;
  aspect?: string;
  assignee?: string;
  dataset_version?: string;
  page?: number;
  page_size?: number;
}) {
  return client.get('/api/v1/issues', { params }).then((r) => r.data.data);
}

export function getIssue(id: string) {
  return client.get(`/api/v1/issues/${id}`).then((r) => r.data.data);
}

export function createIssue(body: IssueCreatePayload) {
  return client.post('/api/v1/issues', body).then((r) => r.data.data);
}

export function updateIssue(id: string, body: IssueUpdatePayload) {
  return client.patch(`/api/v1/issues/${id}`, body).then((r) => r.data.data);
}

export function retrospectIssue(id: string) {
  return client.post(`/api/v1/issues/${id}/retrospect`).then((r) => r.data.data);
}