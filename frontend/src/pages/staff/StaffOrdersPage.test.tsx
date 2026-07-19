import { AxiosError, AxiosHeaders, type AxiosResponse } from 'axios';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../../services/api';
import type { ApiResponse } from '../../types/api';
import type { StaffOrder } from '../../types/staff';
import StaffOrdersPage from './StaffOrdersPage';

const apiMocks = vi.hoisted(() => ({
  getActiveStaffOrder: vi.fn(),
  getAvailableStaffOrders: vi.fn(),
  getCompletedStaffOrders: vi.fn(),
  markStaffOrderDelivered: vi.fn(),
  takeStaffOrder: vi.fn(),
}));

vi.mock('../../services/staffApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/staffApi')>(
    '../../services/staffApi',
  );
  return { ...actual, ...apiMocks };
});

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, fallback?: string) => fallback ?? key,
      i18n: { language: 'en' },
    }),
  };
});

const STARTED_AT = Date.parse('2026-07-18T00:00:00.000Z');

const staffOrder: StaffOrder = {
  id: 'order-1',
  order_number: 'A7-492',
  status: 'TAKEN_BY_COURIER',
  created_at: '2026-07-07T10:00:00Z',
  status_updated_at: null,
  assigned_at: null,
  delivered_at: null,
  customer: {
    telegram_id: 1,
    first_name: 'Azizbek',
    last_name: 'R.',
    phone_number: '+998901112233',
  },
  address: {
    full_address: 'Yakkasaray District, Shota Rustaveli 45',
    latitude: '41.2995',
    longitude: '69.2401',
    entrance: '2',
    apartment: '42',
    floor: '4',
    courier_instructions: null,
  },
  items: [{ id: 'item-1', name: 'Classic Somsa', quantity: 2, price: 18000 }],
  total_amount: 36000,
  delivery_fee: 0,
  payment_method: 'cash',
  payment_status: null,
  assigned_staff: null,
};

const reconciliationResponse = (
  data: StaffOrder | null,
): AxiosResponse<ApiResponse<StaffOrder | null>> => ({
  data: { success: true, data },
  status: 200,
  statusText: 'OK',
  headers: new AxiosHeaders(),
  config: { headers: new AxiosHeaders() },
});

describe('StaffOrdersPage', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.getAvailableStaffOrders.mockResolvedValue({ data: { data: [staffOrder] } });
    apiMocks.getActiveStaffOrder.mockResolvedValue({ data: { data: null } });
    apiMocks.getCompletedStaffOrders.mockResolvedValue({ data: { data: [] } });
    apiMocks.markStaffOrderDelivered.mockResolvedValue({
      data: { data: { ...staffOrder, status: 'DELIVERED' } },
    });
    apiMocks.takeStaffOrder.mockResolvedValue({ data: { data: staffOrder } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('renders simplified staff nav and tabs', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Tables')).toBeInTheDocument();
    expect(screen.getByText('Delivery')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.queryByText('Activity')).not.toBeInTheDocument();
  });

  it('requires cash checkbox before confirming delivery', async () => {
    const user = userEvent.setup();

    apiMocks.getActiveStaffOrder.mockResolvedValue({
      data: { data: { ...staffOrder, assigned_at: '2026-07-07T10:01:00Z' } },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=active']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const markButton = await screen.findByRole('button', { name: /mark delivered/i });
    await user.click(markButton);

    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    expect(confirmButton).toBeDisabled();

    await user.click(screen.getByLabelText(/i have collected/i));
    expect(confirmButton).toBeEnabled();
  });

  it('names, traps, closes, and restores focus for the delivery dialog', async () => {
    const user = userEvent.setup();
    apiMocks.getActiveStaffOrder.mockResolvedValue({
      data: { data: { ...staffOrder, assigned_at: '2026-07-07T10:01:00Z' } },
    });
    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=active']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const markButton = await screen.findByRole('button', { name: 'Mark Delivered' });
    await user.click(markButton);

    const dialog = screen.getByRole('dialog', { name: 'Confirm Delivery' });
    const checkbox = screen.getByRole('checkbox');
    const cancelButton = screen.getByRole('button', { name: 'Cancel' });
    await waitFor(() => expect(checkbox).toHaveFocus());
    expect(markButton.closest('[inert]')).not.toBeNull();

    await user.tab({ shift: true });
    expect(cancelButton).toHaveFocus();
    await user.tab();
    expect(checkbox).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(dialog).not.toBeInTheDocument();
    await waitFor(() => expect(markButton).toHaveFocus());
    expect(markButton.closest('[inert]')).toBeNull();
  });

  it('opens order details from a semantic keyboard link separate from Take', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <Routes>
          <Route path="/staff/orders" element={<StaffOrdersPage />} />
          <Route path="/staff/orders/:orderId" element={<div>Order detail route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    const detailLink = await screen.findByRole('link', {
      name: 'View order #A7-492 details',
    });
    const takeButton = screen.getByRole('button', { name: 'Take Order' });
    expect(detailLink.parentElement).toBe(takeButton.parentElement);

    detailLink.focus();
    await user.keyboard('{Enter}');
    expect(screen.getByText('Order detail route')).toBeInTheDocument();
  });

  it('does not navigate to an available order when another delivery is already active', async () => {
    const user = userEvent.setup();

    apiMocks.getActiveStaffOrder.mockResolvedValue({
      data: { data: { ...staffOrder, id: 'active-order-1', assigned_at: '2026-07-07T10:01:00Z' } },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <Routes>
          <Route path="/staff/orders" element={<StaffOrdersPage />} />
          <Route path="/staff/orders/:orderId" element={<div>Order detail route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole('button', { name: 'Active Delivery In Progress' }),
    ).toBeDisabled();

    await user.click(screen.getAllByText('Yakkasaray District, Shota Rustaveli 45')[0]);

    expect(screen.queryByText('Order detail route')).not.toBeInTheDocument();
  });

  it('keeps active-delivery conflict visible after refreshing orders', async () => {
    const user = userEvent.setup();
    apiMocks.takeStaffOrder.mockRejectedValue({
      response: {
        status: 409,
        data: { detail: 'Finish your active delivery before taking another order.' },
      },
    });
    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Take Order' }));

    expect(apiMocks.takeStaffOrder).toHaveBeenCalledWith('order-1');
    expect(
      await screen.findByText('Finish your active delivery before taking another order.'),
    ).toBeInTheDocument();
  });

  it('keeps already-taken conflict detail visible after refreshing orders', async () => {
    const user = userEvent.setup();
    const reconciliationGet = vi.spyOn(api, 'get');
    apiMocks.takeStaffOrder.mockRejectedValue({
      response: {
        status: 409,
        data: { detail: 'This order was already taken by another staff member.' },
      },
    });
    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Take Order' }));

    expect(await screen.findByText('This order was already taken by another staff member.')).toBeInTheDocument();
    expect(reconciliationGet).not.toHaveBeenCalled();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('enters Active after a transport failure is reconciled by the delayed second read', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    const assignedOrder = {
      ...staffOrder,
      assigned_at: '2026-07-18T00:00:04Z',
    };
    const get = vi.spyOn(api, 'get')
      .mockResolvedValueOnce(reconciliationResponse(null))
      .mockResolvedValueOnce(reconciliationResponse(assignedOrder));

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const takeButton = await screen.findByRole('button', { name: 'Take Order' });
    vi.useFakeTimers();
    vi.setSystemTime(STARTED_AT);
    fireEvent.click(takeButton);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Could not refresh order status. Try again.')).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(get).toHaveBeenCalledTimes(2);
    expect(screen.getByText('Active Delivery')).toBeInTheDocument();
    expect(screen.queryByText('This order is no longer available.')).not.toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('shows the active-order conflict when reconciliation finds a different order', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    const otherActiveOrder = {
      ...staffOrder,
      id: 'order-2',
      order_number: 'B8-203',
      assigned_at: '2026-07-18T00:00:01Z',
    };
    const get = vi.spyOn(api, 'get').mockResolvedValue(reconciliationResponse(otherActiveOrder));

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const takeButton = await screen.findByRole('button', { name: 'Take Order' });
    vi.useFakeTimers();
    vi.setSystemTime(STARTED_AT);
    fireEvent.click(takeButton);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(get).toHaveBeenCalledTimes(1);
    expect(
      screen.getByText('Finish your active delivery before taking another order.'),
    ).toBeInTheDocument();
    expect(screen.getByText('#B8-203')).toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('shows the refresh message only after the final reconciliation read finishes empty', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    let finishFinalRead!: (response: AxiosResponse<ApiResponse<StaffOrder | null>>) => void;
    const finalRead = new Promise<AxiosResponse<ApiResponse<StaffOrder | null>>>((resolve) => {
      finishFinalRead = resolve;
    });
    const get = vi.spyOn(api, 'get')
      .mockResolvedValueOnce(reconciliationResponse(null))
      .mockResolvedValueOnce(reconciliationResponse(null))
      .mockReturnValueOnce(finalRead);

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const takeButton = await screen.findByRole('button', { name: 'Take Order' });
    vi.useFakeTimers();
    vi.setSystemTime(STARTED_AT);
    fireEvent.click(takeButton);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(11000);
    });

    expect(get).toHaveBeenCalledTimes(3);
    expect(screen.queryByText('Could not refresh order status. Try again.')).not.toBeInTheDocument();
    expect(screen.queryByText('This order is no longer available.')).not.toBeInTheDocument();

    await act(async () => {
      finishFinalRead(reconciliationResponse(null));
      await finalRead;
    });

    expect(screen.getByText('Could not refresh order status. Try again.')).toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('waits until at least 11 seconds to reconcile an assignment committed at 9.5 seconds', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    const assignedOrder = {
      ...staffOrder,
      assigned_at: '2026-07-18T00:00:09.500Z',
    };
    const readTimes: number[] = [];
    const get = vi.spyOn(api, 'get').mockImplementation(() => {
      readTimes.push(Date.now());
      return Promise.resolve(
        reconciliationResponse(Date.now() >= STARTED_AT + 9500 ? assignedOrder : null),
      );
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const takeButton = await screen.findByRole('button', { name: 'Take Order' });
    vi.useFakeTimers();
    vi.setSystemTime(STARTED_AT);
    fireEvent.click(takeButton);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9500);
    });

    expect(get).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('Could not refresh order status. Try again.')).not.toBeInTheDocument();
    expect(screen.queryByText('This order is no longer available.')).not.toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1499);
    });
    expect(get).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(readTimes).toEqual([STARTED_AT, STARTED_AT + 5000, STARTED_AT + 11000]);
    expect(screen.getByText('Active Delivery')).toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('aborts in-flight reconciliation when the page unmounts', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    const get = vi.spyOn(api, 'get').mockResolvedValue(reconciliationResponse(null));
    const view = render(
      <MemoryRouter initialEntries={['/staff/orders?tab=available']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    const takeButton = await screen.findByRole('button', { name: 'Take Order' });
    vi.useFakeTimers();
    vi.setSystemTime(STARTED_AT);
    fireEvent.click(takeButton);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const signal = (get.mock.calls[0]?.[1] as { signal?: AbortSignal } | undefined)?.signal;
    expect(signal?.aborted).toBe(false);

    view.unmount();
    expect(signal?.aborted).toBe(true);
    await vi.advanceTimersByTimeAsync(20000);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('shows elapsed delivery time on completed cards', async () => {
    apiMocks.getAvailableStaffOrders.mockResolvedValue({ data: { data: [] } });
    apiMocks.getCompletedStaffOrders.mockResolvedValue({
      data: {
        data: [
          {
            ...staffOrder,
            status: 'DELIVERED',
            assigned_at: '2026-07-07T10:00:00Z',
            delivered_at: '2026-07-07T10:27:00Z',
          },
        ],
      },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders?tab=completed']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/27 min/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View order #A7-492 details' })).toBeInTheDocument();
  });
});
