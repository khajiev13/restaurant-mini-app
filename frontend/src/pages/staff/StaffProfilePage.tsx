import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import StaffLayout from '../../components/staff/StaffLayout';
import { getMe } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import type { User } from '../../types/api';

export default function StaffProfilePage() {
  const { t } = useTranslation();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const logout = useAuthStore((state) => state.logout);
  const isMountedRef = useRef(true);

  const loadProfile = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await getMe();
      if (isMountedRef.current) {
        setUser(response.data.data);
      }
    } catch {
      if (isMountedRef.current) {
        setUser(null);
        setError(t('staff.profile.load_error', 'Could not load your profile.'));
      }
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [t]);

  useEffect(() => {
    isMountedRef.current = true;
    void loadProfile();

    return () => {
      isMountedRef.current = false;
    };
  }, [loadProfile]);

  return (
    <StaffLayout>
      <main style={{ padding: '0 20px', display: 'grid', gap: 20 }}>
        <h1
          style={{
            margin: 0,
            fontFamily: FONTS.headline,
            fontSize: 34,
            fontWeight: 800,
          }}
        >
          Profile
        </h1>

        {isLoading ? <p style={{ margin: 0, color: COLORS.secondary }}>Loading profile...</p> : null}

        {!isLoading && error ? (
          <section
            style={{
              padding: 20,
              borderRadius: 16,
              backgroundColor: COLORS.surfaceContainerLowest,
            }}
          >
            <p style={{ margin: 0, color: COLORS.error, fontWeight: 700 }}>{error}</p>
            <button
              type="button"
              onClick={() => {
                void loadProfile();
              }}
              style={{
                height: 44,
                marginTop: 14,
                padding: '0 16px',
                border: 'none',
                borderRadius: 10,
                backgroundColor: COLORS.primary,
                color: COLORS.onPrimary,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              {t('staff.profile.retry', 'Retry')}
            </button>
          </section>
        ) : null}

        {user ? (
          <section
            style={{
              padding: 24,
              borderRadius: 16,
              backgroundColor: COLORS.surfaceContainerLowest,
              textAlign: 'center',
            }}
          >
            <div
              aria-hidden="true"
              style={{
                width: 84,
                height: 84,
                margin: '0 auto 16px',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: COLORS.primary,
                color: COLORS.onPrimary,
                fontFamily: FONTS.headline,
                fontSize: 30,
                fontWeight: 800,
              }}
            >
              {(user.first_name?.[0] ?? 'S').toUpperCase()}
            </div>

            <h2
              style={{
                margin: 0,
                fontFamily: FONTS.headline,
                fontSize: 26,
                fontWeight: 800,
              }}
            >
              {user.first_name} {user.last_name ?? ''}
            </h2>
            <p style={{ margin: '8px 0 0', color: COLORS.secondary }}>
              {user.username ? `@${user.username}` : t('staff.profile.telegram_staff', 'Telegram staff')}
            </p>
            <p style={{ margin: '8px 0 0', color: COLORS.primary, fontWeight: 800 }}>
              {user.role.toUpperCase()}
            </p>
            {user.phone_number ? (
              <p style={{ margin: '12px 0 0', color: COLORS.onSurface }}>{user.phone_number}</p>
            ) : null}
          </section>
        ) : null}

        <button
          type="button"
          onClick={logout}
          style={{
            height: 52,
            border: 'none',
            borderRadius: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 10,
            backgroundColor: COLORS.surfaceContainerLow,
            color: COLORS.onSurface,
            fontFamily: FONTS.body,
            fontSize: 15,
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          <Icon name="logout" />
          {t('profile.logout', 'Log Out')}
        </button>
      </main>
    </StaffLayout>
  );
}
