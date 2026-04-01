import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { getOrder, getOrderStatus } from '../../services/api';
import { formatPrice } from '../../utils/format';
import type { Order, OrderStatus } from '../../types/api';

const tg = window.Telegram?.WebApp;
const haptic = tg?.HapticFeedback;

const STATUS_STEP: Record<string, number> = {
  NEW: 1, ACCEPTED_BY_RESTAURANT: 2, READY: 3, TAKEN_BY_COURIER: 4, CANCELED: 0,
};

const STEPS = [
  { key: 'NEW', icon: 'check', label: 'Order Placed' },
  { key: 'ACCEPTED_BY_RESTAURANT', icon: 'restaurant', label: 'Being Prepared' },
  { key: 'READY', icon: 'local_dining', label: 'Ready' },
  { key: 'TAKEN_BY_COURIER', icon: 'moped', label: 'On the Way' },
];

export default function ArtisanOrderStatusPage() {
  const { t, i18n } = useTranslation();
  const { orderId } = useParams<{ orderId: string }>();
  const [order, setOrder] = useState<Order | null>(null);
  const [status, setStatus] = useState<OrderStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const prevStatusRef = useRef<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const bb = tg?.BackButton;
    if (!bb) return;
    const h = () => navigate('/');
    bb.onClick(h); bb.show();
    return () => { bb.offClick(h); bb.hide(); };
  }, [navigate]);

  useEffect(() => {
    if (!orderId) return;
    void getOrder(orderId).then((res) => setOrder(res.data.data)).catch(console.error).finally(() => setLoading(false));
  }, [orderId]);

  useEffect(() => {
    if (!orderId) return;
    const poll = () => {
      void getOrderStatus(orderId).then((res) => {
        const newSt = res.data.data?.status;
        setStatus(res.data.data);
        if (prevStatusRef.current && newSt !== prevStatusRef.current) {
          haptic?.notificationOccurred(newSt === 'CANCELED' ? 'error' : 'success');
        }
        prevStatusRef.current = newSt;
      }).catch(console.error);
    };
    poll();
    const interval = window.setInterval(poll, 15000);
    return () => window.clearInterval(interval);
  }, [orderId]);

  if (loading) {
    return (
      <ArtisanLayout>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 60, minHeight: '80vh' }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${COLORS.surfaceContainer}`, borderTopColor: COLORS.primary, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ArtisanLayout>
    );
  }

  const currentStatus = status?.status || order?.status || 'NEW';
  const currentStep = STATUS_STEP[currentStatus] || 1;
  const isCanceled = currentStatus === 'CANCELED';
  const terminated = isCanceled || currentStatus === 'TAKEN_BY_COURIER';

  const statusLabels: Record<string, string> = {
    NEW: t('status.placed'),
    ACCEPTED_BY_RESTAURANT: t('status.preparing'),
    READY: t('status.ready'),
    TAKEN_BY_COURIER: t('status.on_the_way'),
    CANCELED: t('status.cancelled'),
  };

  const statusIcon: Record<string, string> = {
    NEW: 'receipt_long',
    ACCEPTED_BY_RESTAURANT: 'skillet',
    READY: 'local_dining',
    TAKEN_BY_COURIER: 'moped',
    CANCELED: 'cancel',
  };

  return (
    <ArtisanLayout>
      <main style={{ minHeight: '100vh', paddingTop: 96, paddingBottom: 120, paddingLeft: 16, paddingRight: 16, maxWidth: 448, margin: '0 auto', width: '100%' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          {/* Status Header */}
          <section style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: 80, height: 80, backgroundColor: isCanceled ? 'rgba(179, 27, 37, 0.1)' : 'rgba(163, 56, 0, 0.1)',
              borderRadius: '50%', marginBottom: 16, alignSelf: 'center',
            }}>
              <Icon
                name={statusIcon[currentStatus] || 'info'}
                fill size={40}
                style={{ color: isCanceled ? COLORS.error : COLORS.primary }}
              />
            </div>
            <h2 style={{ fontFamily: FONTS.headline, fontSize: 30, fontWeight: 800, letterSpacing: '-0.02em', color: COLORS.onSurface, margin: 0 }}>
              {statusLabels[currentStatus] || currentStatus}
            </h2>
            <p style={{ fontFamily: FONTS.body, color: COLORS.secondary, fontWeight: 600, letterSpacing: '0.1em', margin: 0, fontSize: 13 }}>
              {t('order.order_number')}{status?.order_number || order?.order_number || `#${orderId?.slice(0, 6) || ''}`}
            </p>
          </section>

          {/* Progress Stepper */}
          {!isCanceled && (
            <section style={{ backgroundColor: COLORS.surfaceContainerLow, borderRadius: 12, padding: 24 }}>
              <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                {/* Background line */}
                <div style={{
                  position: 'absolute', top: 16, left: 0, width: '100%', height: 4,
                  backgroundColor: COLORS.surfaceContainerHighest, borderRadius: 9999, zIndex: 0,
                }} />
                {/* Progress line */}
                <div style={{
                  position: 'absolute', top: 16, left: 0,
                  width: `${((currentStep - 1) / (STEPS.length - 1)) * 100}%`,
                  height: 4, background: 'linear-gradient(135deg, #a33800 0%, #ff7941 100%)',
                  borderRadius: 9999, zIndex: 0, transition: 'width 0.5s ease',
                }} />

                {STEPS.map((step, idx) => {
                  const stepNumber = idx + 1;
                  const reached = currentStep >= stepNumber;
                  return (
                    <div key={step.key} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, width: '25%', zIndex: 1 }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                        backgroundColor: reached ? COLORS.primary : COLORS.surfaceContainerHighest,
                        color: reached ? '#fff' : COLORS.outline,
                        boxShadow: `0 0 0 4px ${COLORS.surfaceContainerLow}`,
                        transition: 'all 0.3s ease',
                      }}>
                        <Icon
                          name={reached && idx < currentStep - 1 ? 'check' : step.icon}
                          size={16}
                          fill={reached}
                          weight={reached ? 700 : 400}
                        />
                      </div>
                      <span style={{
                        fontFamily: FONTS.body, fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                        textAlign: 'center', color: reached ? COLORS.primary : COLORS.outline,
                        transition: 'color 0.3s ease',
                      }}>
                        {step.label}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Order Details */}
          <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <h3 style={{ fontFamily: FONTS.headline, fontSize: 18, fontWeight: 700, color: COLORS.onSurfaceVariant, padding: '0 8px', margin: 0 }}>
              {t('order.title')}
            </h3>
            <div style={{
              backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 12, padding: 20,
              display: 'flex', flexDirection: 'column', gap: 16,
              boxShadow: '0 1px 3px rgba(0,0,0,0.04)', border: '1px solid rgba(172,173,173,0.1)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontFamily: FONTS.body, fontSize: 14, color: COLORS.secondary }}>{t('order.internal_order')}</span>
                <span style={{ fontFamily: FONTS.body, fontWeight: 700, color: COLORS.onSurface }}>{orderId?.slice(0, 8)}</span>
              </div>
              {status?.alipos_order_id && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontFamily: FONTS.body, fontSize: 14, color: COLORS.secondary }}>{t('order.alipos_reference')}</span>
                  <span style={{ fontFamily: FONTS.body, fontWeight: 700, color: COLORS.onSurface }}>{status.alipos_order_id.slice(0, 8)}</span>
                </div>
              )}
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                paddingTop: 12, borderTop: '1px solid rgba(172,173,173,0.1)',
              }}>
                <span style={{ fontFamily: FONTS.headline, fontSize: 16, fontWeight: 700, color: COLORS.onSurface }}>{t('common.total')}</span>
                <span style={{ fontFamily: FONTS.headline, fontSize: 20, fontWeight: 700, color: COLORS.primary }}>
                  {formatPrice(order?.total_amount || 0, i18n.language)}
                </span>
              </div>
            </div>
          </section>

          {/* Order Items */}
          {order?.items && order.items.length > 0 && (
            <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <h3 style={{ fontFamily: FONTS.headline, fontSize: 18, fontWeight: 700, color: COLORS.onSurfaceVariant, padding: '0 8px', margin: 0 }}>
                {t('order.items')}
              </h3>
              <div style={{
                backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 12, overflow: 'hidden',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)', border: '1px solid rgba(172,173,173,0.1)',
              }}>
                {order.items.map((item, idx) => (
                  <div key={`${item.id}-${idx}`} style={{
                    padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    borderBottom: idx < order.items.length - 1 ? `1px solid ${COLORS.surfaceContainer}` : 'none',
                  }}>
                    <span style={{ fontSize: 14, color: COLORS.onSurface }}>
                      {item.name || `${t('order.item_format')} ${idx + 1}`}
                    </span>
                    <span style={{ fontSize: 14, color: COLORS.secondary }}>
                      {item.quantity}× {formatPrice(item.price, i18n.language)}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Auto-updating notice */}
          {!terminated && (
            <div style={{ textAlign: 'center', opacity: 0.5, fontSize: 14, paddingTop: 8 }}>
              {t('order.updating')}
            </div>
          )}
        </div>
      </main>
    </ArtisanLayout>
  );
}
