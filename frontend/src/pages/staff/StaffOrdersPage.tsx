import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import ConfirmDeliveredSheet from '../../components/staff/ConfirmDeliveredSheet';
import StaffLayout from '../../components/staff/StaffLayout';
import StaffOrderCard from '../../components/staff/StaffOrderCard';
import StaffOrderTabs, { type StaffOrderTab } from '../../components/staff/StaffOrderTabs';
import StaffPaymentBlock from '../../components/staff/StaffPaymentBlock';
import {
  getActiveStaffOrder,
  getAvailableStaffOrders,
  getCompletedStaffOrders,
  isStaffOrderTakeTransportAmbiguity,
  markStaffOrderDelivered,
  reconcileStaffOrderTake,
  takeStaffOrder,
} from '../../services/staffApi';
import type { StaffOrder } from '../../types/staff';

const validTabs: ReadonlyArray<StaffOrderTab> = ['available', 'active', 'completed'];
const ACTIVE_ORDER_CONFLICT = 'Finish your active delivery before taking another order.';
const TAKE_ORDER_RECONCILIATION_ERROR = 'Could not refresh order status. Try again.';
const TAKE_ORDER_ERROR_DETAILS = new Set([
  ACTIVE_ORDER_CONFLICT,
  'This order was already taken by another staff member.',
  'This order is no longer available.',
  'This order is not ready for delivery payment handling.',
  TAKE_ORDER_RECONCILIATION_ERROR,
]);

function getTakeOrderError(error: unknown): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === 'string' && TAKE_ORDER_ERROR_DETAILS.has(detail)) {
      return detail;
    }
  }

  return 'This order is no longer available.';
}

export default function StaffOrdersPage() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const activeTab: StaffOrderTab = validTabs.includes(tabParam as StaffOrderTab)
    ? (tabParam as StaffOrderTab)
    : 'available';

  const [availableOrders, setAvailableOrders] = useState<StaffOrder[]>([]);
  const [activeOrder, setActiveOrder] = useState<StaffOrder | null>(null);
  const [completedOrders, setCompletedOrders] = useState<StaffOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);
  const [confirmingOrder, setConfirmingOrder] = useState<StaffOrder | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const takeReconciliationControllerRef = useRef<AbortController | null>(null);
  const loadErrorMessage = t('staff.orders.load_error', 'Could not load staff orders. Try again.');

  const loadOrders = useCallback(async () => {
    setIsLoading(true);
    setPageError(null);
    try {
      const [availableResponse, activeResponse, completedResponse] = await Promise.all([
        getAvailableStaffOrders(),
        getActiveStaffOrder(),
        getCompletedStaffOrders(),
      ]);

      setAvailableOrders(availableResponse.data.data ?? []);
      setActiveOrder(activeResponse.data.data ?? null);
      setCompletedOrders(completedResponse.data.data ?? []);
    } catch {
      setPageError(loadErrorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [loadErrorMessage]);

  useEffect(() => {
    void loadOrders();
  }, [loadOrders]);

  useEffect(() => () => {
    takeReconciliationControllerRef.current?.abort();
  }, []);

  const setTab = (tab: StaffOrderTab) => {
    setSearchParams({ tab }, { replace: true });
  };

  const handleTakeOrder = async (order: StaffOrder) => {
    if (activeOrder) {
      setTab('active');
      return;
    }

    takeReconciliationControllerRef.current?.abort();
    const reconciliationController = new AbortController();
    takeReconciliationControllerRef.current = reconciliationController;
    setActionError(null);
    setPageError(null);
    const mutationStartedAt = Date.now();
    try {
      await takeStaffOrder(order.id);
      await loadOrders();
      setTab('active');
    } catch (error) {
      if (isStaffOrderTakeTransportAmbiguity(error)) {
        try {
          const result = await reconcileStaffOrderTake(
            order.id,
            mutationStartedAt,
            reconciliationController.signal,
          );
          if (reconciliationController.signal.aborted) {
            return;
          }

          if (result.outcome === 'same') {
            setActiveOrder(result.order);
            setTab('active');
            return;
          }

          if (result.outcome === 'different') {
            setActiveOrder(result.order);
            setActionError(ACTIVE_ORDER_CONFLICT);
            setTab('active');
            return;
          }

          setActionError(TAKE_ORDER_RECONCILIATION_ERROR);
        } catch {
          if (!reconciliationController.signal.aborted) {
            setActionError(TAKE_ORDER_RECONCILIATION_ERROR);
          }
        }
        return;
      }

      const nextError = getTakeOrderError(error);
      setActionError(nextError);
      await loadOrders();
      if (!reconciliationController.signal.aborted) {
        setActionError(nextError);
      }
    } finally {
      if (takeReconciliationControllerRef.current === reconciliationController) {
        takeReconciliationControllerRef.current = null;
      }
    }
  };

  const handleConfirmDelivered = async () => {
    if (!confirmingOrder) {
      return;
    }

    setIsSubmitting(true);
    setDeliveryError(null);
    try {
      await markStaffOrderDelivered(confirmingOrder.id);
      setConfirmingOrder(null);
      await loadOrders();
      setTab('completed');
    } catch {
      setDeliveryError(t('staff.orders.delivered_error', 'Could not mark the order delivered. Try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <StaffLayout>
      <StaffOrderTabs active={activeTab} onChange={setTab} />

      {actionError || pageError ? (
        <p style={{ margin: '0 20px 16px', color: COLORS.error, fontWeight: 700 }}>
          {actionError ?? pageError}
        </p>
      ) : null}

      {isLoading ? (
        <p style={{ margin: '0 20px', color: COLORS.secondary }}>
          {t('staff.orders.loading', 'Loading orders...')}
        </p>
      ) : null}

      {!isLoading && activeTab === 'available' ? (
        availableOrders.length > 0 ? (
          availableOrders.map((order) => (
            <StaffOrderCard
              key={order.id}
              disabled={!!activeOrder}
              language={i18n.language}
              mode="available"
              onTake={handleTakeOrder}
              order={order}
            />
          ))
        ) : (
          <EmptyState
            actionLabel={t('staff.orders.refresh', 'Refresh')}
            icon="receipt_long"
            onAction={() => void loadOrders()}
            title={t('staff.orders.available_empty', 'No delivery orders available')}
          />
        )
      ) : null}

      {!isLoading && activeTab === 'active' ? (
        activeOrder ? (
          <main style={{ padding: '0 20px 8px' }}>
            <p
              style={{
                margin: 0,
                color: COLORS.primary,
                fontSize: 12,
                fontWeight: 700,
                textTransform: 'uppercase',
              }}
            >
              {t('staff.orders.active_label', 'Active Delivery')}
            </p>
            <h1
              style={{
                margin: '8px 0 20px',
                fontFamily: FONTS.headline,
                fontSize: 34,
                fontWeight: 800,
                lineHeight: 1.15,
              }}
            >
              #{activeOrder.order_number ?? activeOrder.id.slice(0, 6)}
            </h1>

            <section
              style={{
                padding: 20,
                borderRadius: 16,
                backgroundColor: COLORS.surfaceContainerLowest,
              }}
            >
              <p style={{ margin: 0, color: COLORS.secondary, textTransform: 'uppercase', fontSize: 12, fontWeight: 700 }}>
                Customer
              </p>
              <h2
                style={{
                  margin: '8px 0 4px',
                  fontFamily: FONTS.headline,
                  fontSize: 24,
                  fontWeight: 800,
                }}
              >
                {activeOrder.customer.first_name} {activeOrder.customer.last_name ?? ''}
              </h2>
              {activeOrder.customer.phone_number ? (
                <a
                  href={`tel:${activeOrder.customer.phone_number}`}
                  style={actionLinkStyle}
                >
                  Call Customer
                </a>
              ) : null}
              <p style={{ margin: '16px 0 0', color: COLORS.onSurfaceVariant }}>
                {activeOrder.address.full_address}
              </p>
              {activeOrder.address.latitude && activeOrder.address.longitude ? (
                <a
                  href={`https://yandex.com/maps/?rtext=~${activeOrder.address.latitude},${activeOrder.address.longitude}&rtt=auto`}
                  rel="noreferrer"
                  target="_blank"
                  style={{ ...actionLinkStyle, marginTop: 12 }}
                >
                  Open Map
                </a>
              ) : null}
            </section>

            <section
              style={{
                marginTop: 16,
                padding: 20,
                borderRadius: 16,
                backgroundColor: COLORS.surfaceContainerLowest,
              }}
            >
              <p style={{ margin: 0, color: COLORS.secondary, textTransform: 'uppercase', fontSize: 12, fontWeight: 700 }}>
                Order Items
              </p>
              <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                {activeOrder.items.map((item, index) => (
                  <p key={item.id ?? `${activeOrder.id}-${index}`} style={{ margin: 0 }}>
                    <strong>{item.quantity}x</strong> {item.name ?? 'Item'}
                  </p>
                ))}
              </div>
            </section>

            <div style={{ marginTop: 16 }}>
              <StaffPaymentBlock
                amount={activeOrder.total_amount}
                language={i18n.language}
                method={activeOrder.payment_method}
                status={activeOrder.payment_status}
              />
            </div>

            <button
              type="button"
              onClick={() => {
                setDeliveryError(null);
                setConfirmingOrder(activeOrder);
              }}
              style={{
                width: '100%',
                height: 56,
                marginTop: 20,
                border: 'none',
                borderRadius: 12,
                backgroundColor: COLORS.primary,
                color: COLORS.onPrimary,
                fontFamily: FONTS.headline,
                fontSize: 17,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              Mark Delivered
            </button>
          </main>
        ) : (
          <EmptyState
            actionLabel={t('staff.orders.view_available', 'View Available')}
            icon="local_shipping"
            onAction={() => setTab('available')}
            title={t('staff.orders.active_empty', 'No active delivery')}
          />
        )
      ) : null}

      {!isLoading && activeTab === 'completed' ? (
        completedOrders.length > 0 ? (
          completedOrders.map((order) => (
            <StaffOrderCard
              key={order.id}
              language={i18n.language}
              mode="completed"
              order={order}
            />
          ))
        ) : (
          <EmptyState
            icon="done_all"
            title={t('staff.orders.completed_empty', 'No completed deliveries yet')}
          />
        )
      ) : null}

      {confirmingOrder ? (
        <ConfirmDeliveredSheet
          error={deliveryError}
          language={i18n.language}
          onCancel={() => {
            setDeliveryError(null);
            setConfirmingOrder(null);
          }}
          onConfirm={handleConfirmDelivered}
          order={confirmingOrder}
          submitting={isSubmitting}
        />
      ) : null}
    </StaffLayout>
  );
}

function EmptyState({
  actionLabel,
  icon,
  onAction,
  title,
}: {
  actionLabel?: string;
  icon: string;
  onAction?: () => void;
  title: string;
}) {
  return (
    <section style={{ padding: '64px 20px', textAlign: 'center' }}>
      <div
        aria-hidden="true"
        style={{
          width: 56,
          height: 56,
          margin: '0 auto',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: COLORS.surfaceContainerLow,
          color: COLORS.outline,
        }}
      >
        <Icon name={icon} />
      </div>
      <h2
        style={{
          margin: '16px 0 0',
          fontFamily: FONTS.headline,
          fontSize: 24,
          fontWeight: 800,
        }}
      >
        {title}
      </h2>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          style={{
            height: 48,
            marginTop: 20,
            padding: '0 20px',
            border: 'none',
            borderRadius: 12,
            backgroundColor: COLORS.primary,
            color: COLORS.onPrimary,
            fontWeight: 800,
            cursor: 'pointer',
          }}
        >
          {actionLabel}
        </button>
      ) : null}
    </section>
  );
}

const actionLinkStyle: CSSProperties = {
  height: 48,
  marginTop: 14,
  borderRadius: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  backgroundColor: COLORS.surfaceContainerLow,
  color: COLORS.onSurface,
  textDecoration: 'none',
  fontWeight: 700,
};
