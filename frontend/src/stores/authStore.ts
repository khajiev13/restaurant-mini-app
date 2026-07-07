import { create } from 'zustand';
import { authenticateTelegram, getMe } from '../services/api';
import i18n from '../i18n';
import type { User } from '../types/api';

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authenticate: () => Promise<void>;
  refreshMe: () => Promise<User | null>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('jwt'),
  user: null,
  isAuthenticated: !!localStorage.getItem('jwt'),
  isLoading: false,

  authenticate: async () => {
    const tg = window.Telegram?.WebApp;
    if (!tg?.initData) {
      console.warn('Not running inside Telegram - skipping auth');
      return;
    }

    set({ isLoading: true });
    try {
      const res = await authenticateTelegram(tg.initData);
      const token = res.data.data.access_token;
      localStorage.removeItem('manual_logout');
      localStorage.setItem('jwt', token);
      set({ token, isAuthenticated: true });

      // Sync language preference from server
      try {
        const meRes = await getMe();
        const me = meRes.data.data;
        set({ user: me });
        const lang = me?.language;
        if (lang && lang !== i18n.language) {
          await i18n.changeLanguage(lang);
          localStorage.setItem('i18nextLng', lang);
        }
      } catch {
        // Non-critical: keep current language if profile fetch fails
      }
    } catch (err) {
      console.error('Auth failed:', err);
      set({ user: null });
    } finally {
      set({ isLoading: false });
    }
  },

  refreshMe: async () => {
    try {
      const meRes = await getMe();
      const user = meRes.data.data;
      set({ user });
      return user;
    } catch {
      return null;
    }
  },

  logout: () => {
    localStorage.removeItem('jwt');
    localStorage.setItem('manual_logout', '1');
    set({ token: null, user: null, isAuthenticated: false, isLoading: false });
  },
}));
