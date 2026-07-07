import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../../types/api';

const apiMocks = vi.hoisted(() => ({
  authenticateTelegram: vi.fn(),
  getMe: vi.fn(),
}));

const i18nMock = vi.hoisted(() => ({
  default: {
    language: 'en',
    changeLanguage: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('../../services/api', () => apiMocks);
vi.mock('../../i18n', () => i18nMock);

const staffUser: User = {
  telegram_id: 1,
  first_name: 'Staff',
  last_name: 'Member',
  username: 'staffer',
  phone_number: '+998900000000',
  language: 'en',
  role: 'staff',
};

const adminUser: User = {
  ...staffUser,
  telegram_id: 2,
  first_name: 'Admin',
  role: 'admin',
};

async function loadStore() {
  vi.resetModules();
  const mod = await import('../authStore');
  return mod.useAuthStore;
}

describe('authStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    Object.defineProperty(window, 'Telegram', {
      configurable: true,
      value: {
        WebApp: {
          initData: 'telegram-init-data',
        },
      },
    });
  });

  it('authenticate stores the token and hydrated user', async () => {
    apiMocks.authenticateTelegram.mockResolvedValue({
      data: { data: { access_token: 'jwt-123' } },
    });
    apiMocks.getMe.mockResolvedValue({
      data: { data: staffUser },
    });

    const useAuthStore = await loadStore();

    await useAuthStore.getState().authenticate();

    expect(useAuthStore.getState()).toMatchObject({
      token: 'jwt-123',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
    expect(localStorage.getItem('jwt')).toBe('jwt-123');
  });

  it('starts unresolved for a Telegram cold start without a stored token', async () => {
    localStorage.clear();
    const useAuthStore = await loadStore();

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      hasHydratedUser: false,
      hasResolvedInitialAuth: false,
    });
  });

  it('starts resolved outside Telegram when no token is stored', async () => {
    localStorage.clear();
    delete (window as Window & { Telegram?: unknown }).Telegram;

    const useAuthStore = await loadStore();

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
  });

  it('refreshMe replaces the stored user', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'jwt-123',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
    apiMocks.getMe.mockResolvedValue({
      data: { data: adminUser },
    });

    const user = await useAuthStore.getState().refreshMe();

    expect(user).toEqual(adminUser);
    expect(useAuthStore.getState().user).toEqual(adminUser);
  });

  it('refreshMe clears stale user data when profile refresh fails', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'jwt-123',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: false,
    });
    apiMocks.getMe.mockRejectedValue(new Error('refresh failed'));

    const user = await useAuthStore.getState().refreshMe();

    expect(user).toBeNull();
    expect(useAuthStore.getState()).toMatchObject({
      token: 'jwt-123',
      user: null,
      isAuthenticated: true,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
  });

  it('authenticate clears stale auth state when login fails', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'stale-jwt',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: false,
    });
    localStorage.setItem('jwt', 'stale-jwt');
    apiMocks.authenticateTelegram.mockRejectedValue(new Error('auth failed'));

    await useAuthStore.getState().authenticate();

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
    expect(localStorage.getItem('jwt')).toBeNull();
  });

  it('authenticate clears auth state when profile hydration fails after login', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'stale-jwt',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: false,
    });
    localStorage.setItem('jwt', 'stale-jwt');
    apiMocks.authenticateTelegram.mockResolvedValue({
      data: { data: { access_token: 'new-jwt' } },
    });
    apiMocks.getMe.mockRejectedValue(new Error('profile failed'));

    await useAuthStore.getState().authenticate();

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
    expect(localStorage.getItem('jwt')).toBeNull();
  });

  it('logout clears auth state', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'jwt-123',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
    localStorage.setItem('jwt', 'jwt-123');

    useAuthStore.getState().logout();

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
    });
    expect(localStorage.getItem('jwt')).toBeNull();
    expect(localStorage.getItem('manual_logout')).toBe('1');
  });
});
