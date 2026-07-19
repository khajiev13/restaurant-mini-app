# Release Safety Task 9 Final Review Fix Report

## Status

**DONE.** All 10 Important and 2 Minor findings in
`/tmp/final-release-review-7c2580d.md` were accepted and fixed. No finding was
rejected. The work preserves the approved inspection-only table scope, leaves
table online payment disabled by default, keeps provider mutations exact-once
under unknown outcomes, and performs provider I/O outside row-lock
transactions.

Reviewed starting candidate:
`7c2580d99a39ebb313ca4b2ff09fd9431ee8d10f`.

Implementation commits:

- `759b178` — `fix: harden provider release safety`
- `654b6d8` — `fix: make staff release UI accessible`

The rollout update and this report are committed together after the report is
created. The final handoff records the complete exact commit range.

## Finding Disposition

### Important 1 — AliPOS mutation redirects

Accepted and fixed. AliPOS order POST and cancellation DELETE now use
`follow_redirects=False`. Every 3xx after dispatch is an unknown outcome, and
neither mutation is retried. Mock-transport tests prove a 307/308 redirect
target is never called.

### Important 2 — atomic paid rejection and refund queueing

Accepted and fixed. The conditional AliPOS failure finalizer now persists the
submission failure and, for a paid order without a refund attempt, changes
`payment_status` to `refund_pending` and `refund_sync_status` to `queued` in the
same database statement and commit. It returns whether post-commit refund
dispatch is required. A test observes the committed row at the dispatch
boundary and proves there is no charged-without-refund crash gap.

### Important 3 — startup recovery preserving webhook state

Accepted and fixed. Interrupted `sending` recovery still records the AliPOS
outcome as unknown, but changes local status to `SYNC_UNKNOWN` only from `NEW`
or `PAID_AWAITING_RESTAURANT`. An advanced webhook status and order number are
preserved.

### Important 4 — durable Multicard invoice cancellation

Accepted and fixed. A nullable `orders.invoice_cancel_status VARCHAR(32)` field
and idempotent `2026-07-18-release-safety.sql` migration implement
`queued -> sending -> cancelled|unknown`:

- `queued` and then `sending` are committed before the DELETE;
- the single DELETE runs after the transaction/row lock is released;
- token/client-entry failures that prove DELETE was not invoked return to the
  retryable `queued` state;
- every possibly invoked DELETE failure becomes absorbing `unknown`, and
  customer retry, cash switch, expiry, and startup recovery never repeat it;
- success finalizes only a still-pending compatible row, so an authentic paid
  callback wins;
- expiry changes a locally cancelled invoice to `expired` only after confirmed
  cancellation;
- the cash-switch transition is conditional, so a paid callback that arrives
  after cancellation finalization but before cash conversion also wins.

Tests inspect the durable `sending` state from a second session, acquire the
same order row with `NOWAIT` during provider I/O, prove one DELETE across
repeated customer/switch/expiry calls, cover interrupted startup recovery, and
cover both callback race windows.

### Important 5 — stale/out-of-order AliPOS status reconciliation

Accepted and fixed. A nullable `orders.alipos_status_updated_at TIMESTAMP`
field stores provider freshness. Status updates now:

- normalize the provider timestamp to naive UTC;
- reject older provider timestamps;
- reject backward transitions across known ordered states
  `NEW -> ACCEPTED_BY_RESTAURANT -> READY -> TAKEN_BY_COURIER -> DELIVERED`;
- compare the current status, order number, and provider timestamp in a
  conditional update;
- carry the exact status-read claim timestamp through table reconciliation and
  require it during finalization.

The central database helper refreshes the ORM row before deciding, so a faster
webhook/local delivery commit is also reflected in the response object. Tests
cover old timestamps, backward transitions, a webhook race, and a reclaimed
claim rejecting the older worker.

### Important 6 — uncached checkout composition

Accepted and fixed. `alipos_api.get_menu()` now has an explicit `use_cache`
option. Customer browsing retains the five-minute cache; checkout pricing uses
`use_cache=False`. Every successful uncached response also refreshes the shared
cache. Tests prove the provider is called despite a warm cache and that both
repricing and subsequent browsing use the fresh composition.

### Important 7 — AliPOS redaction

Accepted and fixed. Shared read paths log only a bounded operation category,
HTTP status, and retry count. They never log an identifier-bearing path,
provider body, or raw transport exception. Token, HTTP, transport, malformed
JSON, halls-directory, create, and cancel failures raise bounded messages with
provider causes suppressed. Canary tests assert that provider IDs, URLs,
credentials, and response text are absent from exceptions and logs.

### Important 8 — reconcilable staff-take timeout

Accepted and fixed. The staff take service returns the already loaded order
immediately after the assignment commit, removing post-commit reload I/O from
the operation deadline. The frontend classifies only a no-response Axios error
or the exact take-specific 503/detail pair as ambiguous and runs the existing
bounded active-order GET reconciliation; unrelated 503 responses remain
definitive. Tests cover the post-commit boundary and exact response classifier.

### Important 9 — semantic staff order navigation

Accepted and fixed. Pointer navigation was removed from the plain `article`.
Every available and completed card has a direct semantic detail `Link`, as a
sibling of the separate Take button, with an order-specific accessible name, a
48px target, and visible `:focus-visible` styling. A keyboard test activates
the link with Enter and reaches the detail route.

### Important 10 — accessible delivery dialog

Accepted and fixed. The dialog is named with `aria-labelledby`, receives
initial focus, traps Tab/Shift+Tab, closes on Escape, restores focus to the
trigger, and applies/restores `inert` on background branches. Tests assert the
accessible name, cash-checkbox initial focus, both wrap directions, inert
background, Escape close, and trigger restoration.

### Minor 1 — 44px table-context action

Accepted and fixed. `TableContextBar` now has both minimum dimensions at 44px,
with a UI assertion for the rendered inline contract.

### Minor 2 — empty directory with synthetic tables

Accepted and fixed. Directory emptiness counts only listed AliPOS halls/tables.
The empty-directory notice and Retry action can coexist with retained
`is_listed=false` synthetic table cards, and the filter-empty message no longer
contradicts a truly empty live directory. The regression test exercises the
coexisting notice, retry, Unlisted hall, and active local order.

## Additional Safety Fix Found During Self-Review

Moving invoice DELETE outside the lock exposed a second callback window after
confirmed cancellation but before cash conversion. A new red test showed the
stale ORM object could overwrite a paid callback and returned HTTP 200. Cash
conversion is now one conditional `UPDATE` requiring the exact confirmed
inactive payment state. The same test and adjacent switch tests pass, the paid
callback remains authoritative, and no AliPOS submission is dispatched.

## Files Changed

Backend/provider state:

- `backend/app/models/models.py`
- `backend/app/routers/orders.py`
- `backend/app/routers/webhooks.py`
- `backend/app/services/alipos_api.py`
- `backend/app/services/menu_catalog_service.py`
- `backend/app/services/multicard_api.py`
- `backend/app/services/order_service.py`
- `backend/app/services/order_status_service.py`
- `backend/app/services/staff_delivery_service.py`
- `backend/app/services/staff_table_service.py`
- `backend/tests/api/test_orders_status.py`
- `backend/tests/api/test_staff_delivery.py`
- `backend/tests/api/test_staff_tables.py`
- `backend/tests/test_menu_catalog_service.py`
- `backend/tests/test_order_model.py`
- `backend/tests/test_order_service.py`
- `database/init.sql`
- `database/migrations/2026-07-18-release-safety.sql`

Frontend/accessibility:

- `frontend/src/components/artisan/TableContextBar.tsx`
- `frontend/src/components/artisan/TableContextBar.test.tsx`
- `frontend/src/components/staff/ConfirmDeliveredSheet.tsx`
- `frontend/src/components/staff/StaffOrderCard.tsx`
- `frontend/src/components/staff/staff-order-card.css`
- `frontend/src/pages/staff/StaffOrdersPage.test.tsx`
- `frontend/src/pages/staff/StaffTablesPage.tsx`
- `frontend/src/pages/staff/StaffTablesPage.test.tsx`
- `frontend/src/services/staffApi.ts`
- `frontend/src/services/staffApi.test.ts`

Release documentation:

- `docs/admin-staff-table-inspection-rollout.md`
- `.superpowers/sdd/release-safety-task-9-fix-report.md`

## TDD and Focused Verification

Each behavior change began with a failing regression test. Representative RED
evidence included:

- redirect mutation tests observed a second request before redirects were
  disabled;
- the paid-rejection observer saw `failed` without a refund queue before the
  finalizer became atomic;
- startup recovery regressed an advanced status to `SYNC_UNKNOWN`;
- invoice-cancellation tests observed no durable attempt and repeatable DELETE;
- stale status tests allowed older `NEW` to overwrite accepted/ready state;
- checkout pricing returned the warm composition cache;
- AliPOS canaries appeared in paths/bodies/exception causes;
- the take-specific 503 was classified as definitive;
- order detail navigation and modal keyboard/focus tests failed;
- the 40px context action and synthetic-only empty-directory scenario failed;
- malformed AliPOS status JSON initially leaked its decoder exception;
- the additional callback/cash-switch test returned 200 and overwrote `paid`
  before the conditional transition.

Focused green milestones:

- invoice/model safety: `12 passed`;
- status ordering/race safety: `5 passed`;
- affected backend suite after the stale-object correction: `271 passed`;
- callback/cash-switch race and adjacent switch cases: `3 passed`;
- focused frontend release-safety set: `39 passed`.

## Complete Local Verification

All backend commands used Python 3.12.11 from
`/Users/khajievroma/Projects/restaurant-mini-app/backend/.venv312/bin/python`,
loaded the root `.env` without printing it, and overrode only
`POSTGRES_HOST=127.0.0.1` and `POSTGRES_PORT=55432` for the approved local test
database.

```bash
python -m pytest backend/tests -q
```

Result: exit 0, `353 passed, 1 skipped, 10 warnings in 37.71s`. The skipped
test is the explicitly opt-in destructive final-admin proof. Warnings are the
repository's existing FastAPI `on_event` deprecations.

```bash
python -m ruff check backend/app backend/tests
```

Result: exit 0, `All checks passed!`.

```bash
cd frontend
npm test -- --run
npm run typecheck
npm run build
npm run lint
```

Results:

- Vitest: exit 0, 28 files and `204 passed`;
- typecheck: exit 0;
- Vite production build: exit 0, 168 modules transformed;
- ESLint: exit 0, 0 errors and one pre-existing
  `MapPickerOverlay.tsx` exhaustive-deps warning.

```bash
git diff --check
```

Result: exit 0 with no output.

All four release migrations were applied twice in chronological order to the
approved loopback PostgreSQL service with `ON_ERROR_STOP=1`; the final marker
was `migrations_twice_ok`. The new migration is idempotent on both passes.

One affected-suite invocation was excluded from evidence because sourcing the
environment without the loopback override selected Docker-only hostname
`postgres`, so database fixtures stopped at DNS resolution. The unchanged
suite was rerun with the documented loopback override and passed 271/271; the
complete backend suite then passed as recorded above.

## Migration and Runbook Audit

`docs/admin-staff-table-inspection-rollout.md` now treats the release as four
ordered migrations in every authoritative candidate-existence, local
idempotency, production-application, schema-comparison, and final-checklist
location. The schema gates include exact metadata for
`invoice_cancel_status VARCHAR(32)` and
`alipos_status_updated_at TIMESTAMP WITHOUT TIME ZONE`. A repository search
found no remaining authoritative “three migrations” wording; unrelated text
about three CI jobs remains unchanged.

## Scope and Handoff Boundary

- No production host, provider, Telegram, or customer request was made.
- No Docker service or image was changed.
- No secret value was printed, edited, or rotated.
- No remote branch was pushed and no pull request was created.
- No unrelated worktree or branch was edited.
- `INPLACE_ONLINE_PAYMENT_ENABLED` remains default false.
- No table occupancy, reservation, settlement, append-order, or POS-merge
  behavior was added.

Task 9 still requires fresh exact-SHA CI, disposable destructive-admin proof,
Compose/runbook gates, the browser/language/viewport matrix, independent
whole-release review, and the production runbook. Those operations were not
authorized for this fix subtask and must use the final exact SHA; older
candidate evidence is stale.

## Rejected Findings and Concerns

Rejected findings: **none**.

No release-blocking implementation concern remains. Non-blocking verification
noise consists of the existing FastAPI deprecation warnings, Vitest's existing
Node `--localstorage-file` warnings, one pre-existing frontend lint warning,
and the expected opt-in destructive-test skip.
