import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import LoginPage from '../Login';

// mock auth API
const loginMock = vi.fn();
const getMeMock = vi.fn();
vi.mock('../../api/auth', () => ({
  login: (...a: unknown[]) => loginMock(...a),
  getMe: (...a: unknown[]) => getMeMock(...a),
  register: vi.fn(),
  refresh: vi.fn(),
  updateMe: vi.fn(),
}));

// mock zustand store
const signInMock = vi.fn();
const fetchMeMock = vi.fn();
vi.mock('../../store/auth', () => ({
  useAuthStore: () => ({
    user: null,
    initialized: true,
    signIn: signInMock,
    fetchMe: fetchMeMock,
  }),
}));

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    localStorage.clear();
    loginMock.mockReset();
    getMeMock.mockReset();
    fetchMeMock.mockReset();
    signInMock.mockReset();
  });

  it('渲染邮箱与密码输入框和登录按钮', () => {
    renderLogin();
    expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('请输入密码')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '登 录' })).toBeInTheDocument();
  });

  it('登录成功后写入 token 并跳转 Dashboard', async () => {
    loginMock.mockResolvedValueOnce({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      expires_in: 3600,
    });
    getMeMock.mockResolvedValueOnce({ id: 'u1', email: 'a@b.com', role: 'operator' });

    renderLogin();
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'a@b.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '登 录' }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith({ account: 'a@b.com', password: 'password123' });
    });
    await waitFor(() => {
      expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
    });
  });

  it('登录失败时显示后端错误信息', async () => {
    loginMock.mockRejectedValueOnce({
      response: { data: { detail: '邮箱或密码错误' } },
    });

    renderLogin();
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'a@b.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('请输入密码'), {
      target: { value: 'wrong' },
    });
    fireEvent.click(screen.getByRole('button', { name: '登 录' }));

    await waitFor(() => {
      expect(screen.getByText('邮箱或密码错误')).toBeInTheDocument();
    });
  });
});
