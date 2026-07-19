import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCartStore } from '../../stores/cartStore';
import { useMenuStore } from '../../stores/menuStore';
import { useTableOrderStore } from '../../stores/tableOrderStore';
import type { CreateOrderPayload } from '../../types/api';
import ArtisanCheckoutPage from './ArtisanCheckoutPage';

const apiMocks = vi.hoisted(() => ({
  createAddress: vi.fn(),
  createOrder: vi.fn(),
  getAddresses: vi.fn(),
  getMenu: vi.fn(),
  getMe: vi.fn(),
}));

const phoneVerification = vi.hoisted(() => ({
  status: 'ready' as const,
  requestPhone: vi.fn(),
  checkAgain: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));

const authState = vi.hoisted(() => ({
  isAuthenticated: true,
  authenticate: vi.fn(),
  refreshMe: vi.fn<() => Promise<unknown>>().mockResolvedValue(null),
  user: {
    telegram_id: 7301,
    phone_number: '+998901112233',
    phone_verified: true,
    inplace_online_payment_enabled: false,
  },
}));

vi.mock('../../services/api', () => apiMocks);
vi.mock('../../stores/authStore', () => {
  const useAuthStore = (selector: (state: typeof authState) => unknown) => selector(authState);
  useAuthStore.getState = () => authState;
  return { useAuthStore };
});
vi.mock('../../hooks/usePhoneVerification', () => ({
  usePhoneVerification: () => phoneVerification,
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

function LocationProbe() {
  return <div data-testid="location">{useLocation().pathname}</div>;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

describe('ArtisanCheckoutPage table mode', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    authState.user = {
      telegram_id: 7301,
      phone_number: '+998901112233',
      phone_verified: true,
      inplace_online_payment_enabled: false,
    };
    authState.refreshMe.mockClear();
    phoneVerification.requestPhone.mockClear();
    apiMocks.getMe.mockResolvedValue({
      data: { data: { phone_number: '+998901112233' } },
    });
    apiMocks.getAddresses.mockResolvedValue({ data: { data: [] } });
    useCartStore.setState({ items: [item] });
    useMenuStore.setState({
      menu: null,
      loading: false,
      loaded: false,
      error: null,
    });
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
    expect(apiMocks.createOrder.mock.calls[0][0]).not.toHaveProperty('phone_number');
  });

  it('shows the masked verified profile phone without an editable phone field', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('+998 90 *** 2233')).toBeVisible();
    expect(screen.queryByRole('textbox', { name: /telefon|phone/i })).not.toBeInTheDocument();
    expect(apiMocks.getMe).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: /telegram/i }));
    expect(phoneVerification.requestPhone).toHaveBeenCalledTimes(1);
  });

  it('limits the exact customer note to 200 Unicode code points and sends it unchanged', async () => {
    const user = userEvent.setup();
    const note = '😀'.repeat(200);
    apiMocks.createOrder.mockResolvedValue({
      data: { data: { id: 'order-note', payment_method: 'cash', multicard_checkout_url: null } },
    });
    render(
      <MemoryRouter>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const noteInput = await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i);
    expect(noteInput).not.toHaveAttribute('maxlength');
    fireEvent.change(noteInput, { target: { value: `${note}😎` } });
    expect(noteInput).toHaveValue(note);
    expect(screen.getByText(/200 \/ 200/)).toBeVisible();

    await user.click(screen.getByRole('button', { name: /place order|buyurtmani qabul qilish/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));
    expect(apiMocks.createOrder.mock.calls[0][0]).toMatchObject({ comment: note });
  });

  it('refreshes auth for the phone gate without losing checkout state after the stable 409', async () => {
    const user = userEvent.setup();
    apiMocks.createOrder.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'phone_verification_required',
            message: 'Share your phone through Telegram before placing an order.',
          },
        },
      },
    });
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <LocationProbe />
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const placeOrder = await screen.findByRole('button', { name: /place order|buyurtmani qabul qilish/i });
    await user.click(placeOrder);
    await waitFor(() => expect(authState.refreshMe).toHaveBeenCalledTimes(1));

    expect(screen.getByTestId('location')).toHaveTextContent('/checkout');
    expect(useCartStore.getState().items).toEqual([item]);
    expect(screen.getByText(/share your phone through telegram|telegram orqali.*telefon|поделитесь.*telegram/i)).toBeVisible();
    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;

    await user.click(placeOrder);
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const retryPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(retryPayload.client_request_id).toBe(firstPayload.client_request_id);
    expect(useTableOrderStore.getState().context?.accessToken).toBe('signed-table-token');
  });

  it('restores the checkout draft and request ID after the phone gate unmounts the route', async () => {
    const user = userEvent.setup();
    authState.user = {
      ...authState.user,
      inplace_online_payment_enabled: true,
    };
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
            id: 'order-after-verification',
            payment_method: 'rahmat',
            multicard_checkout_url: null,
          },
        },
      });
    authState.refreshMe.mockResolvedValueOnce({
      ...authState.user,
      phone_verified: false,
    });
    const firstView = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const noteInput = await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i);
    await user.type(noteInput, 'Gate draft note');
    await user.click(screen.getByRole('button', { name: /karta|online/i }));
    const payOnline = screen.getByRole('button', { name: /pay online|onlayn to'lash/i });
    await user.click(payOnline);
    await waitFor(() => expect(authState.refreshMe).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(payOnline).toBeEnabled());
    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;

    firstView.unmount();
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i)).toHaveValue('Gate draft note');
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const secondPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(secondPayload).toMatchObject({
      client_request_id: firstPayload.client_request_id,
      comment: 'Gate draft note',
      payment_method: 'rahmat',
      table_access_token: 'signed-table-token',
    });
  });

  it('does not preserve a draft when checkout unmounts before unverified refresh resolves', async () => {
    const user = userEvent.setup();
    const refresh = deferred<unknown>();
    authState.user = {
      ...authState.user,
      inplace_online_payment_enabled: true,
    };
    authState.refreshMe.mockReturnValueOnce(refresh.promise);
    apiMocks.createOrder
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: { detail: { code: 'phone_verification_required' } },
        },
      })
      .mockResolvedValueOnce({
        data: { data: { id: 'new-order', payment_method: 'cash', multicard_checkout_url: null } },
      });
    const firstView = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    await user.type(
      await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i),
      'Must not return',
    );
    await user.click(screen.getByRole('button', { name: /karta|online/i }));
    await user.click(screen.getByRole('button', { name: /pay online|onlayn to'lash/i }));
    await waitFor(() => expect(authState.refreshMe).toHaveBeenCalledTimes(1));
    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;

    firstView.unmount();
    await act(async () => {
      refresh.resolve({ ...authState.user, phone_verified: false });
      await refresh.promise;
    });
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i)).toHaveValue('');
    await user.click(screen.getByRole('button', { name: /place order|buyurtmani qabul qilish/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const secondPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(secondPayload.client_request_id).not.toBe(firstPayload.client_request_id);
    expect(secondPayload.comment).toBeUndefined();
    expect(secondPayload.payment_method).toBe('cash');
  });

  it('does not preserve a draft when refreshed profile is already verified', async () => {
    const user = userEvent.setup();
    authState.user = {
      ...authState.user,
      inplace_online_payment_enabled: true,
    };
    authState.refreshMe.mockResolvedValueOnce({
      ...authState.user,
      phone_verified: true,
    });
    apiMocks.createOrder
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: { detail: { code: 'phone_verification_required' } },
        },
      })
      .mockResolvedValueOnce({
        data: { data: { id: 'verified-order', payment_method: 'cash', multicard_checkout_url: null } },
      });
    const firstView = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    await user.type(
      await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i),
      'Verified draft',
    );
    await user.click(screen.getByRole('button', { name: /karta|online/i }));
    const payOnline = screen.getByRole('button', { name: /pay online|onlayn to'lash/i });
    await user.click(payOnline);
    await waitFor(() => expect(payOnline).toBeEnabled());
    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;

    firstView.unmount();
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    expect(await screen.findByPlaceholderText(/special instructions|ko'rsatmalar|инструк/i)).toHaveValue('');
    await user.click(screen.getByRole('button', { name: /place order|buyurtmani qabul qilish/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const secondPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(secondPayload.client_request_id).not.toBe(firstPayload.client_request_id);
    expect(secondPayload.comment).toBeUndefined();
    expect(secondPayload.payment_method).toBe('cash');
  });

  it('uses an immediate pay-online CTA and opens the returned checkout', async () => {
    const user = userEvent.setup();
    authState.user = {
      telegram_id: 7301,
      phone_number: '+998901112233',
      phone_verified: true,
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
      phone_number: '+998901112233',
      phone_verified: true,
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
      phone_number: '+998901112233',
      phone_verified: true,
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

  it('keeps checkout state and request ID after a 502 response', async () => {
    const user = userEvent.setup();
    apiMocks.createOrder.mockRejectedValue({
      response: {
        status: 502,
        data: { detail: 'Could not submit the order to the restaurant' },
      },
    });
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <LocationProbe />
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const placeOrder = await screen.findByRole('button', { name: /place order|buyurtmani qabul qilish/i });
    await user.click(placeOrder);
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));

    expect(screen.getByTestId('location')).toHaveTextContent('/checkout');
    expect(useCartStore.getState().items).toEqual([item]);
    expect(screen.getByText(/something went wrong|nimadir noto'g'ri|что-то пошло не так/i)).toBeVisible();

    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;
    await user.click(placeOrder);
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));
    const retryPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(retryPayload.client_request_id).toBe(firstPayload.client_request_id);
    expect(screen.getByTestId('location')).toHaveTextContent('/checkout');
    expect(useCartStore.getState().items).toEqual([item]);
  });

  it('requires_a_second_click_after_server_price_conflict', async () => {
    const user = userEvent.setup();
    apiMocks.createOrder
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: {
            detail: {
              code: 'cart_conflict',
              changes: [{ id: item.id, reason: 'price_changed' }],
            },
          },
        },
      })
      .mockRejectedValueOnce({ code: 'ECONNABORTED' });
    apiMocks.getMenu.mockResolvedValue({
      data: {
        data: {
          categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
          items: [{
            id: item.id,
            categoryId: item.categoryId,
            name: item.name,
            description: item.description,
            price: 20000,
            sortOrder: item.sortOrder,
            available: true,
            availableCount: null,
          }],
        },
      },
    });
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <LocationProbe />
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    const placeOrder = await screen.findByRole('button', {
      name: /place order|buyurtmani qabul qilish/i,
    });
    await user.click(placeOrder);

    await waitFor(() => expect(apiMocks.getMenu).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(placeOrder).toBeEnabled());
    expect(apiMocks.createOrder).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('location')).toHaveTextContent('/checkout');
    expect(useCartStore.getState().items).toEqual([
      expect.objectContaining({ id: item.id, quantity: 2, price: 20000 }),
    ]);
    expect(useCartStore.getState().getTotal()).toBe(40000);
    expect(screen.getAllByText(/40.?000/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/44.?000/).length).toBeGreaterThan(0);

    const firstPayload = apiMocks.createOrder.mock.calls[0][0] as CreateOrderPayload;
    expect(firstPayload.items[0].price).toBe(18000);

    await user.click(placeOrder);
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(2));

    const confirmedPayload = apiMocks.createOrder.mock.calls[1][0] as CreateOrderPayload;
    expect(confirmedPayload.items[0].price).toBe(20000);
    expect(confirmedPayload.client_request_id).not.toBe(firstPayload.client_request_id);
    await waitFor(() => expect(placeOrder).toBeEnabled());
    expect(screen.getByTestId('location')).toHaveTextContent('/checkout');
  });

  it('rejects_a_nominal_success_body_for_submission_failed_order', async () => {
    const user = userEvent.setup();
    apiMocks.createOrder.mockResolvedValue({
      data: {
        success: true,
        data: {
          id: 'order-failed',
          status: 'SUBMISSION_FAILED',
          discriminator: 'inplace',
          items_cost: 36000,
          total_amount: 39600,
          created_at: '2026-07-17T00:00:00Z',
          order_number: null,
          items: [],
          comment: null,
          payment_method: 'cash',
          payment_provider: null,
          payment_status: null,
          payment_expires_at: null,
          multicard_checkout_url: null,
          multicard_receipt_url: null,
          alipos_sync_status: 'failed',
          table_title: 'Stol 12',
          hall_title: 'Asosiy zal',
          service_percent: 10,
        },
      },
    });
    render(
      <MemoryRouter initialEntries={['/checkout']}>
        <LocationProbe />
        <ArtisanCheckoutPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: /place order|buyurtmani qabul qilish/i }));
    await waitFor(() => expect(apiMocks.createOrder).toHaveBeenCalledTimes(1));

    expect(screen.getByTestId('location')).toHaveTextContent('/checkout');
    expect(useCartStore.getState().items).toEqual([item]);
    expect(screen.getByText(/something went wrong|nimadir noto'g'ri|что-то пошло не так/i)).toBeVisible();
    expect(apiMocks.createOrder).toHaveBeenCalledTimes(1);
  });

});
