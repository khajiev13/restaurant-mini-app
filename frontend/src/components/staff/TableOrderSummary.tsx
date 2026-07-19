import { useTranslation } from 'react-i18next';
import type { StaffTableOrder, StaffTableSyncState } from '../../types/staffTables';
import { formatDateTime, formatPrice } from '../../utils/format';
import { Icon } from '../artisan/ArtisanLayout';

const safeSyncState = (state: string): StaffTableSyncState => {
  if (state === 'synchronized' || state === 'processing' || state === 'attention') {
    return state;
  }
  return 'attention';
};

export default function TableOrderSummary({ order }: { order: StaffTableOrder }) {
  const { t, i18n } = useTranslation();
  const activeCopy = order.status === 'PAID_AWAITING_RESTAURANT' || order.status === 'NEW'
    ? t('status.placed', 'Placed')
    : order.status === 'ACCEPTED_BY_RESTAURANT'
      ? t('status.preparing', 'Preparing')
      : order.status === 'READY'
        ? t('status.ready', 'Ready')
        : t('staff_tables.active', 'Active');
  const statusCopy = order.sync_label === 'verify_in_pos'
    ? t('staff_tables.verify_pos', 'Verify in POS')
    : order.sync_label === 'not_synchronized'
      ? t('staff_tables.not_synchronized', 'Not synchronized')
      : order.sync_label === 'processing'
        ? t('staff_tables.processing', 'Processing')
        : order.sync_label === 'synchronized'
          ? activeCopy
          : t('staff_tables.active', 'Active');
  const paymentStatusCopy = order.payment_status === 'paid'
    ? t('staff_tables.payment_paid', 'Paid')
    : order.payment_status === 'refund_pending'
      ? t('staff_tables.payment_refund_pending', 'Refund pending')
      : order.payment_status === 'refund_verification_required'
        ? t('staff_tables.payment_refund_verification_required', 'Refund verification required')
        : order.payment_status === 'refund_failed'
          ? t('staff_tables.payment_refund_failed', 'Refund failed')
          : t('staff_tables.payment_unknown', 'Payment status unknown');
  const paymentCopy = order.payment_method === 'cash'
    ? t('staff_tables.payment_cash', 'Cash')
    : `${t('staff_tables.payment_online', 'Online')} · ${paymentStatusCopy}`;
  const stateIcon = order.sync_label === 'processing'
    ? 'hourglass_top'
    : order.sync_label === 'synchronized'
      ? 'check_circle'
      : 'warning';
  const state = safeSyncState(order.sync_state);

  return (
    <article className={`staff-table-order staff-table-order--${state}`}>
      <header>
        <strong>
          {order.order_number ? `#${order.order_number}` : t('staff_tables.order', 'Order')}
        </strong>
        <span className="staff-table-order__state">
          <span aria-hidden="true"><Icon name={stateIcon} /></span>
          {statusCopy}
        </span>
      </header>
      <p>
        <time dateTime={order.created_at}>
          {formatDateTime(order.created_at, i18n.language)}
        </time>
        {' · '}
        {paymentCopy}
      </p>
      <ul className="staff-table-order__items">
        {order.items.map((item, index) => {
          const lineTotal = item.price * item.quantity + item.modifications.reduce(
            (sum, modifier) => sum + modifier.price * modifier.quantity,
            0,
          );
          return (
            <li key={`${item.id}-${item.price}-${index}`}>
              <span>
                {item.name || t('staff_tables.unknown_item', 'Item')} × {item.quantity}
              </span>
              {item.modifications.length > 0 ? (
                <ul aria-label={t('staff_tables.modifiers', 'Modifiers')}>
                  {item.modifications.map((modifier, modifierIndex) => (
                    <li key={`${modifier.id}-${modifier.price}-${modifierIndex}`}>
                      {modifier.name || t('staff_tables.modifiers', 'Modifiers')} × {modifier.quantity}
                    </li>
                  ))}
                </ul>
              ) : null}
              <span>{formatPrice(lineTotal, i18n.language)}</span>
            </li>
          );
        })}
      </ul>
      <dl className="staff-table-order__totals">
        <div>
          <dt>{t('staff_tables.items_cost', 'Items')}</dt>
          <dd>{formatPrice(order.items_cost, i18n.language)}</dd>
        </div>
        <div>
          <dt>{t('staff_tables.service_amount', 'Service')}</dt>
          <dd>{formatPrice(order.service_amount, i18n.language)}</dd>
        </div>
        <div>
          <dt>{t('staff_tables.total_amount', 'Total')}</dt>
          <dd>{formatPrice(order.total_amount, i18n.language)}</dd>
        </div>
      </dl>
    </article>
  );
}
