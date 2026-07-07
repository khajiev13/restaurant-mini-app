import { useEffect } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import ArtisanMenuPage from './pages/artisan/ArtisanMenuPage';
import ArtisanCheckoutPage from './pages/artisan/ArtisanCheckoutPage';
import ArtisanProfilePage from './pages/artisan/ArtisanProfilePage';
import ArtisanOrderStatusPage from './pages/artisan/ArtisanOrderStatusPage';
import ArtisanOrdersPage from './pages/artisan/ArtisanOrdersPage';
import StaffOrdersPage from './pages/staff/StaffOrdersPage';
import StaffOrderDetailPage from './pages/staff/StaffOrderDetailPage';
import StaffProfilePage from './pages/staff/StaffProfilePage';
import { useAuthStore } from './stores/authStore';

export default function App() {
  const authenticate = useAuthStore((state) => state.authenticate);
  const user = useAuthStore((state) => state.user);
  const navigate = useNavigate();
  const isStaffMode = user?.role === 'staff' || user?.role === 'admin';

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

    // Handle deep link return from Multicard payment
    // Bot deep link: https://t.me/olotsomsa_zakaz_bot?startapp=order_<uuid>
    const startParam = tg.initDataUnsafe?.start_param;
    if (startParam?.startsWith('order_')) {
      const orderId = startParam.slice('order_'.length);
      if (orderId) {
        navigate(`/order/${orderId}`, { replace: true });
      }
    }
  }, [navigate]);

  useEffect(() => {
    if (!localStorage.getItem('manual_logout')) {
      void authenticate();
    }
  }, [authenticate]);

  return (
    <Routes>
      <Route
        path="/"
        element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanMenuPage />}
      />
      <Route
        path="/checkout"
        element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanCheckoutPage />}
      />
      <Route
        path="/order"
        element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanOrdersPage />}
      />
      <Route
        path="/profile"
        element={isStaffMode ? <StaffProfilePage /> : <ArtisanProfilePage />}
      />
      <Route
        path="/order/:orderId"
        element={isStaffMode ? <Navigate to="/staff/orders" replace /> : <ArtisanOrderStatusPage />}
      />
      <Route
        path="/staff/orders"
        element={isStaffMode ? <StaffOrdersPage /> : <Navigate to="/" replace />}
      />
      <Route
        path="/staff/orders/:orderId"
        element={isStaffMode ? <StaffOrderDetailPage /> : <Navigate to="/" replace />}
      />
    </Routes>
  );
}
