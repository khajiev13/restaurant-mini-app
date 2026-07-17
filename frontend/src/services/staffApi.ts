import { isAxiosError, type AxiosRequestConfig, type AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse } from '../types/api';
import type { StaffOrder } from '../types/staff';

const TAKE_ORDER_TIMEOUT_MS = 15000;
const RECONCILIATION_READ_TIMEOUT_MS = 2000;
const RECONCILIATION_READ_OFFSETS_MS = [0, 5000, 11000] as const;

type ReconciliationRequestConfig = AxiosRequestConfig & {
  skipRetry: true;
};

export type StaffOrderTakeReconciliationResult =
  | { outcome: 'same'; order: StaffOrder }
  | { outcome: 'different'; order: StaffOrder }
  | { outcome: 'none' };

export const isStaffOrderTakeTransportAmbiguity = (error: unknown): boolean =>
  isAxiosError(error) && !error.response;

const abortReason = (signal: AbortSignal): Error =>
  signal.reason instanceof Error
    ? signal.reason
    : new DOMException('The operation was aborted.', 'AbortError');

const throwIfAborted = (signal: AbortSignal): void => {
  if (signal.aborted) {
    throw abortReason(signal);
  }
};

const waitUntil = (targetTime: number, signal: AbortSignal): Promise<void> => {
  throwIfAborted(signal);
  const delay = Math.max(0, targetTime - Date.now());
  if (delay === 0) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      window.clearTimeout(timer);
      signal.removeEventListener('abort', onAbort);
      reject(abortReason(signal));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, delay);

    signal.addEventListener('abort', onAbort, { once: true });
    if (signal.aborted) {
      onAbort();
    }
  });
};

const isUsableStaffOrder = (value: unknown): value is StaffOrder =>
  typeof value === 'object'
  && value !== null
  && 'id' in value
  && typeof value.id === 'string'
  && value.id.length > 0;

export const getAvailableStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/available');

export const getActiveStaffOrder = (): Promise<AxiosResponse<ApiResponse<StaffOrder | null>>> =>
  api.get('/staff/orders/active');

export const getCompletedStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/completed');

export const getStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.get(`/staff/orders/${id}`);

export const takeStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.post(`/staff/orders/${id}/take`, undefined, { timeout: TAKE_ORDER_TIMEOUT_MS });

export const reconcileStaffOrderTake = async (
  targetOrderId: string,
  mutationStartedAt: number,
  signal: AbortSignal,
): Promise<StaffOrderTakeReconciliationResult> => {
  for (const offset of RECONCILIATION_READ_OFFSETS_MS) {
    await waitUntil(mutationStartedAt + offset, signal);
    throwIfAborted(signal);

    let activeOrder: unknown;
    try {
      const requestConfig: ReconciliationRequestConfig = {
        timeout: RECONCILIATION_READ_TIMEOUT_MS,
        signal,
        skipRetry: true,
      };
      const response = await api.get<ApiResponse<StaffOrder | null>>(
        '/staff/orders/active',
        requestConfig,
      );
      throwIfAborted(signal);
      activeOrder = response.data.data;
    } catch {
      throwIfAborted(signal);
      continue;
    }

    if (!isUsableStaffOrder(activeOrder)) {
      continue;
    }

    return activeOrder.id === targetOrderId
      ? { outcome: 'same', order: activeOrder }
      : { outcome: 'different', order: activeOrder };
  }

  return { outcome: 'none' };
};

export const markStaffOrderDelivered = (
  id: string,
): Promise<AxiosResponse<ApiResponse<StaffOrder>>> => api.post(`/staff/orders/${id}/delivered`);
