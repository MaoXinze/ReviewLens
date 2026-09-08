import client from './client';

// ---------- 类型 ----------

export type RuleType = 'threshold' | 'trend';
export type RuleStatus = 'active' | 'paused';
export type AlertStatus = 'active' | 'acknowledged' | 'resolved';

export interface AlertRule {
  id: string;
  name: string;
  rule_type: RuleType;
  aspect: string;
  product_id?: string | null;
  threshold_value: number;
  time_window_days: number;
  dedup_days: number;
  webhook_url?: string | null;
  status: RuleStatus;
  created_by: string;
  created_at: string;
}

export interface Alert {
  id: string;
  rule_id: string;
  rule_name: string;
  rule_type: RuleType;
  aspect: string;
  product_id?: string | null;
  metric_value: number;
  trigger_value: number;
  status: AlertStatus;
  triggered_at: string;
  resolved_at?: string | null;
  resolved_by?: string | null;
}

export interface ExportRecord {
  id: string;
  exported_by: string;
  dataset_version: string;
  filters: Record<string, unknown>;
  file_path: string;
  row_count: number;
  created_at: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertRuleCreatePayload {
  name: string;
  rule_type: RuleType;
  aspect: string;
  product_id?: string | null;
  threshold_value: number;
  time_window_days?: number;
  dedup_days?: number;
  webhook_url?: string | null;
}

export interface ExportCreatePayload {
  dataset_version: string;
  product_id?: string | null;
  sentiment?: string | null;
  rating_min?: number;
  rating_max?: number;
}

// ---------- 告警规则 ----------

export function listRules(params?: { status?: string; page?: number; page_size?: number }) {
  return client.get('/api/v1/alert-rules', { params }).then((r) => r.data.data);
}

export function createRule(body: AlertRuleCreatePayload) {
  return client.post('/api/v1/alert-rules', body).then((r) => r.data.data);
}

export function updateRuleStatus(id: string, status: RuleStatus) {
  return client.patch(`/api/v1/alert-rules/${id}`, { status }).then((r) => r.data.data);
}

// ---------- 告警 ----------

export function listAlerts(params?: { status?: string; page?: number; page_size?: number }) {
  return client.get('/api/v1/alerts', { params }).then((r) => r.data.data);
}

export function updateAlertStatus(id: string, status: AlertStatus) {
  return client.patch(`/api/v1/alerts/${id}`, { status }).then((r) => r.data.data);
}

// ---------- 导出 ----------

export function createExport(body: ExportCreatePayload) {
  return client.post('/api/v1/exports', body).then((r) => r.data.data);
}

export function listExports(params?: { page?: number; page_size?: number }) {
  return client.get('/api/v1/exports', { params }).then((r) => r.data.data);
}

export function downloadExportUrl(id: string): string {
  return `${client.defaults.baseURL}/api/v1/exports/${id}/download`;
}

export function triggerDownload(id: string) {
  const token = localStorage.getItem('reviewlens_token');
  const url = downloadExportUrl(id);
  // 携带 Bearer 下载
  fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    .then((r) => r.blob())
    .then((blob) => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${id}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
}