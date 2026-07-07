import { COLORS, FONTS } from '../artisan/ArtisanLayout';

export type StaffOrderTab = 'available' | 'active' | 'completed';

const tabList: ReadonlyArray<{ key: StaffOrderTab; label: string }> = [
  { key: 'available', label: 'Available' },
  { key: 'active', label: 'Active' },
  { key: 'completed', label: 'Completed' },
];

export default function StaffOrderTabs({
  active,
  onChange,
}: {
  active: StaffOrderTab;
  onChange: (tab: StaffOrderTab) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Staff orders"
      style={{
        margin: '0 20px 24px',
        padding: 4,
        display: 'grid',
        gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
        gap: 4,
        borderRadius: 14,
        backgroundColor: COLORS.surfaceContainerLow,
      }}
    >
      {tabList.map((tab) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(tab.key)}
            style={{
              height: 44,
              border: 'none',
              borderRadius: 10,
              backgroundColor: selected ? COLORS.surfaceContainerLowest : 'transparent',
              color: selected ? COLORS.primary : COLORS.onSurfaceVariant,
              fontFamily: FONTS.body,
              fontSize: 15,
              fontWeight: 700,
              cursor: 'pointer',
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
