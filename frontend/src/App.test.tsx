import { cleanup, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const authState = vi.hoisted(() => ({
  bootstrapAuth: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  user: null as { role: string } | null,
  token: null as string | null,
  isLoading: false,
  hasHydratedUser: true,
  hasResolvedInitialAuth: true,
}));

vi.mock('./stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

vi.mock('./pages/artisan/ArtisanMenuPage', () => ({
  default: () => <div>Artisan menu page</div>,
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

describe('App', () => {
  beforeEach(() => {
    cleanup();
    authState.bootstrapAuth.mockClear();
    authState.user = null;
    authState.token = null;
    authState.isLoading = false;
    authState.hasHydratedUser = true;
    authState.hasResolvedInitialAuth = true;
    localStorage.clear();
    delete (window as Window & { Telegram?: unknown }).Telegram;
  });

  it('renders the artisan profile route even if a legacy theme is stored', () => {
    localStorage.setItem('app-theme', 'telegram');

    const view = render(
      <MemoryRouter initialEntries={['/profile']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan profile page')).toBeInTheDocument();
  });

  it('renders without Telegram WebApp globals present', () => {
    const view = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan menu page')).toBeInTheDocument();
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

  it('routes staff users from home to staff orders', () => {
    authState.user = { role: 'staff' };

    const view = render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
  });

  it('routes customer users away from staff orders back to home', () => {
    authState.user = { role: 'customer' };

    const view = render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Artisan menu page')).toBeInTheDocument();
    expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
  });

  it('routes staff users from profile to the staff profile shell', () => {
    authState.user = { role: 'staff' };

    const view = render(
      <MemoryRouter initialEntries={['/profile']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff profile page')).toBeInTheDocument();
  });

  it('renders the staff order detail route for admin users', () => {
    authState.user = { role: 'admin' };

    const view = render(
      <MemoryRouter initialEntries={['/staff/orders/abc-123']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff order detail page')).toBeInTheDocument();
  });

  it('routes staff users away from checkout to staff orders', () => {
    authState.user = { role: 'staff' };

    const view = render(
      <MemoryRouter initialEntries={['/checkout']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
  });

  it('routes staff users away from customer order detail to staff orders', () => {
    authState.user = { role: 'admin' };

    const view = render(
      <MemoryRouter initialEntries={['/order/abc-123']}>
        <App />
      </MemoryRouter>,
    );

    expect(view.getByText('Staff orders page')).toBeInTheDocument();
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

    expect(view.getByText('Artisan checkout page')).toBeInTheDocument();
    expect(tg.ready).toHaveBeenCalledTimes(1);
    expect(tg.expand).toHaveBeenCalledTimes(1);
    expect(tg.setHeaderColor).toHaveBeenCalledWith('secondary_bg_color');
    expect(tg.setBackgroundColor).toHaveBeenCalledWith('bg_color');
    expect(tg.setBottomBarColor).toHaveBeenCalledWith('bottom_bar_bg_color');
    expect(tg.disableVerticalSwipes).toHaveBeenCalledTimes(1);
  });
});
