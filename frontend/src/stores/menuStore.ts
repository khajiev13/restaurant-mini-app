import { create } from 'zustand';
import { getMenu } from '../services/api';
import type { MenuData } from '../types/api';

interface MenuState {
  menu: MenuData | null;
  loading: boolean;
  loaded: boolean;
  error: string | null;
  fetchMenu: () => Promise<void>;
  refreshMenu: () => Promise<void>;
  retry: () => Promise<void>;
}

export const useMenuStore = create<MenuState>((set, get) => ({
  menu: null,
  loading: false,
  loaded: false,
  error: null,

  fetchMenu: async () => {
    if (get().loaded) return;
    set({ loading: true, error: null });
    try {
      const res = await getMenu();
      set({ menu: res.data.data, loaded: true });
    } catch (err) {
      console.error('Menu fetch failed:', err);
      set({ error: 'Failed to load menu. Please try again.' });
    } finally {
      set({ loading: false });
    }
  },

  refreshMenu: async () => {
    set({ loading: true, error: null });
    try {
      const res = await getMenu();
      set({ menu: res.data.data, loaded: true });
    } catch (err) {
      console.error('Menu refresh failed:', err);
      set({ error: 'Failed to load menu. Please try again.' });
    } finally {
      set({ loading: false });
    }
  },

  retry: async () => {
    await get().refreshMenu();
  },
}));
