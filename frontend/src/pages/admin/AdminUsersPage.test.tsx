import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminUsersPage from './AdminUsersPage';

const apiMocks = vi.hoisted(() => ({
  searchAdminUsers: vi.fn(),
  updateAdminUserRole: vi.fn(),
}));

vi.mock('../../services/adminApi', () => apiMocks);

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: { user: { role: 'admin' } }) => unknown) =>
    selector({ user: { role: 'admin' } }),
}));

const userRecord = {
  telegram_id: 992208572,
  first_name: 'Rakhmonberdi',
  last_name: 'Khajiev',
  username: 'khajiev13',
  phone_number: '8613269797807',
  language: 'en',
  role: 'customer' as const,
};

describe('AdminUsersPage', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
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
    expect(screen.getByDisplayValue('customer')).toBeInTheDocument();
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
});
