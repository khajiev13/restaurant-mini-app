import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StaffTableDetail, StaffTableOrder } from '../../types/staffTables';
import StaffTableDetailPage from './StaffTableDetailPage';

const apiMocks = vi.hoisted(() => ({ getStaffTable: vi.fn() }));
const authState = vi.hoisted(() => ({
  user: { role: 'staff' },
  refreshMe: vi.fn<() => Promise<{ role: string }>>(),
}));

vi.mock('../../services/staffTablesApi', () => apiMocks);
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, options?: string | { defaultValue?: string; count?: number; percent?: number }) => {
        if (key === 'staff_tables.mini_app_orders' && typeof options === 'object') {
          return `${options.count} mini-app ${options.count === 1 ? 'order' : 'orders'}`;
        }
        const value = typeof options === 'string' ? options : options?.defaultValue ?? key;
        return value
          .replace('{{count}}', String(typeof options === 'object' ? options.count ?? '' : ''))
          .replace('{{percent}}', String(typeof options === 'object' ? options.percent ?? '' : ''));
      },
      i18n: { language: 'en' },
    }),
  };
});

const TABLE_A = '11111111-1111-4111-8111-111111111111';
const TABLE_B = '22222222-2222-4222-8222-222222222222';
const ORDER_UUID_CANARY = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const PHONE_CANARY = '+998901112233';
const TELEGRAM_CANARY = '@private_telegram_canary';

const freshness = {
  generated_at: '2026-07-15T09:00:00Z',
  directory_stale: false,
  directory_last_success_at: '2026-07-15T09:00:00Z',
  order_status_stale: false,
  order_status_oldest_success_at: '2026-07-15T09:00:00Z',
};

const order = (overrides: Partial<StaffTableOrder> = {}): StaffTableOrder => ({
  id: ORDER_UUID_CANARY,
  order_number: '1042',
  created_at: '2026-07-15T08:45:00Z',
  status: 'NEW',
  sync_state: 'synchronized',
  sync_label: 'synchronized',
  payment_method: 'cash',
  payment_status: null,
  items: [{
    id: 'original-somsa',
    name: 'Original Somsa',
    quantity: 1,
    price: 6000,
    modifications: [{ id: 'original-spicy', name: 'Original Spicy', quantity: 1, price: 1000 }],
  }],
  items_cost: 6000,
  service_amount: 600,
  total_amount: 6600,
  ...overrides,
});

const detailFixture: StaffTableDetail = {
  freshness,
  table: {
    table_id: TABLE_A,
    table_title: 'Table Alpha',
    hall_id: '33333333-3333-4333-8333-333333333333',
    hall_title: 'Main hall',
    service_percent: 10,
    is_listed: true,
    synchronized_order_count: 1,
    processing_order_count: 1,
    attention_order_count: 2,
    combined_item_count: 1,
    combined_line_count: 1,
    combined_items: [{
      id: 'combined-somsa',
      name: 'Combined Somsa',
      quantity: 1,
      price: 18000,
      modifications: [{ id: 'combined-spicy', name: 'Combined Spicy', quantity: 1, price: 1000 }],
      line_total: 19000,
    }],
    items_cost: 18000,
    service_amount: 1800,
    total_amount: 19800,
  },
  orders: [
    order(),
    order({
      id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
      order_number: null,
      sync_state: 'processing',
      sync_label: 'processing',
      items: [{ id: 'processing', name: 'Processing item', quantity: 1, price: 20000, modifications: [] }],
      items_cost: 20000,
      service_amount: 2000,
      total_amount: 22000,
    }),
    order({
      id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
      order_number: null,
      sync_state: 'attention',
      sync_label: 'not_synchronized',
      items: [{ id: 'failed', name: 'Failed item', quantity: 1, price: 30000, modifications: [] }],
      items_cost: 30000,
      service_amount: 3000,
      total_amount: 33000,
    }),
    order({
      id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
      order_number: null,
      sync_state: 'attention',
      sync_label: 'verify_in_pos',
      items: [{ id: 'verify', name: 'Verify item', quantity: 1, price: 40000, modifications: [] }],
      items_cost: 40000,
      service_amount: 4000,
      total_amount: 44000,
    }),
  ],
};

function RouteControls() {
  const navigate = useNavigate();
  return (
    <div>
      <button type="button" onClick={() => navigate(`/staff/tables/${TABLE_B}`)}>Open table B</button>
      <button type="button" onClick={() => navigate(-1)}>History back</button>
    </div>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function renderRoute(initialEntry = `/staff/tables/${TABLE_A}`) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/staff/tables/:tableId"
          element={<><StaffTableDetailPage /><RouteControls /><LocationProbe /></>}
        />
        <Route path="/staff/tables" element={<><div>Tables destination</div><RouteControls /><LocationProbe /></>} />
        <Route path="/" element={<div>Role home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const setVisibility = (value: DocumentVisibilityState) => {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    value,
  });
};

const triggerVisibleRefresh = () => {
  setVisibility('visible');
  act(() => { document.dispatchEvent(new Event('visibilitychange')); });
};

const success = (data: StaffTableDetail = detailFixture) => ({
  data: { success: true, data },
});

describe('StaffTableDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.refreshMe.mockResolvedValue({ role: 'staff' });
    apiMocks.getStaffTable.mockResolvedValue(success());
  });

  afterEach(() => {
    setVisibility('visible');
    vi.restoreAllMocks();
    cleanup();
  });

  it('uses only the table aggregate for the combined card and preserves every original order article', async () => {
    const unsafeDetail = {
      ...detailFixture,
      customer_phone: PHONE_CANARY,
      telegram_username: TELEGRAM_CANARY,
    } as StaffTableDetail;
    apiMocks.getStaffTable.mockResolvedValue(success(unsafeDetail));
    const { container } = renderRoute();

    const combined = await screen.findByRole('region', { name: 'Combined summary' });
    expect(within(combined).getByText('Combined Somsa × 1')).toBeInTheDocument();
    expect(within(combined).getByText('Combined Spicy × 1')).toBeInTheDocument();
    expect(within(combined).getByText('19,000 UZS')).toBeInTheDocument();
    expect(within(combined).getByText('19,800 UZS')).toBeInTheDocument();
    expect(within(combined).queryByText('Original Somsa × 1')).not.toBeInTheDocument();
    expect(within(combined).queryByText('22,000 UZS')).not.toBeInTheDocument();
    expect(within(combined).queryByText('33,000 UZS')).not.toBeInTheDocument();
    expect(within(combined).queryByText('44,000 UZS')).not.toBeInTheDocument();

    const originalOrders = screen.getByRole('region', { name: 'Original orders' });
    const articles = within(originalOrders).getAllByRole('article');
    expect(articles).toHaveLength(4);
    expect(within(articles[0]).getByText('6,600 UZS')).toBeInTheDocument();
    expect(within(articles[1]).getByText('22,000 UZS')).toBeInTheDocument();
    expect(within(articles[2]).getByText('33,000 UZS')).toBeInTheDocument();
    expect(within(articles[3]).getByText('44,000 UZS')).toBeInTheDocument();
    expect(within(originalOrders).getByRole('heading', { name: 'Synchronized' })).toBeInTheDocument();
    expect(within(originalOrders).getByRole('heading', { name: 'Processing' })).toBeInTheDocument();
    expect(within(originalOrders).getByRole('heading', { name: 'Needs attention' })).toBeInTheDocument();
    const workspace = container.querySelector('main');
    expect(workspace).not.toHaveTextContent(TABLE_A);
    expect(workspace).not.toHaveTextContent(ORDER_UUID_CANARY);
    expect(workspace).not.toHaveTextContent(PHONE_CANARY);
    expect(workspace).not.toHaveTextContent(TELEGRAM_CANARY);
  });

  it('renders loading, blocking retry, and a definitive 404 without cached detail or Retry', async () => {
    const user = userEvent.setup();
    let resolveInitial!: (value: ReturnType<typeof success>) => void;
    const initial = new Promise<ReturnType<typeof success>>((resolve) => { resolveInitial = resolve; });
    apiMocks.getStaffTable.mockReturnValueOnce(initial);
    const loading = renderRoute();
    expect(screen.getByLabelText('Loading...')).toBeInTheDocument();
    loading.unmount();
    await act(async () => {
      resolveInitial(success());
      await initial;
    });

    apiMocks.getStaffTable
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce(success());
    const retry = renderRoute();
    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('heading', { name: 'Table Alpha' })).toBeInTheDocument();
    retry.unmount();

    apiMocks.getStaffTable
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 404 } });
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByText('Table not found')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
  });

  it('keeps cached detail only for transient refresh failure and announces recovery once', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.getStaffTable
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce(success());
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect((await screen.findAllByText('Could not refresh. Showing cached data.')).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Table Alpha' })).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith('staff_tables_workspace_load_failed', { status: 503 });

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByText('Data is up to date again.')).toBeInTheDocument();
    expect(screen.getAllByText('Data is up to date again.')).toHaveLength(1);
  });

  it('does not retain cached detail for a non-transient client error', async () => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.getStaffTable
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 422 } });
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });

    await user.click(screen.getByRole('button', { name: 'Refresh' }));

    expect(await screen.findByText('Tables are temporarily unavailable.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();
  });

  it('retains saved unlisted hall, table, and service metadata', async () => {
    apiMocks.getStaffTable.mockResolvedValue(success({
      ...detailFixture,
      table: {
        ...detailFixture.table,
        is_listed: false,
        table_title: 'Patio 9',
        hall_title: 'Old patio',
        service_percent: 12,
      },
    }));
    renderRoute();

    expect(await screen.findByRole('heading', { name: 'Patio 9' })).toBeInTheDocument();
    expect(screen.getByText('Old patio')).toBeInTheDocument();
    expect(screen.getByText('12% service')).toBeInTheDocument();
    expect(screen.getByText('Unlisted tables')).toBeInTheDocument();
  });

  it.each([401, 403])('immediately hides cached detail and deduplicates role refresh for %i', async (status) => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let resolveRole!: (value: { role: string }) => void;
    const roleRefresh = new Promise<{ role: string }>((resolve) => { resolveRole = resolve; });
    authState.refreshMe.mockReturnValue(roleRefresh);
    apiMocks.getStaffTable
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status } });
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument());
    expect(screen.queryByText('Combined Somsa × 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Role home')).not.toBeInTheDocument();
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRole({ role: 'staff' });
      await roleRefresh;
    });
    expect(await screen.findByText('Role home')).toBeInTheDocument();
  });

  it.each([
    [401, { response: { status: 503 } }],
    [403, new Error('network')],
  ] as const)(
    'keeps cached detail hidden after boundary %i when the next poll also fails',
    async (status, nextFailure) => {
      const user = userEvent.setup();
      vi.spyOn(console, 'error').mockImplementation(() => undefined);
      let resolveRole!: (value: { role: string }) => void;
      const roleRefresh = new Promise<{ role: string }>((resolve) => { resolveRole = resolve; });
      authState.refreshMe.mockReturnValue(roleRefresh);
      apiMocks.getStaffTable
        .mockResolvedValueOnce(success())
        .mockRejectedValueOnce({ response: { status } })
        .mockRejectedValueOnce(nextFailure);
      renderRoute();
      await screen.findByRole('heading', { name: 'Table Alpha' });

      await user.click(screen.getByRole('button', { name: 'Refresh' }));
      await waitFor(() => expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument());
      triggerVisibleRefresh();
      await waitFor(() => expect(apiMocks.getStaffTable).toHaveBeenCalledTimes(3));

      expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();
      expect(screen.queryByText('Combined Somsa × 1')).not.toBeInTheDocument();
      expect(screen.queryByText('Could not refresh. Showing cached data.')).not.toBeInTheDocument();
      expect(screen.queryByText('Tables are temporarily unavailable.')).not.toBeInTheDocument();
      expect(screen.getByLabelText('Loading...')).toBeInTheDocument();
      expect(authState.refreshMe).toHaveBeenCalledTimes(1);

      await act(async () => {
        resolveRole({ role: 'staff' });
        await roleRefresh;
      });
      expect(await screen.findByText('Role home')).toBeInTheDocument();
    },
  );

  it('reattaches navigation when an authorization boundary recurs during the same role refresh', async () => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let resolveRole!: (value: { role: string }) => void;
    const roleRefresh = new Promise<{ role: string }>((resolve) => { resolveRole = resolve; });
    authState.refreshMe.mockReturnValue(roleRefresh);
    apiMocks.getStaffTable
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 403 } })
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 401 } });
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(authState.refreshMe).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();

    triggerVisibleRefresh();
    expect(await screen.findByRole('heading', { name: 'Table Alpha' })).toBeInTheDocument();

    triggerVisibleRefresh();
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument());
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRole({ role: 'staff' });
      await roleRefresh;
    });
    expect(await screen.findByText('Role home')).toBeInTheDocument();
  });

  it('starts a fresh role check after a recovered boundary settles without navigation', async () => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let resolveFirst!: (value: { role: string }) => void;
    let resolveSecond!: (value: { role: string }) => void;
    const first = new Promise<{ role: string }>((resolve) => { resolveFirst = resolve; });
    const second = new Promise<{ role: string }>((resolve) => { resolveSecond = resolve; });
    authState.refreshMe.mockReturnValueOnce(first).mockReturnValueOnce(second);
    apiMocks.getStaffTable
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 403 } })
      .mockResolvedValueOnce(success())
      .mockRejectedValueOnce({ response: { status: 401 } });
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(authState.refreshMe).toHaveBeenCalledTimes(1));
    triggerVisibleRefresh();
    expect(await screen.findByRole('heading', { name: 'Table Alpha' })).toBeInTheDocument();

    await act(async () => {
      resolveFirst({ role: 'staff' });
      await first;
    });
    expect(screen.queryByText('Role home')).not.toBeInTheDocument();

    triggerVisibleRefresh();
    await waitFor(() => expect(authState.refreshMe).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();
    await act(async () => {
      resolveSecond({ role: 'staff' });
      await second;
    });
    expect(await screen.findByText('Role home')).toBeInTheDocument();
  });

  it('remounts by table id so cached A and its announcement cannot flash while B loads', async () => {
    const user = userEvent.setup();
    let resolveB!: (value: ReturnType<typeof success>) => void;
    const pendingB = new Promise<ReturnType<typeof success>>((resolve) => { resolveB = resolve; });
    const staleA = {
      ...detailFixture,
      freshness: { ...freshness, directory_stale: true },
    };
    apiMocks.getStaffTable.mockImplementation((id: string) => (
      id === TABLE_A ? Promise.resolve(success(staleA)) : pendingB
    ));
    renderRoute();
    await screen.findByRole('heading', { name: 'Table Alpha' });
    expect(screen.getByText(/Table list may be outdated/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open table B' }));
    expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Table list may be outdated/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('Loading...')).toBeInTheDocument();

    const detailB = {
      ...detailFixture,
      freshness,
      table: { ...detailFixture.table, table_id: TABLE_B, table_title: 'Table Beta' },
    };
    await act(async () => {
      resolveB(success(detailB));
      await pendingB;
    });
    expect(await screen.findByRole('heading', { name: 'Table Beta' })).toBeInTheDocument();
    expect(screen.queryByText('Could not refresh. Showing cached data.')).not.toBeInTheDocument();
  });

  it('ignores a late A response after direct navigation to B', async () => {
    const user = userEvent.setup();
    let resolveA!: (value: ReturnType<typeof success>) => void;
    let resolveB!: (value: ReturnType<typeof success>) => void;
    const pendingA = new Promise<ReturnType<typeof success>>((resolve) => { resolveA = resolve; });
    const pendingB = new Promise<ReturnType<typeof success>>((resolve) => { resolveB = resolve; });
    apiMocks.getStaffTable.mockImplementation((id: string) => (id === TABLE_A ? pendingA : pendingB));
    renderRoute();

    await user.click(screen.getByRole('button', { name: 'Open table B' }));
    const detailB = {
      ...detailFixture,
      table: { ...detailFixture.table, table_id: TABLE_B, table_title: 'Table Beta' },
    };
    await act(async () => {
      resolveB(success(detailB));
      await pendingB;
    });
    expect(await screen.findByRole('heading', { name: 'Table Beta' })).toBeInTheDocument();

    await act(async () => {
      resolveA(success());
      await pendingA;
    });
    expect(screen.getByRole('heading', { name: 'Table Beta' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Table Alpha' })).not.toBeInTheDocument();
  });

  it('uses an explicit overview link without replacing browser history', async () => {
    const user = userEvent.setup();
    renderRoute();
    const back = await screen.findByRole('link', { name: 'Back to tables' });
    expect(back).toHaveAttribute('href', '/staff/tables');

    await user.click(back);
    expect(screen.getByText('Tables destination')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'History back' }));
    expect(await screen.findByRole('heading', { name: 'Table Alpha' })).toBeInTheDocument();
  });

  it('uses semantic headings and time plus 44px focusable controls that wrap narrowly', async () => {
    renderRoute();
    expect(await screen.findByRole('heading', { level: 1, name: 'Table Alpha' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Combined summary' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Combined items' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Original orders' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Synchronized' })).toBeInTheDocument();
    expect(document.querySelector('time')).toHaveAttribute('datetime', '2026-07-15T08:45:00Z');

    for (const target of [
      screen.getByRole('link', { name: 'Back to tables' }),
      screen.getByRole('button', { name: 'Refresh' }),
    ]) {
      const style = window.getComputedStyle(target);
      expect(Number.parseFloat(style.minWidth)).toBeGreaterThanOrEqual(44);
      expect(Number.parseFloat(style.minHeight)).toBeGreaterThanOrEqual(44);
    }
    const heading = screen.getByRole('heading', { level: 1, name: 'Table Alpha' });
    expect(window.getComputedStyle(heading).overflowWrap).toBe('anywhere');
    expect(window.getComputedStyle(heading.closest('header') as HTMLElement).flexWrap).toBe('wrap');
  });
});
