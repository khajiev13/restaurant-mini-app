import { StrictMode } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useVisiblePolling } from './useVisiblePolling';

const setVisibility = (value: DocumentVisibilityState) => {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value,
  });
};

const flushPromises = async () => {
  await act(async () => {
    await Promise.resolve();
  });
};

describe('useVisiblePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    setVisibility('visible');
  });

  afterEach(() => {
    setVisibility('visible');
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('loads immediately and polls every 15 seconds', async () => {
    const load = vi.fn().mockResolvedValue({ value: 1 });
    const { result, unmount } = renderHook(() =>
      useVisiblePolling(load, 15_000, 'overview'),
    );

    await flushPromises();
    expect(result.current.data).toEqual({ value: 1 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(load).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('reuses the initial request during StrictMode effect replay', async () => {
    let resolveLoad!: (value: { value: number }) => void;
    const pending = new Promise<{ value: number }>((resolve) => {
      resolveLoad = resolve;
    });
    const load = vi.fn(() => pending);
    const { result } = renderHook(
      () => useVisiblePolling(load, 15_000, 'overview'),
      { wrapper: StrictMode },
    );

    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveLoad({ value: 1 });
      await pending;
    });
    expect(result.current.data).toEqual({ value: 1 });
  });

  it('stops while hidden and refreshes when visible again', async () => {
    const load = vi.fn().mockResolvedValue({ value: 1 });
    setVisibility('hidden');
    renderHook(() => useVisiblePolling(load, 15_000, 'overview'));
    await flushPromises();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(load).toHaveBeenCalledTimes(1);

    setVisibility('visible');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flushPromises();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(load).toHaveBeenCalledTimes(3);

    setVisibility('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(load).toHaveBeenCalledTimes(3);

    setVisibility('visible');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await flushPromises();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(load).toHaveBeenCalledTimes(5);
  });

  it('keeps prior data when a refresh fails', async () => {
    const failure = { response: { status: 503 } };
    const load = vi
      .fn()
      .mockResolvedValueOnce({ value: 1 })
      .mockRejectedValueOnce(failure);
    const { result } = renderHook(() =>
      useVisiblePolling(load, 15_000, 'overview'),
    );
    await flushPromises();

    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.data).toEqual({ value: 1 });
    expect(result.current.error).toBe(failure);
  });

  it('reloads on key change and ignores a superseded response', async () => {
    let resolveFirst!: (value: { value: string }) => void;
    const first = new Promise<{ value: string }>((resolve) => {
      resolveFirst = resolve;
    });
    const loadFirst = vi.fn(() => first);
    const loadSecond = vi.fn().mockResolvedValue({ value: 'second' });
    const { result, rerender } = renderHook(
      ({ tableId }) =>
        useVisiblePolling(
          tableId === 'one' ? loadFirst : loadSecond,
          15_000,
          tableId,
        ),
      { initialProps: { tableId: 'one' } },
    );

    rerender({ tableId: 'two' });
    await flushPromises();
    expect(result.current.data).toEqual({ value: 'second' });

    resolveFirst({ value: 'first' });
    await flushPromises();
    expect(result.current.data).toEqual({ value: 'second' });
  });

  it('invalidates the original request when a key changes away and back', async () => {
    let resolveFirstA!: (value: { value: string }) => void;
    let resolveSecondA!: (value: { value: string }) => void;
    const firstA = new Promise<{ value: string }>((resolve) => {
      resolveFirstA = resolve;
    });
    const secondA = new Promise<{ value: string }>((resolve) => {
      resolveSecondA = resolve;
    });
    const loadA = vi
      .fn<() => Promise<{ value: string }>>()
      .mockReturnValueOnce(firstA)
      .mockReturnValueOnce(secondA);
    const loadB = vi.fn(
      () => new Promise<{ value: string }>(() => undefined),
    );
    const { result, rerender } = renderHook(
      ({ requestKey }) =>
        useVisiblePolling(
          requestKey === 'a' ? loadA : loadB,
          15_000,
          requestKey,
        ),
      { initialProps: { requestKey: 'a' } },
    );

    rerender({ requestKey: 'b' });
    rerender({ requestKey: 'a' });
    expect(loadA).toHaveBeenCalledTimes(2);
    expect(loadB).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveSecondA({ value: 'current a' });
      await secondA;
    });
    expect(result.current.data).toEqual({ value: 'current a' });

    await act(async () => {
      resolveFirstA({ value: 'stale a' });
      await firstA;
    });
    expect(result.current.data).toEqual({ value: 'current a' });
  });

  it('deduplicates overlapping refreshes for the active key', async () => {
    let resolveLoad!: (value: { value: number }) => void;
    const pending = new Promise<{ value: number }>((resolve) => {
      resolveLoad = resolve;
    });
    const load = vi.fn(() => pending);
    const { result } = renderHook(() =>
      useVisiblePolling(load, 15_000, 'overview'),
    );

    expect(load).toHaveBeenCalledTimes(1);
    const firstRefresh = result.current.refresh();
    const secondRefresh = result.current.refresh();
    expect(firstRefresh).toBe(secondRefresh);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveLoad({ value: 1 });
      await firstRefresh;
    });
    expect(result.current.data).toEqual({ value: 1 });

    await act(async () => {
      await result.current.refresh();
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('cleans up its timer and visibility listener on unmount', async () => {
    const addEventListener = vi.spyOn(document, 'addEventListener');
    const removeEventListener = vi.spyOn(document, 'removeEventListener');
    const load = vi.fn().mockResolvedValue({ value: 1 });
    const { unmount } = renderHook(() =>
      useVisiblePolling(load, 15_000, 'overview'),
    );
    await flushPromises();

    const visibilityRegistration = addEventListener.mock.calls.find(
      ([type]) => type === 'visibilitychange',
    );
    expect(visibilityRegistration).toBeDefined();

    unmount();
    expect(removeEventListener).toHaveBeenCalledWith(
      'visibilitychange',
      visibilityRegistration?.[1],
    );
    expect(vi.getTimerCount()).toBe(0);

    setVisibility('hidden');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    setVisibility('visible');
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(load).toHaveBeenCalledTimes(1);
  });
});
