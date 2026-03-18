import { Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import { init, backButton } from '@telegram-apps/sdk-react';
import MenuPage from './pages/MenuPage';
import CartPage from './pages/CartPage';
import ProfilePage from './pages/ProfilePage';
import OrderStatusPage from './pages/OrderStatusPage';
import { useAuthStore } from './stores/authStore';

export default function App() {
  const authenticate = useAuthStore((s) => s.authenticate);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) {
      // Inform Telegram the app is ready — dismisses the loading placeholder
      tg.ready();
      // Expand to maximum available height
      tg.expand();
      // Match Telegram theme colors
      tg.setHeaderColor('secondary_bg_color');
      tg.setBackgroundColor('bg_color');
      if (tg.isVersionAtLeast('7.10')) {
        tg.setBottomBarColor('bottom_bar_bg_color');
      }
      // Disable pull-down-to-close gesture (food order flow needs vertical scroll)
      if (tg.isVersionAtLeast('7.7')) {
        tg.disableVerticalSwipes();
      }
    }

    // Initialize the SDK layer on top of the native WebApp
    try {
      const cleanup = init();
      backButton.mount();
      return cleanup;
    } catch (e) {
      console.warn('TMA SDK init failed (not in Telegram?):', e);
    }
  }, []);

  useEffect(() => {
    authenticate();
  }, [authenticate]);

  return (
    <Routes>
      <Route path="/" element={<MenuPage />} />
      <Route path="/cart" element={<CartPage />} />
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/order/:orderId" element={<OrderStatusPage />} />
    </Routes>
  );
}
