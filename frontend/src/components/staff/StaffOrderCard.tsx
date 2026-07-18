import { useNavigate } from 'react-router-dom';
import type { StaffOrder } from '../../types/staff';
import { formatDateTime, formatPrice } from '../../utils/format';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';

function getItemSummary(order: StaffOrder): string {
  return order.items
    .map((item) => `${item.quantity}x ${item.name ?? 'Item'}`)
    .join(', ');
}

function getDeliveryDuration(order: StaffOrder): string | null {
  if (!order.assigned_at || !order.delivered_at) {
    return null;
  }

  const assignedAt = new Date(order.assigned_at).getTime();
  const deliveredAt = new Date(order.delivered_at).getTime();
  if (!Number.isFinite(assignedAt) || !Number.isFinite(deliveredAt) || deliveredAt < assignedAt) {
    return null;
  }

  const totalMinutes = Math.max(1, Math.round((deliveredAt - assignedAt) / 60000));
  if (totalMinutes < 60) {
    return `${totalMinutes} min`;
  }

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
}

export default function StaffOrderCard({
  disabled = false,
  language,
  mode,
  onTake,
  order,
}: {
  disabled?: boolean;
  language: string;
  mode: 'available' | 'completed';
  onTake?: (order: StaffOrder) => void;
  order: StaffOrder;
}) {
  const navigate = useNavigate();
  const cashOrder = order.payment_method === 'cash';
  const canOpenOrder = mode !== 'available' || !disabled;
  const deliveryDuration = getDeliveryDuration(order);

  return (
    <article
      onClick={() => {
        if (canOpenOrder) {
          navigate(`/staff/orders/${order.id}`);
        }
      }}
      style={{
        margin: '0 20px 16px',
        padding: 18,
        borderRadius: 16,
        backgroundColor: COLORS.surfaceContainerLowest,
        boxShadow: '0 12px 32px rgba(45, 47, 47, 0.08)',
        cursor: canOpenOrder ? 'pointer' : 'default',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <p
            style={{
              margin: 0,
              color: COLORS.secondary,
              fontSize: 12,
              fontWeight: 700,
              textTransform: 'uppercase',
            }}
          >
            Order
          </p>
          <h2
            style={{
              margin: '6px 0 0',
              fontFamily: FONTS.headline,
              fontSize: 24,
              fontWeight: 800,
              lineHeight: 1.2,
            }}
          >
            #{order.order_number ?? order.id.slice(0, 6)}
          </h2>
        </div>
        <strong
          style={{
            flexShrink: 0,
            fontFamily: FONTS.headline,
            fontSize: 20,
            fontWeight: 800,
            color: COLORS.primary,
          }}
        >
          {formatPrice(order.total_amount, language)}
        </strong>
      </div>

      <div
        style={{
          marginTop: 18,
          padding: 14,
          borderRadius: 12,
          backgroundColor: COLORS.surfaceContainerLow,
        }}
      >
        <p style={{ margin: 0, fontWeight: 800 }}>
          {order.customer.first_name} {order.customer.last_name ?? ''}
        </p>
        <p style={{ margin: '8px 0 0', color: COLORS.onSurfaceVariant }}>{order.address.full_address}</p>
      </div>

      <p style={{ margin: '16px 0 6px', color: COLORS.onSurfaceVariant }}>{getItemSummary(order)}</p>
      <p
        style={{
          margin: 0,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          color: cashOrder ? COLORS.onSurface : '#833e9a',
          fontWeight: 700,
        }}
      >
        <Icon name={cashOrder ? 'payments' : 'credit_card'} size={18} />
        {cashOrder ? 'Cash on Delivery' : 'Paid Online'}
      </p>

      {mode === 'available' ? (
        <button
          type="button"
          disabled={disabled}
          onClick={(event) => {
            event.stopPropagation();
            onTake?.(order);
          }}
          style={{
            width: '100%',
            height: 54,
            marginTop: 18,
            border: 'none',
            borderRadius: 12,
            backgroundColor: disabled ? COLORS.surfaceContainerHigh : COLORS.primary,
            color: disabled ? COLORS.onSurfaceVariant : COLORS.onPrimary,
            fontFamily: FONTS.headline,
            fontSize: 16,
            fontWeight: 800,
            cursor: disabled ? 'default' : 'pointer',
          }}
        >
          {disabled ? 'Active Delivery In Progress' : 'Take Order'}
        </button>
      ) : null}

      {mode === 'completed' && order.delivered_at ? (
        <div style={{ display: 'grid', gap: 4, marginTop: 14 }}>
          <p style={{ margin: 0, color: COLORS.secondary }}>
            Delivered {formatDateTime(order.delivered_at, language)}
          </p>
          {deliveryDuration ? (
            <p style={{ margin: 0, color: COLORS.onSurfaceVariant, fontWeight: 700 }}>
              Delivery time {deliveryDuration}
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
