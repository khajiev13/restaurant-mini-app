import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ArtisanProfilePage from './ArtisanProfilePage';

const authState = vi.hoisted(() => ({
  isAuthenticated: true,
  authenticate: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  logout: vi.fn(),
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

vi.mock('../../services/api', () => apiMocks);

describe('ArtisanProfilePage', () => {
  beforeEach(() => {
    authState.logout.mockClear();
    authState.authenticate.mockClear();
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

    expect(apiMocks.getMe).toHaveBeenCalledTimes(1);
    expect(view.queryByText('Design Theme')).not.toBeInTheDocument();
    expect(view.getByText('profile.language')).toBeInTheDocument();
  });
});
