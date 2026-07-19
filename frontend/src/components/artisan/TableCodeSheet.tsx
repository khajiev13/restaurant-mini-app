import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { COLORS, FONTS, Icon } from './ArtisanLayout';

function normalizeCode(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6);
}

function canonicalizeCode(value: string): string {
  return value.replace(/^0+(?=\d)/, '');
}

export default function TableCodeSheet({
  open,
  onClose,
  onResolve,
  resolving,
  error,
}: {
  open: boolean;
  onClose: () => void;
  onResolve: (code: string) => Promise<void>;
  resolving: boolean;
  error: string | null;
}) {
  const { t } = useTranslation();
  const [code, setCode] = useState('');

  useEffect(() => {
    if (!open) setCode('');
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !resolving) onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, open, resolving]);

  if (!open) return null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (code.length === 0 || resolving) return;
    try {
      await onResolve(canonicalizeCode(code));
      onClose();
    } catch {
      // The parent provides the user-facing error from the store.
    }
  };

  return (
    <div
      role="presentation"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !resolving) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 90,
        background: 'rgba(45, 47, 47, 0.38)',
        display: 'flex',
        alignItems: 'flex-end',
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="table-code-title"
        style={{
          width: '100%',
          padding: '12px 20px calc(24px + env(safe-area-inset-bottom))',
          boxSizing: 'border-box',
          borderRadius: '24px 24px 0 0',
          background: COLORS.surfaceContainerLowest,
          boxShadow: '0 -12px 40px rgba(45, 47, 47, 0.18)',
        }}
      >
        <div
          aria-hidden="true"
          style={{ width: 42, height: 4, borderRadius: 99, background: COLORS.surfaceContainerHigh, margin: '0 auto 18px' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h2 id="table-code-title" style={{ margin: 0, fontFamily: FONTS.headline, fontSize: 21, color: COLORS.onSurface }}>
              {t('table.code_title', 'Stol raqamini kiriting')}
            </h2>
            <p style={{ margin: '6px 0 0', color: COLORS.secondary, fontSize: 13, lineHeight: 1.5 }}>
              {t('table.code_description', "QR yonida ko'rsatilgan stol raqamini kiriting.")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={resolving}
            aria-label={t('common.close', 'Yopish')}
            style={{ width: 44, height: 44, border: 'none', borderRadius: 14, background: COLORS.surfaceContainerLow, cursor: 'pointer' }}
          >
            <Icon name="close" size={21} />
          </button>
        </div>

        <form onSubmit={(event) => { void submit(event); }} style={{ marginTop: 20 }}>
          <label htmlFor="table-code" style={{ display: 'block', fontSize: 12, fontWeight: 800, color: COLORS.secondary, marginBottom: 7 }}>
            {t('table.code_label', 'Stol raqami')}
          </label>
          <input
            id="table-code"
            autoFocus
            autoComplete="off"
            inputMode="numeric"
            pattern="[0-9]*"
            enterKeyHint="done"
            value={code}
            onChange={(event) => setCode(normalizeCode(event.target.value))}
            placeholder="12"
            style={{
              width: '100%',
              height: 58,
              boxSizing: 'border-box',
              border: `2px solid ${error ? COLORS.error : COLORS.outlineVariant}`,
              borderRadius: 14,
              padding: '0 16px',
              color: COLORS.onSurface,
              background: COLORS.surface,
              fontFamily: FONTS.headline,
              fontSize: 23,
              fontWeight: 800,
              letterSpacing: '0.18em',
              textAlign: 'center',
              outlineColor: COLORS.primary,
            }}
          />
          {error && (
            <p role="alert" style={{ color: COLORS.error, fontSize: 12, fontWeight: 700, margin: '8px 2px 0' }}>
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={code.length === 0 || resolving}
            style={{
              width: '100%',
              height: 52,
              marginTop: 18,
              border: 'none',
              borderRadius: 15,
              background: code.length > 0 && !resolving ? COLORS.primary : COLORS.surfaceContainerHigh,
              color: code.length > 0 && !resolving ? COLORS.onPrimary : COLORS.secondary,
              fontFamily: FONTS.headline,
              fontSize: 16,
              fontWeight: 800,
              cursor: code.length > 0 && !resolving ? 'pointer' : 'default',
            }}
          >
            {resolving ? t('table.checking', 'Tekshirilmoqda…') : t('table.confirm', 'Tasdiqlash')}
          </button>
        </form>
      </section>
    </div>
  );
}
