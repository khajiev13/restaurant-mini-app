import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import MenuCatalog from './MenuCatalog';

afterEach(cleanup);

const menu = {
  categories: [{ id: 'somsa', name: 'Somsa', sortOrder: 0 }],
  items: [
    { id: 'classic', categoryId: 'somsa', name: 'Classic Somsa', description: 'Beef and onion', price: 18000, sortOrder: 0, available: true, availableCount: 1, images: [{ url: '/classic.jpg' }] },
    { id: 'sold', categoryId: 'somsa', name: 'Fish Somsa', description: null, price: 24000, sortOrder: 1, available: false, availableCount: 0 },
  ],
};

const labels = {
  soldOut: 'Sold out',
  add: 'Add',
  remove: 'Remove',
  limit: 'Available quantity is already in the cart',
  empty: 'No menu items',
};

describe('MenuCatalog', () => {
  it('renders browse mode without ordering controls', () => {
    render(
      <MenuCatalog
        menu={menu}
        language="en"
        mode="browse"
        labels={labels}
      />,
    );

    expect(screen.getAllByText('Somsa')).toHaveLength(2);
    expect(screen.getByText('Beef and onion')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Classic Somsa' })).toHaveAttribute('src', '/classic.jpg');
    expect(screen.getByText('18,000 UZS')).toBeInTheDocument();
    expect(screen.getByText('Sold out')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/cart|checkout|table context/i)).not.toBeInTheDocument();
  });

  it('keeps customer interactive add behavior', async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn();
    render(
      <MenuCatalog
        menu={menu}
        language="en"
        mode="interactive"
        labels={labels}
        quantities={{ classic: 0 }}
        onAdd={onAdd}
        onRemove={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /classic somsa.*add/i }));
    expect(onAdd).toHaveBeenCalledWith(menu.items[0]);
  });

  it('disables the initial add control when no live quantity remains', async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn();
    const zeroCountMenu = {
      ...menu,
      items: [{ ...menu.items[0], availableCount: 0 }],
    };
    render(
      <MenuCatalog
        menu={zeroCountMenu}
        language="en"
        mode="interactive"
        labels={labels}
        quantities={{ classic: 0 }}
        onAdd={onAdd}
        onRemove={vi.fn()}
      />,
    );

    const addButton = screen.getByRole('button', { name: labels.limit });
    expect(addButton).toBeDisabled();
    await user.click(addButton);
    expect(onAdd).not.toHaveBeenCalled();
  });

  it('provides at least 44x44 hit targets for every interactive quantity control', () => {
    const controlsMenu = {
      categories: menu.categories,
      items: [
        { ...menu.items[0], id: 'first', name: 'First Somsa', availableCount: 2 },
        { ...menu.items[0], id: 'second', name: 'Second Somsa', sortOrder: 1, availableCount: 2 },
      ],
    };
    render(
      <MenuCatalog
        menu={controlsMenu}
        language="en"
        mode="interactive"
        labels={labels}
        quantities={{ first: 0, second: 1 }}
        onAdd={vi.fn()}
        onRemove={vi.fn()}
      />,
    );

    const controls = [
      screen.getByRole('button', { name: 'First Somsa Add' }),
      screen.getByRole('button', { name: 'Second Somsa Remove' }),
      screen.getByRole('button', { name: 'Second Somsa Add' }),
    ];

    for (const control of controls) {
      const style = window.getComputedStyle(control);
      const width = Math.max(Number.parseFloat(style.width) || 0, Number.parseFloat(style.minWidth) || 0);
      const height = Math.max(Number.parseFloat(style.height) || 0, Number.parseFloat(style.minHeight) || 0);
      expect(width).toBeGreaterThanOrEqual(44);
      expect(height).toBeGreaterThanOrEqual(44);
    }
  });

  it('keeps remove behavior and disables additions at the live limit', async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    render(
      <MenuCatalog
        menu={menu}
        language="en"
        mode="interactive"
        labels={labels}
        quantities={{ classic: 1 }}
        onAdd={vi.fn()}
        onRemove={onRemove}
      />,
    );

    expect(screen.getByRole('button', { name: labels.limit })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /classic somsa.*remove/i }));
    expect(onRemove).toHaveBeenCalledWith('classic');
  });

  it('renders the localized empty state', () => {
    render(
      <MenuCatalog
        menu={{ categories: [], items: [] }}
        language="en"
        mode="browse"
        labels={labels}
      />,
    );
    expect(screen.getByText('No menu items')).toBeInTheDocument();
  });
});
