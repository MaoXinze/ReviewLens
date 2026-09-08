import { describe, expect, it, vi } from 'vitest';

// mock 底层 client，捕获调用并返回带 data 包壳的响应
const getFn = vi.fn();
const postFn = vi.fn();
const patchFn = vi.fn();

vi.mock('../client', () => ({
  default: {
    get: (...args: unknown[]) => getFn(...args),
    post: (...args: unknown[]) => postFn(...args),
    patch: (...args: unknown[]) => patchFn(...args),
    defaults: { baseURL: 'http://localhost:8000' },
  },
}));

import * as models from '../models';
import * as alerts from '../alerts';

function ok(data: unknown) {
  return { data: { code: 0, data } };
}

describe('models api', () => {
  it('listAnalysisRuns 请求 /analysis-runs 并剥壳', async () => {
    getFn.mockResolvedValueOnce(ok({ items: [], total: 0 }));
    const res = await models.listAnalysisRuns({ page: 1, page_size: 20 });
    expect(getFn).toHaveBeenCalledWith('/api/v1/analysis-runs', { params: { page: 1, page_size: 20 } });
    expect(res).toEqual({ items: [], total: 0 });
  });

  it('getCurrentModel 请求 /models/current', async () => {
    getFn.mockResolvedValueOnce(ok({ model_version: 'v1', publish_status: 'published' }));
    const res = await models.getCurrentModel();
    expect(getFn).toHaveBeenCalledWith('/api/v1/models/current');
    expect(res.publish_status).toBe('published');
  });

  it('publishModel POST /analysis-runs/:id/publish', async () => {
    postFn.mockResolvedValueOnce(ok({ message: 'ok' }));
    await models.publishModel('run-1');
    expect(postFn).toHaveBeenCalledWith('/api/v1/analysis-runs/run-1/publish');
  });
});

describe('alerts api', () => {
  it('listAlerts 请求 /alerts', async () => {
    getFn.mockResolvedValueOnce(ok({ items: [], total: 0, page: 1, page_size: 20 }));
    const res = await alerts.listAlerts({ page: 1 });
    expect(getFn).toHaveBeenCalledWith('/api/v1/alerts', { params: { page: 1 } });
    expect(res.total).toBe(0);
  });

  it('updateAlertStatus PATCH /alerts/:id', async () => {
    patchFn.mockResolvedValueOnce(ok({ id: 'a1', status: 'resolved' }));
    const res = await alerts.updateAlertStatus('a1', 'resolved');
    expect(patchFn).toHaveBeenCalledWith('/api/v1/alerts/a1', { status: 'resolved' });
    expect(res.status).toBe('resolved');
  });

  it('createExport POST /exports', async () => {
    postFn.mockResolvedValueOnce(ok({ id: 'e1', row_count: 10 }));
    const res = await alerts.createExport({ dataset_version: 'd1' });
    expect(postFn).toHaveBeenCalledWith('/api/v1/exports', { dataset_version: 'd1' });
    expect(res.row_count).toBe(10);
  });
});