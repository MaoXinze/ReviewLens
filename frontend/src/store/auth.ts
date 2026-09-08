import { create } from 'zustand';
import type { UserOut } from '../api/auth';
import * as authApi from '../api/auth';
import { clearToken, setToken, clearRefreshToken, setRefreshToken } from '../api/client';

interface AuthState {
  user: UserOut | null;
  /** 是否已尝试过拉取用户信息（用于区分"未登录"与"加载中"） */
  initialized: boolean;
  setUser: (user: UserOut | null) => void;
  /** 登录成功后写入 token（用户信息随后由 fetchMe 拉取） */
  signIn: (accessToken: string, refreshToken: string) => void;
  /** 退出登录：清 token + 清用户信息 */
  signOut: () => void;
  /** 拉取当前用户信息，失败（未登录）时清空状态 */
  fetchMe: () => Promise<UserOut | null>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initialized: false,
  setUser: (user) => set({ user, initialized: true }),
  signIn: (accessToken, refreshToken) => {
    setToken(accessToken);
    setRefreshToken(refreshToken);
    set({ user: null, initialized: false });
  },
  signOut: () => {
    clearToken();
    clearRefreshToken();
    set({ user: null, initialized: true });
  },
  fetchMe: async () => {
    try {
      const user = await authApi.getMe();
      set({ user, initialized: true });
      return user;
    } catch {
      clearToken();
      clearRefreshToken();
      set({ user: null, initialized: true });
      return null;
    }
  },
}));
