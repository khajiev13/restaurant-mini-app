import type { AxiosResponse } from 'axios';
import api from './api';
import type { AdminUser, ApiResponse } from '../types/api';

export const searchAdminUsers = (
  query: string,
): Promise<AxiosResponse<ApiResponse<AdminUser[]>>> =>
  api.get('/admin/users', { params: { query } });

export const updateAdminUserRole = (
  telegramId: number,
  role: AdminUser['role'],
): Promise<AxiosResponse<ApiResponse<AdminUser>>> =>
  api.patch(`/admin/users/${telegramId}/role`, { role });
