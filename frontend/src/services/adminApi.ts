import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse, User } from '../types/api';

export const searchAdminUsers = (
  query: string,
): Promise<AxiosResponse<ApiResponse<User[]>>> => api.get('/admin/users', { params: { query } });

export const updateAdminUserRole = (
  telegramId: number,
  role: User['role'],
): Promise<AxiosResponse<ApiResponse<User>>> =>
  api.patch(`/admin/users/${telegramId}/role`, { role });
