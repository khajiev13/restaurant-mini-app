import { create } from 'zustand';
import { authenticateTelegram } from '../services/api';

export const useAuthStore = create((set) => ({
  token: localStorage.getItem('jwt'),
  isAuthenticated: !!localStorage.getItem('jwt'),
  isLoading: false,

  authenticate: async () => {
    // Get initData from Telegram WebApp
    const tg = window.Telegram?.WebApp;
    if (!tg?.initData) {
      console.warn('Not running inside Telegram — skipping auth');
      return;
    }

    set({ isLoading: true });
    try {
      const res = await authenticateTelegram(tg.initData);
      const token = res.data.data.access_token;
      localStorage.setItem('jwt', token);
      set({ token, isAuthenticated: true });
    } catch (err) {
      console.error('Auth failed:', err);
    } finally {
      set({ isLoading: false });
    }
  },
}));
