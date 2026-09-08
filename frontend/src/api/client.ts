import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

// M1 认证将 token 存于 localStorage（key 与本项目的登录逻辑约定一致）
const TOKEN_KEY = 'reviewlens_token';
const REFRESH_TOKEN_KEY = 'reviewlens_refresh_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setRefreshToken(token: string) {
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

export function clearRefreshToken() {
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

const client = axios.create({
  // 默认同源（开发走 Vite 代理 / 生产走 nginx 反代）；跨域部署时经 VITE_API_BASE_URL 指定
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
});

client.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ---------- 401 自动刷新 + 重放 ----------
// 并发 401 时只触发一次 refresh（共享 promise 锁）
let refreshPromise: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    // 用原始 axios 调用，避免 refresh 失败再次进入拦截器
    const resp = await axios.post<{ data: { access_token: string } }>(
      `${client.defaults.baseURL}/api/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 15000 },
    );
    const newAccess = resp.data.data.access_token;
    setToken(newAccess);
    return newAccess;
  } catch {
    clearToken();
    clearRefreshToken();
    return null;
  }
}

function tryRefresh(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

client.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const { response, config } = error;
    const cfg = config as RetriableConfig | undefined;

    // 仅在 401 且非 refresh 请求本身且未重试过时尝试刷新
    if (
      response?.status === 401 &&
      cfg &&
      !cfg.url?.includes('/api/auth/refresh') &&
      !cfg._retried
    ) {
      const newAccess = await tryRefresh();
      if (newAccess) {
        cfg._retried = true;
        cfg.headers = cfg.headers ?? {};
        cfg.headers.Authorization = `Bearer ${newAccess}`;
        return client(cfg); // 重放原请求
      }
      // refresh 失败 → 跳登录
      redirectToLogin();
      return Promise.reject(error);
    }

    // 刷新接口本身 401（refresh token 也失效）→ 跳登录
    if (response?.status === 401 && cfg?.url?.includes('/api/auth/refresh')) {
      clearToken();
      clearRefreshToken();
      redirectToLogin();
    }

    return Promise.reject(error);
  },
);

function redirectToLogin() {
  if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
    // 记录来源页，登录成功后跳回
    sessionStorage.setItem('reviewlens_from', window.location.pathname + window.location.search);
    window.location.href = '/login';
  }
}

// ---------- 错误信息提取工具 ----------
export function getErrorMessage(e: unknown, fallback = '操作失败'): string {
  if (axios.isAxiosError(e)) {
    const detail = (e.response?.data as { detail?: string | string[] } | undefined)?.detail;
    if (Array.isArray(detail)) return detail.join('；');
    if (typeof detail === 'string' && detail) return detail;
    if (e.message) return e.message;
  }
  return fallback;
}

export interface Envelope<T> {
  code: number;
  data: T;
  message?: string;
}

export default client;
