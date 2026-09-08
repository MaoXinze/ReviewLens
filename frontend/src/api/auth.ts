import client from './client';

// ---------- 类型 ----------

export type UserRole = 'admin' | 'analyst' | 'operator';

export interface UserOut {
  id: string;
  email: string;
  phone: string | null;
  username: string | null;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterResponse {
  id: string;
  email: string;
  phone: string | null;
  username: string | null;
  full_name: string | null;
  role: UserRole;
}

// ---------- API ----------

export interface RegisterBody {
  email?: string;
  phone?: string;
  password: string;
  full_name?: string;
  /** 账号名：缺省时由服务端自动生成 */
  username?: string;
}

export function register(body: RegisterBody) {
  return client
    .post<{ data: RegisterResponse }>('/api/auth/register', body)
    .then((r) => r.data.data);
}

/** 登录：account 为 邮箱 / 手机号 / 账号名 任意一种 */
export function login(body: { account: string; password: string }) {
  return client
    .post<{ data: TokenResponse }>('/api/auth/login', body)
    .then((r) => r.data.data);
}

export function refresh(refreshToken: string) {
  return client
    .post<{ data: TokenResponse }>('/api/auth/refresh', { refresh_token: refreshToken })
    .then((r) => r.data.data);
}

export function getMe() {
  return client.get<{ data: UserOut }>('/api/auth/me').then((r) => r.data.data);
}

export function updateMe(body: { full_name?: string }) {
  return client.put<{ data: UserOut }>('/api/auth/me', body).then((r) => r.data.data);
}
