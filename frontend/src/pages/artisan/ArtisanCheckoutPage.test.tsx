import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCartStore } from '../../stores/cartStore';
import { useTableOrderStore } from '../../stores/tableOrderStore';
import ArtisanCheckoutPage from './ArtisanCheckoutPage';

const apiMocks = vi.hoisted(() => ({
  createAddress: vi.fn(),
  createOrder: vi.fn(),
  getAddresses: vi.fn(),
  getMe: vi.fn(),
}));

const authState = vi.hoisted(() => ({
  isAuthenticated: true,
  authenticate: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('../../components/artisan/MapPickerOverlay', () => ({ default: () => null }));

const item = {
  id: 'item-1',
  categoryId: 'somsa',
  name: 'Classic Somsa',
  description: null,
  price: 18000,
  sortOrder: 0,
  available: true,
  availableCount: null,
  quantity: 2,
};

describe('ArtisanCheckoutPage table mode', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.getMe.mockResolvedValue({
      data: { data: { phone_number: '+998901112233' } },
    });
    apiMocks.getAddresses.mockResolvedValue({ data: { data: [] } });
    useCartStore.setState({ items: [item] });
    useTableOrderStore.setState({
      context: {
        tableTitle: 'Stol 12',
        hallTitle: 'Asosiy zal',
        servicePercent: 10,
        accessToken: 'signed-table-token',
      },
      isResolving: false,
      error: null,
    });
  });

  it('omits delivery UI and submits the signed table context for cash', async () => {
    const user = userEvent.setup();
    apiMocks.createOrder.mockResolvedValue({
      data: {
        data: {
          id: 'order-1',
          payment_method: 'cash',
          multicard_checkout_url: null,
        },
      },
    });
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Stol 12')).toBeVisible();
    expect(screen.queryByText(/delivery address/i)).not.toBeInTheDocument();
    expect(apiMocks.getAddresses).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /place order|buyurtmani qabul qilish/i }));

    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));
    expect(apiMocks.createOrder.mock.calls[0][0]).toMatchObject({
      discriminator: 'inplace',
      table_access_token: 'signed-table-token',
      payment_method: 'cash',
    });
    expect(apiMocks.createOrder.mock.calls[0][0]).not.toHaveProperty('delivery_address');
  });

  it('uses an immediate pay-online CTA and opens the returned checkout', async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    apiMocks.createOrder.mockResolvedValue({
      data: {
        data: {
          id: 'order-2',
          payment_method: 'rahmat',
          multicard_checkout_url: 'https://pay.example/checkout',
        },
      },
    });
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: /karta|online/i }));
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));

    await waitFor(() => expect(open).toHaveBeenCalledWith('https://pay.example/checkout', '_blank'));
    expect(apiMocks.createOrder.mock.calls[0][0]).toMatchObject({
      discriminator: 'inplace',
      payment_method: 'rahmat',
    });
    open.mockRestore();
  });
});
