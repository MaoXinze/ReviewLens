import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import RequireAuth from '../RequireAuth';

// 可控的 zustand store 状态
let storeState: { user: unknown; initialized: boolean };
vi.mock('../../store/auth', () => ({
  useAuthStore: () => storeState,
}));

// mock client token
vi.mock('../../api/client', () => ({
  getToken: vi.fn(),
}));
import { getToken } from '../../api/client';
const getTokenMock = getToken as unknown as ReturnType<typeof vi.fn>;

function renderWithAuth(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/protected"
          element={
            <RequireAuth>
              <div>Protected Content</div>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('RequireAuth', () => {
  beforeEach(() => {
    getTokenMock.mockReset();
    storeState = { user: null, initialized: false };
  });

  it('无 token 时重定向到登录页', () => {
    getTokenMock.mockReturnValue(null);
    renderWithAuth('/protected');
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });

  it('有 token 且用户已加载时渲染子内容', () => {
    getTokenMock.mockReturnValue('token-1');
    storeState = {
      user: { id: 'u1', email: 'a@b.com', role: 'operator' },
      initialized: true,
    };
    renderWithAuth('/protected');
    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });
});
