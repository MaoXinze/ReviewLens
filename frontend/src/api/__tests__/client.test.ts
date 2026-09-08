import { describe, expect, it, beforeEach } from 'vitest';
import { getToken, setToken, clearToken } from '../client';

describe('client token 处理', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('setToken 存入 localStorage reviewlens_token', () => {
    setToken('abc123');
    expect(localStorage.getItem('reviewlens_token')).toBe('abc123');
    expect(getToken()).toBe('abc123');
  });

  it('getToken 在无 token 时返回 null', () => {
    expect(getToken()).toBeNull();
  });

  it('clearToken 移除 token', () => {
    setToken('abc123');
    clearToken();
    expect(getToken()).toBeNull();
  });
});