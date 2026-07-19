# Telegram-Verified Customer Phone Gate Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task by task, with a fresh implementer and a fresh task reviewer for every task.

**Goal:** Require every Telegram customer to share their own verified phone before customer UI or order creation, snapshot the full verified phone into each order, and send AliPOS a masked phone header followed by the unchanged optional customer note.

**Architecture:** A pure backend phone-verification service owns canonicalization, fingerprinting, verification predicates, update ordering, and masking. The protected Telegram webhook is the only verified-phone writer. Customer-order creation enforces the same predicate and snapshots the phone before any pricing or external side effect. The frontend auth store hydrates the server's `phone_verified` truth, a shared hook owns Telegram contact prompting and bounded polling, and `App` hard-gates customer routes while staff/admin routes and QR resolution continue independently.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy async, PostgreSQL 16, pytest, React 19, TypeScript 5.7, Zustand 5, React Router 6, i18next, Vitest, Testing Library.

## Global Constraints

- This is a coordinated pre-launch cutover. Do not add request-phone compatibility behavior or feature activation flags.
- Preserve both currently supported table QR start parameters: issued numeric `t2_...` links and legacy `t_...` links. QR resolution must continue while the customer gate is visible.
- Staff and admin destinations bypass the customer phone gate. Customer routes never render until `phone_verified` is true.
- Only a Telegram contact update with a configured valid webhook secret and `message.from.id == contact.user_id` may create verified phone state.
- Canonical phones are `+` followed by 8–15 digits. Input may contain one optional leading `+`, digits, spaces, hyphens, and parentheses only; reject all other characters.
- Verified state requires a canonical phone, verification receipt time, message time, update ID, and a SHA-256 fingerprint bound to Telegram ID plus canonical phone.
- Compare webhook ordering by `(message.date, update_id)`, message time first. A later message date is accepted even with a lower update ID; the update ID only orders same-second messages and deduplicates replays.
- A new customer order is rejected with HTTP 409 and code `phone_verification_required` before pricing, persistence, payment creation, or AliPOS submission when the profile is not verified.
- `phone_number` is not part of `OrderCreate`; manipulated requests containing it receive 422. Customer notes are at most 200 Unicode characters and over-limit requests receive 422 before side effects.
- A verified order stores the full phone only in `delivery_info.phoneNumber` and sets local `contact_phone_verified=true`. The provenance column must never enter AliPOS `deliveryInfo`.
- AliPOS always receives `Tel: <masked phone>` as the first comment line for a verified snapshot, plus one newline and the unchanged non-empty customer note. `Order.comment` stays unchanged.
- `+998901234567` masks exactly as `+998 90 *** 4567`. Generic valid numbers reveal the last four digits and at most the first three while hiding at least three digits.
- Do not log full phones, complete Telegram updates, credentials, or provider payloads. Do not add phone PII to table-inspection summaries.
- Do not deploy, place a live AliPOS order, or call live payment/provider mutations as part of this implementation.

## Test Environment

Run backend tests from `backend/`. The existing local PostgreSQL test listener is on `127.0.0.1:55432`; load credentials without printing them:

```bash
set -a
. /Users/khajievroma/Projects/restaurant-mini-app/.env
set +a
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest -q --tb=short
```

Run frontend tools directly, avoiding the bundled package-manager wrapper's install check:

```bash
env PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/usr/bin:/bin" ./node_modules/.bin/vitest run
env PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/usr/bin:/bin" ./node_modules/.bin/tsc --noEmit
```

The clean baseline at plan creation is backend Ruff passing, backend `395 passed, 1 skipped`, frontend `206 passed`, and frontend typecheck passing.

### Task 1: Add verified-phone persistence and profile contracts

**Files:**

- Create: `backend/app/services/phone_verification_service.py`
- Create: `backend/tests/test_phone_verification_service.py`
- Create: `database/migrations/2026-07-19-telegram-verified-phone-gate.sql`
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/routers/users.py`
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/tests/api/test_users.py`
- Modify: `backend/tests/api/test_admin_users.py`
- Modify: `backend/tests/test_order_model.py`
- Modify: `database/init.sql`

**Interfaces to add:**

```python
class InvalidPhoneNumber(ValueError): ...

def normalize_phone_number(raw_phone: object) -> str: ...
def phone_verification_fingerprint(telegram_id: int, canonical_phone: str) -> str: ...
def is_phone_verified(user: object) -> bool: ...
def is_newer_contact_update(user: object, message_at: datetime.datetime, update_id: int) -> bool: ...
def mask_phone_number(canonical_phone: str) -> str: ...
```

Add nullable `phone_verified_at`, `phone_verified_fingerprint`, `phone_verified_message_at`, and `phone_verified_update_id` fields to `User`. Use timezone-aware SQLAlchemy datetime columns for the two timestamps. Add `contact_phone_verified`, non-null with Python and server defaults of false, to `Order`.

`UserResponse` and `SelfProfileResponse` must expose `phone_verified: bool` while excluding verification metadata from serialized output. Keep the existing `UserResponse.model_validate(user).model_dump()` call pattern working for both `/users/me` and admin user endpoints by deriving the boolean inside the response model from excluded metadata fields and the shared predicate.

`UserUpdate` accepts language only and uses Pydantic `extra="forbid"`; `PUT /users/me` with `phone_number` must return 422. Remove all phone mutation code from the user router. Admin role updates remain unchanged.

**Step 1: Write failing tests**

Cover all pure helpers before implementation:

- normalization accepts representative Telegram formatting and stores `+digits`;
- normalization rejects misplaced plus signs, letters, punctuation outside the allowlist, fewer than 8 digits, and more than 15 digits;
- fingerprints are deterministic, 64 lowercase hexadecimal characters, and change with Telegram ID or phone;
- verification is false for every missing metadata field and for a fingerprint mismatch, and true only for a complete matching state;
- ordering accepts a later message date with a lower update ID, accepts a greater update ID in the same second, and rejects equal/older pairs;
- Uzbek and generic masks satisfy the exact display and hidden-digit rules.

Add API/model tests for `phone_verified`, metadata exclusion, rejected profile phone writes, language updates, admin responses, and the order provenance default.

Run:

```bash
set -a
. /Users/khajievroma/Projects/restaurant-mini-app/.env
set +a
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest tests/test_phone_verification_service.py tests/api/test_users.py tests/api/test_admin_users.py tests/test_order_model.py -q
```

Expected RED: imports, columns, response fields, and 422 behavior are missing.

**Step 2: Implement the pure policy and additive schema**

Keep `phone_verification_service.py` independent of SQLAlchemy models by reading the required attributes from a structural object. Use a strict allowlist before removing visual separators. Use `hmac.compare_digest` for a same-length fingerprint comparison. The generic mask uses `prefix_length = min(3, digit_count - 7)`, which preserves at least three hidden digits and the last four.

Update both the initial schema and an idempotent migration with `ADD COLUMN IF NOT EXISTS`; do not mark any existing phone verified.

**Step 3: Prove the focused behavior and full backend suite**

Run the focused command again, then:

```bash
set -a
. /Users/khajievroma/Projects/restaurant-mini-app/.env
set +a
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/ruff check .
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest -q --tb=short
```

Expected GREEN: focused tests and full backend lint/tests pass; no full phone appears in captured logs.

**Step 4: Commit**

```bash
git add backend/app/services/phone_verification_service.py backend/app/models/models.py backend/app/schemas/user.py backend/app/routers/users.py backend/app/routers/admin.py backend/tests/test_phone_verification_service.py backend/tests/api/test_users.py backend/tests/api/test_admin_users.py backend/tests/test_order_model.py database/init.sql database/migrations/2026-07-19-telegram-verified-phone-gate.sql
git commit -m "feat: add verified phone state"
```

### Task 2: Harden the Telegram contact webhook

**Files:**

- Modify: `backend/app/routers/webhooks.py`
- Modify: `backend/tests/api/test_webhooks.py`

**Required webhook transaction:**

1. Return 503 before parsing/processing an update when `TELEGRAM_WEBHOOK_SECRET` is empty.
2. Return 401 for a missing or mismatched request secret.
3. Require exact integers for `update_id`, `message.date`, `message.from.id`, and `contact.user_id`; booleans are not valid integers here.
4. Return 200 and ignore missing/incomplete contact updates, sender/contact mismatches, invalid phone values, and unknown users.
5. Normalize the phone, lock the matching `User` row with `FOR UPDATE`, compare `(message time, update ID)`, and return 200 without changes for a replay or stale pair.
6. In one transaction, write canonical phone, server receipt time, fingerprint, Telegram message time, and update ID.
7. Log only outcome, update ID, duration, and the existing masked Telegram identifier.

**Step 1: Extend webhook tests and observe RED**

Add focused cases for missing secret, missing header, strict structural fields, sender/contact mismatch, every normalization boundary, successful canonical persistence, all verification metadata, replay, older message, same-second tie-break, later message with lower update ID, verified phone replacement, unknown user, and two concurrent updates completing out of order.

For the concurrency case, use the existing separate-session fixture and assert the final row contains the ordering-pair winner with a matching fingerprint. Never include a raw phone in assertion failure messages or log captures beyond direct in-memory row equality.

Run:

```bash
set -a
. /Users/khajievroma/Projects/restaurant-mini-app/.env
set +a
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest tests/api/test_webhooks.py -k telegram_bot_webhook -q
```

Expected RED: current webhook fails open without a configured secret, accepts another contact identity, stores raw formatting, and has no replay/concurrency ordering metadata.

**Step 2: Implement the fail-closed writer**

Reuse only Task 1 helpers. Convert `message.date` from Unix seconds to a UTC-aware datetime. Do not fall back from a missing `contact.user_id` to the sender. Keep ignored Telegram updates at HTTP 200 so Telegram does not repeatedly redeliver structurally complete but unacceptable contact cards.

**Step 3: Verify focused and full backend suites**

Run the focused command, Ruff, and the complete backend pytest command from Task 1.

Expected GREEN: webhook cases pass, full backend remains green, and captured logs contain no complete phone or request body.

**Step 4: Commit**

```bash
git add backend/app/routers/webhooks.py backend/tests/api/test_webhooks.py
git commit -m "feat: verify Telegram contact updates"
```

### Task 3: Enforce verified snapshots and compose AliPOS comments

**Files:**

- Modify: `backend/app/schemas/order.py`
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/routers/orders.py`
- Modify: `backend/tests/test_order_service.py`
- Modify: `backend/tests/api/test_orders_create.py`
- Modify: `backend/tests/api/test_staff_delivery.py`

**Backend contract:**

- Change `OrderCreate.comment` to an optional Pydantic field with maximum length 200 and set `extra="forbid"` on `OrderCreate`.
- Remove `phone_number` from `OrderCreate`.
- Add a specific `PhoneVerificationRequired` service exception and map it to:

```json
{"detail":{"code":"phone_verification_required","message":"Share your phone through Telegram before placing an order."}}
```

- Preserve the existing idempotency lookup as the first service action. For a new order, verify the current profile immediately after that lookup and before payment capability checks, address/table resolution, pricing, persistence, or provider calls.
- Build `delivery_info.phoneNumber` only from the verified canonical profile phone and persist `contact_phone_verified=True`.
- Keep idempotent replays bound to their original snapshot even if the current profile later changes or becomes inconsistent.
- Add a pure AliPOS comment composer used by `_build_alipos_payload`. With provenance true it validates and masks the snapshot phone, returns `Tel: <mask>` plus the exact stored note on the next line when non-empty, and never mutates `Order.comment`. With provenance false it returns the historical stored comment only.
- `build_staff_order_response` returns the order snapshot phone when provenance is true and otherwise retains its existing user-profile fallback. Do not change PII-free table workspace responses.

**Step 1: Write failing service and API tests**

Cover:

- unverified new delivery and table orders return the stable 409 before `price_cart`, Multicard, AliPOS, or a new database row;
- an idempotent replay returns the original order before current-profile verification;
- manipulated `phone_number` and over-200-character notes return 422 before the service is called;
- a verified order ignores all browser phone influence, snapshots the canonical profile phone, and sets provenance true;
- later profile phone replacement does not change the persisted snapshot or rebuilt AliPOS payload;
- AliPOS receives full snapshot phone only in structured `deliveryInfo`, exact Uzbek/generic masked comment headers, optional newline/note behavior, and no provenance field;
- an unverified pre-release row keeps its stored comment and never gains a verified-looking header;
- local `Order.comment` remains exactly the customer note;
- staff delivery detail uses a verified snapshot first and uses the existing profile fallback only for an unverified row.

Run:

```bash
set -a
. /Users/khajievroma/Projects/restaurant-mini-app/.env
set +a
POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest tests/test_order_service.py tests/api/test_orders_create.py tests/api/test_staff_delivery.py -q
```

Expected RED: request phone is still required and authoritative, unverified profiles can order, provenance is absent, and AliPOS comments contain only the customer note.

**Step 2: Implement the enforcement boundary**

Keep the check and snapshot code in `create_customer_order`; do not distribute trust decisions across routers. Keep comment composition adjacent to `_build_alipos_payload` and delegate canonical masking to Task 1. A corrupted row claiming verified provenance without a valid snapshot phone must fail payload construction closed instead of sending an unmasked value.

**Step 3: Verify focused and full backend suites**

Run the focused command, Ruff, and complete backend pytest suite.

Expected GREEN: exact payload and side-effect-order tests pass, with all existing payment, reconciliation, table, and staff behavior still green.

**Step 4: Commit**

```bash
git add backend/app/schemas/order.py backend/app/services/order_service.py backend/app/routers/orders.py backend/tests/test_order_service.py backend/tests/api/test_orders_create.py backend/tests/api/test_staff_delivery.py
git commit -m "feat: enforce verified order phones"
```

### Task 4: Add the shared customer phone gate and automatic auth behavior

**Files:**

- Create: `frontend/src/hooks/usePhoneVerification.ts`
- Create: `frontend/src/hooks/usePhoneVerification.test.tsx`
- Create: `frontend/src/components/auth/PhoneVerificationGate.tsx`
- Create: `frontend/src/components/auth/PhoneVerificationGate.test.tsx`
- Modify: `frontend/src/types/telegram.d.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/authStore.ts`
- Modify: `frontend/src/stores/__tests__/authStore.test.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/i18n/locales/uz.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Shared hook contract:**

```typescript
type PhoneVerificationStatus =
  | 'ready'
  | 'requesting'
  | 'verifying'
  | 'declined'
  | 'delayed'
  | 'unsupported'
  | 'outside_telegram'
  | 'network_error';

interface PhoneVerificationController {
  status: PhoneVerificationStatus;
  requestPhone: () => void;
  checkAgain: () => Promise<void>;
}

function usePhoneVerification(options: { autoRequest: boolean }): PhoneVerificationController;
```

The hook owns all `requestContact` use and `/users/me` polling. A shared contact callback triggers an immediate profile request and then one every 1.5 seconds, with at most ten total profile requests. Any response with `phone_verified=true` is accepted into the auth store and unlocks the app. At least one successful-but-unverified response ending the cycle produces `delayed`; a cycle containing only network failures produces `network_error`.

Keep the automatic prompt-once claim in module scope and claim it before calling Telegram, so StrictMode effects and remounts cannot open a second prompt in the same Mini App JavaScript launch. A decline never auto-prompts again; a visible customer action may call `requestPhone` repeatedly. Make `TelegramWebApp.requestContact` optional in the type so old clients enter `unsupported` instead of throwing.

**Auth and routing contract:**

- Add `phone_verified` to the frontend `User` contract and add a narrowly named auth-store action that accepts a profile returned by `/users/me` for the hook.
- Delete `manual_logout` as an auth decision. Remove any stale marker during bootstrap and always exchange present Telegram `initData`, even when a marker or JWT exists.
- Keep staff/admin logout clearing only the current token/state; the next Mini App launch auto-authenticates. Do not reauthenticate immediately in the same mounted page.
- Make authentication failures retryable instead of rendering customer content.
- In `App`, finish auth/role hydration first, route staff/admin unchanged, then render `PhoneVerificationGate` for an unverified customer instead of any customer route element.
- Leave the existing start-parameter effect independent of the gate. Both `t2_...` and `t_...` resolve exactly once into the table store while the gate is visible and remain available after unlock.
- Translate every new gate and auth-retry string in Uzbek, Russian, and English.

**Step 1: Write failing hook, store, gate, and route tests**

Use fake timers for the 1.5-second schedule and prove exact request counts. Cover immediate success, delayed success, ten-request timeout, all-network-error cycle, decline, manual retry, check again, unsupported Telegram, outside Telegram, automatic prompt once under StrictMode, and no automatic repeat after remount.

Extend store/App tests for stale `manual_logout`, Telegram auth on every launch, retryable auth failure, no customer-content flash, customer gate/unlock, and staff/admin bypass. Add QR cases for both formats proving resolution begins behind the gate and the resolved table store is unchanged when the verified profile unlocks the menu.

Run:

```bash
env PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/usr/bin:/bin" ./node_modules/.bin/vitest run src/hooks/usePhoneVerification.test.tsx src/components/auth/PhoneVerificationGate.test.tsx src/stores/__tests__/authStore.test.ts src/App.test.tsx
```

Expected RED: the shared hook/gate and profile truth field do not exist, manual logout suppresses launch auth, and customer routes are not phone-gated.

**Step 2: Implement the shared flow and route boundary**

Keep gate presentation in the component and Telegram/polling state in the hook. Do not clear the table store on any verification error. The visible `Share phone` action remains present in ready, declined, delayed, unsupported, outside-Telegram, and network-error presentations where the action is technically possible; unsupported/outside states instead provide update/reopen guidance without manual phone entry.

**Step 3: Verify focused, full frontend, and types**

Run the focused command, then the complete frontend Vitest and TypeScript commands from Test Environment.

Expected GREEN: focused and full suites pass with no `act` warnings, unhandled promise rejections, timer leaks, or hard-coded new customer copy.

**Step 4: Commit**

```bash
git add frontend/src/hooks/usePhoneVerification.ts frontend/src/hooks/usePhoneVerification.test.tsx frontend/src/components/auth/PhoneVerificationGate.tsx frontend/src/components/auth/PhoneVerificationGate.test.tsx frontend/src/types/telegram.d.ts frontend/src/types/api.ts frontend/src/stores/authStore.ts frontend/src/stores/__tests__/authStore.test.ts frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json
git commit -m "feat: gate customers on Telegram phone"
```

### Task 5: Make checkout and profile verified-phone-only

**Files:**

- Create: `frontend/src/utils/phone.ts`
- Create: `frontend/src/utils/__tests__/phone.test.ts`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanProfilePage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanProfilePage.test.tsx`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/i18n/locales/uz.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`

**UI contract:**

- Add a frontend display-only `maskPhoneNumber` utility matching the server's Uzbek and generic display rules. It never controls the AliPOS payload.
- Remove checkout phone state, editable input, profile fetch solely for phone, validation, and `phone_number` order payload property.
- Display the authenticated verified phone read-only in checkout. The `Update through Telegram` action uses `usePhoneVerification({autoRequest:false})` and never accepts typed input.
- Detect a backend `phone_verification_required` response, refresh the authenticated profile so `App` can re-enter the gate, preserve cart/table/request ID, and show translated guidance.
- Set the customer-note control to `maxLength={200}`, display a translated remaining/count indicator, and keep the exact note in the payload.
- Profile displays only a masked verified phone and an always-available `Update through Telegram` action using the same hook. Remove the customer logout section. Keep staff/admin profile logout behavior in `StaffProfilePage` unchanged.
- `CreateOrderPayload` has no `phone_number` property.
- Translate every new checkout/profile label in all three locale files.

**Step 1: Write failing utility and page tests**

Cover exact Uzbek/generic masks, no editable phone textbox, no phone in create-order payload, read-only masked display, shared update action, note boundary at 200/201 characters, the stable backend verification error returning the app to its gate without losing checkout state, masked profile display, profile phone refresh through the shared hook, and absence of customer logout.

Run:

```bash
env PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/usr/bin:/bin" ./node_modules/.bin/vitest run src/utils/__tests__/phone.test.ts src/pages/artisan/ArtisanCheckoutPage.test.tsx src/pages/artisan/ArtisanProfilePage.test.tsx
```

Expected RED: checkout still owns an editable phone and submits it, profile exposes the full phone and customer logout, and no shared update action or 200-character UI boundary exists.

**Step 2: Implement the read-only surfaces**

Use the hydrated auth-store profile as the phone source. Keep table checkout from fetching addresses, preserve the existing client-request-ID retry behavior, and do not restructure unrelated checkout/payment code.

**Step 3: Verify focused, full frontend, and types**

Run the focused command, complete frontend Vitest, and TypeScript commands.

Expected GREEN: all page contracts pass, the type system rejects request-phone payloads, and all existing checkout/payment/table behavior remains green.

**Step 4: Commit**

```bash
git add frontend/src/utils/phone.ts frontend/src/utils/__tests__/phone.test.ts frontend/src/pages/artisan/ArtisanCheckoutPage.tsx frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx frontend/src/pages/artisan/ArtisanProfilePage.tsx frontend/src/pages/artisan/ArtisanProfilePage.test.tsx frontend/src/types/api.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json
git commit -m "feat: use verified phone in customer UI"
```

## Final Verification

After all five task reviews are clean:

1. Run `git diff --check` and confirm only intended files differ from the numeric-QR production base.
2. Run backend Ruff and the full backend pytest suite using the Test Environment command.
3. Run full frontend Vitest, TypeScript typecheck, ESLint, and production build directly from `node_modules/.bin` with the bundled Node path.
4. Run the existing QR script tests from the repository root with the backend virtualenv to prove the issued asset tooling remains intact:

```bash
backend/.venv/bin/python -m pytest tests/scripts/test_download_table_manifest.py tests/scripts/test_generate_table_qr_pngs.py -q
```

5. Search changed source and captured test reports for accidental complete phone values, provider credentials, or payload logging; test fixtures may contain synthetic phone values but application logs must not.
6. Generate one whole-branch review package from base `5c9b684` through final HEAD and dispatch the strongest available final reviewer.
7. Fix every Critical or Important finding through a dedicated subagent, rerun affected/full checks, regenerate the package, and obtain a clean re-review before finishing the branch.

