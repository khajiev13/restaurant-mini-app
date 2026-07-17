import { useEffect, useId, useRef, useState } from 'react';
import type { StaffOrder } from '../../types/staff';
import { formatPrice } from '../../utils/format';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';

export default function ConfirmDeliveredSheet({
  error,
  language,
  onCancel,
  onConfirm,
  order,
  submitting,
}: {
  error: string | null;
  language: string;
  onCancel: () => void;
  onConfirm: () => void;
  order: StaffOrder;
  submitting: boolean;
}) {
  const isCash = order.payment_method === 'cash';
  const [collectedCash, setCollectedCash] = useState(!isCash);
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const checkboxRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    const trigger = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const inerted: Array<{ element: HTMLElement; hadInert: boolean }> = [];
    let branch: HTMLElement | null = dialog;
    while (branch?.parentElement && branch.parentElement !== document.body) {
      for (const sibling of Array.from(branch.parentElement.children)) {
        if (sibling !== branch && sibling instanceof HTMLElement) {
          inerted.push({ element: sibling, hadInert: sibling.hasAttribute('inert') });
          sibling.setAttribute('inert', '');
        }
      }
      branch = branch.parentElement;
    }

    const focusables = () => Array.from(dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ));
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancelRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const candidates = focusables();
      if (candidates.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = candidates[0];
      const last = candidates[candidates.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    (isCash ? checkboxRef.current : confirmRef.current)?.focus();

    return () => {
      document.removeEventListener('keydown', onKeyDown);
      for (const { element, hadInert } of inerted) {
        if (!hadInert) element.removeAttribute('inert');
      }
      if (trigger?.isConnected) trigger.focus();
    };
  }, [isCash]);

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 80,
        display: 'flex',
        alignItems: 'flex-end',
        backgroundColor: 'rgba(45, 47, 47, 0.35)',
      }}
    >
      <section
        style={{
          width: '100%',
          padding: '24px 24px 28px',
          borderTopLeftRadius: 24,
          borderTopRightRadius: 24,
          backgroundColor: COLORS.surfaceContainerLowest,
        }}
      >
        <div
          aria-hidden="true"
          style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#fee2d5',
          }}
        >
          <Icon name="inventory_2" style={{ color: COLORS.primary }} />
        </div>

        <h2
          id={titleId}
          style={{
            margin: '20px 0 8px',
            fontFamily: FONTS.headline,
            fontSize: 28,
            fontWeight: 800,
          }}
        >
          Confirm Delivery
        </h2>
        <p style={{ margin: 0, color: COLORS.onSurfaceVariant }}>
          Mark order #{order.order_number ?? order.id.slice(0, 6)} as delivered.
        </p>

        {isCash ? (
          <label
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 14,
              marginTop: 24,
              padding: 18,
              borderRadius: 14,
              backgroundColor: COLORS.surfaceContainerLow,
            }}
          >
            <input
              ref={checkboxRef}
              type="checkbox"
              aria-label={`I have collected ${formatPrice(order.total_amount, language)} cash`}
              checked={collectedCash}
              onChange={(event) => setCollectedCash(event.target.checked)}
              style={{
                width: 22,
                height: 22,
                margin: 0,
                accentColor: COLORS.primary,
              }}
            />
            <span style={{ fontWeight: 700, lineHeight: 1.4 }}>
              I have collected {formatPrice(order.total_amount, language)} cash.
            </span>
          </label>
        ) : null}

        {error ? (
          <p style={{ margin: '16px 0 0', color: COLORS.error, fontWeight: 700 }}>{error}</p>
        ) : null}

        <button
          ref={confirmRef}
          type="button"
          disabled={!collectedCash || submitting}
          onClick={onConfirm}
          style={{
            width: '100%',
            height: 54,
            marginTop: 24,
            border: 'none',
            borderRadius: 12,
            backgroundColor: !collectedCash || submitting ? COLORS.surfaceContainerHigh : COLORS.primary,
            color: !collectedCash || submitting ? COLORS.onSurfaceVariant : COLORS.onPrimary,
            fontFamily: FONTS.headline,
            fontSize: 16,
            fontWeight: 800,
            cursor: !collectedCash || submitting ? 'default' : 'pointer',
          }}
        >
          {submitting ? 'Submitting...' : 'Confirm & Mark Delivered'}
        </button>

        <button
          type="button"
          onClick={onCancel}
          style={{
            width: '100%',
            height: 50,
            marginTop: 12,
            border: 'none',
            borderRadius: 12,
            backgroundColor: COLORS.surfaceContainerLow,
            color: COLORS.onSurface,
            fontFamily: FONTS.body,
            fontSize: 15,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          Cancel
        </button>
      </section>
    </div>
  );
}
