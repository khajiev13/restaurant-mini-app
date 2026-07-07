import { type FormEvent, useState } from 'react';
import StaffLayout from '../../components/staff/StaffLayout';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { searchAdminUsers, updateAdminUserRole } from '../../services/adminApi';
import { useAuthStore } from '../../stores/authStore';
import type { User } from '../../types/api';

const ROLE_OPTIONS: ReadonlyArray<User['role']> = ['customer', 'staff', 'admin'];

function getDisplayName(user: User): string {
  return `${user.first_name} ${user.last_name ?? ''}`.trim() || `Telegram ${user.telegram_id}`;
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'response' in error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }
  return fallback;
}

export default function AdminUsersPage() {
  const currentAuthUser = useAuthStore((state) => state.user);
  const refreshMe = useAuthStore((state) => state.refreshMe);
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<User[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<Record<number, User['role']>>({});
  const [isSearching, setIsSearching] = useState(false);
  const [savingUserId, setSavingUserId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const runSearch = async () => {
    setIsSearching(true);
    setError(null);
    setMessage(null);
    try {
      const response = await searchAdminUsers(query);
      const nextUsers = response.data.data ?? [];
      setUsers(nextUsers);
      setSelectedRoles(
        Object.fromEntries(nextUsers.map((user) => [user.telegram_id, user.role])),
      );
      setHasSearched(true);
    } catch (searchError) {
      setUsers([]);
      setSelectedRoles({});
      setError(getApiErrorMessage(searchError, 'Could not search users. Try again.'));
    } finally {
      setIsSearching(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runSearch();
  };

  const handleRoleChange = (telegramId: number, role: User['role']) => {
    setSelectedRoles((current) => ({ ...current, [telegramId]: role }));
    setMessage(null);
    setError(null);
  };

  const handleSaveRole = async (user: User) => {
    const role = selectedRoles[user.telegram_id] ?? user.role;
    setSavingUserId(user.telegram_id);
    setError(null);
    setMessage(null);
    try {
      const response = await updateAdminUserRole(user.telegram_id, role);
      const updatedUser = response.data.data;
      setUsers((currentUsers) =>
        currentUsers.map((currentUser) =>
          currentUser.telegram_id === updatedUser.telegram_id ? updatedUser : currentUser,
        ),
      );
      setSelectedRoles((currentRoles) => ({
        ...currentRoles,
        [updatedUser.telegram_id]: updatedUser.role,
      }));
      if (updatedUser.telegram_id === currentAuthUser?.telegram_id) {
        await refreshMe();
      }
      setMessage('Role updated.');
    } catch (saveError) {
      setError(getApiErrorMessage(saveError, 'Could not update this role. Try again.'));
    } finally {
      setSavingUserId(null);
    }
  };

  return (
    <StaffLayout>
      <main style={{ padding: '0 20px', display: 'grid', gap: 18 }}>
        <section>
          <p
            style={{
              margin: '0 0 8px',
              color: COLORS.primary,
              fontSize: 12,
              fontWeight: 800,
              textTransform: 'uppercase',
            }}
          >
            Admin
          </p>
          <h1
            style={{
              margin: 0,
              fontFamily: FONTS.headline,
              fontSize: 34,
              fontWeight: 800,
              lineHeight: 1.12,
            }}
          >
            Staff roles
          </h1>
        </section>

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 10 }}>
          <label htmlFor="admin-user-search" style={{ fontWeight: 800 }}>
            Search users
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              id="admin-user-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Phone, name, or username"
              style={{
                minWidth: 0,
                flex: 1,
                height: 48,
                borderRadius: 12,
                border: `1px solid ${COLORS.outlineVariant}`,
                padding: '0 14px',
                font: 'inherit',
                backgroundColor: COLORS.surfaceContainerLowest,
                color: COLORS.onSurface,
              }}
            />
            <button
              type="submit"
              disabled={isSearching}
              style={{
                width: 104,
                border: 'none',
                borderRadius: 12,
                backgroundColor: COLORS.primary,
                color: COLORS.onPrimary,
                fontWeight: 800,
                cursor: isSearching ? 'wait' : 'pointer',
              }}
            >
              {isSearching ? 'Searching' : 'Search'}
            </button>
          </div>
        </form>

        {message ? <p style={{ margin: 0, color: COLORS.primary, fontWeight: 800 }}>{message}</p> : null}
        {error ? <p style={{ margin: 0, color: COLORS.error, fontWeight: 800 }}>{error}</p> : null}

        <section style={{ display: 'grid', gap: 12 }}>
          {users.map((user) => {
            const displayName = getDisplayName(user);
            const selectedRole = selectedRoles[user.telegram_id] ?? user.role;
            const isSaving = savingUserId === user.telegram_id;
            return (
              <article
                key={user.telegram_id}
                style={{
                  padding: 18,
                  borderRadius: 14,
                  backgroundColor: COLORS.surfaceContainerLowest,
                  boxShadow: '0 10px 24px rgba(45, 47, 47, 0.08)',
                  display: 'grid',
                  gap: 14,
                }}
              >
                <div>
                  <h2
                    style={{
                      margin: 0,
                      fontFamily: FONTS.headline,
                      fontSize: 20,
                      fontWeight: 800,
                    }}
                  >
                    {displayName}
                  </h2>
                  {user.username ? (
                    <p style={{ margin: '6px 0 0', color: COLORS.secondary }}>@{user.username}</p>
                  ) : null}
                  <p style={{ margin: '6px 0 0', color: COLORS.onSurfaceVariant }}>
                    {user.phone_number ?? 'No phone'} · {user.telegram_id}
                  </p>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0, 1fr) auto',
                    gap: 10,
                    alignItems: 'center',
                  }}
                >
                  <label style={{ display: 'grid', gap: 6, fontWeight: 800 }}>
                    Role for {displayName}
                    <select
                      aria-label={`Role for ${displayName}`}
                      value={selectedRole}
                      onChange={(event) =>
                        handleRoleChange(user.telegram_id, event.target.value as User['role'])
                      }
                      style={{
                        height: 44,
                        borderRadius: 10,
                        border: `1px solid ${COLORS.outlineVariant}`,
                        padding: '0 12px',
                        font: 'inherit',
                        backgroundColor: COLORS.surfaceContainerLowest,
                        color: COLORS.onSurface,
                      }}
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button
                    type="button"
                    aria-label={`Save role for ${displayName}`}
                    disabled={isSaving || selectedRole === user.role}
                    onClick={() => void handleSaveRole(user)}
                    style={{
                      width: 48,
                      height: 44,
                      alignSelf: 'end',
                      border: 'none',
                      borderRadius: 10,
                      backgroundColor:
                        selectedRole === user.role ? COLORS.surfaceContainer : COLORS.primary,
                      color: selectedRole === user.role ? COLORS.secondary : COLORS.onPrimary,
                      cursor: isSaving ? 'wait' : 'pointer',
                    }}
                  >
                    <Icon name="save" />
                  </button>
                </div>
              </article>
            );
          })}

          {hasSearched && !isSearching && users.length === 0 ? (
            <section
              style={{
                padding: 24,
                borderRadius: 14,
                backgroundColor: COLORS.surfaceContainerLowest,
                textAlign: 'center',
              }}
            >
              <p style={{ margin: 0, color: COLORS.secondary, fontWeight: 800 }}>No users found</p>
            </section>
          ) : null}
        </section>
      </main>
    </StaffLayout>
  );
}
