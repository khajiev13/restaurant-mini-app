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
  hasResolvedInitialAuth: boolean;
  authError: string | null;
  bootstrapAuth: () => Promise<void>;
  authenticate: () => Promise<void>;
  refreshMe: () => Promise<User | null>;
  logout: () => void;
}

function hasTelegramInitData(): boolean {
  return !!window.Telegram?.WebApp?.initData;
}

function hasManualLogout(): boolean {
  return localStorage.getItem('manual_logout') === '1';
}

function shouldResolveInitialAuth(token: string | null): boolean {
  if (hasManualLogout()) {
    return false;
  }

  return !!token || hasTelegramInitData();
}

function isUnauthorizedError(error: unknown): boolean {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return false;
  }

  return (error as { response?: { status?: number } }).response?.status === 401;
}

const AUTH_RETRY_MESSAGE = 'Could not verify your role. Check your connection and try again.';

export const useAuthStore = create<AuthState>((set, get) => {
  const token = localStorage.getItem('jwt');
  const needsInitialAuthResolution = shouldResolveInitialAuth(token);

  return {
    token,
    user: null,
    isAuthenticated: !!token,
    isLoading: false,
    hasHydratedUser: !needsInitialAuthResolution,
    hasResolvedInitialAuth: !needsInitialAuthResolution,
    authError: null,

    bootstrapAuth: async () => {
      if (hasManualLogout()) {
        localStorage.removeItem('jwt');
        set({
          token: null,
          user: null,
          isAuthenticated: false,
          isLoading: false,
          hasHydratedUser: true,
          hasResolvedInitialAuth: true,
          authError: null,
        });
        return;
      }

      if (hasTelegramInitData()) {
        await get().authenticate();
        return;
      }

      if (get().token) {
        await get().refreshMe();
        return;
      }

      set({
        isLoading: false,
        hasHydratedUser: true,
        hasResolvedInitialAuth: true,
        authError: null,
      });
    },

    authenticate: async () => {
      const tg = window.Telegram?.WebApp;
      if (!tg?.initData) {
        console.warn('Not running inside Telegram - skipping auth');
        set({
          isLoading: false,
          hasHydratedUser: true,
          hasResolvedInitialAuth: true,
          authError: null,
        });
        return;
      }

      set({
        isLoading: true,
        hasHydratedUser: false,
        hasResolvedInitialAuth: false,
        authError: null,
      });
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
          set({
            user: me,
            hasHydratedUser: true,
            hasResolvedInitialAuth: true,
            authError: null,
          });
          const lang = me?.language;
          if (lang && lang !== i18n.language) {
            await i18n.changeLanguage(lang);
            localStorage.setItem('i18nextLng', lang);
          }
        } catch (err) {
          if (isUnauthorizedError(err)) {
            localStorage.removeItem('jwt');
            set({
              token: null,
              user: null,
              isAuthenticated: false,
              hasHydratedUser: true,
              hasResolvedInitialAuth: true,
              authError: null,
            });
          } else {
            set({
              user: null,
              hasHydratedUser: false,
              hasResolvedInitialAuth: true,
              authError: AUTH_RETRY_MESSAGE,
            });
          }
        }
      } catch (err) {
        console.error('Auth failed:', err);
        localStorage.removeItem('jwt');
        set({
          token: null,
          user: null,
          isAuthenticated: false,
          hasHydratedUser: true,
          hasResolvedInitialAuth: true,
          authError: null,
        });
      } finally {
        set({ isLoading: false });
      }
    },

    refreshMe: async () => {
      try {
        const meRes = await getMe();
        const user = meRes.data.data;
        set({
          user,
          hasHydratedUser: true,
          hasResolvedInitialAuth: true,
          authError: null,
        });
        return user;
      } catch (err) {
        if (isUnauthorizedError(err)) {
          localStorage.removeItem('jwt');
          set({
            token: null,
            user: null,
            isAuthenticated: false,
            hasHydratedUser: true,
            hasResolvedInitialAuth: true,
            authError: null,
          });
        } else {
          set({
            user: null,
            hasHydratedUser: false,
            hasResolvedInitialAuth: true,
            authError: AUTH_RETRY_MESSAGE,
          });
        }
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
        hasResolvedInitialAuth: true,
        authError: null,
      });
    },
  };
});
