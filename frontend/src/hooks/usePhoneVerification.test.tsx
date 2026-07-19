import { StrictMode, type ReactNode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types/api';
import { usePhoneVerification } from './usePhoneVerification';

const apiMocks = vi.hoisted(() => ({
  getMe: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  acceptVerifiedProfile: vi.fn(),
}));

vi.mock('../services/api', () => apiMocks);
vi.mock('../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

const unverifiedUser: User = {
  telegram_id: 101,
  first_name: 'Customer',
  last_name: null,
  username: 'customer',
  phone_number: null,
  phone_verified: false,
  language: 'en',
  role: 'customer',
  inplace_online_payment_enabled: false,
};

const verifiedUser: User = {
  ...unverifiedUser,
  phone_number: '+998901234567',
  phone_verified: true,
};

function setTelegram(
  requestContact?: (callback: (shared: boolean) => void) => void,
  options: { initData?: string; supportsContactApi?: boolean } = {},
) {
  const isVersionAtLeast = vi.fn(() => options.supportsContactApi ?? true);
  Object.defineProperty(window, 'Telegram', {
    configurable: true,
    value: {
      WebApp: {
        initData: options.initData ?? 'telegram-init-data',
        isVersionAtLeast,
        requestContact,
      },
    },
  });
  return { isVersionAtLeast };
}

function profileResponse(user: User) {
  return { data: { data: user } };
}

describe('usePhoneVerification', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    setTelegram(vi.fn());
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('accepts an immediately verified profile after contact sharing', async () => {
    let contactCallback: ((shared: boolean) => void) | undefined;
    const requestContact = vi.fn((callback: (shared: boolean) => void) => {
      contactCallback = callback;
    });
    setTelegram(requestContact);
    apiMocks.getMe.mockResolvedValue(profileResponse(verifiedUser));
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    act(() => result.current.requestPhone());
    expect(result.current.status).toBe('requesting');

    await act(async () => {
      contactCallback?.(true);
      await Promise.resolve();
    });

    expect(apiMocks.getMe).toHaveBeenCalledTimes(1);
    expect(authState.acceptVerifiedProfile).toHaveBeenCalledWith(verifiedUser);
  });

  it('polls immediately and every 1.5 seconds until verification succeeds', async () => {
    let contactCallback: ((shared: boolean) => void) | undefined;
    setTelegram((callback) => { contactCallback = callback; });
    apiMocks.getMe
      .mockResolvedValueOnce(profileResponse(unverifiedUser))
      .mockResolvedValueOnce(profileResponse(verifiedUser));
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    await act(async () => {
      result.current.requestPhone();
      contactCallback?.(true);
      await Promise.resolve();
    });
    expect(apiMocks.getMe).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_500);
    });

    expect(apiMocks.getMe).toHaveBeenCalledTimes(2);
    expect(authState.acceptVerifiedProfile).toHaveBeenCalledWith(verifiedUser);
  });

  it('stops after exactly ten successful-but-unverified profile requests', async () => {
    let contactCallback: ((shared: boolean) => void) | undefined;
    setTelegram((callback) => { contactCallback = callback; });
    apiMocks.getMe.mockResolvedValue(profileResponse(unverifiedUser));
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    await act(async () => {
      result.current.requestPhone();
      contactCallback?.(true);
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(13_500);
    });

    expect(apiMocks.getMe).toHaveBeenCalledTimes(10);
    expect(result.current.status).toBe('delayed');
  });

  it('reports a network error when all ten profile requests fail', async () => {
    let contactCallback: ((shared: boolean) => void) | undefined;
    setTelegram((callback) => { contactCallback = callback; });
    apiMocks.getMe.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    await act(async () => {
      result.current.requestPhone();
      contactCallback?.(true);
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(13_500);
    });

    expect(apiMocks.getMe).toHaveBeenCalledTimes(10);
    expect(result.current.status).toBe('network_error');
  });

  it('reports delayed when at least one response succeeds but remains unverified', async () => {
    let contactCallback: ((shared: boolean) => void) | undefined;
    setTelegram((callback) => { contactCallback = callback; });
    apiMocks.getMe
      .mockResolvedValueOnce(profileResponse(unverifiedUser))
      .mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    await act(async () => {
      result.current.requestPhone();
      contactCallback?.(true);
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(13_500);
    });

    expect(apiMocks.getMe).toHaveBeenCalledTimes(10);
    expect(result.current.status).toBe('delayed');
  });

  it('stays declined until a visible manual action requests contact again', () => {
    const callbacks: Array<(shared: boolean) => void> = [];
    const requestContact = vi.fn((callback: (shared: boolean) => void) => {
      callbacks.push(callback);
    });
    setTelegram(requestContact);
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    act(() => result.current.requestPhone());
    act(() => callbacks[0]?.(false));
    expect(result.current.status).toBe('declined');
    expect(requestContact).toHaveBeenCalledTimes(1);

    act(() => result.current.requestPhone());
    expect(result.current.status).toBe('requesting');
    expect(requestContact).toHaveBeenCalledTimes(2);
  });

  it('checks the profile again without reopening the native contact prompt', async () => {
    const requestContact = vi.fn();
    setTelegram(requestContact);
    apiMocks.getMe.mockResolvedValue(profileResponse(verifiedUser));
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    await act(async () => {
      await result.current.checkAgain();
    });

    expect(apiMocks.getMe).toHaveBeenCalledTimes(1);
    expect(requestContact).not.toHaveBeenCalled();
    expect(authState.acceptVerifiedProfile).toHaveBeenCalledWith(verifiedUser);
  });

  it('reports unsupported when Telegram lacks requestContact', () => {
    setTelegram(undefined);

    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    expect(result.current.status).toBe('unsupported');
    act(() => result.current.requestPhone());
    expect(result.current.status).toBe('unsupported');
  });

  it('reports outside Telegram when the globally loaded SDK has empty initData', async () => {
    const requestContact = vi.fn();
    const { isVersionAtLeast } = setTelegram(requestContact, { initData: '   ' });
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    expect(result.current.status).toBe('outside_telegram');
    act(() => result.current.requestPhone());
    await act(async () => {
      await result.current.checkAgain();
    });

    expect(result.current.status).toBe('outside_telegram');
    expect(requestContact).not.toHaveBeenCalled();
    expect(isVersionAtLeast).not.toHaveBeenCalled();
    expect(apiMocks.getMe).not.toHaveBeenCalled();
  });

  it('reports unsupported inside Telegram before WebApp 6.9', async () => {
    const requestContact = vi.fn();
    const { isVersionAtLeast } = setTelegram(requestContact, { supportsContactApi: false });
    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    expect(result.current.status).toBe('unsupported');
    act(() => result.current.requestPhone());
    await act(async () => {
      await result.current.checkAgain();
    });

    expect(result.current.status).toBe('unsupported');
    expect(requestContact).not.toHaveBeenCalled();
    expect(isVersionAtLeast).toHaveBeenCalledWith('6.9');
    expect(apiMocks.getMe).not.toHaveBeenCalled();
  });

  it('reports outside Telegram without a manual phone fallback', () => {
    delete (window as Window & { Telegram?: unknown }).Telegram;

    const { result } = renderHook(() => usePhoneVerification({ autoRequest: false }));

    expect(result.current.status).toBe('outside_telegram');
    act(() => result.current.requestPhone());
    expect(result.current.status).toBe('outside_telegram');
  });

  it('claims the automatic prompt once and keeps its callback active through StrictMode effects', async () => {
    let contactCallback: ((shared: boolean) => void) | undefined;
    const requestContact = vi.fn((callback: (shared: boolean) => void) => {
      contactCallback = callback;
    });
    setTelegram(requestContact);
    apiMocks.getMe.mockResolvedValue(profileResponse(verifiedUser));
    const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;

    const first = renderHook(() => usePhoneVerification({ autoRequest: true }), { wrapper });
    expect(requestContact).toHaveBeenCalledTimes(1);

    await act(async () => {
      contactCallback?.(true);
      await Promise.resolve();
    });
    expect(authState.acceptVerifiedProfile).toHaveBeenCalledWith(verifiedUser);

    first.unmount();
    renderHook(() => usePhoneVerification({ autoRequest: true }), { wrapper });

    expect(requestContact).toHaveBeenCalledTimes(1);
  });
});
