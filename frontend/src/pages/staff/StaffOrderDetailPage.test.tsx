import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffOrderDetailPage from './StaffOrderDetailPage';

const apiMocks = vi.hoisted(() => ({
  getActiveStaffOrder: vi.fn(),
  getStaffOrder: vi.fn(),
  takeStaffOrder: vi.fn(),
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
      t: (key: string, fallback?: string) => fallback ?? key,
      i18n: { language: 'en' },
    }),
  };
});

const availableOrder = {
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
    apiMocks.getStaffOrder.mockResolvedValue({ data: { data: availableOrder } });
    apiMocks.getActiveStaffOrder.mockResolvedValue({ data: { data: null } });
    apiMocks.takeStaffOrder.mockResolvedValue({ data: { data: availableOrder } });
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
});
