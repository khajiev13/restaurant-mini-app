import { formatPrice } from '../../utils/format';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';

export default function StaffPaymentBlock({
  amount,
  language,
  method,
  status,
}: {
  amount: number;
  language: string;
  method: string;
  status: string | null;
}) {
  const isCash = method === 'cash';
  const heading = isCash ? `Collect ${formatPrice(amount, language)}` : 'Paid Online';
  const detail = isCash
    ? 'Cash upon delivery'
    : status === 'paid'
      ? 'Card payment completed'
      : 'Online payment';

  return (
    <section
      style={{
        padding: 20,
        borderRadius: 16,
        backgroundColor: isCash ? '#fee2d5' : COLORS.surfaceContainerLowest,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: 52,
          height: 52,
          flexShrink: 0,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: isCash ? COLORS.primaryContainer : COLORS.surfaceContainerLow,
        }}
      >
        <Icon
          name={isCash ? 'payments' : 'credit_card'}
          style={{ color: isCash ? COLORS.onPrimary : COLORS.onSurfaceVariant }}
        />
      </div>
      <div style={{ minWidth: 0 }}>
        <p
          style={{
            margin: 0,
            fontSize: 12,
            fontWeight: 700,
            color: COLORS.secondary,
            textTransform: 'uppercase',
          }}
        >
          Payment
        </p>
        <p
          style={{
            margin: '4px 0 0',
            fontFamily: FONTS.headline,
            fontSize: 22,
            fontWeight: 800,
            lineHeight: 1.2,
          }}
        >
          {heading}
        </p>
        <p style={{ margin: '6px 0 0', color: COLORS.onSurfaceVariant }}>{detail}</p>
      </div>
    </section>
  );
}
