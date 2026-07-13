import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCartStore } from '../../stores/cartStore';
import type { Order } from '../../types/api';
import ArtisanOrderStatusPage from './ArtisanOrderStatusPage';

const apiMocks = vi.hoisted(() => ({
  cancelOrder: vi.fn(),
  getOrder: vi.fn(),
  getOrderStatus: vi.fn(),
  switchOrderToCash: vi.fn(),
}));

vi.mock('../../services/api', () => apiMocks);

const tableOrder: Order = {
  id: '11111111-1111-4111-8111-111111111111',
  status: 'NEW',
  discriminator: 'inplace',
  items_cost: 36000,
  total_amount: 39600,
  created_at: '2026-07-13T12:00:00',
  order_number: '42',
  items: [{ id: 'somsa-1', name: 'Classic Somsa', quantity: 2, price: 18000, modifications: [] }],
  comment: null,
  payment_method: 'cash',
  payment_provider: null,
  payment_status: null,
  payment_expires_at: null,
  multicard_checkout_url: null,
  multicard_receipt_url: null,
  alipos_order_id: '22222222-2222-4222-8222-222222222222',
  alipos_sync_status: 'synced',
  table_title: 'Stol 12',
  hall_title: 'Asosiy zal',
  service_percent: 10,
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/order/${tableOrder.id}`]}>
      <Routes>
        <Route path="/order/:orderId" element={<ArtisanOrderStatusPage />} />
        <Route path="/" element={<div>Menu destination</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ArtisanOrderStatusPage table mode', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    Object.defineProperty(window, 'Telegram', {
      configurable: true,
      value: {
        WebApp: {
          initData: 'telegram-init-data',
          BackButton: { onClick: vi.fn(), offClick: vi.fn(), show: vi.fn(), hide: vi.fn() },
          HapticFeedback: { notificationOccurred: vi.fn() },
          openLink: vi.fn(),
        },
      },
    });
    apiMocks.getOrder.mockResolvedValue({ data: { data: tableOrder } });
    apiMocks.getOrderStatus.mockResolvedValue({
      data: {
        data: {
          status: 'NEW',
          order_number: '42',
          alipos_order_id: tableOrder.alipos_order_id,
          payment_status: null,
          payment_expires_at: null,
          multicard_receipt_url: null,
          table_title: 'Stol 12',
          hall_title: 'Asosiy zal',
          service_percent: 10,
          alipos_sync_status: 'synced',
        },
      },
    });
    useCartStore.setState({ items: [] });
  });

  it('shows table tracking without delivery or internal identifiers', async () => {
    renderPage();

    expect(await screen.findByText('Stol 12')).toBeVisible();
    expect(screen.getByText('Asosiy zal')).toBeVisible();
    expect(screen.getByText(/naqd pul|cash/i)).toBeVisible();
    expect(screen.queryByText(/on the way|yo'lda/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ichki buyurtma|internal order/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/alipos/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /bekor qilish|cancel order/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /yana buyurtma|order more/i })).toBeVisible();
  });

  it('cancels a new table order after confirmation', async () => {
    const user = userEvent.setup();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    apiMocks.cancelOrder.mockResolvedValue({
      data: { data: { ...tableOrder, status: 'CANCELLED' } },
    });
    renderPage();

    await user.click(await screen.findByRole('button', { name: /bekor qilish|cancel order/i }));

    await waitFor(() => expect(apiMocks.cancelOrder).toHaveBeenCalledWith(tableOrder.id));
    expect(await screen.findByText(/bekor qilindi|cancelled/i)).toBeVisible();
  });

  it('can invalidate a pending online invoice and submit the order as cash', async () => {
    const user = userEvent.setup();
    const pending = {
      ...tableOrder,
      status: 'AWAITING_PAYMENT',
      payment_method: 'rahmat',
      payment_provider: 'multicard',
      payment_status: 'pending',
      multicard_checkout_url: 'https://pay.example/checkout',
      alipos_order_id: null,
      alipos_sync_status: 'awaiting_payment',
    } satisfies Order;
    apiMocks.getOrder.mockResolvedValue({ data: { data: pending } });
    apiMocks.getOrderStatus.mockResolvedValue({
      data: { data: { ...pending, multicard_checkout_url: undefined } },
    });
    apiMocks.switchOrderToCash.mockResolvedValue({
      data: { data: { ...pending, status: 'NEW', payment_method: 'cash', payment_status: null } },
    });
    renderPage();

    expect(await screen.findByRole('button', { name: /online.*qayta|retry online/i })).toBeVisible();
    await user.click(screen.getByRole('button', { name: /naqd.*o'tish|switch to cash/i }));

    await waitFor(() => expect(apiMocks.switchOrderToCash).toHaveBeenCalledWith(tableOrder.id));
    expect(await screen.findByText(/naqd pul|cash/i)).toBeVisible();
  });

  it('clears only the current cart when ordering more', async () => {
    const user = userEvent.setup();
    useCartStore.setState({ items: [{
      id: 'other', categoryId: 'somsa', name: 'Other', description: null,
      price: 1000, sortOrder: 0, available: true, availableCount: null,
      quantity: 1,
    }] });
    renderPage();

    await user.click(await screen.findByRole('button', { name: /yana buyurtma|order more/i }));

    expect(useCartStore.getState().items).toEqual([]);
    expect(screen.getByText('Menu destination')).toBeVisible();
  });
});
