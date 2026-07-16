export type TableWorkspaceView = 'tables' | 'menu';

export default function TableWorkspaceToggle({
  view,
  onChange,
  labels,
}: {
  view: TableWorkspaceView;
  onChange: (view: TableWorkspaceView) => void;
  labels: { group: string; tables: string; menu: string };
}) {
  return (
    <div role="group" aria-label={labels.group} className="staff-tables__toggle">
      {(['tables', 'menu'] as const).map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={view === value}
          onClick={() => onChange(value)}
        >
          {labels[value]}
        </button>
      ))}
    </div>
  );
}
