import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Order } from '../../types/api';
import ArtisanOrdersPage from './ArtisanOrdersPage';

const apiMocks = vi.hoisted(() => ({ getOrders: vi.fn() }));
vi.mock('../../services/api', () => apiMocks);

const order: Order = {
  id: '11111111-1111-4111-8111-111111111111',
  status: 'READY',
  discriminator: 'inplace',
  items_cost: 36000,
  total_amount: 39600,
  created_at: '2026-07-13T12:00:00',
  order_number: '42',
  items: [{ id: 'somsa-1', name: 'Classic Somsa', quantity: 2, price: 18000, modifications: [] }],
  comment: null,
  payment_method: 'rahmat',
  payment_provider: 'multicard',
  payment_status: 'paid',
  payment_expires_at: null,
  multicard_checkout_url: null,
  multicard_receipt_url: null,
  alipos_order_id: null,
  alipos_sync_status: 'synced',
  table_title: 'Stol 12',
  hall_title: 'Asosiy zal',
  service_percent: 10,
};

describe('ArtisanOrdersPage table orders', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.getOrders.mockResolvedValue({ data: { data: [order] } });
  });

  it('identifies the table and online payment without exposing a shared table bill', async () => {
    render(
      <MemoryRouter>
        <ArtisanOrdersPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Stol 12')).toBeVisible();
    expect(screen.getByText('Asosiy zal')).toBeVisible();
    expect(screen.getByText(/online.*to'langan|paid online/i)).toBeVisible();
    expect(screen.queryByText(/table total|stol jami/i)).not.toBeInTheDocument();
  });
});
