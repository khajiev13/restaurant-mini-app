import { Link } from 'react-router-dom';
import type { StaffTableSummary } from '../../types/staffTables';
import { formatPrice } from '../../utils/format';
import { Icon } from '../artisan/ArtisanLayout';

export interface TableInspectionCardLabels {
  details: (title: string) => string;
  unknownTable: string;
  unknownItem: string;
  noOrders: string;
  miniAppOrders: (count: number) => string;
  moreItems: (count: number) => string;
  processing: (count: number) => string;
  attention: (count: number) => string;
}

export default function TableInspectionCard({
  table,
  language,
  labels,
}: {
  table: StaffTableSummary;
  language: string;
  labels: TableInspectionCardLabels;
}) {
  const title = table.table_title || labels.unknownTable;
  const activityCount = table.synchronized_order_count
    + table.processing_order_count
    + table.attention_order_count;
  const remainingLines = Math.max(
    0,
    table.combined_line_count - table.combined_items.length,
  );

  return (
    <Link
      to={`/staff/tables/${table.table_id}`}
      className={`staff-table-card ${table.synchronized_order_count > 0 ? 'staff-table-card--active' : ''}`}
      aria-label={labels.details(title)}
    >
      <h3>{title}</h3>
      {activityCount === 0 ? (
        <p className="staff-table-card__neutral">{labels.noOrders}</p>
      ) : (
        <>
          {table.synchronized_order_count > 0 ? (
            <>
              <p>{labels.miniAppOrders(table.synchronized_order_count)}</p>
              <ul>
                {table.combined_items.map((item) => (
                  <li key={`${item.id}-${item.price}-${JSON.stringify(item.modifications)}`}>
                    {item.name || labels.unknownItem} × {item.quantity}
                  </li>
                ))}
              </ul>
              {remainingLines > 0 ? <p>{labels.moreItems(remainingLines)}</p> : null}
              <strong>{formatPrice(table.total_amount, language)}</strong>
            </>
          ) : null}
          <div className="staff-table-card__states">
            {table.processing_order_count > 0 ? (
              <span>
                <span aria-hidden="true"><Icon name="hourglass_top" /></span>
                {labels.processing(table.processing_order_count)}
              </span>
            ) : null}
            {table.attention_order_count > 0 ? (
              <span>
                <span aria-hidden="true"><Icon name="warning" /></span>
                {labels.attention(table.attention_order_count)}
              </span>
            ) : null}
          </div>
        </>
      )}
    </Link>
  );
}
