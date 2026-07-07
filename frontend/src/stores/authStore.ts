import { create } from 'zustand';
import { authenticateTelegram, getMe } from '../services/api';
import i18n from '../i18n';
import type { User } from '../types/api';

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  hasHydratedUser: boolean;
  authenticate: () => Promise<void>;
  refreshMe: () => Promise<User | null>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => {
  const token = localStorage.getItem('jwt');

  return {
    token,
    user: null,
    isAuthenticated: !!token,
    isLoading: false,
    hasHydratedUser: !token,

    authenticate: async () => {
      const tg = window.Telegram?.WebApp;
      if (!tg?.initData) {
        console.warn('Not running inside Telegram - skipping auth');
        set({ isLoading: false, hasHydratedUser: true });
        return;
      }

      set({ isLoading: true, hasHydratedUser: false });
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
          set({ user: me, hasHydratedUser: true });
          const lang = me?.language;
          if (lang && lang !== i18n.language) {
            await i18n.changeLanguage(lang);
            localStorage.setItem('i18nextLng', lang);
          }
        } catch {
          // Non-critical: keep current language if profile fetch fails
          set({ user: null, hasHydratedUser: true });
        }
      } catch (err) {
        console.error('Auth failed:', err);
        set({ user: null, hasHydratedUser: true });
      } finally {
        set({ isLoading: false });
      }
    },

    refreshMe: async () => {
      try {
        const meRes = await getMe();
        const user = meRes.data.data;
        set({ user, hasHydratedUser: true });
        return user;
      } catch {
        set({ hasHydratedUser: true });
        return null;
      }
    },

    logout: () => {
      localStorage.removeItem('jwt');
      localStorage.setItem('manual_logout', '1');
      set({
        token: null,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        hasHydratedUser: true,
      });
    },
  };
});
