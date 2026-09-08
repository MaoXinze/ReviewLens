import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import RegisterPage from '../Register';

const registerMock = vi.fn();
vi.mock('../../api/auth', () => ({
  register: (...a: unknown[]) => registerMock(...a),
  login: vi.fn(),
  getMe: vi.fn(),
  refresh: vi.fn(),
  updateMe: vi.fn(),
}));

function renderRegister() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RegisterPage', () => {
  beforeEach(() => {
    registerMock.mockReset();
  });

  it('渲染注册表单字段', () => {
    renderRegister();
    expect(screen.getByPlaceholderText('you@example.com')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('至少 8 位')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('再次输入密码')).toBeInTheDocument();
  });

  it('两次密码不一致时校验失败', async () => {
    renderRegister();
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'a@b.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('至少 8 位'), {
      target: { value: 'password123' },
    });
    fireEvent.change(screen.getByPlaceholderText('再次输入密码'), {
      target: { value: 'different' },
    });
    fireEvent.click(screen.getByRole('button', { name: '注 册' }));

    await waitFor(() => {
      expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument();
    });
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('注册成功后展示自动生成的账号名并引导登录', async () => {
    registerMock.mockResolvedValueOnce({
      id: 'u1',
      email: 'a@b.com',
      username: 'a_b1a2',
    });
    renderRegister();
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'a@b.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('至少 8 位'), {
      target: { value: 'password123' },
    });
    fireEvent.change(screen.getByPlaceholderText('再次输入密码'), {
      target: { value: 'password123' },
    });
    fireEvent.click(screen.getByRole('button', { name: '注 册' }));

    await waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith({
        email: 'a@b.com',
        password: 'password123',
        full_name: undefined,
      });
    });
    // 成功页展示自动生成的账号名与去登录入口
    await waitFor(() => {
      expect(screen.getByText('a_b1a2')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '去登录' })).toBeInTheDocument();
  });
});
