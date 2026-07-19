import { useTranslation } from 'react-i18next';
import {
  usePhoneVerification,
  type PhoneVerificationStatus,
} from '../../hooks/usePhoneVerification';

const DESCRIPTION_KEYS: Record<PhoneVerificationStatus, string> = {
  ready: 'phone_verification.ready',
  requesting: 'phone_verification.requesting',
  verifying: 'phone_verification.verifying',
  declined: 'phone_verification.declined',
  delayed: 'phone_verification.delayed',
  unsupported: 'phone_verification.unsupported',
  outside_telegram: 'phone_verification.outside_telegram',
  network_error: 'phone_verification.network_error',
};

export default function PhoneVerificationGate() {
  const { t } = useTranslation();
  const { status, requestPhone, checkAgain } = usePhoneVerification({ autoRequest: true });
  const isBusy = status === 'requesting' || status === 'verifying';
  const canShare = status === 'ready' || status === 'declined';
  const canRetryBoth = status === 'delayed' || status === 'network_error';

  return (
    <main
      aria-busy={isBusy}
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        backgroundColor: '#fff8f5',
        color: '#2d2f2f',
      }}
    >
      <section style={{ width: '100%', maxWidth: 380, textAlign: 'center' }}>
        <div aria-hidden="true" style={{ fontSize: 48, lineHeight: 1 }}>📱</div>
        <h1 style={{ margin: '20px 0 0', fontSize: 26, lineHeight: 1.2 }}>
          {t('phone_verification.title')}
        </h1>
        <p style={{ margin: '12px 0 0', fontSize: 16, lineHeight: 1.5 }}>
          {t(DESCRIPTION_KEYS[status])}
        </p>

        {canShare ? (
          <button
            type="button"
            onClick={requestPhone}
            style={{
              width: '100%',
              height: 52,
              marginTop: 24,
              border: 'none',
              borderRadius: 14,
              backgroundColor: '#a33800',
              color: '#ffefeb',
              fontSize: 16,
              fontWeight: 800,
              cursor: 'pointer',
            }}
          >
            {t('phone_verification.share')}
          </button>
        ) : null}

        {canRetryBoth ? (
          <div style={{ display: 'grid', gap: 10, marginTop: 24 }}>
            <button
              type="button"
              onClick={() => { void checkAgain(); }}
              style={{
                height: 52,
                border: 'none',
                borderRadius: 14,
                backgroundColor: '#a33800',
                color: '#ffefeb',
                fontSize: 16,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              {t('phone_verification.check_again')}
            </button>
            <button
              type="button"
              onClick={requestPhone}
              style={{
                height: 48,
                border: '1px solid #a33800',
                borderRadius: 14,
                backgroundColor: 'transparent',
                color: '#7c2e08',
                fontSize: 15,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              {t('phone_verification.share_again')}
            </button>
          </div>
        ) : null}
      </section>
    </main>
  );
}
