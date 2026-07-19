import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import ArtisanLayout from './ArtisanLayout';

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: { isAuthenticated: boolean }) => unknown) =>
    selector({ isAuthenticated: false }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => ({
      'nav.menu': 'Menu',
      'nav.orders': 'Orders',
      'nav.cart': 'Cart',
      'nav.profile': 'Profile',
    }[key] ?? key),
  }),
}));

describe('ArtisanLayout customer navigation', () => {
  it('keeps the existing four customer destinations unchanged', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <ArtisanLayout><div>Content</div></ArtisanLayout>
      </MemoryRouter>,
    );

    const links = within(screen.getByRole('navigation')).getAllByRole('link');
    expect(links.map((link) => link.querySelector('span:last-child')?.textContent)).toEqual([
      'Menu', 'Orders', 'Cart', 'Profile',
    ]);
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/', '/order', '/checkout', '/profile',
    ]);
  });
});
