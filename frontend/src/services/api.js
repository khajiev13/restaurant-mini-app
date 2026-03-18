import axios from 'axios';

// When accessed via Telegram (through Cloudflare tunnel), use the backend tunnel URL.
// In local dev with Docker proxy, use '/api'.
const BACKEND_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: BACKEND_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('jwt');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Auth
export const authenticateTelegram = (initData) =>
  api.post('/auth/telegram', { init_data: initData });

// Menu
export const getMenu = () => api.get('/menu');

// User
export const getMe = () => api.get('/users/me');
export const updateMe = (data) => api.put('/users/me', data);

// Addresses
export const getAddresses = () => api.get('/addresses');
export const createAddress = (data) => api.post('/addresses', data);
export const deleteAddress = (id) => api.delete(`/addresses/${id}`);

// Orders
export const createOrder = (data) => api.post('/orders', data);
export const getOrders = () => api.get('/orders');
export const getOrder = (id) => api.get(`/orders/${id}`);
export const getOrderStatus = (id) => api.get(`/orders/${id}/status`);

export default api;
