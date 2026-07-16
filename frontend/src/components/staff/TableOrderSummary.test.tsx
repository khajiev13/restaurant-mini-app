import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { StaffTableOrder } from '../../types/staffTables';
import TableOrderSummary from './TableOrderSummary';

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback ?? _key,
      i18n: { language: 'en' },
    }),
  };
});

const ORDER_UUID_CANARY = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const PROVIDER_STATUS_CANARY = 'PROVIDER_PRIVATE_STATUS_CANARY';
const PROVIDER_SYNC_CANARY = 'PROVIDER_PRIVATE_SYNC_CANARY';

const makeOrder = (overrides: Partial<StaffTableOrder> = {}): StaffTableOrder => ({
  id: ORDER_UUID_CANARY,
  order_number: null,
  created_at: '2026-07-15T08:45:00Z',
  status: 'NEW',
  sync_state: 'synchronized',
  sync_label: 'synchronized',
  payment_method: 'cash',
  payment_status: null,
  items: [{
    id: 'somsa',
    name: 'Classic Somsa',
    quantity: 1,
    price: 18000,
    modifications: [{ id: 'spicy', name: 'Spicy', quantity: 1, price: 1000 }],
  }],
  items_cost: 18000,
  service_amount: 1800,
  total_amount: 19800,
  ...overrides,
});

afterEach(() => cleanup());

describe('TableOrderSummary', () => {
  it.each([
    ['NEW', 'Placed'],
    ['PAID_AWAITING_RESTAURANT', 'Placed'],
    ['ACCEPTED_BY_RESTAURANT', 'Preparing'],
    ['READY', 'Ready'],
    [PROVIDER_STATUS_CANARY, 'Active'],
    ['toString', 'Active'],
  ])('maps provider status %s to safe copy', (status, expected) => {
    const { container } = render(<TableOrderSummary order={makeOrder({ status })} />);

    expect(within(container).getByText(expected)).toBeInTheDocument();
    expect(container).not.toHaveTextContent(PROVIDER_STATUS_CANARY);
    expect(container).not.toHaveTextContent(ORDER_UUID_CANARY);
  });

  it.each([
    ['processing', 'Processing'],
    ['not_synchronized', 'Not synchronized'],
    ['verify_in_pos', 'Verify in POS'],
    [PROVIDER_SYNC_CANARY, 'Active'],
  ] as const)('maps sync label %s without exposing provider copy', (syncLabel, expected) => {
    const unsafeOrder = {
      ...makeOrder({ status: PROVIDER_STATUS_CANARY }),
      sync_label: syncLabel,
      sync_state: PROVIDER_SYNC_CANARY,
    } as unknown as StaffTableOrder;
    const { container } = render(<TableOrderSummary order={unsafeOrder} />);

    expect(within(container).getByText(expected)).toBeInTheDocument();
    expect(container).not.toHaveTextContent(PROVIDER_STATUS_CANARY);
    expect(container).not.toHaveTextContent(PROVIDER_SYNC_CANARY);
    expect(container.querySelector('article')).toHaveClass('staff-table-order--attention');
  });

  it.each([
    ['cash', null, 'Cash'],
    ['online', 'paid', 'Online · Paid'],
    ['online', null, 'Online · Payment status unknown'],
  ] as const)('maps %s payment state safely', (paymentMethod, paymentStatus, expected) => {
    const { container } = render(
      <TableOrderSummary
        order={makeOrder({ payment_method: paymentMethod, payment_status: paymentStatus })}
      />,
    );

    expect(within(container).getByText(new RegExp(expected.replace(' · ', '.*')))).toBeInTheDocument();
    expect(container).not.toHaveTextContent(ORDER_UUID_CANARY);
  });

  it('keeps the order boundary, semantic timestamp, modifiers, and persisted totals', () => {
    render(<TableOrderSummary order={makeOrder({ order_number: '1042' })} />);

    const article = screen.getByRole('article');
    expect(within(article).getByText('#1042')).toBeInTheDocument();
    expect(within(article).getByText('Classic Somsa × 1')).toBeInTheDocument();
    expect(within(article).getByRole('list', { name: 'Modifiers' })).toHaveTextContent('Spicy × 1');
    expect(within(article).getByText('19,000 UZS')).toBeInTheDocument();
    expect(within(article).getByText('19,800 UZS')).toBeInTheDocument();
    expect(article.querySelector('time')).toHaveAttribute('datetime', '2026-07-15T08:45:00Z');
    expect(within(article).getByText('check_circle').closest('[aria-hidden="true"]')).not.toBeNull();
  });
});
