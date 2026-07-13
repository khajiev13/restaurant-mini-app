import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import TableCodeSheet from './TableCodeSheet';

describe('TableCodeSheet', () => {
  it('normalizes and submits a six-character table code', async () => {
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

    await user.type(screen.getByRole('textbox'), 'a7-k2 p9');
    await user.click(screen.getByRole('button', { name: /confirm|tasdiqlash/i }));

    expect(resolveCode).toHaveBeenCalledWith('A7K2P9');
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
