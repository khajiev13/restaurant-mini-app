import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffOrdersPage from './StaffOrdersPage';

const apiMocks = vi.hoisted(() => ({
  getActiveStaffOrder: vi.fn(),
  getAvailableStaffOrders: vi.fn(),
  getCompletedStaffOrders: vi.fn(),
  markStaffOrderDelivered: vi.fn(),
  takeStaffOrder: vi.fn(),
}));

vi.mock('../../services/staffApi', () => apiMocks);

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

const staffOrder = {
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

  it('renders simplified staff nav and tabs', async () => {
    render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <StaffOrdersPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Available')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
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
  });
});
