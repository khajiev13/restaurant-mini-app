import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import ArtisanMenuPage from './pages/artisan/ArtisanMenuPage';
import ArtisanCheckoutPage from './pages/artisan/ArtisanCheckoutPage';
import ArtisanProfilePage from './pages/artisan/ArtisanProfilePage';
import ArtisanOrderStatusPage from './pages/artisan/ArtisanOrderStatusPage';
import ArtisanOrdersPage from './pages/artisan/ArtisanOrdersPage';
import StaffOrdersPage from './pages/staff/StaffOrdersPage';
import StaffOrderDetailPage from './pages/staff/StaffOrderDetailPage';
import StaffProfilePage from './pages/staff/StaffProfilePage';
import StaffTablesPage from './pages/staff/StaffTablesPage';
import StaffTableDetailPage from './pages/staff/StaffTableDetailPage';
import AdminUsersPage from './pages/admin/AdminUsersPage';
import PhoneVerificationGate from './components/auth/PhoneVerificationGate';
import { useAuthStore } from './stores/authStore';
import { useTableOrderStore } from './stores/tableOrderStore';

function RoleRouteLoadingShell() {
  return <div aria-busy="true" className="min-h-screen" data-testid="role-route-loading" />;
}

function AuthRetryShell({
  messageKey,
  onRetry,
}: {
  messageKey: string;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
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
        <p style={{ margin: 0, fontSize: 16, fontWeight: 700, lineHeight: 1.45 }}>{t(messageKey)}</p>
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
          {t('common.retry')}
        </button>
      </section>
    </main>
  );
}

export default function App() {
  const bootstrapAuth = useAuthStore((state) => state.bootstrapAuth);
  const role = useAuthStore((state) => state.user?.role ?? 'customer');
  const isPhoneVerified = useAuthStore((state) => state.user?.phone_verified === true);
  const isLoading = useAuthStore((state) => state.isLoading);
  const hasHydratedUser = useAuthStore((state) => state.hasHydratedUser);
  const hasResolvedInitialAuth = useAuthStore((state) => state.hasResolvedInitialAuth);
  const authError = useAuthStore((state) => state.authError);
  const resolveTableEntry = useTableOrderStore((state) => state.resolveEntry);
  const navigate = useNavigate();
  const handledStartParam = useRef<string | null>(null);
  const isResolvingRole = isLoading || !hasResolvedInitialAuth || !hasHydratedUser;

  const renderResolvedRoute = (element: ReactNode) => {
    if (authError) {
      return <AuthRetryShell messageKey={authError} onRetry={() => { void bootstrapAuth(); }} />;
    }

    if (isResolvingRole) {
      return <RoleRouteLoadingShell />;
    }

    return element;
  };

  const renderByRole = (
    customerElement: ReactNode,
    staffElement: ReactNode,
    adminElement: ReactNode,
  ) => {
    if (role === 'admin') {
      return renderResolvedRoute(adminElement);
    }

    if (role === 'staff') {
      return renderResolvedRoute(staffElement);
    }

    return renderResolvedRoute(isPhoneVerified ? customerElement : <PhoneVerificationGate />);
  };

  const renderStaffOrAdminRoute = (staffElement: ReactNode) =>
    renderByRole(<Navigate to="/" replace />, staffElement, staffElement);

  const renderAdminRoute = (adminElement: ReactNode) =>
    renderByRole(<Navigate to="/" replace />, <Navigate to="/staff/orders" replace />, adminElement);

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
    if (!startParam || handledStartParam.current === startParam) return;
    handledStartParam.current = startParam;
    if (startParam?.startsWith('order_')) {
      const orderId = startParam.slice('order_'.length);
      if (orderId) {
        navigate(`/order/${orderId}`, { replace: true });
      }
      return;
    }
    const isTableStartParam = startParam.startsWith('t2_') || startParam.startsWith('t_');
    if (isTableStartParam) {
      navigate('/', { replace: true });
      void resolveTableEntry(startParam).catch(() => {
        // The menu exposes a retryable manual-code fallback.
      });
    }
  }, [navigate, resolveTableEntry]);

  useEffect(() => {
    void bootstrapAuth();
  }, [bootstrapAuth]);

  return (
    <Routes>
      <Route
        path="/"
        element={renderByRole(
          <ArtisanMenuPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route
        path="/checkout"
        element={renderByRole(
          <ArtisanCheckoutPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route
        path="/order"
        element={renderByRole(
          <ArtisanOrdersPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route
        path="/profile"
        element={renderByRole(
          <ArtisanProfilePage />,
          <StaffProfilePage />,
          <StaffProfilePage />,
        )}
      />
      <Route
        path="/order/:orderId"
        element={renderByRole(
          <ArtisanOrderStatusPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route path="/admin" element={renderAdminRoute(<AdminUsersPage />)} />
      <Route path="/admin/users" element={renderAdminRoute(<AdminUsersPage />)} />
      <Route path="/staff/orders" element={renderStaffOrAdminRoute(<StaffOrdersPage />)} />
      <Route path="/staff/orders/:orderId" element={renderStaffOrAdminRoute(<StaffOrderDetailPage />)} />
      <Route path="/staff/tables" element={renderStaffOrAdminRoute(<StaffTablesPage />)} />
      <Route
        path="/staff/tables/:tableId"
        element={renderStaffOrAdminRoute(<StaffTableDetailPage />)}
      />
    </Routes>
  );
}
