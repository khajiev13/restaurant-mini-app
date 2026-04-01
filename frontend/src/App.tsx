import { useEffect } from 'react';
import { Route, Routes } from 'react-router-dom';
import ArtisanMenuPage from './pages/artisan/ArtisanMenuPage';
import ArtisanCheckoutPage from './pages/artisan/ArtisanCheckoutPage';
import ArtisanProfilePage from './pages/artisan/ArtisanProfilePage';
import ArtisanOrderStatusPage from './pages/artisan/ArtisanOrderStatusPage';
import ArtisanOrdersPage from './pages/artisan/ArtisanOrdersPage';
import { useAuthStore } from './stores/authStore';

export default function App() {
  const authenticate = useAuthStore((state) => state.authenticate);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    tg.ready();
    tg.expand();
    tg.setHeaderColor('secondary_bg_color');
    tg.setBackgroundColor('bg_color');

    if (tg.isVersionAtLeast('7.10')) {
      tg.setBottomBarColor('bottom_bar_bg_color');
    }

    if (tg.isVersionAtLeast('7.7')) {
      tg.disableVerticalSwipes();
    }
  }, []);

  useEffect(() => {
    if (!localStorage.getItem('manual_logout')) {
      void authenticate();
    }
  }, [authenticate]);

  return (
    <Routes>
      <Route path="/" element={<ArtisanMenuPage />} />
      <Route path="/checkout" element={<ArtisanCheckoutPage />} />
      <Route path="/order" element={<ArtisanOrdersPage />} />
      <Route path="/profile" element={<ArtisanProfilePage />} />
      <Route path="/order/:orderId" element={<ArtisanOrderStatusPage />} />
    </Routes>
  );
}
