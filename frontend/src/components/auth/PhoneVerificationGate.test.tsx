import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '../../i18n';
import type { PhoneVerificationStatus } from '../../hooks/usePhoneVerification';
import PhoneVerificationGate from './PhoneVerificationGate';

const controller = vi.hoisted(() => ({
  status: 'ready' as PhoneVerificationStatus,
  requestPhone: vi.fn(),
  checkAgain: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
}));

const hookMock = vi.hoisted(() => vi.fn(() => controller));

vi.mock('../../hooks/usePhoneVerification', () => ({
  usePhoneVerification: hookMock,
}));

describe('PhoneVerificationGate', () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    controller.status = 'ready';
    await i18n.changeLanguage('en');
  });

  afterEach(() => {
    cleanup();
  });

  it('automatically requests once through the hook and keeps a visible share action', async () => {
    const user = userEvent.setup();
    render(<PhoneVerificationGate />);

    expect(hookMock).toHaveBeenCalledWith({ autoRequest: true });
    expect(screen.getByRole('heading', { name: 'Verify your phone' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Share phone' }));
    expect(controller.requestPhone).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['requesting', 'Waiting for Telegram…'],
    ['verifying', 'Verifying your phone…'],
  ] as const)('shows a busy presentation while %s', (status, copy) => {
    controller.status = status;
    render(<PhoneVerificationGate />);

    expect(screen.getByText(copy)).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveAttribute('aria-busy', 'true');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('keeps a manual retry after contact sharing is declined', async () => {
    const user = userEvent.setup();
    controller.status = 'declined';
    render(<PhoneVerificationGate />);

    expect(screen.getByText('Phone sharing was declined.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Share phone' }));
    expect(controller.requestPhone).toHaveBeenCalledTimes(1);
  });

  it('offers both profile polling and a fresh share after webhook delay', async () => {
    const user = userEvent.setup();
    controller.status = 'delayed';
    render(<PhoneVerificationGate />);

    await user.click(screen.getByRole('button', { name: 'Check again' }));
    await user.click(screen.getByRole('button', { name: 'Share phone again' }));
    expect(controller.checkAgain).toHaveBeenCalledTimes(1);
    expect(controller.requestPhone).toHaveBeenCalledTimes(1);
  });

  it('offers retry actions after a network-only polling cycle', async () => {
    const user = userEvent.setup();
    controller.status = 'network_error';
    render(<PhoneVerificationGate />);

    expect(screen.getByText('We could not check your phone. Check your connection and try again.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Check again' }));
    await user.click(screen.getByRole('button', { name: 'Share phone again' }));
    expect(controller.checkAgain).toHaveBeenCalledTimes(1);
    expect(controller.requestPhone).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['unsupported', 'Update Telegram and reopen this Mini App.'],
    ['outside_telegram', 'Open this Mini App inside Telegram to continue.'],
  ] as const)('shows guidance without manual phone entry for %s', (status, guidance) => {
    controller.status = status;
    render(<PhoneVerificationGate />);

    expect(screen.getByText(guidance)).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
