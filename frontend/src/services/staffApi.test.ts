import {
  AxiosError,
  AxiosHeaders,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ApiResponse } from '../types/api';
import type { StaffOrder } from '../types/staff';
import api from './api';
import { reconcileStaffOrderTake, takeStaffOrder } from './staffApi';

const STARTED_AT = Date.parse('2026-07-18T00:00:00.000Z');

const makeOrder = (id: string): StaffOrder => ({
  id,
  order_number: 'D-42',
  status: 'READY',
  created_at: '2026-07-18T00:00:00Z',
  status_updated_at: null,
  assigned_at: null,
  delivered_at: null,
  customer: {
    telegram_id: 42,
    first_name: 'Staff',
    last_name: null,
    phone_number: null,
  },
  address: {
    full_address: 'Test address',
    latitude: null,
    longitude: null,
    entrance: null,
    apartment: null,
    floor: null,
    courier_instructions: null,
  },
  items: [],
  total_amount: 100,
  delivery_fee: 0,
  payment_method: 'cash',
  payment_status: null,
  assigned_staff: null,
});

const success = <T>(data: T): AxiosResponse<ApiResponse<T>> => ({
  data: { success: true, data },
  status: 200,
  statusText: 'OK',
  headers: new AxiosHeaders(),
  config: { headers: new AxiosHeaders() },
});

describe('staffApi take-order safety', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(STARTED_AT);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('uses exactly a 15-second timeout for the take-order POST', async () => {
    const order = makeOrder('target-order');
    const post = vi.spyOn(api, 'post').mockResolvedValue(success(order));

    await takeStaffOrder(order.id);

    expect(post).toHaveBeenCalledWith(
      '/staff/orders/target-order/take',
      undefined,
      { timeout: 15000 },
    );
  });

  it('returns same immediately and passes the exact bounded read config', async () => {
    const order = makeOrder('target-order');
    const controller = new AbortController();
    const get = vi.spyOn(api, 'get').mockResolvedValue(success(order));
    const post = vi.spyOn(api, 'post');

    await expect(reconcileStaffOrderTake(order.id, STARTED_AT, controller.signal)).resolves.toEqual({
      outcome: 'same',
      order,
    });

    expect(get).toHaveBeenCalledOnce();
    expect(get).toHaveBeenCalledWith('/staff/orders/active', {
      timeout: 2000,
      signal: controller.signal,
      skipRetry: true,
    });
    expect(post).not.toHaveBeenCalled();
  });

  it('returns different immediately for another active order', async () => {
    const activeOrder = makeOrder('another-order');
    vi.spyOn(api, 'get').mockResolvedValue(success(activeOrder));

    await expect(
      reconcileStaffOrderTake('target-order', STARTED_AT, new AbortController().signal),
    ).resolves.toEqual({ outcome: 'different', order: activeOrder });
  });

  it('starts reads at offsets 0, 5000, and 11000 from mutation start', async () => {
    const readTimes: number[] = [];
    const get = vi.spyOn(api, 'get').mockImplementation(() => {
      readTimes.push(Date.now());
      return Promise.resolve(success<StaffOrder | null>(null));
    });
    const controller = new AbortController();

    const pending = reconcileStaffOrderTake('target-order', STARTED_AT, controller.signal);
    await vi.advanceTimersByTimeAsync(0);
    expect(readTimes).toEqual([STARTED_AT]);

    await vi.advanceTimersByTimeAsync(4999);
    expect(get).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(readTimes).toEqual([STARTED_AT, STARTED_AT + 5000]);

    await vi.advanceTimersByTimeAsync(5999);
    expect(get).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);

    await expect(pending).resolves.toEqual({ outcome: 'none' });
    expect(readTimes).toEqual([STARTED_AT, STARTED_AT + 5000, STARTED_AT + 11000]);
    expect(get.mock.calls).toEqual([
      ['/staff/orders/active', { timeout: 2000, signal: controller.signal, skipRetry: true }],
      ['/staff/orders/active', { timeout: 2000, signal: controller.signal, skipRetry: true }],
      ['/staff/orders/active', { timeout: 2000, signal: controller.signal, skipRetry: true }],
    ]);
  });

  it('stops when the delayed second read finds the target order', async () => {
    const order = makeOrder('target-order');
    const get = vi.spyOn(api, 'get')
      .mockResolvedValueOnce(success<StaffOrder | null>(null))
      .mockResolvedValueOnce(success(order));

    const pending = reconcileStaffOrderTake(order.id, STARTED_AT, new AbortController().signal);
    await vi.advanceTimersByTimeAsync(5000);

    await expect(pending).resolves.toEqual({ outcome: 'same', order });
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('finds a 9.5-second backend commit only on the read at or after 11 seconds', async () => {
    const order = makeOrder('target-order');
    const readTimes: number[] = [];
    const get = vi.spyOn(api, 'get').mockImplementation(() => {
      readTimes.push(Date.now());
      return Promise.resolve(
        success<StaffOrder | null>(Date.now() >= STARTED_AT + 9500 ? order : null),
      );
    });

    const pending = reconcileStaffOrderTake(order.id, STARTED_AT, new AbortController().signal);
    await vi.advanceTimersByTimeAsync(9500);
    expect(get).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1499);
    expect(get).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(1);

    await expect(pending).resolves.toEqual({ outcome: 'same', order });
    expect(readTimes).toEqual([STARTED_AT, STARTED_AT + 5000, STARTED_AT + 11000]);
  });

  it('returns none after at most three empty or unusable reads', async () => {
    const get = vi.spyOn(api, 'get')
      .mockRejectedValueOnce(new Error('network'))
      // Deliberately malformed data exercises the unusable-response boundary.
      .mockResolvedValueOnce(success({} as StaffOrder))
      .mockResolvedValueOnce(success<StaffOrder | null>(null));
    const post = vi.spyOn(api, 'post');

    const pending = reconcileStaffOrderTake(
      'target-order',
      STARTED_AT,
      new AbortController().signal,
    );
    await vi.advanceTimersByTimeAsync(11000);

    await expect(pending).resolves.toEqual({ outcome: 'none' });
    expect(get).toHaveBeenCalledTimes(3);
    expect(post).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(60000);
    expect(get).toHaveBeenCalledTimes(3);
  });

  it('cancels during a scheduled wait without starting another read', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue(success<StaffOrder | null>(null));
    const controller = new AbortController();
    const pending = reconcileStaffOrderTake('target-order', STARTED_AT, controller.signal);
    const rejection = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    await vi.advanceTimersByTimeAsync(0);
    expect(get).toHaveBeenCalledOnce();

    controller.abort();
    await rejection;
    await vi.advanceTimersByTimeAsync(20000);

    expect(get).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('honors skipRetry in the shared Axios response interceptor', async () => {
    const originalAdapter = api.defaults.adapter;
    const adapter = vi.fn((config: InternalAxiosRequestConfig) =>
      Promise.reject(new AxiosError('timed out', 'ECONNABORTED', config)));
    api.defaults.adapter = adapter;
    const controller = new AbortController();
    const config = {
      timeout: 2000,
      signal: controller.signal,
      skipRetry: true,
    } as AxiosRequestConfig & { skipRetry: true };

    try {
      const request = api.get('/staff/orders/active', config);
      const rejection = expect(request).rejects.toMatchObject({ code: 'ECONNABORTED' });
      await vi.runAllTimersAsync();
      await rejection;
      expect(adapter).toHaveBeenCalledOnce();
    } finally {
      api.defaults.adapter = originalAdapter;
    }
  });
});
