import { AxiosError } from 'axios';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StaffOrder } from '../../types/staff';
import StaffOrderDetailPage from './StaffOrderDetailPage';

const apiMocks = vi.hoisted(() => ({
  getActiveStaffOrder: vi.fn(),
  getStaffOrder: vi.fn(),
  reconcileStaffOrderTake: vi.fn(),
  takeStaffOrder: vi.fn(),
}));

const translationMocks = vi.hoisted(() => ({
  t: vi.fn((key: string, fallback?: string) => fallback ?? key),
}));

vi.mock('../../services/staffApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/staffApi')>('../../services/staffApi');
  return {
    ...actual,
    ...apiMocks,
  };
});

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: translationMocks.t,
      i18n: { language: 'en' },
    }),
  };
});

const STARTED_AT = Date.parse('2026-07-18T00:00:00.000Z');

const availableOrder: StaffOrder = {
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

describe('StaffOrderDetailPage', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.getStaffOrder.mockResolvedValue({ data: { data: availableOrder } });
    apiMocks.getActiveStaffOrder.mockResolvedValue({ data: { data: null } });
    apiMocks.takeStaffOrder.mockResolvedValue({ data: { data: availableOrder } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('hides the take CTA when the unassigned order is not ready for courier pickup', async () => {
    apiMocks.getStaffOrder.mockResolvedValue({
      data: {
        data: {
          ...availableOrder,
          status: 'ACCEPTED_BY_RESTAURANT',
        },
      },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('#A7-492')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take Order' })).not.toBeInTheDocument();
  });

  it('hides the take CTA when an online order is not paid yet', async () => {
    apiMocks.getStaffOrder.mockResolvedValue({
      data: {
        data: {
          ...availableOrder,
          payment_method: 'rahmat',
          payment_status: 'pending',
        },
      },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('#A7-492')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take Order' })).not.toBeInTheDocument();
  });

  it('hides the take CTA when another active delivery exists', async () => {
    apiMocks.getActiveStaffOrder.mockResolvedValue({
      data: {
        data: {
          ...availableOrder,
          id: 'active-order-2',
          order_number: 'B9-301',
          assigned_at: '2026-07-07T10:05:00Z',
        },
      },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('#A7-492')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Take Order' })).not.toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).not.toHaveBeenCalled();
  });

  it('navigates to Active when transport ambiguity reconciles to the same order', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    const assignedOrder = {
      ...availableOrder,
      assigned_at: '2026-07-18T00:00:04Z',
    };
    apiMocks.reconcileStaffOrderTake.mockResolvedValue({
      outcome: 'same',
      order: assignedOrder,
    });
    vi.spyOn(Date, 'now').mockReturnValue(STARTED_AT);

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Active orders route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Take Order' }));

    expect(await screen.findByText('Active orders route')).toBeInTheDocument();
    expect(apiMocks.reconcileStaffOrderTake).toHaveBeenCalledWith(
      'order-1',
      STARTED_AT,
      expect.any(AbortSignal),
    );
    expect(screen.queryByText('This order is no longer available.')).not.toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('shows the active-order conflict when reconciliation finds a different order', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    const otherActiveOrder = {
      ...availableOrder,
      id: 'order-2',
      order_number: 'B8-203',
      assigned_at: '2026-07-18T00:00:01Z',
    };
    apiMocks.reconcileStaffOrderTake.mockResolvedValue({
      outcome: 'different',
      order: otherActiveOrder,
    });
    vi.spyOn(Date, 'now').mockReturnValue(STARTED_AT);

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Take Order' }));

    expect(
      await screen.findByText('Finish your current delivery before taking another order.'),
    ).toBeInTheDocument();
    expect(apiMocks.reconcileStaffOrderTake).toHaveBeenCalledWith(
      'order-1',
      STARTED_AT,
      expect.any(AbortSignal),
    );
    expect(screen.queryByRole('button', { name: 'Take Order' })).not.toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('shows the refresh message only after the final reconciliation read finishes empty', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    let finishReconciliation!: (result: { outcome: 'none' }) => void;
    const reconciliation = new Promise<{ outcome: 'none' }>((resolve) => {
      finishReconciliation = resolve;
    });
    apiMocks.reconcileStaffOrderTake.mockReturnValue(reconciliation);

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Take Order' }));

    await waitFor(() => expect(apiMocks.reconcileStaffOrderTake).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Could not refresh order status. Try again.')).not.toBeInTheDocument();
    expect(screen.queryByText('This order is no longer available.')).not.toBeInTheDocument();

    await act(async () => {
      finishReconciliation({ outcome: 'none' });
      await reconciliation;
    });

    expect(screen.getByText('Could not refresh order status. Try again.')).toBeInTheDocument();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('does not reconcile an explicit HTTP response', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue({
      response: {
        status: 409,
        data: { detail: 'This order was already taken by another staff member.' },
      },
    });

    render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Take Order' }));

    expect(await screen.findByText('This order is no longer available.')).toBeInTheDocument();
    expect(apiMocks.reconcileStaffOrderTake).not.toHaveBeenCalled();
    expect(apiMocks.takeStaffOrder).toHaveBeenCalledTimes(1);
  });

  it('aborts in-flight reconciliation when the page unmounts', async () => {
    apiMocks.takeStaffOrder.mockRejectedValue(new AxiosError('network failed', 'ERR_NETWORK'));
    apiMocks.reconcileStaffOrderTake.mockReturnValue(new Promise(() => {}));
    const view = render(
      <MemoryRouter initialEntries={['/staff/orders/order-1']}>
        <Routes>
          <Route path="/staff/orders/:orderId" element={<StaffOrderDetailPage />} />
          <Route path="/staff/orders" element={<div>Orders list</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Take Order' }));
    await waitFor(() => expect(apiMocks.reconcileStaffOrderTake).toHaveBeenCalledTimes(1));

    const signal = apiMocks.reconcileStaffOrderTake.mock.calls[0]?.[2] as AbortSignal | undefined;
    expect(signal?.aborted).toBe(false);

    view.unmount();
    expect(signal?.aborted).toBe(true);
    expect(apiMocks.reconcileStaffOrderTake).toHaveBeenCalledTimes(1);
  });
});
