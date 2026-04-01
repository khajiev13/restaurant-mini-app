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
      sortOrder: 1
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
      sortOrder: 1
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
      sortOrder: 1
    };

    useCartStore.getState().addItem(item);
    useCartStore.getState().addItem(item);

    const total = useCartStore.getState().getTotal();
    expect(total).toBe(30.0);
  });
});
