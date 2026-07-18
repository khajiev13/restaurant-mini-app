import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TableContextBar from './TableContextBar';

describe('TableContextBar', () => {
  it('shows the safe table snapshot without exposing its access token', () => {
    const onChange = vi.fn();
    render(
      <TableContextBar
        context={{
          tableTitle: 'Stol 12',
          hallTitle: 'Asosiy zal',
          servicePercent: 10,
          accessToken: 'secret-signed-token',
        }}
        onChange={onChange}
      />,
    );

    expect(screen.getByText('Stol 12')).toBeVisible();
    expect(screen.getByText(/Asosiy zal/)).toBeVisible();
    expect(screen.queryByText('secret-signed-token')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button'));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('keeps the change-table control at least 44px tall', () => {
    render(<TableContextBar context={null} onChange={vi.fn()} />);

    expect(
      screen.getByRole('button', { name: 'Enter table number' }),
    ).toHaveStyle({
      minHeight: '44px',
    });
  });
});
