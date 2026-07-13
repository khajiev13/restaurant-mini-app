import { beforeEach, describe, expect, it, vi } from 'vitest';
import { searchAdminUsers, updateAdminUserRole } from './adminApi';

type AdminApiUser = Awaited<ReturnType<typeof searchAdminUsers>>['data']['data'][number];

const adminUserWithoutSelfCapability = {
  telegram_id: 992208572,
  first_name: 'Rakhmonberdi',
  last_name: 'Khajiev',
  username: 'khajiev13',
  phone_number: '8613269797807',
  language: 'en',
  role: 'customer' as const,
} satisfies AdminApiUser;

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
    apiMocks.get.mockResolvedValue({
      data: { data: [adminUserWithoutSelfCapability] },
    });

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
