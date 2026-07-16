import { StrictMode } from 'react';
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MenuData } from '../../types/api';
import type { StaffTableSummary, StaffTablesOverview } from '../../types/staffTables';
import menuCatalogSource from '../../components/menu/MenuCatalog.tsx?raw';
import staffTablesStyles from '../../staff-tables.css?raw';
import staffTablesPageSource from './StaffTablesPage.tsx?raw';
import StaffTablesPage from './StaffTablesPage';

const apiMocks = vi.hoisted(() => ({ getStaffTables: vi.fn() }));
const menuState = vi.hoisted(() => ({
  menu: {
    categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
    items: [{
      id: 'classic',
      categoryId: 'somsa',
      name: 'Classic',
      description: null,
      price: 18000,
      sortOrder: 0,
      available: true,
      availableCount: null,
    }],
  } as MenuData | null,
  loading: false,
  error: null as string | null,
  fetchMenu: vi.fn<() => Promise<void>>(),
  retry: vi.fn<() => Promise<void>>(),
}));
const authState = vi.hoisted(() => ({
  user: { role: 'staff' },
  refreshMe: vi.fn<() => Promise<{ role: string }>>(),
}));

vi.mock('../../services/staffTablesApi', () => apiMocks);
vi.mock('../../stores/menuStore', () => ({
  useMenuStore: (selector: (state: typeof menuState) => unknown) => selector(menuState),
}));
vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('../../components/menu/MenuCatalog', () => ({
  default: ({ mode }: { mode: string }) => <div>{mode} catalog</div>,
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
        const value = typeof options === 'string'
          ? options
          : options?.defaultValue ?? key;
        return value
          .replace('{{count}}', String(typeof options === 'object' ? options.count ?? '' : ''))
          .replace('{{percent}}', String(typeof options === 'object' ? options.percent ?? '' : ''));
      },
      i18n: { language: 'en' },
    }),
  };
});

const freshness = {
  generated_at: '2026-07-15T09:00:00Z',
  directory_stale: false,
  directory_last_success_at: '2026-07-15T09:00:00Z',
  order_status_stale: false,
  order_status_oldest_success_at: '2026-07-15T09:00:00Z',
};

const table = (overrides: Partial<StaffTableSummary> = {}): StaffTableSummary => ({
  table_id: '11111111-1111-4111-8111-111111111111',
  table_title: 'Table 2',
  hall_id: '22222222-2222-4222-8222-222222222222',
  hall_title: 'Main hall',
  service_percent: 10,
  is_listed: true,
  synchronized_order_count: 1,
  processing_order_count: 0,
  attention_order_count: 0,
  combined_item_count: 2,
  combined_line_count: 2,
  combined_items: [{
    id: 'somsa',
    name: 'Somsa',
    quantity: 1,
    price: 18000,
    modifications: [],
    line_total: 18000,
  }],
  items_cost: 18000,
  service_amount: 1800,
  total_amount: 19800,
  ...overrides,
});

const overview: StaffTablesOverview = {
  freshness,
  halls: [
    {
      hall_id: '22222222-2222-4222-8222-222222222222',
      hall_title: 'Main hall',
      service_percent: 10,
      is_listed: true,
      tables: [
        table({
          table_id: '11111111-1111-4111-8111-111111111110',
          table_title: 'Table 10',
          synchronized_order_count: 0,
          combined_item_count: 0,
          combined_line_count: 0,
          combined_items: [],
          items_cost: 0,
          service_amount: 0,
          total_amount: 0,
        }),
        table({
          table_id: '33333333-3333-4333-8333-333333333333',
          table_title: 'Table 3',
          synchronized_order_count: 0,
          processing_order_count: 1,
          combined_item_count: 0,
          combined_line_count: 0,
          combined_items: [],
          items_cost: 0,
          service_amount: 0,
          total_amount: 0,
        }),
        table(),
      ],
    },
    {
      hall_id: null,
      hall_title: null,
      service_percent: null,
      is_listed: false,
      tables: [table({
        table_id: '99999999-9999-4999-8999-999999999999',
        table_title: 'Removed 9',
        hall_id: null,
        hall_title: null,
        is_listed: false,
        synchronized_order_count: 0,
        attention_order_count: 1,
        combined_item_count: 0,
        combined_line_count: 0,
        combined_items: [],
        items_cost: 0,
        service_amount: 0,
        total_amount: 0,
      })],
    },
  ],
};

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
}

function HistoryControls() {
  const navigate = useNavigate();
  return (
    <div>
      <button type="button" onClick={() => navigate(-1)}>History back</button>
      <button type="button" onClick={() => navigate(1)}>History forward</button>
    </div>
  );
}

function renderPage(entry = '/staff/tables', strict = false) {
  const router = (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/staff/tables"
          element={<><StaffTablesPage /><LocationProbe /><HistoryControls /></>}
        />
        <Route path="/" element={<div>Role home</div>} />
      </Routes>
    </MemoryRouter>
  );
  return render(strict ? <StrictMode>{router}</StrictMode> : router);
}

const currentSearch = () => new URLSearchParams(screen.getByTestId('location').textContent ?? '');

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

describe('StaffTablesPage', () => {
  let styleElement: HTMLStyleElement | null = null;

  afterEach(() => {
    setVisibility('visible');
    styleElement?.remove();
    styleElement = null;
    vi.restoreAllMocks();
    cleanup();
  });

  beforeEach(() => {
    styleElement = document.createElement('style');
    styleElement.textContent = staffTablesStyles;
    document.head.append(styleElement);
    vi.clearAllMocks();
    menuState.error = null;
    menuState.loading = false;
    menuState.menu = {
      categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
      items: [{
        id: 'classic', categoryId: 'somsa', name: 'Classic', description: null,
        price: 18000, sortOrder: 0, available: true, availableCount: null,
      }],
    };
    menuState.fetchMenu.mockResolvedValue(undefined);
    menuState.retry.mockResolvedValue(undefined);
    authState.refreshMe.mockResolvedValue({ role: 'staff' });
    apiMocks.getStaffTables.mockResolvedValue({ data: { success: true, data: overview } });
  });

  it('renders every table in natural order with neutral copy and the unlisted group', async () => {
    renderPage();

    expect(await screen.findByText('No mini-app orders')).toBeInTheDocument();
    expect(screen.getByText('Unlisted tables')).toBeInTheDocument();
    const cards = screen.getAllByRole('link').filter((link) =>
      link.getAttribute('href')?.startsWith('/staff/tables/'),
    );
    expect(cards.map((card) => within(card).getByRole('heading').textContent)).toEqual([
      'Table 2', 'Table 3', 'Table 10', 'Removed 9',
    ]);
  });

  it('shows synchronized items and totals plus hall service and unlisted context', async () => {
    renderPage();

    const card = await screen.findByRole('link', { name: 'View table details: Table 2' });
    expect(within(card).getByText('1 mini-app order')).toBeInTheDocument();
    expect(within(card).getByText('Somsa × 1')).toBeInTheDocument();
    expect(within(card).getByText('+1 more')).toBeInTheDocument();
    expect(within(card).getByText('19,800 UZS')).toBeInTheDocument();

    const listedHall = screen.getByRole('region', { name: 'Main hall' });
    expect(within(listedHall).getByText('10% service')).toBeInTheDocument();
    const unlistedHall = screen.getByRole('region', { name: 'Unlisted tables' });
    expect(within(unlistedHall).getByText(
      'These tables are no longer in the current AliPOS list; saved order details are shown.',
    )).toBeInTheDocument();
  });

  it('treats processing-only activity as With orders without contradictory zero-order copy', async () => {
    const user = userEvent.setup();
    renderPage('/staff/tables?view=tables');

    const processingCard = await screen.findByRole('link', { name: 'View table details: Table 3' });
    expect(within(processingCard).getByText('1 processing')).toBeInTheDocument();
    expect(within(processingCard).queryByText('No mini-app orders')).not.toBeInTheDocument();
    expect(within(processingCard).queryByText('0 mini-app orders')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'With orders' }));
    expect(screen.getByRole('heading', { name: 'Table 3' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Table 10' })).not.toBeInTheDocument();
  });

  it('preserves query keys and browser history across filter and workspace changes', async () => {
    const user = userEvent.setup();
    renderPage('/staff/tables?view=tables&filter=all');
    await screen.findByText('Table 2');

    await user.click(screen.getByRole('button', { name: 'With orders' }));
    expect(currentSearch().get('view')).toBe('tables');
    expect(currentSearch().get('filter')).toBe('active');

    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(currentSearch().get('view')).toBe('menu');
    expect(currentSearch().get('filter')).toBe('active');

    await user.click(screen.getByRole('button', { name: 'History back' }));
    await waitFor(() => expect(currentSearch().get('view')).toBe('tables'));
    expect(currentSearch().get('filter')).toBe('active');

    await user.click(screen.getByRole('button', { name: 'History back' }));
    await waitFor(() => expect(currentSearch().get('filter')).toBe('all'));
    expect(currentSearch().get('view')).toBe('tables');

    await user.click(screen.getByRole('button', { name: 'History forward' }));
    await waitFor(() => expect(currentSearch().get('filter')).toBe('active'));
    expect(currentSearch().get('view')).toBe('tables');
  });

  it('filters attention separately while retaining the workspace query key', async () => {
    const user = userEvent.setup();
    renderPage('/staff/tables?view=tables');
    await screen.findByText('Table 2');

    await user.click(screen.getByRole('button', { name: 'Attention' }));
    expect(screen.getByText('Removed 9')).toBeInTheDocument();
    expect(screen.queryByText('Table 2')).not.toBeInTheDocument();
    expect(currentSearch().get('view')).toBe('tables');
    expect(currentSearch().get('filter')).toBe('attention');
  });

  it('keeps cached cards on refresh failure and announces recovery once', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.getStaffTables
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ data: { success: true, data: overview } });
    renderPage();
    await screen.findByText('Table 2');

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect((await screen.findAllByText('Could not refresh. Showing cached data.')).length).toBeGreaterThan(0);
    expect(consoleError).toHaveBeenCalledWith('staff_tables_workspace_load_failed', { status: 503 });
    expect(screen.getByText('Table 2')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByText('Data is up to date again.')).toBeInTheDocument();
    expect(screen.getAllByText('Data is up to date again.')).toHaveLength(1);
  });

  it('renders blocking retry for the first failure and a distinct empty directory', async () => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.getStaffTables
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce({ data: { success: true, data: overview } });
    const view = renderPage();

    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('Table 2')).toBeInTheDocument();
    view.unmount();

    apiMocks.getStaffTables.mockResolvedValue({
      data: { success: true, data: { freshness, halls: [] } },
    });
    renderPage();
    expect(await screen.findByText('AliPOS returned no tables.')).toBeInTheDocument();
  });

  it('direct-loads menu view, preserves filter, and never supplies order controls', async () => {
    renderPage('/staff/tables?view=menu&filter=attention');

    expect(await screen.findByText('Browse only · Orders cannot be placed here')).toBeInTheDocument();
    expect(screen.getByText('browse catalog')).toBeInTheDocument();
    expect(menuState.fetchMenu).toHaveBeenCalledTimes(1);
    expect(currentSearch().get('filter')).toBe('attention');
    expect(screen.queryByRole('button', { name: /add|remove/i })).not.toBeInTheDocument();
  });

  it('deduplicates a direct menu load during StrictMode effect replay', async () => {
    let resolveMenu!: () => void;
    menuState.fetchMenu.mockReturnValue(new Promise<void>((resolve) => { resolveMenu = resolve; }));

    renderPage('/staff/tables?view=menu', true);

    expect(await screen.findByText('browse catalog')).toBeInTheDocument();
    expect(menuState.fetchMenu).toHaveBeenCalledTimes(1);
    act(() => { resolveMenu(); });
  });

  it('keeps Tables available when menu loading fails and retries only the menu', async () => {
    const user = userEvent.setup();
    menuState.menu = null;
    menuState.error = 'failed';
    renderPage('/staff/tables?view=menu');

    await user.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(menuState.retry).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: 'Tables' }));
    expect(await screen.findByText('Table 2')).toBeInTheDocument();
  });

  it('falls back invalid query values to Tables and All', async () => {
    renderPage('/staff/tables?view=invalid&filter=invalid');

    expect(await screen.findByRole('button', { name: 'Tables' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows both stale warnings without hiding cached tables', async () => {
    apiMocks.getStaffTables.mockResolvedValue({
      data: {
        success: true,
        data: {
          ...overview,
          freshness: { ...freshness, directory_stale: true, order_status_stale: true },
        },
      },
    });
    renderPage();

    expect(await screen.findByText(/Table list may be outdated/)).toBeInTheDocument();
    expect(screen.getByText(/Order status may be outdated/)).toBeInTheDocument();
    expect(screen.getByText('Table 2')).toBeInTheDocument();
  });

  it.each([401, 403])('immediately hides cached table data while role refresh for %i is pending', async (status) => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let resolveRole!: (value: { role: string }) => void;
    const roleRefresh = new Promise<{ role: string }>((resolve) => { resolveRole = resolve; });
    authState.refreshMe.mockReturnValue(roleRefresh);
    apiMocks.getStaffTables
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status } });
    renderPage();
    await screen.findByText('Table 2');

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByText('Table 2')).not.toBeInTheDocument());
    expect(screen.queryByText('Removed 9')).not.toBeInTheDocument();
    expect(screen.queryByText('Role home')).not.toBeInTheDocument();
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);

    act(() => { resolveRole({ role: 'staff' }); });
    expect(await screen.findByText('Role home')).toBeInTheDocument();
  });

  it.each([
    [401, { response: { status: 503 } }],
    [403, new Error('network')],
  ] as const)(
    'keeps cached tables hidden after boundary %i when the next poll also fails',
    async (status, nextFailure) => {
      const user = userEvent.setup();
      vi.spyOn(console, 'error').mockImplementation(() => undefined);
      let resolveRole!: (value: { role: string }) => void;
      const roleRefresh = new Promise<{ role: string }>((resolve) => { resolveRole = resolve; });
      authState.refreshMe.mockReturnValue(roleRefresh);
      apiMocks.getStaffTables
        .mockResolvedValueOnce({ data: { success: true, data: overview } })
        .mockRejectedValueOnce({ response: { status } })
        .mockRejectedValueOnce(nextFailure);
      renderPage();
      await screen.findByText('Table 2');

      await user.click(screen.getByRole('button', { name: 'Refresh' }));
      await waitFor(() => expect(screen.queryByText('Table 2')).not.toBeInTheDocument());
      triggerVisibleRefresh();
      await waitFor(() => expect(apiMocks.getStaffTables).toHaveBeenCalledTimes(3));

      expect(screen.queryByText('Table 2')).not.toBeInTheDocument();
      expect(screen.queryByText('Removed 9')).not.toBeInTheDocument();
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
    apiMocks.getStaffTables
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status: 403 } })
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status: 401 } });
    renderPage();
    await screen.findByText('Table 2');

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByText('Table 2')).not.toBeInTheDocument());
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);

    triggerVisibleRefresh();
    expect(await screen.findByText('Table 2')).toBeInTheDocument();

    triggerVisibleRefresh();
    await waitFor(() => expect(screen.queryByText('Table 2')).not.toBeInTheDocument());
    expect(authState.refreshMe).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveRole({ role: 'staff' });
      await roleRefresh;
    });
    expect(await screen.findByText('Role home')).toBeInTheDocument();
  });

  it('starts a new role refresh after a recovered boundary settles without navigation', async () => {
    const user = userEvent.setup();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    let resolveFirst!: (value: { role: string }) => void;
    let resolveSecond!: (value: { role: string }) => void;
    const firstRefresh = new Promise<{ role: string }>((resolve) => { resolveFirst = resolve; });
    const secondRefresh = new Promise<{ role: string }>((resolve) => { resolveSecond = resolve; });
    authState.refreshMe
      .mockReturnValueOnce(firstRefresh)
      .mockReturnValueOnce(secondRefresh);
    apiMocks.getStaffTables
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status: 403 } })
      .mockResolvedValueOnce({ data: { success: true, data: overview } })
      .mockRejectedValueOnce({ response: { status: 403 } });
    renderPage();
    await screen.findByText('Table 2');

    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByText('Table 2')).not.toBeInTheDocument());
    triggerVisibleRefresh();
    expect(await screen.findByText('Table 2')).toBeInTheDocument();

    await act(async () => {
      resolveFirst({ role: 'staff' });
      await firstRefresh;
    });
    expect(screen.queryByText('Role home')).not.toBeInTheDocument();

    triggerVisibleRefresh();
    await waitFor(() => expect(screen.queryByText('Table 2')).not.toBeInTheDocument());
    expect(authState.refreshMe).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveSecond({ role: 'staff' });
      await secondRefresh;
    });
    expect(await screen.findByText('Role home')).toBeInTheDocument();
  });

  it('uses the unnamed-table fallback in both heading and complete accessible link label', async () => {
    const unnamedId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    apiMocks.getStaffTables.mockResolvedValue({
      data: {
        success: true,
        data: {
          freshness,
          halls: [{
            hall_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            hall_title: 'Main hall',
            service_percent: 10,
            is_listed: true,
            tables: [table({ table_id: unnamedId, table_title: '' })],
          }],
        },
      },
    });
    renderPage();

    const card = await screen.findByRole('link', { name: 'View table details: Unnamed table' });
    expect(within(card).getByRole('heading', { name: 'Unnamed table' })).toBeInTheDocument();
    expect(screen.queryByText(unnamedId)).not.toBeInTheDocument();
  });

  it('provides at least 44 by 44 pixel targets for workspace controls and table cards', async () => {
    renderPage();
    await screen.findByText('Table 2');

    const targets = [
      screen.getByRole('button', { name: 'Tables' }),
      screen.getByRole('button', { name: 'Menu' }),
      screen.getByRole('button', { name: 'Refresh' }),
      screen.getByRole('button', { name: 'All' }),
      screen.getByRole('button', { name: 'With orders' }),
      screen.getByRole('button', { name: 'Attention' }),
      screen.getByRole('link', { name: 'View table details: Table 2' }),
    ];

    for (const target of targets) {
      const style = window.getComputedStyle(target);
      expect(Number.parseFloat(style.minWidth)).toBeGreaterThanOrEqual(44);
      expect(Number.parseFloat(style.minHeight)).toBeGreaterThanOrEqual(44);
    }
  });

  it('keeps staff browse sources free of cart, table-order, checkout, and order mutation imports', () => {
    const forbidden = /useCartStore|useTableOrderStore|tableOrderStore|checkout|createOrder/;
    expect(staffTablesPageSource).not.toMatch(forbidden);
    expect(menuCatalogSource).not.toMatch(forbidden);
  });
});
