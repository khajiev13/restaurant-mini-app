import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { useAuthStore } from './stores/authStore';
import { useCartStore } from './stores/cartStore';
import { useTableOrderStore } from './stores/tableOrderStore';
import type { Address, CreateOrderPayload, User } from './types/api';

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

const addresses: Address[] = [
  {
    id: 'address-home',
    label: 'Home',
    full_address: '1 Home Street',
    latitude: null,
    longitude: null,
    entrance: null,
    apartment: null,
    floor: null,
    door_code: null,
    courier_instructions: null,
    is_default: true,
  },
  {
    id: 'address-work',
    label: 'Work',
    full_address: '2 Work Avenue',
    latitude: null,
    longitude: null,
    entrance: null,
    apartment: null,
    floor: null,
    door_code: null,
    courier_instructions: null,
    is_default: false,
  },
];

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
    expect(useCartStore.getState().items).toEqual([item]);
    expect(useTableOrderStore.getState().context?.accessToken).toBe('signed-table-token');

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

  it('restores the delivery draft after a real refresh failure and auth retry', async () => {
    const user = userEvent.setup();
    const exactNote = 'Keep address through auth retry';
    let completeContactRequest: ((shared: boolean) => void) | undefined;
    useTableOrderStore.setState({ context: null, isResolving: false, error: null });
    apiMocks.getAddresses.mockResolvedValue({ data: { data: addresses } });
    apiMocks.getMe
      .mockRejectedValueOnce(new Error('network unavailable'))
      .mockResolvedValueOnce({
        data: { data: { ...verifiedUser, phone_verified: false } },
      })
      .mockResolvedValueOnce({ data: { data: verifiedUser } });
    apiMocks.authenticateTelegram.mockResolvedValue({
      data: { data: { access_token: 'recovered-token' } },
    });

    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    await user.click(await screen.findByText('Work'));
    const noteInput = screen.getByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i);
    await user.type(noteInput, exactNote);
    await user.click(screen.getByRole('button', { name: /karta|online/i }));
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));

    const retry = await screen.findByRole('button', { name: /retry|qayta|повтор/i });
    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;
    expect(firstPayload).toMatchObject({
      address_id: 'address-work',
      comment: exactNote,
      payment_method: 'rahmat',
    });
    expect(useAuthStore.getState()).toMatchObject({
      user: null,
      authError: 'auth.retry_message',
      hasHydratedUser: false,
      hasResolvedInitialAuth: true,
    });
    expect(useCartStore.getState().items).toEqual([item]);
    expect(useTableOrderStore.getState().context).toBeNull();

    (window as Window & { Telegram?: unknown }).Telegram = {
      WebApp: {
        initData: 'retry-init-data',
        ready: vi.fn(),
        expand: vi.fn(),
        setHeaderColor: vi.fn(),
        setBackgroundColor: vi.fn(),
        setBottomBarColor: vi.fn(),
        disableVerticalSwipes: vi.fn(),
        isVersionAtLeast: vi.fn(() => true),
        requestContact: vi.fn((callback: (shared: boolean) => void) => {
          completeContactRequest = callback;
        }),
      },
    } as unknown as typeof window.Telegram;
    await user.click(retry);

    expect(await screen.findByRole('heading', { name: /verify your phone|telefoningizni tasdiqlang|подтвердите телефон/i })).toBeVisible();
    const sharePhone = screen.queryByRole('button', { name: /share phone|telefonni ulashish|поделиться телефоном/i });
    if (sharePhone) {
      await user.click(sharePhone);
    }
    await waitFor(() => expect(completeContactRequest).toBeTypeOf('function'));
    act(() => {
      completeContactRequest?.(true);
    });

    expect(await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i)).toHaveValue(exactNote);
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const secondPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(secondPayload).toMatchObject({
      client_request_id: firstPayload.client_request_id,
      address_id: 'address-work',
      comment: exactNote,
      payment_method: 'rahmat',
    });
    expect(apiMocks.authenticateTelegram).toHaveBeenCalledWith('retry-init-data');
    expect(apiMocks.getMe).toHaveBeenCalledTimes(3);
  });
});
