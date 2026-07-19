import { cleanup, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffLayout from './StaffLayout';

const authState = vi.hoisted(() => ({
  user: { role: 'staff' as 'customer' | 'staff' | 'admin' },
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => ({
      'staff_tables.nav_admin': 'Admin',
      'staff_tables.nav_tables': 'Tables',
      'staff_tables.nav_delivery': 'Delivery',
      'nav.profile': 'Profile',
    }[key] ?? fallback ?? key),
  }),
}));

describe('StaffLayout', () => {
  beforeEach(() => {
    cleanup();
    authState.user = { role: 'staff' };
  });

  it('renders the translated three-link staff navigation and activates table details', () => {
    render(
      <MemoryRouter initialEntries={['/staff/tables/table-2']}>
        <StaffLayout>
          <div>Staff content</div>
        </StaffLayout>
      </MemoryRouter>,
    );

    const nav = screen.getByRole('navigation', { name: 'Staff navigation' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.querySelector('span:last-child')?.textContent)).toEqual([
      'Tables', 'Delivery', 'Profile',
    ]);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/staff/tables', '/staff/orders', '/profile',
    ]);
    expect(links[0]).toHaveAccessibleName('Tables');
    expect(links[1]).toHaveAccessibleName('Delivery');
    expect(links[2]).toHaveAccessibleName('Profile');
    expect(links).toHaveLength(3);
    expect(within(nav).getByRole('link', { name: /tables/i })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: /delivery/i })).not.toHaveAttribute('aria-current');
  });

  it('renders the translated four-link admin navigation with the expected active item', () => {
    authState.user = { role: 'admin' };

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <StaffLayout>
          <div>Admin content</div>
        </StaffLayout>
      </MemoryRouter>,
    );

    const nav = screen.getByRole('navigation', { name: 'Admin navigation' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.querySelector('span:last-child')?.textContent)).toEqual([
      'Admin', 'Tables', 'Delivery', 'Profile',
    ]);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/admin', '/staff/tables', '/staff/orders', '/profile',
    ]);
    expect(links[0]).toHaveAccessibleName('Admin');
    expect(links[1]).toHaveAccessibleName('Tables');
    expect(links[2]).toHaveAccessibleName('Delivery');
    expect(links[3]).toHaveAccessibleName('Profile');
    expect(links).toHaveLength(4);
    expect(within(nav).getByRole('link', { name: /admin/i })).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: /tables/i })).not.toHaveAttribute('aria-current');
  });
});
