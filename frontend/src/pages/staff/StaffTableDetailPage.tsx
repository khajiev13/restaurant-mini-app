import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams } from 'react-router-dom';
import StaffLayout from '../../components/staff/StaffLayout';
import TableOrderSummary from '../../components/staff/TableOrderSummary';
import { useVisiblePolling } from '../../hooks/useVisiblePolling';
import { getStaffTable } from '../../services/staffTablesApi';
import { useAuthStore } from '../../stores/authStore';
import type { StaffTableDetail } from '../../types/staffTables';
import { formatDateTime, formatPrice } from '../../utils/format';
import '../../staff-tables.css';

const httpStatus = (cause: unknown) =>
  (cause as { response?: { status?: number } } | null)?.response?.status;

const isRoleBoundary = (cause: unknown) => {
  const status = httpStatus(cause);
  return status === 401 || status === 403;
};

const isTransient = (cause: unknown) => {
  const status = httpStatus(cause);
  return status === undefined || status >= 500;
};

interface DetailWorkspaceProps {
  tableId: string | undefined;
  startRoleRefresh: () => Promise<unknown>;
  leaveWorkspace: () => void;
}

function StaffTableDetailWorkspace({
  tableId,
  startRoleRefresh,
  leaveWorkspace,
}: DetailWorkspaceProps) {
  const { t, i18n } = useTranslation();
  const load = useCallback(async () => {
    if (!tableId) {
      throw Object.assign(new Error('Table not found'), { response: { status: 404 } });
    }
    const response = await getStaffTable(tableId);
    return response.data.data;
  }, [tableId]);
  const { data, loading, error, refresh } = useVisiblePolling<StaffTableDetail>(
    load,
    15_000,
    tableId,
  );
  const directRoleBoundary = isRoleBoundary(error);
  const [roleBoundarySeen, setRoleBoundarySeen] = useState(false);
  const roleBoundary = directRoleBoundary || (roleBoundarySeen && error !== null);
  const notFound = httpStatus(error) === 404;
  const canShowCached = data !== null && (error === null || isTransient(error));
  const hasCachedError = data !== null && error !== null && isTransient(error);

  useEffect(() => {
    if (directRoleBoundary) {
      setRoleBoundarySeen(true);
    } else if (error === null) {
      setRoleBoundarySeen(false);
    }
  }, [directRoleBoundary, error]);

  useEffect(() => {
    if (!roleBoundary) return;
    const request = startRoleRefresh();
    let cancelled = false;
    const leave = () => {
      if (!cancelled) leaveWorkspace();
    };
    void request.then(leave, leave);
    return () => { cancelled = true; };
  }, [leaveWorkspace, roleBoundary, startRoleRefresh]);

  useEffect(() => {
    if (error === null) return;
    console.error('staff_tables_workspace_load_failed', {
      status: httpStatus(error) ?? 'network',
    });
  }, [error]);

  const hasFreshnessIssue = Boolean(
    canShowCached
    && (
      hasCachedError
      || data?.freshness.directory_stale
      || data?.freshness.order_status_stale
    ),
  );
  const previousIssue = useRef(false);
  const [announcement, setAnnouncement] = useState('');
  useEffect(() => {
    if (hasFreshnessIssue) {
      setAnnouncement(t(
        'staff_tables.refresh_failed',
        'Could not refresh. Showing cached data.',
      ));
    } else if (previousIssue.current && error === null && data !== null) {
      setAnnouncement(t(
        'staff_tables.freshness_restored',
        'Data is up to date again.',
      ));
    } else if (error !== null || data === null) {
      setAnnouncement('');
    }
    previousIssue.current = hasFreshnessIssue;
  }, [data, error, hasFreshnessIssue, t]);

  const groupedOrders = data ? [
    {
      key: 'synchronized',
      title: t('staff_tables.synchronized_orders', 'Synchronized'),
      orders: data.orders.filter((order) => order.sync_state === 'synchronized'),
    },
    {
      key: 'processing',
      title: t('staff_tables.processing_orders', 'Processing'),
      orders: data.orders.filter((order) => order.sync_state === 'processing'),
    },
    {
      key: 'attention',
      title: t('staff_tables.attention_orders', 'Needs attention'),
      orders: data.orders.filter((order) => order.sync_state === 'attention'),
    },
  ].filter((group) => group.orders.length > 0) : [];

  const formattedTime = (value: string) => (
    <time dateTime={value}>{formatDateTime(value, i18n.language)}</time>
  );

  if (roleBoundary) {
    return (
      <StaffLayout>
        <main className="staff-tables staff-table-detail">
          <div
            className="staff-tables__role-check"
            aria-busy="true"
            aria-label={t('common.loading', 'Loading...')}
          />
        </main>
      </StaffLayout>
    );
  }

  return (
    <StaffLayout>
      <main className="staff-tables staff-table-detail">
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {announcement}
        </div>
        <Link to="/staff/tables" className="staff-table-detail__back">
          {t('staff_tables.back_to_tables', 'Back to tables')}
        </Link>

        {loading && !data ? (
          <div
            className="staff-tables__skeletons"
            aria-busy="true"
            aria-label={t('common.loading', 'Loading...')}
          />
        ) : notFound ? (
          <p>{t('staff_tables.not_found', 'Table not found')}</p>
        ) : error !== null && !canShowCached ? (
          <section className="staff-tables__blocking-error">
            <p>{t('staff_tables.unavailable', 'Tables are temporarily unavailable.')}</p>
            <button type="button" onClick={() => void refresh()}>
              {t('staff_tables.retry', 'Retry')}
            </button>
          </section>
        ) : canShowCached && data ? (
          <>
            <header className="staff-table-detail__header">
              <div>
                <h1>{data.table.table_title || t('staff_tables.unknown_table', 'Unnamed table')}</h1>
                <p>{data.table.hall_title || t('staff_tables.unknown_hall', 'Unnamed hall')}</p>
                <p>
                  {t('staff_tables.service_charge', {
                    percent: data.table.service_percent,
                    defaultValue: '{{percent}}% service',
                  })}
                </p>
              </div>
              {!data.table.is_listed ? (
                <div className="staff-table-detail__unlisted">
                  <strong>{t('staff_tables.unlisted', 'Unlisted tables')}</strong>
                  <p>
                    {t(
                      'staff_tables.unlisted_explanation',
                      'These tables are no longer in the current AliPOS list; saved order details are shown.',
                    )}
                  </p>
                </div>
              ) : null}
              <button type="button" onClick={() => void refresh()}>
                {t('staff_tables.refresh', 'Refresh')}
              </button>
            </header>

            {data.freshness.directory_stale ? (
              <p className="staff-tables__warning">
                {t('staff_tables.directory_stale', 'Table list may be outdated. Last updated:')}{' '}
                {formattedTime(data.freshness.directory_last_success_at)}
              </p>
            ) : null}
            {data.freshness.order_status_stale || hasCachedError ? (
              <p className="staff-tables__warning">
                {hasCachedError ? (
                  <span>
                    {t('staff_tables.refresh_failed', 'Could not refresh. Showing cached data.')}
                  </span>
                ) : null}
                <span>{t('staff_tables.status_stale', 'Order status may be outdated.')}</span>
                {data.freshness.order_status_oldest_success_at ? (
                  <span>
                    {t('staff_tables.last_confirmed', 'Last confirmed:')}{' '}
                    {formattedTime(data.freshness.order_status_oldest_success_at)}
                  </span>
                ) : null}
              </p>
            ) : null}

            <section
              className="staff-table-detail__combined"
              aria-labelledby="staff-table-combined-summary"
            >
              <h2 id="staff-table-combined-summary">
                {t('staff_tables.combined_summary', 'Combined summary')}
              </h2>
              <p>
                {t('staff_tables.mini_app_orders', {
                  count: data.table.synchronized_order_count,
                  defaultValue: '{{count}} mini-app orders',
                })}
              </p>
              <p>
                {data.table.combined_item_count}{' '}
                {t('staff_tables.combined_items', 'Combined items')}
              </p>
              <dl>
                <div>
                  <dt>{t('staff_tables.items_cost', 'Items')}</dt>
                  <dd>{formatPrice(data.table.items_cost, i18n.language)}</dd>
                </div>
                <div>
                  <dt>{t('staff_tables.service_amount', 'Service')}</dt>
                  <dd>{formatPrice(data.table.service_amount, i18n.language)}</dd>
                </div>
                <div>
                  <dt>{t('staff_tables.total_amount', 'Total')}</dt>
                  <dd>{formatPrice(data.table.total_amount, i18n.language)}</dd>
                </div>
              </dl>
              <h2>{t('staff_tables.combined_items', 'Combined items')}</h2>
              <ul className="staff-table-detail__combined-items">
                {data.table.combined_items.map((item, index) => (
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
                    <span>{formatPrice(item.line_total, i18n.language)}</span>
                  </li>
                ))}
              </ul>
            </section>

            <section
              className="staff-table-detail__orders"
              aria-labelledby="staff-table-original-orders"
            >
              <h2 id="staff-table-original-orders">
                {t('staff_tables.original_orders', 'Original orders')}
              </h2>
              {groupedOrders.map((group) => (
                <section key={group.key}>
                  <h3>{group.title}</h3>
                  {group.orders.map((originalOrder) => (
                    <TableOrderSummary key={originalOrder.id} order={originalOrder} />
                  ))}
                </section>
              ))}
            </section>
          </>
        ) : null}
      </main>
    </StaffLayout>
  );
}

export default function StaffTableDetailPage() {
  const { tableId } = useParams();
  const navigate = useNavigate();
  const refreshMe = useAuthStore((state) => state.refreshMe);
  const roleRefreshInFlight = useRef<Promise<unknown> | null>(null);

  const startRoleRefresh = useCallback(() => {
    let request = roleRefreshInFlight.current;
    if (!request) {
      request = refreshMe();
      roleRefreshInFlight.current = request;
      const clearRequest = () => {
        if (roleRefreshInFlight.current === request) {
          roleRefreshInFlight.current = null;
        }
      };
      void request.then(clearRequest, clearRequest);
    }
    return request;
  }, [refreshMe]);
  const leaveWorkspace = useCallback(() => {
    navigate('/', { replace: true });
  }, [navigate]);

  return (
    <StaffTableDetailWorkspace
      key={tableId ?? 'missing-table'}
      tableId={tableId}
      startRoleRefresh={startRoleRefresh}
      leaveWorkspace={leaveWorkspace}
    />
  );
}
