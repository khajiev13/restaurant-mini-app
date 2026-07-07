import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffLayout from './StaffLayout';

const authState = vi.hoisted(() => ({
  user: { role: 'staff' as 'customer' | 'staff' | 'admin' },
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

describe('StaffLayout', () => {
  beforeEach(() => {
    cleanup();
    authState.user = { role: 'staff' };
  });

  it('shows two nav items for staff', () => {
    render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <StaffLayout>
          <div>Staff content</div>
        </StaffLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole('navigation', { name: 'Staff navigation' })).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
  });

  it('shows three nav items for admin', () => {
    authState.user = { role: 'admin' };

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <StaffLayout>
          <div>Admin content</div>
        </StaffLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole('navigation', { name: 'Admin navigation' })).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
  });
});
