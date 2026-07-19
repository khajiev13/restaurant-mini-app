import { describe, it, expect, beforeEach } from 'vitest';
import { useCartStore } from '../cartStore';

describe('cartStore', () => {
  beforeEach(() => {
    useCartStore.setState({ items: [] });
  });

  it('initially has an empty cart', () => {
    const items = useCartStore.getState().items;
    expect(items).toEqual([]);
  });

  it('can add an item to the cart', () => {
    useCartStore.getState().addItem({
      id: '1',
      categoryId: '1',
      name: 'Cola',
      price: 15.0,
      description: null,
      sortOrder: 1,
      available: true,
      availableCount: null,
    });
    
    const items = useCartStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].name).toBe('Cola');
    expect(items[0].quantity).toBe(1);
  });

  it('increases quantity when same item is added', () => {
    const item = {
      id: '1',
      categoryId: '1',
      name: 'Cola',
      price: 15.0,
      description: null,
      sortOrder: 1,
      available: true,
      availableCount: null,
    };

    useCartStore.getState().addItem(item);
    useCartStore.getState().addItem(item);

    const items = useCartStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].quantity).toBe(2);
  });

  it('calculates total price correctly', () => {
    const item = {
      id: '1',
      categoryId: '1',
      name: 'Cola',
      price: 15.0,
      description: null,
      sortOrder: 1,
      available: true,
      availableCount: null,
    };

    useCartStore.getState().addItem(item);
    useCartStore.getState().addItem(item);

    const total = useCartStore.getState().getTotal();
    expect(total).toBe(30.0);
  });

  it('removes sold-out items and caps limited quantities after a menu refresh', () => {
    const soldOut = {
      id: '1', categoryId: '1', name: 'Cola', price: 15,
      description: null, sortOrder: 1, available: true, availableCount: null,
    };
    const limited = {
      id: '2', categoryId: '1', name: 'Somsa', price: 18,
      description: null, sortOrder: 2, available: true, availableCount: null,
    };
    useCartStore.getState().addItem(soldOut);
    useCartStore.getState().addItem(limited);
    useCartStore.getState().updateQuantity('2', 4);

    const adjustment = useCartStore.getState().reconcileAvailability([
      { ...soldOut, available: false, availableCount: 0 },
      { ...limited, availableCount: 2 },
    ]);

    expect(adjustment).toEqual({ removed: 1, reduced: 1, repriced: 0 });
    expect(useCartStore.getState().items).toEqual([
      expect.objectContaining({ id: '2', quantity: 2, availableCount: 2 }),
    ]);
  });

  it('updates_price_only_catalog_changes', () => {
    const item = {
      id: '1', categoryId: '1', name: 'Cola', price: 15,
      description: null, sortOrder: 1, available: true, availableCount: null,
    };
    useCartStore.getState().addItem(item);

    const adjustment = useCartStore.getState().reconcileAvailability([
      { ...item, price: 18 },
    ]);

    expect(adjustment).toEqual({ removed: 0, reduced: 0, repriced: 1 });
    expect(useCartStore.getState().items).toEqual([
      expect.objectContaining({ id: '1', quantity: 1, price: 18 }),
    ]);
    expect(useCartStore.getState().getTotal()).toBe(18);
  });
});
