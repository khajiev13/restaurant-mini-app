import { cleanup, render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ArtisanProfilePage from './ArtisanProfilePage';

const authState = vi.hoisted(() => ({
  isAuthenticated: true,
  authenticate: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  user: {
    telegram_id: 1,
    first_name: 'Jane',
    last_name: 'Doe',
    username: 'janedoe',
    photo_url: null,
    phone_number: '+998901234567',
    phone_verified: true,
    language: 'en',
    role: 'customer' as const,
    inplace_online_payment_enabled: false,
  },
}));

const phoneVerification = vi.hoisted(() => ({
  status: 'ready' as const,
  requestPhone: vi.fn(),
  checkAgain: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));

const apiMocks = vi.hoisted(() => ({
  deleteAddress: vi.fn(),
  getAddresses: vi.fn(),
  getMe: vi.fn(),
  getOrders: vi.fn(),
  updateMe: vi.fn(),
}));

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, fallback?: string) => fallback ?? key,
      i18n: {
        language: 'en',
        changeLanguage: vi.fn<(_: string) => Promise<void>>().mockResolvedValue(undefined),
      },
    }),
  };
});

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));
vi.mock('../../hooks/usePhoneVerification', () => ({
  usePhoneVerification: () => phoneVerification,
}));

vi.mock('../../services/api', () => apiMocks);

describe('ArtisanProfilePage', () => {
  beforeEach(() => {
    cleanup();
    authState.authenticate.mockClear();
    authState.user.phone_number = '+998901234567';
    phoneVerification.requestPhone.mockClear();
    apiMocks.getMe.mockResolvedValue({
      data: {
        data: {
          telegram_id: 1,
          first_name: 'Jane',
          last_name: 'Doe',
          username: 'janedoe',
          photo_url: null,
          phone_number: '+998901234567',
          language: 'en',
        },
      },
    });
    apiMocks.getOrders.mockResolvedValue({
      data: {
        data: [],
      },
    });
    apiMocks.getAddresses.mockResolvedValue({
      data: {
        data: [],
      },
    });
    apiMocks.updateMe.mockResolvedValue({ data: { data: null } });
    apiMocks.deleteAddress.mockResolvedValue({ data: { data: null } });
  });

  it('does not render the old theme selector section', async () => {
    const view = render(
      <MemoryRouter>
        <ArtisanProfilePage />
      </MemoryRouter>,
    );

    expect(await view.findByText('Jane Doe')).toBeInTheDocument();

    expect(apiMocks.getMe).not.toHaveBeenCalled();
    expect(view.queryByText('Design Theme')).not.toBeInTheDocument();
    expect(view.getByText('profile.language')).toBeInTheDocument();
  });

  it('masks the verified phone, updates it through the shared hook, and has no customer logout', async () => {
    const user = userEvent.setup();
    const view = render(
      <MemoryRouter>
        <ArtisanProfilePage />
      </MemoryRouter>,
    );

    expect(await view.findByText('+998 90 *** 4567')).toBeVisible();
    expect(view.queryByText('+998901234567')).not.toBeInTheDocument();
    expect(view.queryByRole('button', { name: /log out|logout/i })).not.toBeInTheDocument();

    await user.click(view.getByRole('button', { name: /phone_verification\.update|telegram/i }));
    expect(phoneVerification.requestPhone).toHaveBeenCalledTimes(1);

    authState.user.phone_number = '+998935559999';
    view.rerender(
      <MemoryRouter>
        <ArtisanProfilePage />
      </MemoryRouter>,
    );
    expect(view.getByText('+998 93 *** 9999')).toBeVisible();
  });
});
