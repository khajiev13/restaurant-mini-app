import type { CSSProperties, ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import logo from '../../assets/logo.webp';
import { useAuthStore } from '../../stores/authStore';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';

const shellStyle: CSSProperties = {
  minHeight: '100vh',
  backgroundColor: COLORS.surface,
  color: COLORS.onSurface,
  fontFamily: FONTS.body,
};

const frameStyle: CSSProperties = {
  maxWidth: 720,
  margin: '0 auto',
  paddingTop: 88,
  paddingBottom: 116,
};

const topBarStyle: CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  zIndex: 40,
  height: 68,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: 'rgba(246, 246, 246, 0.9)',
  backdropFilter: 'blur(12px)',
  boxShadow: '0 1px 0 rgba(172, 173, 173, 0.3)',
};

const getNavStyle = (itemCount: number): CSSProperties => ({
  position: 'fixed',
  left: 0,
  right: 0,
  bottom: 0,
  zIndex: 40,
  height: 88,
  display: 'grid',
  gridTemplateColumns: `repeat(${itemCount}, minmax(0, 1fr))`,
  alignItems: 'center',
  padding: '8px 16px 24px',
  boxSizing: 'border-box',
  backgroundColor: 'rgba(255, 255, 255, 0.92)',
  backdropFilter: 'blur(12px)',
  boxShadow: '0 -8px 24px rgba(45, 47, 47, 0.08)',
});

const brandStyle: CSSProperties = {
  margin: 0,
  fontFamily: FONTS.headline,
  fontSize: 20,
  fontWeight: 800,
  letterSpacing: 0,
  color: COLORS.primary,
};

const brandIconStyle: CSSProperties = {
  position: 'absolute',
  left: 20,
  width: 36,
  height: 36,
  borderRadius: '50%',
};

function NavItem({
  active,
  icon,
  label,
  to,
}: {
  active: boolean;
  icon: string;
  label: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      style={{
        height: 56,
        margin: '0 8px',
        borderRadius: 12,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        textDecoration: 'none',
        color: active ? COLORS.primary : COLORS.secondary,
        backgroundColor: active ? 'rgba(255, 121, 65, 0.12)' : 'transparent',
      }}
    >
      <Icon name={icon} fill={active} />
      <span style={{ fontSize: 13, fontWeight: 700 }}>{label}</span>
    </Link>
  );
}

export default function StaffLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const role = useAuthStore((state) => state.user?.role);
  const isAdmin = role === 'admin';

  const ordersActive = location.pathname.startsWith('/staff/orders');
  const profileActive = location.pathname === '/profile';
  const adminActive = location.pathname.startsWith('/admin');
  const navItems = isAdmin
    ? [
        { active: adminActive, icon: 'admin_panel_settings', label: 'Admin', to: '/admin' },
        { active: ordersActive, icon: 'receipt_long', label: 'Orders', to: '/staff/orders' },
        { active: profileActive, icon: 'person', label: 'Profile', to: '/profile' },
      ]
    : [
        { active: ordersActive, icon: 'receipt_long', label: 'Orders', to: '/staff/orders' },
        { active: profileActive, icon: 'person', label: 'Profile', to: '/profile' },
      ];

  return (
    <div style={shellStyle}>
      <header style={topBarStyle}>
        <img src={logo} alt="" aria-hidden="true" style={brandIconStyle} />
        <p style={brandStyle}>OLOT SOMSA</p>
      </header>

      <div style={frameStyle}>{children}</div>

      <nav aria-label={isAdmin ? 'Admin navigation' : 'Staff navigation'} style={getNavStyle(navItems.length)}>
        {navItems.map((item) => (
          <NavItem
            key={item.to}
            active={item.active}
            icon={item.icon}
            label={item.label}
            to={item.to}
          />
        ))}
      </nav>
    </div>
  );
}
