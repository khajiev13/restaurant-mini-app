import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const authState = vi.hoisted(() => ({
  authenticate: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
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

describe('App', () => {
  beforeEach(() => {
    authState.authenticate.mockClear();
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
    expect(authState.authenticate).toHaveBeenCalledTimes(1);
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
