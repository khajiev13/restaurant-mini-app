import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { getOrders } from '../../services/api';
import { formatPrice, formatDate } from '../../utils/format';
import type { Order } from '../../types/api';

const tg = window.Telegram?.WebApp;

const STATUS_LABELS_MAP: Record<string, { label: string; color: string; bg: string; dot: string }> = {
  NEW: { label: 'Placed', color: '#0369a1', bg: '#e0f2fe', dot: '#0284c7' },
  ACCEPTED_BY_RESTAURANT: { label: 'Preparing', color: '#b45309', bg: '#fef3c7', dot: '#d97706' },
  READY: { label: 'Ready', color: '#047857', bg: '#d1fae5', dot: '#059669' },
  TAKEN_BY_COURIER: { label: 'On the Way', color: '#7c3aed', bg: '#ede9fe', dot: '#8b5cf6' },
  CANCELED: { label: 'Cancelled', color: '#b91c1c', bg: '#fef2f2', dot: '#dc2626' },
};

export default function ArtisanOrdersPage() {
  const { t, i18n } = useTranslation();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const bb = tg?.BackButton;
    if (!bb) return;
    const h = () => navigate('/');
    bb.onClick(h); bb.show();
    return () => { bb.offClick(h); bb.hide(); };
  }, [navigate]);

  useEffect(() => {
    let cancelled = false;
    void getOrders()
      .then((res) => { if (!cancelled) setOrders(res.data.data || []); })
      .catch(console.error)
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <ArtisanLayout>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 80, minHeight: '60vh' }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${COLORS.surfaceContainer}`, borderTopColor: COLORS.primary, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ArtisanLayout>
    );
  }

  return (
    <ArtisanLayout>
      <main style={{ paddingTop: 80, paddingBottom: 96, paddingLeft: 16, paddingRight: 16, maxWidth: 672, margin: '0 auto' }}>
        <h2 style={{ fontFamily: FONTS.headline, fontSize: 22, fontWeight: 800, letterSpacing: '-0.01em', margin: '0 0 20px', color: COLORS.onSurface }}>
          {t('profile.orders', 'Order History')}
        </h2>

        {orders.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '56px 0', gap: 16 }}>
            <div style={{ width: 80, height: 80, backgroundColor: COLORS.surfaceContainer, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Icon name="receipt_long" size={36} style={{ color: COLORS.outline }} />
            </div>
            <div style={{ textAlign: 'center' }}>
              <h3 style={{ fontWeight: 700, fontSize: 18, margin: '0 0 4px' }}>{t('profile.no_orders', 'No orders yet')}</h3>
              <p style={{ fontSize: 14, color: COLORS.secondary, margin: 0 }}>{t('profile.no_orders_description', 'Your order history will appear here')}</p>
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
              {t('profile.browse_menu', 'Browse Menu')}
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {orders.map((order) => {
              const st = STATUS_LABELS_MAP[order.status] || STATUS_LABELS_MAP.NEW;
              return (
                <div
                  key={order.id}
                  onClick={() => navigate(`/order/${order.id}`)}
                  style={{
                    backgroundColor: COLORS.surfaceContainerLowest, padding: 16, borderRadius: 16,
                    display: 'flex', flexDirection: 'column', gap: 12, cursor: 'pointer',
                    transition: 'transform 0.1s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: COLORS.outline }}>
                        {formatDate(new Date(order.created_at), i18n.language)}
                      </span>
                      <h4 style={{ fontFamily: FONTS.headline, fontWeight: 700, color: COLORS.onSurface, margin: '2px 0 0' }}>
                        {order.order_number ? `#${order.order_number}` : `#${order.id.slice(0, 6)}`}
                      </h4>
                    </div>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px',
                      backgroundColor: st.bg, color: st.color,
                      borderRadius: 9999, fontSize: 12, fontWeight: 700,
                    }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: st.dot }} />
                      {st.label}
                    </div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 8, borderTop: `1px solid ${COLORS.surfaceContainer}` }}>
                    <p style={{ fontSize: 13, color: COLORS.secondary, margin: 0 }}>
                      {order.items?.map((i) => `${i.quantity}x ${i.name || 'Item'}`).join(', ')}
                    </p>
                    <p style={{ fontWeight: 700, color: COLORS.primary, fontSize: 17, fontFamily: FONTS.headline, margin: 0 }}>
                      {formatPrice(order.total_amount, i18n.language)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </ArtisanLayout>
  );
}
