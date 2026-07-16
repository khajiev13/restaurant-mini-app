import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCartStore } from '../../stores/cartStore';
import { useTableOrderStore } from '../../stores/tableOrderStore';
import type { CreateOrderPayload } from '../../types/api';
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
  user: {
    telegram_id: 7301,
    inplace_online_payment_enabled: false,
  },
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
    authState.user = {
      telegram_id: 7301,
      inplace_online_payment_enabled: false,
    };
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
    expect(screen.queryByRole('button', { name: /karta|online/i })).not.toBeInTheDocument();
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
    authState.user = {
      telegram_id: 7301,
      inplace_online_payment_enabled: true,
    };
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

  it('resets a stale online selection when table payment becomes unavailable', async () => {
    const user = userEvent.setup();
    authState.user = {
      telegram_id: 7301,
      inplace_online_payment_enabled: true,
    };
    apiMocks.createOrder.mockResolvedValue({
      data: {
        data: {
          id: 'order-capability-changed',
          payment_method: 'cash',
          multicard_checkout_url: null,
        },
      },
    });
    const view = render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: /karta|online/i }));
    authState.user = {
      telegram_id: 7301,
      inplace_online_payment_enabled: false,
    };
    view.rerender(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('button', { name: /karta|online/i })).not.toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: /place order|buyurtmani qabul qilish/i }));

    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));
    expect(apiMocks.createOrder.mock.calls[0][0]).toMatchObject({
      discriminator: 'inplace',
      payment_method: 'cash',
    });
  });

  it('keeps cash and online methods for delivery regardless of table capability', async () => {
    useTableOrderStore.setState({
      context: null,
      isResolving: false,
      error: null,
    });
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('button', { name: /cash|naqd/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /karta|online/i })).toBeVisible();
  });

  it('reuses one client request ID when a timed-out checkout is retried', async () => {
    const user = userEvent.setup();
    apiMocks.createOrder
      .mockRejectedValueOnce({ code: 'ECONNABORTED' })
      .mockResolvedValueOnce({
        data: { data: { id: 'order-recovered', payment_method: 'cash', multicard_checkout_url: null } },
      });
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const placeOrder = await screen.findByRole('button', { name: /place order|buyurtmani qabul qilish/i });
    await user.click(placeOrder);
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));
    await user.click(placeOrder);
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));

    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;
    const secondPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    const firstId = firstPayload.client_request_id;
    const secondId = secondPayload.client_request_id;
    expect(firstId).toMatch(/^[0-9a-f-]{36}$/i);
    expect(secondId).toBe(firstId);
  });

  it('lets a first-time table customer enter a phone number inline', async () => {
    const user = userEvent.setup();
    apiMocks.getMe.mockResolvedValue({ data: { data: { phone_number: null } } });
    apiMocks.createOrder.mockResolvedValue({
      data: { data: { id: 'order-first-time', payment_method: 'cash', multicard_checkout_url: null } },
    });
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const phone = await screen.findByRole('textbox', { name: /telefon|phone/i });
    await user.type(phone, '+998901234567');
    await user.click(screen.getByRole('button', { name: /place order|buyurtmani qabul qilish/i }));

    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));
    const payload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;
    expect(payload.phone_number).toBe('+998901234567');
  });
});
