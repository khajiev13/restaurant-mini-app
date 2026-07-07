# Admin Staff Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit admin mode with `Admin`, `Orders`, and `Profile` tabs while preserving admin access to staff delivery work.

**Architecture:** This is a frontend-focused follow-up. Reuse the existing backend admin and staff delivery APIs, add a focused admin dashboard page, make the existing staff shell role-aware, and make route selection explicit for `customer`, `staff`, and `admin`.

**Tech Stack:** React, TypeScript, React Router, Zustand auth store, Axios API client, Vitest, Testing Library, FastAPI backend already deployed with admin/staff APIs.

## Global Constraints

- No database migration is required.
- Keep `admin` as a superset role: admins can manage roles and can also perform deliveries.
- Keep staff users on the two-tab delivery shell: `Orders`, `Profile`.
- Admin users use the three-tab shell: `Admin`, `Orders`, `Profile`.
- Admin defaults to `/admin` after login.
- Staff defaults to `/staff/orders` after login.
- Customer navigation must not change.
- Staff delivery endpoints remain usable by `role in ('staff', 'admin')`.
- Admin role-management endpoints remain admin-only.
- Delivery assignment continues to use `assigned_staff_id = current_user.telegram_id`.
- Use existing OLOT SOMSA colors, fonts, logo, and bottom-nav styling.

---

## File Structure

- Create `frontend/src/services/adminApi.ts`
  - Owns admin API helpers: `searchAdminUsers(query)` and `updateAdminUserRole(telegramId, role)`.
  - Consumes the shared Axios `api` client from `frontend/src/services/api.ts`.

- Modify `frontend/src/services/staffApi.ts`
  - Remove unused admin helper exports from the staff delivery service module.
  - Keep only staff delivery API calls.

- Create `frontend/src/pages/admin/AdminUsersPage.tsx`
  - Admin dashboard route body.
  - Searches users and updates roles.
  - Uses `StaffLayout` so admin nav is consistent with delivery/profile screens.

- Create `frontend/src/pages/admin/AdminUsersPage.test.tsx`
  - Covers search, role update, empty state, and final-admin error rendering.

- Modify `frontend/src/components/staff/StaffLayout.tsx`
  - Make bottom nav role-aware by reading `useAuthStore((state) => state.user?.role)`.
  - Show `Admin | Orders | Profile` for admins and `Orders | Profile` for staff.

- Create `frontend/src/components/staff/StaffLayout.test.tsx`
  - Covers the two-tab staff shell and three-tab admin shell.

- Modify `frontend/src/App.tsx`
  - Import `AdminUsersPage`.
  - Replace the current `isStaffMode` boolean with explicit role-sensitive render helpers.
  - Add `/admin` and `/admin/users`.

- Modify `frontend/src/App.test.tsx`
  - Mock `AdminUsersPage`.
  - Update admin route expectations.
  - Add tests for admin default landing, admin access to staff orders, and non-admin access denial for `/admin`.

---

### Task 1: Separate Admin API Helpers

**Files:**
- Create: `frontend/src/services/adminApi.ts`
- Modify: `frontend/src/services/staffApi.ts`

**Interfaces:**
- Consumes: `api` default export from `frontend/src/services/api.ts`; `ApiResponse` and `User` from `frontend/src/types/api.ts`.
- Produces:
  - `searchAdminUsers(query: string): Promise<AxiosResponse<ApiResponse<User[]>>>`
  - `updateAdminUserRole(telegramId: number, role: User['role']): Promise<AxiosResponse<ApiResponse<User>>>`

- [ ] **Step 1: Create the admin API module**

Create `frontend/src/services/adminApi.ts`:

```ts
import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse, User } from '../types/api';

export const searchAdminUsers = (
  query: string,
): Promise<AxiosResponse<ApiResponse<User[]>>> => api.get('/admin/users', { params: { query } });

export const updateAdminUserRole = (
  telegramId: number,
  role: User['role'],
): Promise<AxiosResponse<ApiResponse<User>>> =>
  api.patch(`/admin/users/${telegramId}/role`, { role });
```

- [ ] **Step 2: Remove admin helpers from the staff API module**

In `frontend/src/services/staffApi.ts`, remove the `User` import and the two admin exports. The file should keep this shape:

```ts
import type { AxiosResponse } from 'axios';
import api from './api';
import type { ApiResponse } from '../types/api';
import type { StaffOrder } from '../types/staff';

export const getAvailableStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/available');

export const getActiveStaffOrder = (): Promise<AxiosResponse<ApiResponse<StaffOrder | null>>> =>
  api.get('/staff/orders/active');

export const getCompletedStaffOrders = (): Promise<AxiosResponse<ApiResponse<StaffOrder[]>>> =>
  api.get('/staff/orders/completed');

export const getStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.get(`/staff/orders/${id}`);

export const takeStaffOrder = (id: string): Promise<AxiosResponse<ApiResponse<StaffOrder>>> =>
  api.post(`/staff/orders/${id}/take`);

export const markStaffOrderDelivered = (
  id: string,
): Promise<AxiosResponse<ApiResponse<StaffOrder>>> => api.post(`/staff/orders/${id}/delivered`);
```

- [ ] **Step 3: Verify TypeScript sees the split**

Run:

```bash
cd frontend && npm run typecheck
```

Expected: command exits `0`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/adminApi.ts frontend/src/services/staffApi.ts
git commit -m "refactor: separate admin api helpers"
```

---

### Task 2: Build the Admin Role Dashboard

**Files:**
- Create: `frontend/src/pages/admin/AdminUsersPage.tsx`
- Create: `frontend/src/pages/admin/AdminUsersPage.test.tsx`

**Interfaces:**
- Consumes:
  - `searchAdminUsers(query)` and `updateAdminUserRole(telegramId, role)` from `frontend/src/services/adminApi.ts`.
  - `StaffLayout` from `frontend/src/components/staff/StaffLayout.tsx`.
  - `COLORS`, `FONTS`, and `Icon` from `frontend/src/components/artisan/ArtisanLayout.tsx`.
- Produces:
  - `AdminUsersPage` default React component.

- [ ] **Step 1: Write failing dashboard tests**

Create `frontend/src/pages/admin/AdminUsersPage.test.tsx`:

```tsx
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminUsersPage from './AdminUsersPage';

const apiMocks = vi.hoisted(() => ({
  searchAdminUsers: vi.fn(),
  updateAdminUserRole: vi.fn(),
}));

vi.mock('../../services/adminApi', () => apiMocks);

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: { user: { role: 'admin' } }) => unknown) =>
    selector({ user: { role: 'admin' } }),
}));

const userRecord = {
  telegram_id: 992208572,
  first_name: 'Rakhmonberdi',
  last_name: 'Khajiev',
  username: 'khajiev13',
  phone_number: '8613269797807',
  language: 'en',
  role: 'customer' as const,
};

describe('AdminUsersPage', () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    apiMocks.searchAdminUsers.mockResolvedValue({ data: { data: [userRecord] } });
    apiMocks.updateAdminUserRole.mockResolvedValue({
      data: { data: { ...userRecord, role: 'staff' } },
    });
  });

  it('searches users and renders role controls', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText('Search users'), '8613269797807');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(apiMocks.searchAdminUsers).toHaveBeenCalledWith('8613269797807');
    expect(await screen.findByText('Rakhmonberdi Khajiev')).toBeInTheDocument();
    expect(screen.getByText('@khajiev13')).toBeInTheDocument();
    expect(screen.getByDisplayValue('customer')).toBeInTheDocument();
  });

  it('updates a user role and refreshes that row locally', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Search' }));
    await user.selectOptions(screen.getByLabelText('Role for Rakhmonberdi Khajiev'), 'staff');
    await user.click(screen.getByRole('button', { name: 'Save role for Rakhmonberdi Khajiev' }));

    expect(apiMocks.updateAdminUserRole).toHaveBeenCalledWith(992208572, 'staff');
    expect(await screen.findByText('Role updated.')).toBeInTheDocument();
    expect(screen.getByDisplayValue('staff')).toBeInTheDocument();
  });

  it('shows an empty state when no users match', async () => {
    apiMocks.searchAdminUsers.mockResolvedValue({ data: { data: [] } });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('No users found')).toBeInTheDocument();
  });

  it('shows final-admin demotion errors from the backend', async () => {
    const user = userEvent.setup();
    apiMocks.updateAdminUserRole.mockRejectedValue({
      response: { data: { detail: 'Cannot remove the final admin role.' } },
    });

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <AdminUsersPage />
      </MemoryRouter>,
    );

    await user.click(await screen.findByRole('button', { name: 'Search' }));
    await user.selectOptions(screen.getByLabelText('Role for Rakhmonberdi Khajiev'), 'staff');
    await user.click(screen.getByRole('button', { name: 'Save role for Rakhmonberdi Khajiev' }));

    expect(await screen.findByText('Cannot remove the final admin role.')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail before implementation**

Run:

```bash
cd frontend && npm test -- src/pages/admin/AdminUsersPage.test.tsx
```

Expected: FAIL because `frontend/src/pages/admin/AdminUsersPage.tsx` does not exist.

- [ ] **Step 3: Implement `AdminUsersPage`**

Create `frontend/src/pages/admin/AdminUsersPage.tsx`:

```tsx
import { type FormEvent, useState } from 'react';
import StaffLayout from '../../components/staff/StaffLayout';
import { COLORS, FONTS, Icon } from '../../components/artisan/ArtisanLayout';
import { searchAdminUsers, updateAdminUserRole } from '../../services/adminApi';
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
```

- [ ] **Step 4: Run dashboard tests**

Run:

```bash
cd frontend && npm test -- src/pages/admin/AdminUsersPage.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/admin/AdminUsersPage.tsx frontend/src/pages/admin/AdminUsersPage.test.tsx
git commit -m "feat: add admin role dashboard"
```

---

### Task 3: Make the Staff Shell Role-Aware

**Files:**
- Modify: `frontend/src/components/staff/StaffLayout.tsx`
- Create: `frontend/src/components/staff/StaffLayout.test.tsx`

**Interfaces:**
- Consumes: `useAuthStore` from `frontend/src/stores/authStore.ts`.
- Produces: same `StaffLayout({ children }: { children: ReactNode })` component, with role-aware nav.

- [ ] **Step 1: Write failing shell tests**

Create `frontend/src/components/staff/StaffLayout.test.tsx`:

```tsx
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import StaffLayout from './StaffLayout';

const authState = vi.hoisted(() => ({
  user: { role: 'staff' as 'customer' | 'staff' | 'admin' },
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: (selector: (state: typeof authState) => unknown) => selector(authState),
}));

describe('StaffLayout', () => {
  beforeEach(() => {
    cleanup();
    authState.user = { role: 'staff' };
  });

  it('shows two nav items for staff', () => {
    render(
      <MemoryRouter initialEntries={['/staff/orders']}>
        <StaffLayout>
          <div>Staff content</div>
        </StaffLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole('navigation', { name: 'Staff navigation' })).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.queryByText('Admin')).not.toBeInTheDocument();
  });

  it('shows three nav items for admin', () => {
    authState.user = { role: 'admin' };

    render(
      <MemoryRouter initialEntries={['/admin']}>
        <StaffLayout>
          <div>Admin content</div>
        </StaffLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole('navigation', { name: 'Admin navigation' })).toBeInTheDocument();
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(screen.getByText('Orders')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify the admin case fails**

Run:

```bash
cd frontend && npm test -- src/components/staff/StaffLayout.test.tsx
```

Expected: FAIL because `Admin` nav is not rendered.

- [ ] **Step 3: Implement role-aware nav**

Modify `frontend/src/components/staff/StaffLayout.tsx`:

```tsx
import type { CSSProperties, ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import logo from '../../assets/logo.webp';
import { useAuthStore } from '../../stores/authStore';
import { COLORS, FONTS, Icon } from '../artisan/ArtisanLayout';
```

Replace the fixed `navStyle` grid with a helper:

```tsx
const getNavStyle = (itemCount: number): CSSProperties => ({
  position: 'fixed',
  left: 0,
  right: 0,
  bottom: 0,
  zIndex: 40,
  height: 88,
  display: 'grid',
  gridTemplateColumns: `repeat(${itemCount}, minmax(0, 1fr))`,
  alignItems: 'center',
  padding: '8px 16px 24px',
  boxSizing: 'border-box',
  backgroundColor: 'rgba(255, 255, 255, 0.92)',
  backdropFilter: 'blur(12px)',
  boxShadow: '0 -8px 24px rgba(45, 47, 47, 0.08)',
});
```

Update `StaffLayout`:

```tsx
export default function StaffLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const role = useAuthStore((state) => state.user?.role);
  const isAdmin = role === 'admin';
  const adminActive = location.pathname.startsWith('/admin');
  const ordersActive = location.pathname.startsWith('/staff/orders');
  const profileActive = location.pathname === '/profile';
  const navItems = isAdmin
    ? [
        { active: adminActive, icon: 'admin_panel_settings', label: 'Admin', to: '/admin' },
        { active: ordersActive, icon: 'receipt_long', label: 'Orders', to: '/staff/orders' },
        { active: profileActive, icon: 'person', label: 'Profile', to: '/profile' },
      ]
    : [
        { active: ordersActive, icon: 'receipt_long', label: 'Orders', to: '/staff/orders' },
        { active: profileActive, icon: 'person', label: 'Profile', to: '/profile' },
      ];

  return (
    <div style={shellStyle}>
      <header style={topBarStyle}>
        <img src={logo} alt="" aria-hidden="true" style={brandIconStyle} />
        <p style={brandStyle}>OLOT SOMSA</p>
      </header>

      <div style={frameStyle}>{children}</div>

      <nav aria-label={isAdmin ? 'Admin navigation' : 'Staff navigation'} style={getNavStyle(navItems.length)}>
        {navItems.map((item) => (
          <NavItem
            key={item.to}
            active={item.active}
            icon={item.icon}
            label={item.label}
            to={item.to}
          />
        ))}
      </nav>
    </div>
  );
}
```

- [ ] **Step 4: Run layout tests and existing staff page tests**

Run:

```bash
cd frontend && npm test -- src/components/staff/StaffLayout.test.tsx src/pages/staff/StaffOrdersPage.test.tsx
```

Expected: PASS. `StaffOrdersPage` should still show `Orders` and `Profile` only when the auth store has no admin user.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/staff/StaffLayout.tsx frontend/src/components/staff/StaffLayout.test.tsx
git commit -m "feat: make staff shell admin-aware"
```

---

### Task 4: Wire Explicit Customer, Staff, and Admin Routing

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `AdminUsersPage` default export from `frontend/src/pages/admin/AdminUsersPage.tsx`.
- Produces:
  - `/admin` route.
  - `/admin/users` route.
  - Explicit role routing helpers inside `App`.

- [ ] **Step 1: Write failing routing tests**

Modify `frontend/src/App.test.tsx`.

Add the mock after the staff page mocks:

```tsx
vi.mock('./pages/admin/AdminUsersPage', () => ({
  default: () => <div>Admin users page</div>,
}));
```

Replace the current admin route test named `renders the staff order detail route for admin users` with:

```tsx
it('routes admin users from home to admin users page', () => {
  authState.user = { role: 'admin' };

  const view = render(
    <MemoryRouter initialEntries={['/']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Admin users page')).toBeInTheDocument();
  expect(view.queryByText('Staff orders page')).not.toBeInTheDocument();
});

it('lets admin users open staff orders', () => {
  authState.user = { role: 'admin' };

  const view = render(
    <MemoryRouter initialEntries={['/staff/orders']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Staff orders page')).toBeInTheDocument();
});

it('renders the staff order detail route for admin users', () => {
  authState.user = { role: 'admin' };

  const view = render(
    <MemoryRouter initialEntries={['/staff/orders/abc-123']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Staff order detail page')).toBeInTheDocument();
});

it('routes staff users away from admin routes to staff orders', () => {
  authState.user = { role: 'staff' };

  const view = render(
    <MemoryRouter initialEntries={['/admin']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Staff orders page')).toBeInTheDocument();
  expect(view.queryByText('Admin users page')).not.toBeInTheDocument();
});

it('routes customer users away from admin routes to home', () => {
  authState.user = { role: 'customer' };

  const view = render(
    <MemoryRouter initialEntries={['/admin']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Artisan menu page')).toBeInTheDocument();
  expect(view.queryByText('Admin users page')).not.toBeInTheDocument();
});
```

Change the existing test `routes staff users away from customer order detail to staff orders` so it uses `staff` instead of `admin`:

```tsx
it('routes staff users away from customer order detail to staff orders', () => {
  authState.user = { role: 'staff' };

  const view = render(
    <MemoryRouter initialEntries={['/order/abc-123']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Staff orders page')).toBeInTheDocument();
});
```

Add a separate admin customer-route test:

```tsx
it('routes admin users away from customer order detail to admin page', () => {
  authState.user = { role: 'admin' };

  const view = render(
    <MemoryRouter initialEntries={['/order/abc-123']}>
      <App />
    </MemoryRouter>,
  );

  expect(view.getByText('Admin users page')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify new admin routing fails**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx
```

Expected: FAIL because `/admin` is not routed and `/` still sends admin to staff orders.

- [ ] **Step 3: Implement explicit role routing**

Modify `frontend/src/App.tsx` imports:

```tsx
import AdminUsersPage from './pages/admin/AdminUsersPage';
```

Replace `isStaffMode` and `renderRoleSensitiveRoute` with these helpers:

```tsx
  const role = user?.role ?? 'customer';
  const isResolvingRole = isLoading || !hasResolvedInitialAuth || !hasHydratedUser;

  const renderResolvedRoute = (element: ReactNode) => {
    if (authError) {
      return <AuthRetryShell message={authError} onRetry={() => { void bootstrapAuth(); }} />;
    }

    if (isResolvingRole) {
      return <RoleRouteLoadingShell />;
    }

    return element;
  };

  const renderByRole = (
    customerElement: ReactNode,
    staffElement: ReactNode,
    adminElement: ReactNode,
  ) => {
    if (role === 'admin') {
      return renderResolvedRoute(adminElement);
    }

    if (role === 'staff') {
      return renderResolvedRoute(staffElement);
    }

    return renderResolvedRoute(customerElement);
  };

  const renderStaffOrAdminRoute = (staffElement: ReactNode) =>
    renderByRole(<Navigate to="/" replace />, staffElement, staffElement);

  const renderAdminRoute = (adminElement: ReactNode) =>
    renderByRole(<Navigate to="/" replace />, <Navigate to="/staff/orders" replace />, adminElement);
```

Replace route elements with:

```tsx
      <Route
        path="/"
        element={renderByRole(
          <ArtisanMenuPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route
        path="/checkout"
        element={renderByRole(
          <ArtisanCheckoutPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route
        path="/order"
        element={renderByRole(
          <ArtisanOrdersPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route
        path="/profile"
        element={renderByRole(<ArtisanProfilePage />, <StaffProfilePage />, <StaffProfilePage />)}
      />
      <Route
        path="/order/:orderId"
        element={renderByRole(
          <ArtisanOrderStatusPage />,
          <Navigate to="/staff/orders" replace />,
          <Navigate to="/admin" replace />,
        )}
      />
      <Route path="/admin" element={renderAdminRoute(<AdminUsersPage />)} />
      <Route path="/admin/users" element={renderAdminRoute(<AdminUsersPage />)} />
      <Route path="/staff/orders" element={renderStaffOrAdminRoute(<StaffOrdersPage />)} />
      <Route
        path="/staff/orders/:orderId"
        element={renderStaffOrAdminRoute(<StaffOrderDetailPage />)}
      />
```

- [ ] **Step 4: Run routing tests**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: route admins to admin dashboard"
```

---

### Task 5: Full Frontend Verification and Deployment Note

**Files:**
- Modify only files from Tasks 1-4 if verification reveals a regression.
- Do not modify backend files unless a frontend test proves the existing backend contract is insufficient.

**Interfaces:**
- Consumes all previous task outputs.
- Produces a verified frontend implementation ready for review and deployment.

- [ ] **Step 1: Run focused admin and routing tests**

Run:

```bash
cd frontend && npm test -- src/pages/admin/AdminUsersPage.test.tsx src/components/staff/StaffLayout.test.tsx src/App.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run the full frontend verification suite**

Run:

```bash
cd frontend && npm test && npm run typecheck && npm run build && npm run lint
```

Expected:

- Vitest exits `0`.
- TypeScript exits `0`.
- Vite build exits `0`.
- ESLint exits `0` or preserves only the existing `frontend/src/components/artisan/MapPickerOverlay.tsx` hook dependency warning.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit `0`.

- [ ] **Step 4: Manual Telegram smoke test after deployment**

After deploying this frontend follow-up, open the Telegram mini app as the admin user `8613269797807` and verify:

```text
1. Home/default route opens Admin.
2. Bottom nav shows Admin, Orders, Profile.
3. Admin tab can search for a user by phone number.
4. Role selector can change a non-final-admin user to staff.
5. Orders tab opens the delivery list.
6. Profile tab shows the admin profile.
```

Expected: admin can manage roles and can still enter delivery work.

- [ ] **Step 5: Commit any verification-only fixes**

If no fixes were needed in this task, skip this commit. If fixes were needed:

```bash
git add frontend/src
git commit -m "fix: stabilize admin navigation follow-up"
```

---

## Self-Review

Spec coverage:

- Admin default landing at `/admin`: Task 4.
- Admin `Admin | Orders | Profile` shell: Task 3.
- Staff `Orders | Profile` shell preserved: Task 3.
- Admin role management dashboard: Task 2.
- Existing staff delivery UI reused for admins: Task 4.
- Backend permissions unchanged: Global Constraints and Task 5.
- Error handling for final-admin demotion: Task 2.
- Testing coverage listed in the spec: Tasks 2, 3, 4, and 5.
- No database migration: Global Constraints and Task 5.

Placeholder scan:

- This plan contains no placeholder markers or deferred implementation sections.

Type consistency:

- `User['role']` is used consistently for role selectors and updates.
- `searchAdminUsers` and `updateAdminUserRole` signatures are defined in Task 1 and consumed in Task 2.
- `AdminUsersPage` is defined in Task 2 and consumed in Task 4.
- `StaffLayout` keeps the same default export signature while adding role-aware nav.
