import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import MenuCatalog from '../../components/menu/MenuCatalog';
import StaffLayout from '../../components/staff/StaffLayout';
import TableHallSection from '../../components/staff/TableHallSection';
import TableWorkspaceToggle, { type TableWorkspaceView } from '../../components/staff/TableWorkspaceToggle';
import { useVisiblePolling } from '../../hooks/useVisiblePolling';
import { getStaffTables } from '../../services/staffTablesApi';
import { useAuthStore } from '../../stores/authStore';
import { useMenuStore } from '../../stores/menuStore';
import { formatDateTime } from '../../utils/format';
import '../../staff-tables.css';

type TableFilter = 'all' | 'active' | 'attention';

const httpStatus = (cause: unknown) =>
  (cause as { response?: { status?: number } } | null)?.response?.status;

const isRoleBoundary = (cause: unknown) => {
  const status = httpStatus(cause);
  return status === 401 || status === 403;
};

const buildTableLabels = (t: TFunction) => ({
  details: (title: string) => `${t('staff_tables.view_details', 'View table details:')} ${title}`,
  unknownTable: t('staff_tables.unknown_table', 'Unnamed table'),
  unknownHall: t('staff_tables.unknown_hall', 'Unnamed hall'),
  unknownItem: t('staff_tables.unknown_item', 'Item'),
  noOrders: t('staff_tables.no_orders', 'No mini-app orders'),
  miniAppOrders: (count: number) => t('staff_tables.mini_app_orders', {
    count,
    defaultValue: '{{count}} mini-app orders',
  }),
  moreItems: (count: number) => t('staff_tables.more_items', {
    count,
    defaultValue: '+{{count}} more',
  }),
  processing: (count: number) => t('staff_tables.processing_count', {
    count,
    defaultValue: '{{count}} processing',
  }),
  attention: (count: number) => t('staff_tables.attention_count', {
    count,
    defaultValue: '{{count}} need attention',
  }),
  unlisted: t('staff_tables.unlisted', 'Unlisted tables'),
  unlistedExplanation: t(
    'staff_tables.unlisted_explanation',
    'These tables are no longer in the current AliPOS list; saved order details are shown.',
  ),
  serviceCharge: (percent: number) => t('staff_tables.service_charge', {
    percent,
    defaultValue: '{{percent}}% service',
  }),
});

export default function StaffTablesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const view: TableWorkspaceView = searchParams.get('view') === 'menu' ? 'menu' : 'tables';
  const filter = ['active', 'attention'].includes(searchParams.get('filter') ?? '')
    ? (searchParams.get('filter') as TableFilter)
    : 'all';
  const load = useCallback(
    () => getStaffTables().then((response) => response.data.data),
    [],
  );
  const { data, loading, error, refresh } = useVisiblePolling(
    load,
    15_000,
    'staff-tables',
  );
  const refreshMe = useAuthStore((state) => state.refreshMe);
  const menu = useMenuStore((state) => state.menu);
  const menuLoading = useMenuStore((state) => state.loading);
  const menuError = useMenuStore((state) => state.error);
  const fetchMenu = useMenuStore((state) => state.fetchMenu);
  const retryMenu = useMenuStore((state) => state.retry);
  const menuFetchStarted = useRef(false);
  const roleRefreshInFlight = useRef<Promise<unknown> | null>(null);
  const roleBoundary = isRoleBoundary(error);

  const setParam = (key: 'view' | 'filter', value: string) => {
    const params = new URLSearchParams(searchParams);
    params.set(key, value);
    setSearchParams(params);
  };
  const setView = (next: TableWorkspaceView) => setParam('view', next);
  const setFilter = (next: TableFilter) => setParam('filter', next);

  const filteredHalls = useMemo(() => (data?.halls ?? [])
    .map((hall) => ({
      ...hall,
      tables: hall.tables.filter((table) => {
        const hasAnyOrder = table.synchronized_order_count
          + table.processing_order_count
          + table.attention_order_count > 0;
        if (filter === 'active') return hasAnyOrder;
        if (filter === 'attention') return table.attention_order_count > 0;
        return true;
      }),
    }))
    .filter((hall) => hall.tables.length > 0), [data?.halls, filter]);
  const directoryTableCount = useMemo(
    () => (data?.halls ?? []).reduce((sum, hall) => sum + hall.tables.length, 0),
    [data?.halls],
  );
  const hasCachedError = error !== null && data !== null && !roleBoundary;

  useEffect(() => {
    if (view !== 'menu' || menuFetchStarted.current) return;
    menuFetchStarted.current = true;
    void fetchMenu();
  }, [fetchMenu, view]);

  useEffect(() => {
    if (!roleBoundary) return;
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
    let cancelled = false;
    const leaveWorkspace = () => {
      if (!cancelled) navigate('/', { replace: true });
    };
    void request.then(leaveWorkspace, leaveWorkspace);
    return () => { cancelled = true; };
  }, [navigate, refreshMe, roleBoundary]);

  useEffect(() => {
    if (error === null) return;
    console.error('staff_tables_workspace_load_failed', {
      status: httpStatus(error) ?? 'network',
    });
  }, [error]);

  const hasFreshnessIssue = Boolean(
    hasCachedError
    || data?.freshness.directory_stale
    || data?.freshness.order_status_stale,
  );
  const previousIssue = useRef(false);
  const [announcement, setAnnouncement] = useState('');
  useEffect(() => {
    if (hasFreshnessIssue) {
      setAnnouncement(t(
        'staff_tables.refresh_failed',
        'Could not refresh. Showing cached data.',
      ));
    } else if (previousIssue.current) {
      setAnnouncement(t(
        'staff_tables.freshness_restored',
        'Data is up to date again.',
      ));
    }
    previousIssue.current = hasFreshnessIssue;
  }, [hasFreshnessIssue, t]);

  if (roleBoundary) {
    return (
      <StaffLayout>
        <main className="staff-tables">
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
      <main className="staff-tables">
        <h1>{t('staff_tables.title', 'Tables')}</h1>
        <TableWorkspaceToggle
          view={view}
          onChange={setView}
          labels={{
            group: t('staff_tables.workspace', 'Table workspace'),
            tables: t('staff_tables.tables', 'Tables'),
            menu: t('staff_tables.menu', 'Menu'),
          }}
        />
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {announcement}
        </div>

        {view === 'tables' ? (
          <>
            <div className="staff-tables__refresh-row">
              {data ? (
                <span>
                  {t('staff_tables.updated', 'Updated')}{' '}
                  {formatDateTime(data.freshness.generated_at, i18n.language)}
                </span>
              ) : null}
              <button type="button" onClick={() => void refresh()}>
                {t('staff_tables.refresh', 'Refresh')}
              </button>
            </div>
            {data?.freshness.directory_stale ? (
              <p className="staff-tables__warning">
                {t('staff_tables.directory_stale', 'Table list may be outdated. Last updated:')}{' '}
                {formatDateTime(data.freshness.directory_last_success_at, i18n.language)}
              </p>
            ) : null}
            {data?.freshness.order_status_stale || hasCachedError ? (
              <p className="staff-tables__warning">
                {hasCachedError ? (
                  <span>{t('staff_tables.refresh_failed', 'Could not refresh. Showing cached data.')}</span>
                ) : null}
                <span>{t('staff_tables.status_stale', 'Order status may be outdated.')}</span>
                {data?.freshness.order_status_oldest_success_at ? (
                  <span>
                    {t('staff_tables.last_confirmed', 'Last confirmed:')}{' '}
                    {formatDateTime(data.freshness.order_status_oldest_success_at, i18n.language)}
                  </span>
                ) : null}
              </p>
            ) : null}
            {loading && !data ? (
              <div
                className="staff-tables__skeletons"
                aria-busy="true"
                aria-label={t('common.loading', 'Loading...')}
              />
            ) : error !== null && !data ? (
              <section className="staff-tables__blocking-error">
                <p>{t('staff_tables.unavailable', 'Tables are temporarily unavailable.')}</p>
                <button type="button" onClick={() => void refresh()}>
                  {t('staff_tables.retry', 'Retry')}
                </button>
              </section>
            ) : data && directoryTableCount === 0 ? (
              <section className="staff-tables__empty">
                <p>{t('staff_tables.empty_directory', 'AliPOS returned no tables.')}</p>
                <button type="button" onClick={() => void refresh()}>
                  {t('staff_tables.retry', 'Retry')}
                </button>
              </section>
            ) : data ? (
              <>
                <div
                  role="group"
                  aria-label={t('staff_tables.filters', 'Table filters')}
                  className="staff-tables__filters"
                >
                  {(['all', 'active', 'attention'] as const).map((value) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={filter === value}
                      onClick={() => setFilter(value)}
                    >
                      {value === 'all'
                        ? t('staff_tables.all', 'All')
                        : value === 'active'
                          ? t('staff_tables.with_orders', 'With orders')
                          : t('staff_tables.attention', 'Attention')}
                    </button>
                  ))}
                </div>
                {filteredHalls.length === 0 ? (
                  <p>{t('staff_tables.no_filter_results', 'No tables match this filter.')}</p>
                ) : filteredHalls.map((hall) => (
                  <TableHallSection
                    key={hall.hall_id ?? 'unlisted'}
                    hall={hall}
                    language={i18n.language}
                    labels={buildTableLabels(t)}
                  />
                ))}
              </>
            ) : null}
          </>
        ) : (
          <>
            <div role="note" className="staff-tables__browse-note">
              {t('staff_tables.browse_only', 'Browse only · Orders cannot be placed here')}
            </div>
            {menu ? (
              <MenuCatalog
                menu={menu}
                language={i18n.language}
                mode="browse"
                labels={{
                  soldOut: t('menu.sold_out', 'Sold out'),
                  add: t('menu.add', 'Add'),
                  remove: t('menu.remove', 'Remove'),
                  limit: t('menu.limit', 'Available quantity is already in the cart'),
                  empty: t('menu.empty', 'No menu items'),
                }}
              />
            ) : menuError ? (
              <button type="button" onClick={() => void retryMenu()}>
                {t('staff_tables.retry', 'Retry')}
              </button>
            ) : (
              <div aria-busy={menuLoading}>{t('common.loading', 'Loading...')}</div>
            )}
          </>
        )}
      </main>
    </StaffLayout>
  );
}
