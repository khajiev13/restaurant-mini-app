import { useId } from 'react';
import type { StaffHall, StaffTableSummary } from '../../types/staffTables';
import TableInspectionCard, { type TableInspectionCardLabels } from './TableInspectionCard';

export interface TableHallSectionLabels extends TableInspectionCardLabels {
  unlisted: string;
  unlistedExplanation: string;
  unknownHall: string;
  serviceCharge: (percent: number) => string;
}

const naturalTableSort = (left: StaffTableSummary, right: StaffTableSummary) =>
  left.table_title.localeCompare(right.table_title, undefined, {
    numeric: true,
    sensitivity: 'base',
  });

export default function TableHallSection({
  hall,
  language,
  labels,
}: {
  hall: StaffHall;
  language: string;
  labels: TableHallSectionLabels;
}) {
  const headingId = useId();
  const title = hall.is_listed
    ? hall.hall_title || labels.unknownHall
    : labels.unlisted;

  return (
    <section className="staff-tables__hall" aria-labelledby={headingId}>
      <div className="staff-tables__hall-heading">
        <h2 id={headingId}>{title}</h2>
        {hall.service_percent !== null ? (
          <span>{labels.serviceCharge(hall.service_percent)}</span>
        ) : null}
      </div>
      {!hall.is_listed ? (
        <p className="staff-tables__unlisted-explanation">{labels.unlistedExplanation}</p>
      ) : null}
      <div className="staff-tables__grid">
        {hall.tables.slice().sort(naturalTableSort).map((table) => (
          <TableInspectionCard
            key={table.table_id}
            table={table}
            language={language}
            labels={labels}
          />
        ))}
      </div>
    </section>
  );
}
