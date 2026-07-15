import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MenuCatalogProps } from '../../components/menu/MenuCatalog';
import ArtisanMenuPage from './ArtisanMenuPage';

const menuState = vi.hoisted(() => ({
  menu: {
    categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
    items: [{
      id: 'classic',
      categoryId: 'somsa',
      name: 'Classic Somsa',
      description: 'Beef and onion',
      price: 18000,
      sortOrder: 0,
      available: true,
      availableCount: 5,
      images: [{ url: '/classic.jpg' }],
    }],
  },
  loading: false,
  error: null as string | null,
  fetchMenu: vi.fn(() => Promise.resolve()),
  retry: vi.fn(() => Promise.resolve()),
}));

const cartState = vi.hoisted(() => ({
  items: [{
    id: 'classic',
    categoryId: 'somsa',
    name: 'Classic Somsa',
    description: 'Beef and onion',
    price: 18000,
    sortOrder: 0,
    available: true,
    availableCount: 5,
    images: [{ url: '/classic.jpg' }],
    quantity: 1,
  }],
  addItem: vi.fn(),
  removeItem: vi.fn(),
  updateQuantity: vi.fn(),
  getItemCount: vi.fn(() => 1),
  getTotal: vi.fn(() => 18000),
  reconcileAvailability: vi.fn(() => ({ removed: 0, reduced: 0 })),
}));

const tableState = vi.hoisted(() => ({
  context: {
    tableTitle: 'Table 2',
    hallTitle: 'Main hall',
    servicePercent: 10,
    accessToken: 'signed-table-token',
  },
  resolveCode: vi.fn(() => Promise.resolve()),
  isResolving: false,
  error: null as string | null,
  clearError: vi.fn(),
}));

const authState = vi.hoisted(() => ({ isAuthenticated: false }));
const apiMocks = vi.hoisted(() => ({ getMe: vi.fn() }));

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, fallback?: string) => key === 'menu.checkout' ? 'Checkout' : fallback ?? key,
      i18n: { language: 'en' },
    }),
  };
});

vi.mock('../../stores/menuStore', () => ({
  useMenuStore: (selector: (state: typeof menuState) => unknown) => selector(menuState),
}));
vi.mock('../../stores/cartStore', () => ({
  useCartStore: (selector: (state: typeof cartState) => unknown) => selector(cartState),
}));
vi.mock('../../stores/tableOrderStore', () => ({
  useTableOrderStore: (selector: (state: typeof tableState) => unknown) => selector(tableState),
}));
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('../../services/api', () => apiMocks);

vi.mock('../../components/menu/MenuCatalog', () => ({
  default: (props: MenuCatalogProps) => {
    if (props.mode !== 'interactive') return <div>browse catalog</div>;
    const item = props.menu.items[0];
    return (
      <div>
        <span>interactive catalog</span>
        <button type="button" onClick={() => props.onAdd(item)}>Catalog add</button>
        <button type="button" onClick={() => props.onRemove(item.id)}>Catalog remove</button>
      </div>
    );
  },
}));

describe('ArtisanMenuPage catalog extraction', () => {
  beforeEach(() => vi.clearAllMocks());

  it('preserves loading, table context, cart wiring, and checkout presentation', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ArtisanMenuPage />
      </MemoryRouter>,
    );

    expect(screen.getByText('interactive catalog')).toBeInTheDocument();
    expect(screen.getByText('Table 2')).toBeInTheDocument();
    expect(screen.getByText('18,000 UZS')).toBeInTheDocument();
    expect(screen.getByText('Checkout')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Catalog add' }));
    expect(cartState.addItem).toHaveBeenCalledWith(menuState.menu.items[0]);
    await user.click(screen.getByRole('button', { name: 'Catalog remove' }));
    expect(cartState.removeItem).toHaveBeenCalledWith('classic');
    expect(menuState.fetchMenu).toHaveBeenCalledTimes(1);
    expect(apiMocks.getMe).not.toHaveBeenCalled();
  });
});
