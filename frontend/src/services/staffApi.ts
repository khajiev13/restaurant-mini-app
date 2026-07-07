import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse, User } from '../types/api';
import type { StaffOrder } from '../types/staff';

export const getAvailableStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/available');

export const getActiveStaffOrder = (): Promise<AxiosResponse<ApiResponse<StaffOrder | null>>> =>
  api.get('/staff/orders/active');

export const getCompletedStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/completed');

export const getStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.get(`/staff/orders/${id}`);

export const takeStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.post(`/staff/orders/${id}/take`);

export const markStaffOrderDelivered = (
  id: string,
): Promise<AxiosResponse<ApiResponse<StaffOrder>>> => api.post(`/staff/orders/${id}/delivered`);

export const searchAdminUsers = (
  query: string,
): Promise<AxiosResponse<ApiResponse<User[]>>> => api.get('/admin/users', { params: { query } });

export const updateAdminUserRole = (
  telegramId: number,
  role: User['role'],
): Promise<AxiosResponse<ApiResponse<User>>> =>
  api.patch(`/admin/users/${telegramId}/role`, { role });
