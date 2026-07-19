import { create } from 'zustand';
import type { CartItem, MenuItem } from '../types/api';

interface CartState {
  items: CartItem[];
  addItem: (product: MenuItem) => void;
  removeItem: (productId: string) => void;
  updateQuantity: (productId: string, quantity: number) => void;
  clearCart: () => void;
  getTotal: () => number;
  getItemCount: () => number;
  reconcileAvailability: (products: MenuItem[]) => {
    removed: number;
    reduced: number;
    repriced: number;
  };
}

function catalogItemChanged(item: CartItem, current: MenuItem): boolean {
  return item.categoryId !== current.categoryId
    || item.name !== current.name
    || item.description !== current.description
    || item.price !== current.price
    || item.sortOrder !== current.sortOrder
    || item.available !== current.available
    || item.availableCount !== current.availableCount
    || item.images?.length !== current.images?.length
    || Boolean(item.images?.some(
      (image, index) => image.url !== current.images?.[index]?.url,
    ));
}

export const useCartStore = create<CartState>((set, get) => ({
  items: [],

  addItem: (product) => {
    if (!product.available) return;
    const items = get().items;
    const existing = items.find((item) => item.id === product.id);
    if (existing) {
      if (product.availableCount !== null && existing.quantity >= product.availableCount) return;
      set({
        items: items.map((item) =>
          item.id === product.id ? { ...item, quantity: item.quantity + 1 } : item,
        ),
      });
      return;
    }

    set({ items: [...items, { ...product, quantity: 1 }] });
  },

  removeItem: (productId) => {
    set({ items: get().items.filter((item) => item.id !== productId) });
  },

  updateQuantity: (productId, quantity) => {
    if (quantity <= 0) {
      set({ items: get().items.filter((item) => item.id !== productId) });
      return;
    }

    set({
      items: get().items.map((item) =>
        item.id === productId ? { ...item, quantity } : item,
      ),
    });
  },

  clearCart: () => set({ items: [] }),

  getTotal: () => get().items.reduce((sum, item) => sum + item.price * item.quantity, 0),

  getItemCount: () => get().items.reduce((sum, item) => sum + item.quantity, 0),

  reconcileAvailability: (products) => {
    const catalog = new Map(products.map((product) => [product.id, product]));
    let removed = 0;
    let reduced = 0;
    let repriced = 0;
    let catalogChanged = false;
    const items = get().items.flatMap((item) => {
      const current = catalog.get(item.id);
      if (!current || !current.available || current.availableCount === 0) {
        removed += 1;
        return [];
      }
      const quantity = current.availableCount !== null
        ? Math.min(item.quantity, current.availableCount)
        : item.quantity;
      if (quantity < item.quantity) reduced += 1;
      if (item.price !== current.price) repriced += 1;
      if (catalogItemChanged(item, current)) catalogChanged = true;
      return [{ ...item, ...current, quantity }];
    });
    if (removed > 0 || reduced > 0 || catalogChanged) set({ items });
    return { removed, reduced, repriced };
  },
}));
