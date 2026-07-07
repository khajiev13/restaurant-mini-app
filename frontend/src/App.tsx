import { useEffect } from 'react';
import type { ReactNode } from 'react';
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

function RoleRouteLoadingShell() {
  return <div aria-busy="true" className="min-h-screen" data-testid="role-route-loading" />;
}

function AuthRetryShell({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        backgroundColor: '#f6f6f6',
        color: '#2d2f2f',
      }}
    >
      <section style={{ maxWidth: 360, textAlign: 'center' }}>
        <p style={{ margin: 0, fontSize: 16, fontWeight: 700, lineHeight: 1.45 }}>{message}</p>
        <button
          type="button"
          onClick={onRetry}
          style={{
            height: 48,
            marginTop: 18,
            padding: '0 22px',
            border: 'none',
            borderRadius: 12,
            backgroundColor: '#a33800',
            color: '#ffefeb',
            fontWeight: 800,
            cursor: 'pointer',
          }}
        >
          Retry
        </button>
      </section>
    </main>
  );
}

export default function App() {
  const bootstrapAuth = useAuthStore((state) => state.bootstrapAuth);
  const user = useAuthStore((state) => state.user);
  const isLoading = useAuthStore((state) => state.isLoading);
  const hasHydratedUser = useAuthStore((state) => state.hasHydratedUser);
  const hasResolvedInitialAuth = useAuthStore((state) => state.hasResolvedInitialAuth);
  const authError = useAuthStore((state) => state.authError);
  const navigate = useNavigate();
  const isStaffMode = user?.role === 'staff' || user?.role === 'admin';
  const isResolvingRole = isLoading || !hasResolvedInitialAuth || !hasHydratedUser;

  const renderRoleSensitiveRoute = (customerElement: ReactNode, staffElement: ReactNode) => {
    if (authError) {
      return <AuthRetryShell message={authError} onRetry={() => { void bootstrapAuth(); }} />;
    }

    if (isResolvingRole) {
      return <RoleRouteLoadingShell />;
    }

    return isStaffMode ? staffElement : customerElement;
  };

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
    void bootstrapAuth();
  }, [bootstrapAuth]);

  return (
    <Routes>
      <Route
        path="/"
        element={renderRoleSensitiveRoute(<ArtisanMenuPage />, <Navigate to="/staff/orders" replace />)}
      />
      <Route
        path="/checkout"
        element={renderRoleSensitiveRoute(
          <ArtisanCheckoutPage />,
          <Navigate to="/staff/orders" replace />,
        )}
      />
      <Route
        path="/order"
        element={renderRoleSensitiveRoute(
          <ArtisanOrdersPage />,
          <Navigate to="/staff/orders" replace />,
        )}
      />
      <Route
        path="/profile"
        element={renderRoleSensitiveRoute(<ArtisanProfilePage />, <StaffProfilePage />)}
      />
      <Route
        path="/order/:orderId"
        element={renderRoleSensitiveRoute(
          <ArtisanOrderStatusPage />,
          <Navigate to="/staff/orders" replace />,
        )}
      />
      <Route
        path="/staff/orders"
        element={renderRoleSensitiveRoute(<Navigate to="/" replace />, <StaffOrdersPage />)}
      />
      <Route
        path="/staff/orders/:orderId"
        element={renderRoleSensitiveRoute(<Navigate to="/" replace />, <StaffOrderDetailPage />)}
      />
    </Routes>
  );
}
