import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse } from '../types/api';
import type { StaffTableDetail, StaffTablesOverview } from '../types/staffTables';

export const getStaffTables = (): Promise<AxiosResponse<ApiResponse<StaffTablesOverview>>> =>
  api.get('/staff/tables');

export const getStaffTable = (
  tableId: string,
): Promise<AxiosResponse<ApiResponse<StaffTableDetail>>> =>
  api.get(`/staff/tables/${encodeURIComponent(tableId)}`);
