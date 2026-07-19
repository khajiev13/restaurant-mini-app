import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '../../i18n';
import AdminUsersPage from './AdminUsersPage';

const apiMocks = vi.hoisted(() => ({
  searchAdminUsers: vi.fn(),
  updateAdminUserRole: vi.fn(),
}));

const authStoreState = vi.hoisted(() => ({
  user: {
    telegram_id: 4001,
    role: 'admin' as const,
  },
  refreshMe: vi.fn<() => Promise<unknown>>().mockResolvedValue(null),
}));

vi.mock('../../services/adminApi', () => apiMocks);

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (
    selector: (state: {
      user: typeof authStoreState.user;
      refreshMe: typeof authStoreState.refreshMe;
    }) => unknown,
  ) => selector(authStoreState),
}));

const userRecord = {
  telegram_id: 992208572,
  first_name: 'Rakhmonberdi',
  last_name: 'Khajiev',
  username: 'khajiev13',
  phone_number: '8613269797807',
  phone_verified: false,
  language: 'en',
  role: 'customer' as const,
};

describe('AdminUsersPage', () => {
  beforeEach(async () => {
    cleanup();
    vi.clearAllMocks();
    await i18n.changeLanguage('en');
    authStoreState.user = {
      telegram_id: 4001,
      role: 'admin',
    };
    apiMocks.searchAdminUsers.mockResolvedValue({ data: { data: [userRecord] } });
    apiMocks.updateAdminUserRole.mockResolvedValue({
      data: { data: { ...userRecord, role: 'staff' } },
    });
  });

  it('searches users and renders role controls', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText('Search users'), '8613269797807');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(apiMocks.searchAdminUsers).toHaveBeenCalledWith('8613269797807');
    expect(await screen.findByText('Rakhmonberdi Khajiev')).toBeInTheDocument();
    expect(screen.getByText('@khajiev13')).toBeInTheDocument();
    expect(screen.getByText(/8613269797807.*Unverified/)).toBeInTheDocument();
    expect(screen.getByDisplayValue('customer')).toBeInTheDocument();
  });

  it('labels a verified phone explicitly', async () => {
    const user = userEvent.setup();
    apiMocks.searchAdminUsers.mockResolvedValue({
      data: { data: [{ ...userRecord, phone_verified: true }] },
    });
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText(/8613269797807.*Verified/)).toBeInTheDocument();
    expect(screen.queryByText(/Unverified/)).not.toBeInTheDocument();
  });

  it('updates a user role and refreshes that row locally', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Search' }));
    await user.selectOptions(screen.getByLabelText('Role for Rakhmonberdi Khajiev'), 'staff');
    await user.click(screen.getByRole('button', { name: 'Save role for Rakhmonberdi Khajiev' }));

    expect(apiMocks.updateAdminUserRole).toHaveBeenCalledWith(992208572, 'staff');
    expect(await screen.findByText('Role updated.')).toBeInTheDocument();
    expect(screen.getByDisplayValue('staff')).toBeInTheDocument();
  });

  it('refreshes the current auth user after saving that same user role', async () => {
    const user = userEvent.setup();
    authStoreState.user = {
      telegram_id: userRecord.telegram_id,
      role: 'admin',
    };

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Search' }));
    await user.selectOptions(screen.getByLabelText('Role for Rakhmonberdi Khajiev'), 'staff');
    await user.click(screen.getByRole('button', { name: 'Save role for Rakhmonberdi Khajiev' }));

    expect(await screen.findByText('Role updated.')).toBeInTheDocument();
    expect(authStoreState.refreshMe).toHaveBeenCalledTimes(1);
  });

  it('shows an empty state when no users match', async () => {
    const user = userEvent.setup();
    apiMocks.searchAdminUsers.mockResolvedValue({ data: { data: [] } });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('No users found')).toBeInTheDocument();
  });

  it('shows final-admin demotion errors from the backend', async () => {
    const user = userEvent.setup();
    apiMocks.updateAdminUserRole.mockRejectedValue({
      response: { data: { detail: 'Cannot remove the final admin role.' } },
    });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Search' }));
    await user.selectOptions(screen.getByLabelText('Role for Rakhmonberdi Khajiev'), 'staff');
    await user.click(screen.getByRole('button', { name: 'Save role for Rakhmonberdi Khajiev' }));

    expect(await screen.findByText('Cannot remove the final admin role.')).toBeInTheDocument();
  });

  it('clears stale results when a later search fails', async () => {
    const user = userEvent.setup();
    apiMocks.searchAdminUsers
      .mockResolvedValueOnce({ data: { data: [userRecord] } })
      .mockRejectedValueOnce({
        response: { data: { detail: 'Search failed.' } },
      });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('Rakhmonberdi Khajiev')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('Search failed.')).toBeInTheDocument();
    expect(screen.queryByText('Rakhmonberdi Khajiev')).not.toBeInTheDocument();
  });
});
