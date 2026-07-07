import { type CSSProperties, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import StaffLayout from '../../components/staff/StaffLayout';
import StaffPaymentBlock from '../../components/staff/StaffPaymentBlock';
import { getActiveStaffOrder, getStaffOrder, takeStaffOrder } from '../../services/staffApi';
import type { StaffOrder } from '../../types/staff';

const floatingButtonBar: CSSProperties = {
  position: 'fixed',
  left: 0,
  right: 0,
  bottom: 88,
  padding: '16px 20px',
  backgroundColor: 'rgba(246, 246, 246, 0.92)',
  backdropFilter: 'blur(12px)',
};

function canHandleDeliveryPayment(order: StaffOrder): boolean {
  return order.payment_method === 'cash' || order.payment_status === 'paid';
}

export default function StaffOrderDetailPage() {
  const { i18n, t } = useTranslation();
  const navigate = useNavigate();
  const { orderId } = useParams();
  const [order, setOrder] = useState<StaffOrder | null>(null);
  const [activeOrder, setActiveOrder] = useState<StaffOrder | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!orderId) {
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    void Promise.all([getStaffOrder(orderId), getActiveStaffOrder()])
      .then(([orderResponse, activeOrderResponse]) => {
        if (!cancelled) {
          setOrder(orderResponse.data.data);
          setActiveOrder(activeOrderResponse.data.data ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(t('staff.order_detail.load_error', 'Could not load this order.'));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [orderId, t]);

  const handleTakeOrder = async () => {
    if (!order) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const activeOrderResponse = await getActiveStaffOrder();
      const latestActiveOrder = activeOrderResponse.data.data ?? null;

      if (latestActiveOrder && latestActiveOrder.id !== order.id) {
        setActiveOrder(latestActiveOrder);
        setError(
          t(
            'staff.order_detail.active_delivery_error',
            'Finish your current delivery before taking another order.',
          ),
        );
        return;
      }

      await takeStaffOrder(order.id);
      navigate('/staff/orders?tab=active', { replace: true });
    } catch {
      setError(t('staff.order_detail.take_error', 'This order is no longer available.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  const hasAnotherActiveOrder = !!activeOrder && !!order && activeOrder.id !== order.id;
  const showTakeButton = !!order
    && order.status === 'TAKEN_BY_COURIER'
    && canHandleDeliveryPayment(order)
    && !order.assigned_at
    && !order.delivered_at
    && !hasAnotherActiveOrder;

  return (
    <StaffLayout>
      {isLoading ? (
        <p style={{ margin: '0 20px', color: COLORS.secondary }}>
          {t('staff.order_detail.loading', 'Loading order...')}
        </p>
      ) : null}

      {!isLoading && !order ? (
        <section style={{ padding: '0 20px' }}>
          <h1 style={{ margin: 0, fontFamily: FONTS.headline, fontSize: 30, fontWeight: 800 }}>
            {t('staff.order_detail.not_found', 'Order not found')}
          </h1>
          {error ? <p style={{ color: COLORS.error }}>{error}</p> : null}
          <button
            type="button"
            onClick={() => navigate('/staff/orders')}
            style={{
              height: 48,
              marginTop: 12,
              padding: '0 18px',
              border: 'none',
              borderRadius: 12,
              backgroundColor: COLORS.primary,
              color: COLORS.onPrimary,
              fontWeight: 800,
              cursor: 'pointer',
            }}
          >
            Back to Orders
          </button>
        </section>
      ) : null}

      {order ? (
        <>
          <main style={{ padding: '0 20px', display: 'grid', gap: 18 }}>
            <button
              type="button"
              onClick={() => navigate('/staff/orders')}
              aria-label="Back to orders"
              style={{
                width: 44,
                height: 44,
                border: 'none',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: COLORS.surfaceContainerLow,
                cursor: 'pointer',
              }}
            >
              <Icon name="arrow_back" />
            </button>

            <div>
              <p
                style={{
                  margin: 0,
                  color: COLORS.primary,
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                }}
              >
                {showTakeButton ? 'Ready For Pickup' : 'Delivery Order'}
              </p>
              <h1
                style={{
                  margin: '8px 0 0',
                  fontFamily: FONTS.headline,
                  fontSize: 36,
                  fontWeight: 800,
                  lineHeight: 1.1,
                }}
              >
                #{order.order_number ?? order.id.slice(0, 6)}
              </h1>
            </div>

            <section style={detailBlockStyle}>
              <p style={detailLabelStyle}>Customer</p>
              <h2 style={detailHeadingStyle}>
                {order.customer.first_name} {order.customer.last_name ?? ''}
              </h2>
              {order.customer.phone_number ? (
                <a href={`tel:${order.customer.phone_number}`} style={detailLinkStyle}>
                  Call Customer
                </a>
              ) : null}
            </section>

            <section style={detailBlockStyle}>
              <p style={detailLabelStyle}>Delivery Address</p>
              <p style={{ margin: '10px 0 0', fontWeight: 700, lineHeight: 1.45 }}>
                {order.address.full_address}
              </p>
              {order.address.latitude && order.address.longitude ? (
                <a
                  href={`https://yandex.com/maps/?rtext=~${order.address.latitude},${order.address.longitude}&rtt=auto`}
                  rel="noreferrer"
                  target="_blank"
                  style={{ ...detailLinkStyle, marginTop: 16 }}
                >
                  Open Map
                </a>
              ) : null}
            </section>

            <section style={detailBlockStyle}>
              <p style={detailLabelStyle}>Order Items</p>
              <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
                {order.items.map((item, index) => (
                  <p key={item.id ?? `${order.id}-${index}`} style={{ margin: 0 }}>
                    <strong>{item.quantity}x</strong> {item.name ?? 'Item'}
                  </p>
                ))}
              </div>
            </section>

            <StaffPaymentBlock
              amount={order.total_amount}
              language={i18n.language}
              method={order.payment_method}
              status={order.payment_status}
            />

            {error ? <p style={{ margin: 0, color: COLORS.error, fontWeight: 700 }}>{error}</p> : null}
          </main>

          {showTakeButton ? (
            <div style={floatingButtonBar}>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleTakeOrder}
                style={{
                  width: '100%',
                  height: 56,
                  border: 'none',
                  borderRadius: 12,
                  backgroundColor: isSubmitting ? COLORS.surfaceContainerHigh : COLORS.primary,
                  color: isSubmitting ? COLORS.onSurfaceVariant : COLORS.onPrimary,
                  fontFamily: FONTS.headline,
                  fontSize: 17,
                  fontWeight: 800,
                  cursor: isSubmitting ? 'default' : 'pointer',
                }}
              >
                {isSubmitting ? 'Taking...' : 'Take Order'}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </StaffLayout>
  );
}

const detailBlockStyle: CSSProperties = {
  padding: 20,
  borderRadius: 16,
  backgroundColor: COLORS.surfaceContainerLowest,
};

const detailLabelStyle: CSSProperties = {
  margin: 0,
  color: COLORS.secondary,
  fontSize: 12,
  fontWeight: 700,
  textTransform: 'uppercase',
};

const detailHeadingStyle: CSSProperties = {
  margin: '8px 0 0',
  fontFamily: FONTS.headline,
  fontSize: 24,
  fontWeight: 800,
};

const detailLinkStyle: CSSProperties = {
  height: 48,
  borderRadius: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: COLORS.surfaceContainerLow,
  color: COLORS.onSurface,
  textDecoration: 'none',
  fontWeight: 700,
};
