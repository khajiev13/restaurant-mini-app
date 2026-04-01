import { create } from 'zustand';
import { authenticateTelegram, getMe } from '../services/api';
import i18n from '../i18n';

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  authenticate: () => Promise<void>;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('jwt'),
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
        const lang = meRes.data.data?.language;
        if (lang && lang !== i18n.language) {
          await i18n.changeLanguage(lang);
          localStorage.setItem('i18nextLng', lang);
        }
      } catch {
        // Non-critical: keep current language if profile fetch fails
      }
    } catch (err) {
      console.error('Auth failed:', err);
    } finally {
      set({ isLoading: false });
    }
  },

  logout: () => {
    localStorage.removeItem('jwt');
    localStorage.setItem('manual_logout', '1');
    set({ token: null, isAuthenticated: false, isLoading: false });
  },
}));
