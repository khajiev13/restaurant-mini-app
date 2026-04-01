import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../../stores/authStore';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { deleteAddress, getAddresses, getMe, getOrders, updateMe } from '../../services/api';
import { formatPrice, formatDate } from '../../utils/format';
import type { Address, Order, User } from '../../types/api';

const tg = window.Telegram?.WebApp;
const haptic = tg?.HapticFeedback;

const tgAlert = (message: string) => {
  if (tg?.showAlert) tg.showAlert(message);
  else alert(message);
};

function formatAddressDetails(a: Address) {
  const parts: string[] = [];
  if (a.entrance) parts.push(`Ent. ${a.entrance}`);
  if (a.floor) parts.push(`Fl. ${a.floor}`);
  if (a.apartment) parts.push(`Apt. ${a.apartment}`);
  return parts.length > 0 ? parts.join(', ') : null;
}

// --- Sub-components ---

function ProfileHeader({ user, onSharePhone }: { user: User; onSharePhone: () => void }) {
  const initial = (user.first_name?.[0] || '?').toUpperCase();
  const { t } = useTranslation();
  return (
    <section style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '24px 0', gap: 16 }}>
      <div style={{ position: 'relative' }}>
        {user.photo_url ? (
          <img
            src={user.photo_url}
            alt="Profile"
            style={{
              width: 96, height: 96, borderRadius: '50%', objectFit: 'cover',
              boxShadow: '0 10px 25px -5px rgba(163, 56, 0, 0.3)',
            }}
          />
        ) : (
          <div
            style={{
              width: 96, height: 96, borderRadius: '50%',
              background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: COLORS.onPrimary, fontSize: 36, fontFamily: FONTS.headline, fontWeight: 700,
              boxShadow: '0 10px 25px -5px rgba(163, 56, 0, 0.3)',
            }}
          >
            {initial}
          </div>
        )}
      </div>
      <div>
        <h1 style={{ fontSize: 24, fontFamily: FONTS.headline, fontWeight: 700, letterSpacing: '-0.01em', color: COLORS.onSurface, margin: 0 }}>
          {user.first_name} {user.last_name || ''}
        </h1>
        <p style={{ color: COLORS.secondary, fontWeight: 500, margin: '4px 0 0' }}>
          @{user.username || 'N/A'}
        </p>
      </div>
      {user.phone_number ? (
        <button
          style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px',
            backgroundColor: COLORS.surfaceContainerLow, borderRadius: 12,
            color: COLORS.onSurface, fontWeight: 600, border: 'none', cursor: 'pointer',
            fontFamily: FONTS.body, fontSize: 14,
          }}
        >
          <Icon name="phone_iphone" style={{ color: COLORS.primary }} />
          <span>{user.phone_number}</span>
        </button>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
          <p style={{ color: COLORS.error, margin: 0, fontSize: 13, fontWeight: 600 }}>{t('profile.no_phone', 'No phone number')}</p>
          <button
            onClick={onSharePhone}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px',
              background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)', borderRadius: 12,
              color: COLORS.onPrimary, fontWeight: 700, border: 'none', cursor: 'pointer',
              fontFamily: FONTS.body, fontSize: 14, boxShadow: '0 4px 14px rgba(163, 56, 0, 0.3)',
            }}
          >
            <Icon name="person_add" style={{ color: COLORS.onPrimary }} />
            <span>{t('profile.share_phone', 'Share Phone to Login')}</span>
          </button>
        </div>
      )}
    </section>
  );
}

function AddressCard({ address, onDelete }: { address: Address; onDelete: (id: string) => void }) {
  const details = formatAddressDetails(address);
  const iconName = address.label.toLowerCase().includes('office') ? 'work' : 'home';

  return (
    <div
      style={{
        backgroundColor: COLORS.surfaceContainerLowest, padding: 16, borderRadius: 12,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        transition: 'all 0.2s ease',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
        <div style={{ padding: 8, backgroundColor: COLORS.surfaceContainer, borderRadius: 8, color: COLORS.primary }}>
          <Icon name={iconName} />
        </div>
        <div>
          <h3 style={{ fontWeight: 700, color: COLORS.onSurface, margin: 0, fontSize: 15 }}>{address.label}</h3>
          <p style={{ fontSize: 13, color: COLORS.secondary, margin: '2px 0 0' }}>
            {address.full_address}
            {details ? ` · ${details}` : ''}
          </p>
        </div>
      </div>
      <button
        onClick={() => onDelete(address.id)}
        style={{ color: COLORS.outline, border: 'none', background: 'none', cursor: 'pointer', padding: 8 }}
      >
        <Icon name="delete" />
      </button>
    </div>
  );
}

function OrderCard({ order, onClick, language }: { order: Order; onClick: () => void; language: string }) {
  return (
    <div
      onClick={onClick}
      style={{
        backgroundColor: COLORS.surfaceContainerLowest, padding: 16, borderRadius: 16,
        display: 'flex', flexDirection: 'column', gap: 12, cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.outline }}>
            {formatDate(new Date(order.created_at), language)}
          </span>
          <h4 style={{ fontFamily: FONTS.headline, fontWeight: 700, color: COLORS.onSurface, margin: '2px 0 0' }}>
            {order.order_number ? `#${order.order_number}` : `#${order.id.slice(0, 6)}`}
          </h4>
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px',
          backgroundColor: order.status === 'CANCELED' ? '#fef2f2' : '#f0fdf4',
          color: order.status === 'CANCELED' ? '#b91c1c' : '#15803d',
          borderRadius: 9999, fontSize: 12, fontWeight: 700,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: order.status === 'CANCELED' ? '#dc2626' : '#16a34a' }} />
          {order.status === 'CANCELED' ? 'Cancelled' : 'Delivered'}
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 8, borderTop: `1px solid ${COLORS.surfaceContainer}` }}>
        <p style={{ fontSize: 13, color: COLORS.secondary, margin: 0 }}>
          {order.items?.map((i) => `${i.quantity}x ${i.name || 'Item'}`).join(', ')}
        </p>
        <p style={{ fontWeight: 700, color: COLORS.primary, fontSize: 17, fontFamily: FONTS.headline, margin: 0 }}>
          {formatPrice(order.total_amount, language)}
        </p>
      </div>
    </div>
  );
}

// --- Main Profile Page ---
export default function ArtisanProfilePage() {
  const { t, i18n } = useTranslation();
  const [user, setUser] = useState<User | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;

  const logout = useAuthStore((s) => s.logout);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const authenticate = useAuthStore((s) => s.authenticate);

  useEffect(() => {
    const backButton = tg?.BackButton;
    if (!backButton) return;
    const handler = () => navigateRef.current('/');
    backButton.onClick(handler);
    backButton.show();
    return () => { backButton.offClick(handler); backButton.hide(); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    setLoading(true);
    // Use allSettled so that if e.g. getOrders fails, we still get the user profile
    void Promise.allSettled([getMe(), getOrders(), getAddresses()])
      .then(([userRes, ordersRes, addressesRes]) => {
        if (cancelled) return;
        if (userRes.status === 'fulfilled') setUser(userRes.value.data.data);
        if (ordersRes.status === 'fulfilled') setOrders(ordersRes.value.data.data);
        if (addressesRes.status === 'fulfilled') setAddresses(addressesRes.value.data.data || []);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isAuthenticated]);

  const handleSharePhone = () => {
    if (!tg) return;

    const pollForPhone = async (attempts = 10) => {
      for (let index = 0; index < attempts; index += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        try {
          const res = await getMe();
          const nextPhone = res.data.data?.phone_number;
          if (nextPhone) {
            setUser((current) => (current ? { ...current, phone_number: nextPhone } : current));
            haptic?.notificationOccurred('success');
            return;
          }
        } catch {
          // Keep polling
        }
      }
    };

    tg.requestContact((shared) => {
      if (shared) {
        void pollForPhone();
      }
    });
  };

  const handleDeleteAddress = (id: string) => {
    const remove = async () => {
      try {
        await deleteAddress(id);
        setAddresses((c) => c.filter((a) => a.id !== id));
        haptic?.notificationOccurred('success');
      } catch { tgAlert(t('checkout.error_save_address')); }
    };

    if (tg?.showConfirm) {
      tg.showConfirm(t('profile.delete_address_confirm'), (confirmed) => { if (confirmed) void remove(); });
      return;
    }
    void remove();
  };

  const handleLanguageChange = async (lang: string) => {
    await i18n.changeLanguage(lang);
    localStorage.setItem('i18nextLng', lang);
    try { await updateMe({ language: lang }); } catch { /* best-effort */ }
  };

  if (loading) {
    return (
      <ArtisanLayout>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 80 }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${COLORS.surfaceContainer}`, borderTopColor: COLORS.primary, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ArtisanLayout>
    );
  }

  if (!isAuthenticated) {
    return (
      <ArtisanLayout>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '120px 24px', textAlign: 'center' }}>
          <div style={{ paddingBottom: 24 }}>
            <Icon name="profile" style={{ fontSize: 64, color: COLORS.surface }} />
          </div>
          <h2 style={{ fontFamily: FONTS.headline, fontSize: 24, color: COLORS.onSurface, margin: '0 0 8px 0' }}>{t('profile.not_logged_in_title', 'Not Logged In')}</h2>
          <p style={{ fontFamily: FONTS.body, fontSize: 16, color: COLORS.secondary, margin: '0 0 32px 0' }}>
            {t('profile.not_logged_in_desc', 'Please log in with Telegram to view your profile and orders.')}
          </p>
          <button
            onClick={() => void authenticate()}
            style={{
              backgroundColor: COLORS.primary,
              color: COLORS.onPrimary,
              border: 'none',
              borderRadius: 12,
              padding: '16px 24px',
              fontFamily: FONTS.headline,
              fontSize: 16,
              fontWeight: 700,
              width: '100%',
              cursor: 'pointer',
            }}
          >
            {t('profile.login_button', 'Login with Telegram')}
          </button>
        </div>
      </ArtisanLayout>
    );
  }

  const initial = user ? (user.first_name?.[0] || '?').toUpperCase() : 'A';

  return (
    <ArtisanLayout avatarInitial={initial} avatarUrl={user?.photo_url || undefined}>
      {/* Background texture */}
      <div
        style={{
          position: 'fixed', top: 0, left: 0, width: '100%', height: 192,
          zIndex: -1, opacity: 0.1, pointerEvents: 'none', overflow: 'hidden',
        }}
      >
        <img
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          src="https://lh3.googleusercontent.com/aida-public/AB6AXuCTOolvazc6YCY0EJmxUUW0L1oA_HYzXcXop8XiWOlfSdjUzGXEI3WhhzmutBnMMWljLnKU7sGA9s7gtvu1YuytxqVuRXUlzyTbLc9XdtF-KFHDM7f4HjgLyEjfge3G6I8wsB6CVYVW0eLPGIvEZ5BUuANwtDxXRsIwPDXCvap581cbGsGUuMlLz2FImzasDkGPpg6D1Oge16RLE_IIt4q15h5kua5m58T3n-m7bNwbTgOCRBBX-8WscTkVvOcu-Yn8SmVIjFvwGQw"
          alt=""
        />
      </div>

      <main style={{ paddingTop: 80, paddingBottom: 96, paddingLeft: 16, paddingRight: 16, maxWidth: 672, margin: '0 auto' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          {/* Profile Header */}
          {user && <ProfileHeader user={user} onSharePhone={handleSharePhone} />}

          {/* Saved Addresses */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{ fontSize: 18, fontFamily: FONTS.headline, fontWeight: 700, margin: 0 }}>
                {t('profile.addresses')}
              </h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {addresses.length === 0 ? (
                <p style={{ fontSize: 14, color: COLORS.secondary }}>{t('profile.no_addresses')}</p>
              ) : (
                addresses.map((a) => (
                  <AddressCard key={a.id} address={a} onDelete={handleDeleteAddress} />
                ))
              )}
            </div>
          </section>

          {/* Language Settings */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <h2 style={{ fontSize: 18, fontFamily: FONTS.headline, fontWeight: 700, margin: 0 }}>
              {t('profile.language')}
            </h2>
            <div style={{ backgroundColor: COLORS.surfaceContainerLow, padding: 8, borderRadius: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
              {[
                { code: 'uz', flag: '🇺🇿' },
                { code: 'ru', flag: '🇷🇺' },
                { code: 'en', flag: '🇬🇧' },
              ].map(({ code, flag }) => {
                const active = i18n.language === code;
                return (
                  <label
                    key={code}
                    style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 12, borderRadius: 12,
                      backgroundColor: active ? COLORS.surfaceContainerLowest : 'transparent',
                      cursor: 'pointer', transition: 'background-color 0.2s ease',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{ fontSize: 20 }}>{flag}</span>
                      <span style={{ fontWeight: active ? 600 : 400, fontFamily: FONTS.body }}>
                        {t(`profile.language_${code}`)}
                      </span>
                    </div>
                    <input
                      type="radio" name="language" checked={active}
                      onChange={() => void handleLanguageChange(code)}
                      style={{ accentColor: COLORS.primary, width: 20, height: 20 }}
                    />
                  </label>
                );
              })}
            </div>
          </section>

          {/* Order History */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingBottom: 48 }}>
            <h2 style={{ fontSize: 18, fontFamily: FONTS.headline, fontWeight: 700, margin: 0 }}>
              {t('profile.orders')}
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {orders.length === 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '48px 0', gap: 16 }}>
                  <div style={{ width: 80, height: 80, backgroundColor: COLORS.surfaceContainer, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Icon name="receipt_long" size={36} style={{ color: COLORS.outline }} />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <h3 style={{ fontWeight: 700, fontSize: 18, margin: '0 0 4px' }}>{t('profile.no_orders')}</h3>
                    <p style={{ fontSize: 14, color: COLORS.secondary, margin: 0 }}>{t('profile.no_orders_description')}</p>
                  </div>
                  <button
                    onClick={() => navigate('/')}
                    style={{
                      background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)',
                      color: COLORS.onPrimary, padding: '12px 32px', borderRadius: 12,
                      fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
                      fontSize: 13, border: 'none', cursor: 'pointer',
                      boxShadow: '0 4px 14px rgba(163, 56, 0, 0.3)',
                    }}
                  >
                    {t('profile.browse_menu')}
                  </button>
                </div>
              ) : (
                orders.map((order) => (
                  <OrderCard
                    key={order.id}
                    order={order}
                    language={i18n.language}
                    onClick={() => navigate(`/order/${order.id}`)}
                  />
                ))
              )}
            </div>
          </section>

          {/* Logout Button */}
          <section style={{ paddingBottom: 24 }}>
            <button
              onClick={logout}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                padding: 16,
                backgroundColor: 'rgba(179, 27, 37, 0.1)',
                color: '#b31b25',
                border: `1px solid rgba(179, 27, 37, 0.2)`,
                borderRadius: 16,
                fontFamily: FONTS.headline,
                fontWeight: 700,
                fontSize: 16,
                cursor: 'pointer',
              }}
            >
              <Icon name="logout" style={{ fontSize: 20 }} />
              {t('profile.logout', 'Log Out')}
            </button>
          </section>
        </div>
      </main>
    </ArtisanLayout>
  );
}
