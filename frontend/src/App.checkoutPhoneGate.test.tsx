import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { useAuthStore } from './stores/authStore';
import { useCartStore } from './stores/cartStore';
import { useTableOrderStore } from './stores/tableOrderStore';
import type { CreateOrderPayload, User } from './types/api';

const apiMocks = vi.hoisted(() => ({
  authenticateTelegram: vi.fn(),
  createAddress: vi.fn(),
  createOrder: vi.fn(),
  getAddresses: vi.fn(),
  getMe: vi.fn(),
  getMenu: vi.fn(),
  resolveTable: vi.fn(),
  restoreTable: vi.fn(),
}));

vi.mock('./services/api', () => apiMocks);
vi.mock('./components/artisan/MapPickerOverlay', () => ({ default: () => null }));
vi.mock('./pages/artisan/ArtisanMenuPage', () => ({ default: () => <div>Menu page</div> }));
vi.mock('./pages/artisan/ArtisanOrdersPage', () => ({ default: () => <div>Orders page</div> }));
vi.mock('./pages/artisan/ArtisanProfilePage', () => ({ default: () => <div>Profile page</div> }));
vi.mock('./pages/artisan/ArtisanOrderStatusPage', () => ({ default: () => <div>Order status page</div> }));
vi.mock('./pages/staff/StaffOrdersPage', () => ({ default: () => null }));
vi.mock('./pages/staff/StaffOrderDetailPage', () => ({ default: () => null }));
vi.mock('./pages/staff/StaffProfilePage', () => ({ default: () => null }));
vi.mock('./pages/staff/StaffTablesPage', () => ({ default: () => null }));
vi.mock('./pages/staff/StaffTableDetailPage', () => ({ default: () => null }));
vi.mock('./pages/admin/AdminUsersPage', () => ({ default: () => null }));

const verifiedUser: User = {
  telegram_id: 7301,
  first_name: 'Gate',
  last_name: 'Tester',
  username: 'gate_tester',
  photo_url: null,
  phone_number: '+998901112233',
  phone_verified: true,
  language: 'en',
  role: 'customer',
  inplace_online_payment_enabled: true,
};

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

describe('App checkout phone-gate transition', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    delete (window as Window & { Telegram?: unknown }).Telegram;
    useAuthStore.setState({
      token: null,
      user: verifiedUser,
      isAuthenticated: true,
      isLoading: false,
      hasHydratedUser: true,
      hasResolvedInitialAuth: true,
      authError: null,
    });
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
    apiMocks.getMe.mockResolvedValue({
      data: { data: { ...verifiedUser, phone_verified: false } },
    });
    apiMocks.getAddresses.mockResolvedValue({ data: { data: [] } });
    apiMocks.createOrder
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: { detail: { code: 'phone_verification_required' } },
        },
      })
      .mockResolvedValueOnce({
        data: {
          data: {
            id: 'order-after-gate',
            payment_method: 'rahmat',
            multicard_checkout_url: null,
          },
        },
      });
  });

  it('preserves the checkout draft when real auth refresh enters and exits the gate', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    const noteInput = await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i);
    await user.type(noteInput, 'Keep through real gate');
    await user.click(screen.getByRole('button', { name: /karta|online/i }));
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));

    expect(await screen.findByRole('heading', { name: /verify your phone|telefoningizni tasdiqlang|подтвердите телефон/i })).toBeVisible();
    expect(apiMocks.getMe).toHaveBeenCalledTimes(1);
    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;

    act(() => {
      useAuthStore.setState({ user: verifiedUser });
    });

    expect(await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i)).toHaveValue('Keep through real gate');
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const secondPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(secondPayload).toMatchObject({
      client_request_id: firstPayload.client_request_id,
      comment: 'Keep through real gate',
      payment_method: 'rahmat',
      table_access_token: 'signed-table-token',
    });
  });
});
