import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffProfilePage from './StaffProfilePage';

const authState = vi.hoisted(() => ({
  logout: vi.fn(),
}));

const apiMocks = vi.hoisted(() => ({
  getMe: vi.fn(),
}));

const i18nMock = vi.hoisted(() => ({
  t: (key: string, fallback?: string) => fallback ?? key,
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

vi.mock('../../services/api', async () => {
  const actual = await vi.importActual<typeof import('../../services/api')>('../../services/api');
  return {
    ...actual,
    ...apiMocks,
  };
});

vi.mock('react-i18next', async () => {
  const actual = await vi.importActual<typeof import('react-i18next')>('react-i18next');
  return {
    ...actual,
    useTranslation: () => i18nMock,
  };
});

describe('StaffProfilePage', () => {
  beforeEach(() => {
    authState.logout.mockClear();
    apiMocks.getMe.mockReset();
  });

  it('shows an error state and retries when loading the profile fails', async () => {
    const user = userEvent.setup();

    apiMocks.getMe
      .mockRejectedValueOnce(new Error('profile failed'))
      .mockResolvedValueOnce({
        data: {
          data: {
            telegram_id: 7,
            first_name: 'Dilshod',
            last_name: 'T.',
            username: 'dilshod',
            phone_number: '+998900001122',
            role: 'staff',
            language: 'en',
            photo_url: null,
          },
        },
      });

    render(
      <MemoryRouter>
        <StaffProfilePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Could not load your profile.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByText('Dilshod T.')).toBeInTheDocument();
    expect(apiMocks.getMe).toHaveBeenCalledTimes(2);
  });
});
