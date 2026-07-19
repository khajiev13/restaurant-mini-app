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
  inplace_online_payment_enabled: false,
  first_name: 'Staff',
  last_name: 'Member',
  username: 'staffer',
  phone_number: '+998900000000',
  phone_verified: true,
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

  it('bootstrap removes a stale manual logout marker and authenticates Telegram initData', async () => {
    localStorage.setItem('manual_logout', '1');
    localStorage.setItem('jwt', 'stale-jwt');
    apiMocks.authenticateTelegram.mockResolvedValue({
      data: { data: { access_token: 'fresh-jwt' } },
    });
    apiMocks.getMe.mockResolvedValue({ data: { data: staffUser } });
    const useAuthStore = await loadStore();

    await useAuthStore.getState().bootstrapAuth();

    expect(apiMocks.authenticateTelegram).toHaveBeenCalledWith('telegram-init-data');
    expect(localStorage.getItem('manual_logout')).toBeNull();
    expect(localStorage.getItem('jwt')).toBe('fresh-jwt');
    expect(useAuthStore.getState().user).toEqual(staffUser);
  });

  it('exchanges Telegram initData on launch even when a JWT already exists', async () => {
    localStorage.setItem('jwt', 'stored-jwt');
    apiMocks.authenticateTelegram.mockResolvedValue({
      data: { data: { access_token: 'launch-jwt' } },
    });
    apiMocks.getMe.mockResolvedValue({ data: { data: staffUser } });
    const useAuthStore = await loadStore();

    await useAuthStore.getState().bootstrapAuth();

    expect(apiMocks.authenticateTelegram).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('jwt')).toBe('launch-jwt');
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

  it('refreshMe keeps role routing blocked with a retryable error when profile refresh fails transiently', async () => {
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
      hasHydratedUser: false,
      hasResolvedInitialAuth: true,
      authError: 'auth.retry_message',
    });
  });

  it('refreshMe keeps routing blocked with a retryable error when profile refresh is unauthorized', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'jwt-123',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: false,
    });
    localStorage.setItem('jwt', 'jwt-123');
    apiMocks.getMe.mockRejectedValue({ response: { status: 401 } });

    const user = await useAuthStore.getState().refreshMe();

    expect(user).toBeNull();
    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      isAuthenticated: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: true,
      authError: 'auth.retry_message',
    });
    expect(localStorage.getItem('jwt')).toBeNull();
  });

  it('authenticate blocks customer rendering with a retryable error when login fails', async () => {
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
      hasHydratedUser: false,
      hasResolvedInitialAuth: true,
      authError: 'auth.retry_message',
    });
    expect(localStorage.getItem('jwt')).toBeNull();
  });

  it('authenticate keeps role routing blocked with a retryable error when profile hydration fails transiently after login', async () => {
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
      token: 'new-jwt',
      user: null,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: true,
      authError: 'auth.retry_message',
    });
    expect(localStorage.getItem('jwt')).toBe('new-jwt');
  });

  it('authenticate keeps routing blocked with a retryable error when profile hydration is unauthorized', async () => {
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
    apiMocks.getMe.mockRejectedValue({ response: { status: 401 } });

    await useAuthStore.getState().authenticate();

    expect(useAuthStore.getState()).toMatchObject({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      hasHydratedUser: false,
      hasResolvedInitialAuth: true,
      authError: 'auth.retry_message',
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
    expect(localStorage.getItem('manual_logout')).toBeNull();
  });

  it('accepts a verified profile returned by the shared phone hook', async () => {
    const useAuthStore = await loadStore();
    useAuthStore.setState({
      token: 'jwt-123',
      user: staffUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
      authError: null,
    });
    const verifiedAdmin = { ...adminUser, phone_verified: true };

    useAuthStore.getState().acceptVerifiedProfile(verifiedAdmin);

    expect(useAuthStore.getState()).toMatchObject({
      user: verifiedAdmin,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
      authError: null,
    });
  });
});
