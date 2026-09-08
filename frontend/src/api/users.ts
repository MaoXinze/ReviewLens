import client from './client';
import type { UserOut, UserRole } from './auth';

// ---------- API ----------

export interface UserListResponse {
  items: UserOut[];
  total: number;
  page: number;
  page_size: number;
}

export function listUsers(params?: { page?: number; page_size?: number }) {
  return client
    .get<{ data: UserListResponse }>('/api/v1/users', { params })
    .then((r) => r.data.data);
}

export function updateUserRole(userId: string, role: UserRole) {
  return client
    .patch<{ data: UserOut }>(`/api/v1/users/${userId}/role`, { role })
    .then((r) => r.data.data);
}
