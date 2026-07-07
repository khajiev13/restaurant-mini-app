import { beforeEach, describe, expect, it, vi } from 'vitest';
import { searchAdminUsers, updateAdminUserRole } from './adminApi';

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('./api', () => ({
  default: apiMocks,
}));

describe('adminApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('searches admin users by query', async () => {
    apiMocks.get.mockResolvedValue({ data: { data: [] } });

    await searchAdminUsers('8613269797807');

    expect(apiMocks.get).toHaveBeenCalledWith('/admin/users', {
      params: { query: '8613269797807' },
    });
  });

  it('updates a user role', async () => {
    apiMocks.patch.mockResolvedValue({ data: { data: { role: 'staff' } } });

    await updateAdminUserRole(992208572, 'staff');

    expect(apiMocks.patch).toHaveBeenCalledWith('/admin/users/992208572/role', {
      role: 'staff',
    });
  });
});
