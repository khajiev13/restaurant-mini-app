import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import './i18n';
import App from './App';

const authState = vi.hoisted(() => ({
  bootstrapAuth: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  user: null as { role: string; phone_verified: boolean } | null,
  token: null as string | null,
  isLoading: false,
  hasHydratedUser: true,
  hasResolvedInitialAuth: true,
  authError: null as string | null,
}));

const tableOrderState = vi.hoisted(() => ({
  resolveEntry: vi.fn<(entry: string) => Promise<void>>().mockResolvedValue(undefined),
}));

vi.mock('./stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

vi.mock('./stores/tableOrderStore', () => ({
  useTableOrderStore: (selector: (state: typeof tableOrderState) => unknown) => selector(tableOrderState),
}));

vi.mock('./components/auth/PhoneVerificationGate', () => ({
  default: () => <main>Phone verification gate</main>,
}));

vi.mock('./pages/artisan/ArtisanMenuPage', () => ({
  default: () => <div>Artisan menu page <Link to="/checkout">Go to checkout</Link></div>,
}));

vi.mock('./pages/artisan/ArtisanCheckoutPage', () => ({
  default: () => <div>Artisan checkout page</div>,
}));

vi.mock('./pages/artisan/ArtisanOrdersPage', () => ({
  default: () => <div>Artisan orders page</div>,
}));

vi.mock('./pages/artisan/ArtisanProfilePage', () => ({
  default: () => <div>Artisan profile page</div>,
}));

vi.mock('./pages/artisan/ArtisanOrderStatusPage', () => ({
  default: () => <div>Artisan order status page</div>,
}));

vi.mock('./pages/staff/StaffOrdersPage', () => ({
  default: () => <div>Staff orders page</div>,
}));

vi.mock('./pages/staff/StaffOrderDetailPage', () => ({
  default: () => <div>Staff order detail page</div>,
}));

vi.mock('./pages/staff/StaffProfilePage', () => ({
  default: () => <div>Staff profile page</div>,
}));

vi.mock('./pages/staff/StaffTablesPage', () => ({
  default: () => <div>Staff tables page</div>,
}));

vi.mock('./pages/staff/StaffTableDetailPage', () => ({
  default: () => <div>Staff table detail page</div>,
}));

vi.mock('./pages/admin/AdminUsersPage', () => ({
  default: () => <div>Admin users page</div>,
}));

describe('App', () => {
  beforeEach(() => {
    cleanup();
    authState.bootstrapAuth.mockClear();
    authState.user = null;
    authState.token = null;
    authState.isLoading = false;
    authState.hasHydratedUser = true;
    authState.hasResolvedInitialAuth = true;
    authState.authError = null;
    tableOrderState.resolveEntry.mockClear();
    localStorage.clear();
    sessionStorage.clear();
    delete (window as Window & { Telegram?: unknown }).Telegram;
  });

  it('renders the artisan profile route even if a legacy theme is stored', () => {
    localStorage.setItem('app-theme', 'telegram');

    const view = render(
      <MemoryRouter initialEntries={['/profile']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Phone verification gate')).toBeInTheDocument();
  });

  it('renders without Telegram WebApp globals present', () => {
    const view = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Phone verification gate')).toBeInTheDocument();
    expect(view.queryByTestId('role-route-loading')).not.toBeInTheDocument();
    expect(authState.bootstrapAuth).toHaveBeenCalledTimes(1);
  });

  it('renders a neutral shell on Telegram cold start before auth resolves', () => {
    authState.hasHydratedUser = false;
    authState.hasResolvedInitialAuth = false;
    (window as unknown as { Telegram?: { WebApp: unknown } }).Telegram = {
      WebApp: {
        initData: 'telegram-init-data',
        ready: vi.fn(),
        expand: vi.fn(),
        setHeaderColor: vi.fn(),
        setBackgroundColor: vi.fn(),
        setBottomBarColor: vi.fn(),
        disableVerticalSwipes: vi.fn(),
        isVersionAtLeast: vi.fn(() => false),
      },
    };

    const view = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByTestId('role-route-loading')).toBeInTheDocument();
    expect(view.queryByText('Artisan menu page')).not.toBeInTheDocument();
    expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
    expect(authState.bootstrapAuth).toHaveBeenCalledTimes(1);
  });

  it('holds staff routes on a neutral shell until the stored-token user is hydrated', () => {
    authState.token = 'persisted-jwt';
    authState.hasHydratedUser = false;
    authState.hasResolvedInitialAuth = false;

    const view = render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByTestId('role-route-loading')).toBeInTheDocument();
    expect(view.queryByText('Artisan menu page')).not.toBeInTheDocument();
    expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
  });

  it('renders a retry shell when stored-token role hydration fails transiently', async () => {
    const user = userEvent.setup();
    authState.token = 'persisted-jwt';
    authState.hasHydratedUser = false;
    authState.hasResolvedInitialAuth = true;
    authState.authError = 'auth.retry_message';

    render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText('Could not verify your Telegram account. Check your connection and try again.')).toBeInTheDocument();
    expect(screen.queryByText('Artisan menu page')).not.toBeInTheDocument();
    expect(screen.queryByText('Staff orders page')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(authState.bootstrapAuth).toHaveBeenCalledTimes(2);
  });

  it('routes admin users from home to admin users page', () => {
    authState.user = { role: 'admin', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Admin users page')).toBeInTheDocument();
    expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
  });

  it('lets admin users open staff orders', () => {
    authState.user = { role: 'admin', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
  });

  it('lets staff and admin users open staff tables', () => {
    for (const role of ['staff', 'admin']) {
      cleanup();
      authState.user = { role, phone_verified: false };

      render(
        <MemoryRouter initialEntries={['/staff/tables']}>
          <App />
        </MemoryRouter>,
      );

      expect(screen.getByText('Staff tables page')).toBeInTheDocument();
    }
  });

  it('routes customer users away from staff tables back to home', () => {
    authState.user = { role: 'customer', phone_verified: true };

    render(
      <MemoryRouter initialEntries={['/staff/tables']}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText('Artisan menu page')).toBeInTheDocument();
    expect(screen.queryByText('Staff tables page')).not.toBeInTheDocument();
  });

  it('lets staff and admin open table detail but redirects customers', () => {
    for (const role of ['staff', 'admin']) {
      cleanup();
      authState.user = { role, phone_verified: false };
      render(
        <MemoryRouter initialEntries={['/staff/tables/11111111-1111-4111-8111-111111111111']}>
          <App />
        </MemoryRouter>,
      );
      expect(screen.getByText('Staff table detail page')).toBeInTheDocument();
    }

    cleanup();
    authState.user = { role: 'customer', phone_verified: true };
    render(
      <MemoryRouter initialEntries={['/staff/tables/11111111-1111-4111-8111-111111111111']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText('Artisan menu page')).toBeInTheDocument();
    expect(screen.queryByText('Staff table detail page')).not.toBeInTheDocument();
  });

  it('renders the staff order detail route for admin users', () => {
    authState.user = { role: 'admin', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/staff/orders/abc-123']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff order detail page')).toBeInTheDocument();
  });

  it('routes staff users away from admin routes to staff orders', () => {
    authState.user = { role: 'staff', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/admin']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
    expect(view.queryByText('Admin users page')).not.toBeInTheDocument();
  });

  it('renders the explicit admin users route for admin users', () => {
    authState.user = { role: 'admin', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Admin users page')).toBeInTheDocument();
    expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
  });

  it('routes staff users away from explicit admin users route to staff orders', () => {
    authState.user = { role: 'staff', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
    expect(view.queryByText('Admin users page')).not.toBeInTheDocument();
  });

  it('routes customer users away from admin routes to home', () => {
    authState.user = { role: 'customer', phone_verified: true };

    const view = render(
      <MemoryRouter initialEntries={['/admin']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan menu page')).toBeInTheDocument();
    expect(view.queryByText('Admin users page')).not.toBeInTheDocument();
  });

  it('routes staff users from home to staff orders', () => {
    authState.user = { role: 'staff', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
  });

  it('routes customer users away from staff orders back to home', () => {
    authState.user = { role: 'customer', phone_verified: true };

    const view = render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan menu page')).toBeInTheDocument();
    expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
  });

  it('routes staff users from profile to the staff profile shell', () => {
    authState.user = { role: 'staff', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/profile']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff profile page')).toBeInTheDocument();
  });

  it('routes staff users away from checkout to staff orders', () => {
    authState.user = { role: 'staff', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
  });

  it('routes staff users away from customer order detail to staff orders', () => {
    authState.user = { role: 'staff', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/order/abc-123']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
  });

  it('routes admin users away from customer order detail to admin page', () => {
    authState.user = { role: 'admin', phone_verified: false };

    const view = render(
      <MemoryRouter initialEntries={['/order/abc-123']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Admin users page')).toBeInTheDocument();
  });

  it('initializes Telegram WebApp chrome when available', () => {
    const tg = {
      ready: vi.fn(),
      expand: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
      setBottomBarColor: vi.fn(),
      disableVerticalSwipes: vi.fn(),
      isVersionAtLeast: vi.fn(() => true),
    };

    (window as unknown as { Telegram?: { WebApp: unknown } }).Telegram = { WebApp: tg };

    const view = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Phone verification gate')).toBeInTheDocument();
    expect(tg.ready).toHaveBeenCalledTimes(1);
    expect(tg.expand).toHaveBeenCalledTimes(1);
    expect(tg.setHeaderColor).toHaveBeenCalledWith('secondary_bg_color');
    expect(tg.setBackgroundColor).toHaveBeenCalledWith('bg_color');
    expect(tg.setBottomBarColor).toHaveBeenCalledWith('bottom_bar_bg_color');
    expect(tg.disableVerticalSwipes).toHaveBeenCalledTimes(1);
  });

  it('resolves a numeric Telegram table start parameter behind the gate and keeps it after unlock', () => {
    const tg = {
      initDataUnsafe: { start_param: 't2_12_q1w2e3r4t5y6' },
      ready: vi.fn(),
      expand: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
      setBottomBarColor: vi.fn(),
      disableVerticalSwipes: vi.fn(),
      isVersionAtLeast: vi.fn(() => false),
    };
    (window as unknown as { Telegram?: { WebApp: unknown } }).Telegram = { WebApp: tg };

    authState.user = { role: 'customer', phone_verified: false };
    const view = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(tableOrderState.resolveEntry).toHaveBeenCalledWith('t2_12_q1w2e3r4t5y6');
    expect(view.getByText('Phone verification gate')).toBeInTheDocument();

    authState.user = { role: 'customer', phone_verified: true };
    view.rerender(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan menu page')).toBeInTheDocument();
    expect(tableOrderState.resolveEntry).toHaveBeenCalledTimes(1);
  });

  it('resolves a legacy Telegram table start parameter behind the gate and keeps it after unlock', () => {
    const tg = {
      initDataUnsafe: { start_param: 't_A7K2P9_q1w2e3r4t5y6' },
      ready: vi.fn(),
      expand: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
      setBottomBarColor: vi.fn(),
      disableVerticalSwipes: vi.fn(),
      isVersionAtLeast: vi.fn(() => false),
    };
    (window as unknown as { Telegram?: { WebApp: unknown } }).Telegram = { WebApp: tg };

    authState.user = { role: 'customer', phone_verified: false };
    const view = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(tableOrderState.resolveEntry).toHaveBeenCalledWith('t_A7K2P9_q1w2e3r4t5y6');
    expect(view.getByText('Phone verification gate')).toBeInTheDocument();

    authState.user = { role: 'customer', phone_verified: true };
    view.rerender(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan menu page')).toBeInTheDocument();
    expect(tableOrderState.resolveEntry).toHaveBeenCalledTimes(1);
  });

  it('consumes a table start parameter only once so checkout navigation remains usable', async () => {
    const user = userEvent.setup();
    const tg = {
      initDataUnsafe: { start_param: 't2_12_q1w2e3r4t5y6' },
      ready: vi.fn(),
      expand: vi.fn(),
      setHeaderColor: vi.fn(),
      setBackgroundColor: vi.fn(),
      setBottomBarColor: vi.fn(),
      disableVerticalSwipes: vi.fn(),
      isVersionAtLeast: vi.fn(() => false),
    };
    (window as unknown as { Telegram?: { WebApp: unknown } }).Telegram = { WebApp: tg };
    authState.user = { role: 'customer', phone_verified: true };

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('link', { name: 'Go to checkout' }));

    expect(screen.getByText('Artisan checkout page')).toBeInTheDocument();
    expect(tableOrderState.resolveEntry).toHaveBeenCalledTimes(1);
  });
});
