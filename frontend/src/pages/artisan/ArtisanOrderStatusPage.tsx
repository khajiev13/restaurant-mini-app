import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ArtisanLayout, { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { cancelOrder, getOrder, getOrderStatus, switchOrderToCash } from '../../services/api';
import { useCartStore } from '../../stores/cartStore';
import { formatPrice } from '../../utils/format';
import type { Order, OrderStatus } from '../../types/api';

const DELIVERY_STEPS = [
  { key: 'NEW', icon: 'check', labelKey: 'status.placed' },
  { key: 'ACCEPTED_BY_RESTAURANT', icon: 'restaurant', labelKey: 'status.preparing' },
  { key: 'READY', icon: 'local_dining', labelKey: 'status.ready' },
  { key: 'TAKEN_BY_COURIER', icon: 'moped', labelKey: 'status.on_the_way' },
];

const TABLE_STEPS = [
  { key: 'NEW', icon: 'check', labelKey: 'status.placed' },
  { key: 'ACCEPTED_BY_RESTAURANT', icon: 'restaurant', labelKey: 'status.preparing' },
  { key: 'READY', icon: 'local_dining', labelKey: 'status.ready' },
];

const STATUS_STEP: Record<string, number> = {
  NEW: 1,
  PAID_AWAITING_RESTAURANT: 1,
  ACCEPTED_BY_RESTAURANT: 2,
  READY: 3,
  TAKEN_BY_COURIER: 4,
};

function errorDetail(error: unknown): { status?: number; detail?: string } {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown } } }).response;
  return {
    status: response?.status,
    detail: typeof response?.data?.detail === 'string' ? response.data.detail : undefined,
  };
}

export default function ArtisanOrderStatusPage() {
  const { t, i18n } = useTranslation();
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const clearCart = useCartStore((state) => state.clearCart);
  const [order, setOrder] = useState<Order | null>(null);
  const [status, setStatus] = useState<OrderStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<'cancel' | 'cash' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const previousStatus = useRef<string | null>(null);
  const tg = window.Telegram?.WebApp;
  const isInsideTelegram = !!tg?.initData;

  useEffect(() => {
    const backButton = tg?.BackButton;
    if (!backButton) return undefined;
    const handleBack = () => navigate('/order');
    backButton.onClick(handleBack);
    backButton.show();
    return () => {
      backButton.offClick(handleBack);
      backButton.hide();
    };
  }, [navigate, tg]);

  useEffect(() => {
    if (!orderId || !isInsideTelegram) return;
    let cancelled = false;
    void getOrder(orderId)
      .then((response) => {
        if (!cancelled) setOrder(response.data.data);
      })
      .catch(console.error)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [isInsideTelegram, orderId]);

  useEffect(() => {
    if (!orderId || !isInsideTelegram) return undefined;
    let cancelled = false;
    const poll = () => {
      void getOrderStatus(orderId)
        .then((response) => {
          if (cancelled) return;
          const next = response.data.data;
          setStatus(next);
          if (previousStatus.current && next.status !== previousStatus.current) {
            const isCancelled = next.status === 'CANCELED' || next.status === 'CANCELLED';
            tg?.HapticFeedback?.notificationOccurred(isCancelled ? 'error' : 'success');
          }
          previousStatus.current = next.status;
        })
        .catch(console.error);
    };
    poll();
    const interval = window.setInterval(poll, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [isInsideTelegram, orderId, tg]);

  const applyOrderUpdate = (updated: Order) => {
    setOrder(updated);
    setStatus((current) => (current ? {
      ...current,
      status: updated.status,
      order_number: updated.order_number,
      alipos_order_id: updated.alipos_order_id,
      payment_status: updated.payment_status,
      payment_expires_at: updated.payment_expires_at,
      multicard_receipt_url: updated.multicard_receipt_url,
      table_title: updated.table_title,
      hall_title: updated.hall_title,
      service_percent: updated.service_percent,
      alipos_sync_status: updated.alipos_sync_status,
    } : current));
  };

  const handleCancel = async () => {
    if (!orderId || action) return;
    if (!window.confirm(t('order.cancel_confirm'))) return;
    setAction('cancel');
    setActionError(null);
    try {
      const response = await cancelOrder(orderId);
      applyOrderUpdate(response.data.data);
      tg?.HapticFeedback?.notificationOccurred('success');
    } catch (error) {
      const details = errorDetail(error);
      setActionError(details.status === 409
        ? t('order.cancel_too_late')
        : t('order.action_failed'));
      if (details.status === 409) {
        void getOrderStatus(orderId).then((response) => setStatus(response.data.data));
      }
      tg?.HapticFeedback?.notificationOccurred('error');
    } finally {
      setAction(null);
    }
  };

  const handleSwitchToCash = async () => {
    if (!orderId || action) return;
    setAction('cash');
    setActionError(null);
    try {
      const response = await switchOrderToCash(orderId);
      applyOrderUpdate(response.data.data);
      tg?.HapticFeedback?.notificationOccurred('success');
    } catch (error) {
      const details = errorDetail(error);
      setActionError(details.status === 409
        ? t('order.payment_changed')
        : t('order.switch_cash_failed'));
      tg?.HapticFeedback?.notificationOccurred('error');
    } finally {
      setAction(null);
    }
  };

  if (!isInsideTelegram) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', backgroundColor: COLORS.surface, padding: 24, textAlign: 'center' }}>
        <div>
          <Icon name="smartphone" fill size={64} style={{ color: COLORS.primary }} />
          <h2 style={{ fontFamily: FONTS.headline, fontSize: 24, color: COLORS.onSurface }}>{t('order.open_telegram')}</h2>
          <a href="https://t.me/olotsomsa_zakaz_bot" style={{ display: 'inline-block', backgroundColor: COLORS.primary, color: '#fff', padding: '14px 24px', borderRadius: 14, textDecoration: 'none', fontWeight: 700 }}>
            {t('order.open_telegram_action')}
          </a>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <ArtisanLayout>
        <div style={{ display: 'grid', placeItems: 'center', minHeight: '80vh' }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${COLORS.surfaceContainer}`, borderTopColor: COLORS.primary, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ArtisanLayout>
    );
  }

  if (!order) {
    return (
      <ArtisanLayout>
        <main style={{ padding: '120px 24px', textAlign: 'center' }}>{t('order.not_found')}</main>
      </ArtisanLayout>
    );
  }

  const isTableOrder = order.discriminator === 'inplace';
  const currentStatus = status?.status || order.status;
  const paymentStatus = status?.payment_status ?? order.payment_status;
  const tableTitle = status?.table_title || order.table_title;
  const hallTitle = status?.hall_title || order.hall_title;
  const servicePercent = status?.service_percent ?? order.service_percent;
  const syncStatus = status?.alipos_sync_status ?? order.alipos_sync_status;
  const isCancelled = currentStatus === 'CANCELED' || currentStatus === 'CANCELLED';
  const isPendingPayment = paymentStatus === 'pending' && currentStatus === 'AWAITING_PAYMENT';
  const isPaid = paymentStatus === 'paid';
  const steps = isTableOrder ? TABLE_STEPS : DELIVERY_STEPS;
  const currentStep = STATUS_STEP[currentStatus] || 1;
  const canCancel = isTableOrder && (currentStatus === 'NEW' || currentStatus === 'AWAITING_PAYMENT');
  const canSwitchToCash = isTableOrder && isPendingPayment && !!order.multicard_checkout_url;
  const receiptUrl = status?.multicard_receipt_url ?? order.multicard_receipt_url;

  const statusLabels: Record<string, string> = {
    AWAITING_PAYMENT: t('status.awaiting_payment'),
    PAYMENT_FAILED: t('status.payment_failed'),
    PAID_AWAITING_RESTAURANT: t('status.placed'),
    NEW: t('status.placed'),
    ACCEPTED_BY_RESTAURANT: t('status.preparing'),
    READY: t('status.ready'),
    TAKEN_BY_COURIER: t('status.on_the_way'),
    SYNC_UNKNOWN: t('status.sync_unknown'),
    SUBMISSION_FAILED: t('status.submission_failed'),
    CANCELED: t('status.cancelled'),
    CANCELLED: t('status.cancelled'),
  };

  const paymentLabel = paymentStatus === 'refund_pending'
    ? t('payment.refund_pending')
    : paymentStatus === 'refunded'
      ? t('payment.refunded')
      : paymentStatus === 'refund_failed'
        ? t('payment.refund_failed')
        : isPaid
          ? t('payment.paid_online')
          : order.payment_method === 'cash'
            ? t('payment.cash')
            : t('payment.awaiting');

  return (
    <ArtisanLayout>
      <main style={{ minHeight: '100vh', padding: '88px 16px 120px', maxWidth: 448, margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <section style={{ textAlign: 'center' }}>
            <div style={{ width: 76, height: 76, margin: '0 auto 14px', borderRadius: '50%', backgroundColor: isCancelled ? 'rgba(179,27,37,0.1)' : 'rgba(163,56,0,0.1)', display: 'grid', placeItems: 'center' }}>
              <Icon name={isCancelled ? 'cancel' : isTableOrder ? 'table_restaurant' : 'receipt_long'} fill size={38} style={{ color: isCancelled ? COLORS.error : COLORS.primary }} />
            </div>
            <h2 style={{ fontFamily: FONTS.headline, fontSize: 28, fontWeight: 800, color: COLORS.onSurface, margin: 0 }}>
              {statusLabels[currentStatus] || currentStatus}
            </h2>
            <p style={{ color: COLORS.secondary, fontWeight: 700, margin: '8px 0 0' }}>
              {t('order.order_number')}{status?.order_number || order.order_number || `#${order.id.slice(0, 6)}`}
            </p>
          </section>

          {isTableOrder && tableTitle && (
            <section style={{ background: '#fff7ed', border: '1px solid rgba(163,56,0,0.14)', borderRadius: 16, padding: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 44, height: 44, borderRadius: 13, background: 'rgba(163,56,0,0.12)', display: 'grid', placeItems: 'center' }}>
                <Icon name="table_restaurant" size={24} style={{ color: COLORS.primary }} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: FONTS.headline, fontWeight: 800 }}>{tableTitle}</div>
                {hallTitle && <div style={{ color: COLORS.secondary, fontSize: 12, marginTop: 2 }}>{hallTitle}</div>}
              </div>
              <span style={{ padding: '6px 10px', borderRadius: 999, background: '#fff', color: COLORS.primary, fontSize: 12, fontWeight: 800 }}>
                {paymentLabel}
              </span>
            </section>
          )}

          {order.payment_method === 'rahmat' && (
            <section style={{ backgroundColor: COLORS.surfaceContainerLowest, border: `1px solid ${isCancelled ? COLORS.error : COLORS.outlineVariant}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 16 }}>
                <Icon name={isPaid ? 'check_circle' : paymentStatus === 'refunded' ? 'currency_exchange' : 'schedule'} fill size={26} style={{ color: isPaid ? '#047857' : COLORS.primary }} />
                <div>
                  <div style={{ fontWeight: 800 }}>{paymentLabel}</div>
                  <div style={{ fontSize: 12, color: COLORS.secondary, marginTop: 2 }}>
                    {isPendingPayment ? t('payment.awaiting_desc') : isPaid ? t('payment.confirmed_desc') : t('payment.status_updated')}
                  </div>
                </div>
              </div>
              {isPendingPayment && order.multicard_checkout_url && (
                <button type="button" onClick={() => tg?.openLink ? tg.openLink(order.multicard_checkout_url as string) : window.open(order.multicard_checkout_url as string, '_blank')} style={{ width: '100%', padding: 14, border: 0, backgroundColor: COLORS.primary, color: COLORS.onPrimary, fontWeight: 800, cursor: 'pointer' }}>
                  {t('payment.retry_online')}
                </button>
              )}
              {isPaid && receiptUrl && (
                <button type="button" onClick={() => tg?.openLink ? tg.openLink(receiptUrl) : window.open(receiptUrl, '_blank')} style={{ width: '100%', padding: 14, border: 0, backgroundColor: COLORS.surfaceContainerLow, color: COLORS.primary, fontWeight: 800, cursor: 'pointer' }}>
                  {t('payment.view_receipt')}
                </button>
              )}
            </section>
          )}

          {(syncStatus === 'unknown' || syncStatus === 'failed') && (
            <div role="alert" style={{ padding: 14, borderRadius: 12, background: '#fff7ed', color: '#9a3412', fontSize: 13, fontWeight: 700 }}>
              {t('order.sync_help')}
            </div>
          )}

          {!isCancelled && !isPendingPayment && (
            <section style={{ backgroundColor: COLORS.surfaceContainerLow, borderRadius: 14, padding: 20 }}>
              <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between' }}>
                <div style={{ position: 'absolute', top: 16, left: 0, width: '100%', height: 4, backgroundColor: COLORS.surfaceContainerHighest, borderRadius: 99 }} />
                <div style={{ position: 'absolute', top: 16, left: 0, width: `${((currentStep - 1) / (steps.length - 1)) * 100}%`, height: 4, backgroundColor: COLORS.primary, borderRadius: 99 }} />
                {steps.map((step, index) => {
                  const reached = currentStep >= index + 1;
                  return (
                    <div key={step.key} style={{ zIndex: 1, width: `${100 / steps.length}%`, textAlign: 'center' }}>
                      <div style={{ margin: '0 auto 10px', width: 32, height: 32, borderRadius: '50%', display: 'grid', placeItems: 'center', backgroundColor: reached ? COLORS.primary : COLORS.surfaceContainerHighest, color: reached ? '#fff' : COLORS.outline, boxShadow: `0 0 0 4px ${COLORS.surfaceContainerLow}` }}>
                        <Icon name={reached && index < currentStep - 1 ? 'check' : step.icon} size={16} fill={reached} />
                      </div>
                      <span style={{ fontSize: 10, fontWeight: 800, color: reached ? COLORS.primary : COLORS.outline }}>
                        {t(step.labelKey)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section style={{ backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 16, padding: 18, display: 'grid', gap: 12 }}>
            {!isTableOrder && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: COLORS.secondary }}>{t('order.internal_order')}</span>
                  <strong>{order.id.slice(0, 8)}</strong>
                </div>
                {status?.alipos_order_id && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: COLORS.secondary }}>{t('order.alipos_reference')}</span>
                    <strong>{status.alipos_order_id.slice(0, 8)}</strong>
                  </div>
                )}
              </>
            )}
            {isTableOrder && servicePercent > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', color: COLORS.secondary, fontSize: 13 }}>
                <span>{t('checkout.service_charge')} ({servicePercent}%)</span>
                <span>{formatPrice(order.total_amount - order.items_cost, i18n.language)}</span>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10, borderTop: `1px solid ${COLORS.surfaceContainer}` }}>
              <strong>{t('common.total')}</strong>
              <strong style={{ color: COLORS.primary, fontSize: 20 }}>{formatPrice(order.total_amount, i18n.language)}</strong>
            </div>
          </section>

          {order.items.length > 0 && (
            <section style={{ backgroundColor: COLORS.surfaceContainerLowest, borderRadius: 16, overflow: 'hidden' }}>
              {order.items.map((item, index) => (
                <div key={`${item.id}-${index}`} style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', borderBottom: index < order.items.length - 1 ? `1px solid ${COLORS.surfaceContainer}` : undefined }}>
                  <span>{item.name || `${t('order.item_format')} ${index + 1}`}</span>
                  <span style={{ color: COLORS.secondary }}>{item.quantity}× {formatPrice(item.price, i18n.language)}</span>
                </div>
              ))}
            </section>
          )}

          {actionError && <div role="alert" style={{ color: COLORS.error, background: 'rgba(179,27,37,0.08)', padding: 14, borderRadius: 12, fontWeight: 700 }}>{actionError}</div>}

          {isTableOrder && (
            <section style={{ display: 'grid', gap: 10 }}>
              {canSwitchToCash && (
                <button type="button" disabled={action !== null} onClick={() => void handleSwitchToCash()} style={{ padding: 14, borderRadius: 12, border: `1px solid ${COLORS.primary}`, background: '#fff', color: COLORS.primary, fontWeight: 800, cursor: 'pointer' }}>
                  {action === 'cash' ? t('common.loading') : t('payment.switch_to_cash')}
                </button>
              )}
              <button type="button" onClick={() => { clearCart(); navigate('/'); }} style={{ padding: 15, borderRadius: 12, border: 0, background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.primaryContainer})`, color: COLORS.onPrimary, fontWeight: 800, cursor: 'pointer' }}>
                {t('order.order_more')}
              </button>
              {canCancel && (
                <button type="button" disabled={action !== null} onClick={() => void handleCancel()} style={{ padding: 13, borderRadius: 12, border: 0, background: 'transparent', color: COLORS.error, fontWeight: 800, cursor: 'pointer' }}>
                  {action === 'cancel' ? t('common.loading') : t('order.cancel_order')}
                </button>
              )}
            </section>
          )}

          {!isCancelled && !isPendingPayment && (
            <div style={{ textAlign: 'center', color: COLORS.outline, fontSize: 12 }}>{t('order.updating')}</div>
          )}
        </div>
      </main>
    </ArtisanLayout>
  );
}
