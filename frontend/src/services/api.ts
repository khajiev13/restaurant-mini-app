import axios, {
  AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import type {
  Address,
  AddressCreate,
  ApiResponse,
  AuthResponse,
  CreateOrderPayload,
  MenuData,
  Order,
  OrderStatus,
  User,
} from '../types/api';

const BACKEND_URL = import.meta.env.VITE_API_BASE_URL || '/api';
const REQUEST_TIMEOUT_MS = 10000;
const RETRY_DELAY_MS = 500;
const RETRYABLE_METHODS = new Set(['get', 'head', 'options']);

type RetriableRequestConfig = InternalAxiosRequestConfig & {
  _retryCount?: number;
};

const api = axios.create({
  baseURL: BACKEND_URL,
  timeout: REQUEST_TIMEOUT_MS,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('jwt');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableRequestConfig | undefined;
    const method = config?.method?.toLowerCase();
    const status = error.response?.status;
    const isRetryableMethod = method ? RETRYABLE_METHODS.has(method) : false;
    const isTransientFailure =
      error.code === 'ECONNABORTED'
      || !error.response
      || (typeof status === 'number' && status >= 500);

    if (!config || !isRetryableMethod || !isTransientFailure) {
      throw error;
    }

    const retryCount = config._retryCount ?? 0;
    if (retryCount >= 1) {
      throw error;
    }

    config._retryCount = retryCount + 1;
    await new Promise((resolve) => window.setTimeout(resolve, RETRY_DELAY_MS));
    return api.request(config);
  },
);

export const authenticateTelegram = (
  initData: string,
): Promise<AxiosResponse<ApiResponse<AuthResponse>>> =>
  api.post('/auth/telegram', { init_data: initData });

export const getMenu = (): Promise<AxiosResponse<ApiResponse<MenuData>>> => api.get('/menu');

export const getMe = (): Promise<AxiosResponse<ApiResponse<User>>> => api.get('/users/me');

export const updateMe = (
  data: Partial<User>,
): Promise<AxiosResponse<ApiResponse<User>>> => api.put('/users/me', data);

export const getAddresses = (): Promise<AxiosResponse<ApiResponse<Address[]>>> => api.get('/addresses');

export const createAddress = (
  data: AddressCreate,
): Promise<AxiosResponse<ApiResponse<Address>>> => api.post('/addresses', data);

export const deleteAddress = (id: string): Promise<AxiosResponse<ApiResponse<null>>> =>
  api.delete(`/addresses/${id}`);

export const updateAddress = (
  id: string,
  data: AddressCreate,
): Promise<AxiosResponse<ApiResponse<Address>>> => api.put(`/addresses/${id}`, data);

export const createOrder = (
  data: CreateOrderPayload,
): Promise<AxiosResponse<ApiResponse<Order>>> => api.post('/orders', data);

export const getOrders = (): Promise<AxiosResponse<ApiResponse<Order[]>>> => api.get('/orders');

export const getOrder = (id: string): Promise<AxiosResponse<ApiResponse<Order>>> =>
  api.get(`/orders/${id}`);

export const getOrderStatus = (
  id: string,
): Promise<AxiosResponse<ApiResponse<OrderStatus>>> => api.get(`/orders/${id}/status`);

export default api;
