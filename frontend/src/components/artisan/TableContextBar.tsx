import { useTranslation } from 'react-i18next';
import type { TableContext } from '../../stores/tableOrderStore';
import { COLORS, FONTS, Icon } from './ArtisanLayout';

export default function TableContextBar({
  context,
  onChange,
}: {
  context: TableContext | null;
  onChange: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div
      style={{
        minHeight: 52,
        padding: '6px 12px',
        boxSizing: 'border-box',
        background: '#fff7ed',
        borderBottom: '1px solid rgba(163, 56, 0, 0.12)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        <div
          aria-hidden="true"
          style={{
            width: 36,
            height: 36,
            borderRadius: 11,
            background: 'rgba(163, 56, 0, 0.11)',
            color: COLORS.primary,
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
          }}
        >
          <Icon name={context ? 'table_restaurant' : 'qr_code_scanner'} size={21} />
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              color: COLORS.onSurface,
              fontFamily: FONTS.headline,
              fontSize: 13,
              lineHeight: 1.25,
              fontWeight: 800,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {context?.tableTitle ?? t('table.dine_in_prompt', 'Stolda buyurtma berasizmi?')}
          </div>
          <div
            style={{
              color: COLORS.secondary,
              fontFamily: FONTS.body,
              fontSize: 11,
              lineHeight: 1.3,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {context
              ? `${context.hallTitle} · ${t('table.service', 'Xizmat')} ${context.servicePercent}%`
              : t('table.enter_code_hint', 'Stol kodini kiriting')}
          </div>
        </div>
      </div>
      <button
        type="button"
        onClick={onChange}
        aria-label={context
          ? t('table.change', 'Stolni almashtirish')
          : t('table.enter_code', 'Stol kodini kiritish')}
        style={{
          minWidth: 44,
          minHeight: 44,
          padding: '0 12px',
          border: 'none',
          borderRadius: 12,
          background: COLORS.surfaceContainerLowest,
          color: COLORS.primary,
          fontFamily: FONTS.body,
          fontSize: 12,
          fontWeight: 800,
          boxShadow: '0 1px 4px rgba(67, 18, 0, 0.08)',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        {context ? t('table.change_short', 'Almashtirish') : t('table.enter_short', 'Kod kiritish')}
      </button>
    </div>
  );
}
