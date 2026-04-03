import { type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../stores/authStore';
import logo from '../../assets/logo.webp';

// --- Shared Style Constants ---
const COLORS = {
  primary: '#a33800',
  primaryContainer: '#ff7941',
  onPrimary: '#ffefeb',
  onPrimaryContainer: '#431200',
  secondary: '#5c5b5b',
  surface: '#f6f6f6',
  surfaceContainerLowest: '#ffffff',
  surfaceContainerLow: '#f0f1f1',
  surfaceContainer: '#e7e8e8',
  surfaceContainerHigh: '#e1e3e3',
  surfaceContainerHighest: '#dbdddd',
  onSurface: '#2d2f2f',
  onSurfaceVariant: '#5a5c5c',
  outline: '#767777',
  outlineVariant: '#acadad',
  error: '#b31b25',
} as const;

const FONTS = {
  headline: "'Plus Jakarta Sans', sans-serif",
  body: "'Manrope', sans-serif",
} as const;

// --- Material Icon Helper ---
function Icon({
  name,
  fill,
  size,
  weight,
  style,
}: {
  name: string;
  fill?: boolean;
  size?: number;
  weight?: number;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className="material-symbols-outlined"
      style={{
        fontVariationSettings: `'FILL' ${fill ? 1 : 0}, 'wght' ${weight || 400}, 'GRAD' 0, 'opsz' 24`,
        fontSize: size,
        ...style,
      }}
    >
      {name}
    </span>
  );
}

// --- Top App Bar ---
function ArtisanTopBar({
  title,
  showBack = false,
  avatarInitial,
  avatarUrl,
}: {
  title?: string;
  showBack?: boolean;
  avatarInitial?: string;
  avatarUrl?: string;
}) {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;

  const finalAvatarUrl = isAuthenticated ? (avatarUrl || tgUser?.photo_url) : undefined;
  const finalInitial = isAuthenticated 
    ? (avatarInitial || tgUser?.first_name?.[0]?.toUpperCase() || 'A')
    : 'A';

  return (
    <header
      style={{
        position: 'fixed',
        top: 0,
        width: '100%',
        zIndex: 50,
        backgroundColor: 'rgba(250, 250, 249, 0.8)',
        backdropFilter: 'blur(12px)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0 24px',
        height: 64,
        boxSizing: 'border-box',
      }}
    >
      {showBack ? (
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button
            onClick={() => navigate(-1)}
            style={{
              width: 40,
              height: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '50%',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
            }}
          >
            <Icon name="chevron_left" style={{ color: COLORS.onSurface }} />
          </button>
          <h1
            style={{
              marginLeft: 16,
              fontSize: 18,
              fontWeight: 700,
              letterSpacing: '-0.01em',
              color: COLORS.onSurface,
              textTransform: 'uppercase',
              fontFamily: FONTS.headline,
            }}
          >
            {title}
          </h1>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <img src={logo} alt="OLOT SOMSA" style={{ width: 28, height: 28, borderRadius: '50%' }} />
          <span
            style={{
              fontSize: 20,
              fontWeight: 800,
              color: '#7c2d12',
              fontFamily: FONTS.headline,
              letterSpacing: '-0.01em',
            }}
          >
            OLOT SOMSA
          </span>
        </div>
      )}

      {!showBack && (
        <Link to="/profile">
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: '50%',
              background: COLORS.primaryContainer,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: COLORS.onPrimaryContainer,
              fontWeight: 700,
              fontSize: 16,
              border: `2px solid ${COLORS.surfaceContainerLowest}`,
              overflow: 'hidden',
            }}
          >
            {finalAvatarUrl ? (
              <img src={finalAvatarUrl} alt="Avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              finalInitial
            )}
          </div>
        </Link>
      )}
    </header>
  );
}

// --- Bottom Navigation ---
const NAV_ITEMS = [
  { path: '/', icon: 'menu_book', labelKey: 'nav.menu' },
  { path: '/order', icon: 'local_shipping', labelKey: 'nav.orders' },
  { path: '/checkout', icon: 'shopping_bag', labelKey: 'nav.cart' },
  { path: '/profile', icon: 'person', labelKey: 'nav.profile' },
] as const;

function ArtisanBottomNav() {
  const location = useLocation();
  const { t } = useTranslation();

  const isActive = (path: string) => {
    if (path === '/order') return location.pathname.startsWith('/order');
    return location.pathname === path;
  };

  return (
    <nav
      style={{
        position: 'fixed',
        bottom: 0,
        width: '100%',
        zIndex: 50,
        borderTopLeftRadius: 16,
        borderTopRightRadius: 16,
        backgroundColor: 'rgba(250, 250, 249, 0.8)',
        backdropFilter: 'blur(12px)',
        boxShadow: '0 -1px 0 0 rgba(0,0,0,0.05), 0 -4px 16px rgba(0,0,0,0.08)',
        display: 'flex',
        justifyContent: 'space-around',
        alignItems: 'center',
        paddingTop: 8,
        paddingBottom: 24,
        paddingLeft: 16,
        paddingRight: 16,
        boxSizing: 'border-box',
      }}
    >
      {NAV_ITEMS.map((item) => {
        const active = isActive(item.path);
        return (
          <Link
            key={item.path}
            to={item.path}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              textDecoration: 'none',
              color: active ? '#c2410c' : '#a8a29e',
              backgroundColor: active ? 'rgba(255, 237, 213, 0.5)' : 'transparent',
              borderRadius: 12,
              padding: active ? '4px 12px' : '4px 12px',
              transition: 'all 0.2s ease',
            }}
          >
            <Icon name={item.icon} fill={active} />
            <span
              style={{
                fontFamily: FONTS.body,
                fontSize: 10,
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                marginTop: 2,
              }}
            >
              {t(item.labelKey)}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

// --- Layout Wrapper ---
export default function ArtisanLayout({
  children,
  showBack = false,
  backTitle,
  avatarInitial,
  avatarUrl,
  hideBottomNav = false,
}: {
  children: ReactNode;
  showBack?: boolean;
  backTitle?: string;
  avatarInitial?: string;
  avatarUrl?: string;
  hideBottomNav?: boolean;
}) {
  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: COLORS.surface,
        fontFamily: FONTS.body,
        color: COLORS.onSurface,
      }}
    >
      <ArtisanTopBar
        showBack={showBack}
        title={backTitle}
        avatarInitial={avatarInitial}
        avatarUrl={avatarUrl}
      />
      {children}
      {!hideBottomNav && <ArtisanBottomNav />}
    </div>
  );
}

// Export helpers for use in page components
export { COLORS, FONTS, Icon };
