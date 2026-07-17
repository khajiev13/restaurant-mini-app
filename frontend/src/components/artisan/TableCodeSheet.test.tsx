import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TableCodeSheet from './TableCodeSheet';

describe('TableCodeSheet', () => {
  beforeEach(cleanup);

  it('keeps one to six digits and submits the canonical table number', async () => {
    const user = userEvent.setup();
    const resolveCode = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
      <TableCodeSheet
        open
        onClose={onClose}
        onResolve={resolveCode}
        resolving={false}
        error={null}
      />,
    );

    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('inputmode', 'numeric');
    expect(input).toHaveAttribute('pattern', '[0-9]*');

    await user.type(input, '00a1-2b34567');
    expect(input).toHaveValue('001234');
    await user.click(screen.getByRole('button', { name: /confirm|tasdiqlash/i }));

    expect(resolveCode).toHaveBeenCalledWith('1234');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps confirmation disabled until at least one digit exists', () => {
    render(
      <TableCodeSheet
        open
        onClose={vi.fn()}
        onResolve={vi.fn()}
        resolving={false}
        error={null}
      />,
    );

    expect(screen.getByRole('button', { name: /confirm|tasdiqlash/i })).toBeDisabled();
  });
});
