import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('./api', () => ({ default: apiMocks }));

import { getStaffTable, getStaffTables } from './staffTablesApi';

describe('staffTablesApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads the complete table overview', async () => {
    apiMocks.get.mockResolvedValue({ data: { success: true, data: { halls: [] } } });
    await getStaffTables();
    expect(apiMocks.get).toHaveBeenCalledWith('/staff/tables');
  });

  it('loads one table using an encoded id', async () => {
    apiMocks.get.mockResolvedValue({ data: { success: true, data: {} } });
    await getStaffTable('table/id');
    expect(apiMocks.get).toHaveBeenCalledWith('/staff/tables/table%2Fid');
  });
});
