# Telegram-Verified Customer Phone Gate

**Date:** 2026-07-19
**Status:** Approved design
**Scope:** Customer authentication, Telegram phone verification, order contact snapshots, and masked AliPOS comments

**Pre-launch decision:** No customers have started using the Mini App yet. The
release is therefore a coordinated clean cut: old browser payloads do not need
a compatibility window, verified-phone enforcement is unconditional, and the
masked AliPOS comment header is always composed for verified orders.

## Summary

Every customer who opens the Mini App must authenticate through Telegram and
share their own phone number before any customer-facing UI route becomes
usable.
The phone number is accepted only through Telegram's native contact-sharing
flow, persisted as verified profile data, and enforced again by the backend
when an order is created.

The backend copies the verified phone into an immutable order snapshot and
sends the full value in AliPOS's structured `deliveryInfo.phoneNumber` field.
The AliPOS order comment also receives a masked value for quick recognition,
for example `Tel: +998 90 *** 4567`, followed by the customer's optional note.
The original customer note remains unchanged in the local database.

## Goals

- Authenticate Telegram customers automatically on every Mini App launch.
- Block all customer UI routes until the customer's own phone is verified.
- Preserve a scanned QR/table context while authentication and verification
  complete.
- Prevent a manipulated browser request from substituting an arbitrary phone.
- Give AliPOS operators a masked, recognizable phone reference without
  printing the full number in the free-form comment.
- Keep a full, immutable order contact snapshot for AliPOS's structured field
  and authorized operational use.
- Provide clear retry states for declined prompts, webhook delay, old Telegram
  clients, authentication errors, and network errors.

## Non-goals

- SMS OTP, a manually typed phone fallback, or a non-Telegram login system.
- Requiring customer phone verification for staff or admin routes.
- Changing QR contents, table-code formats, table resolution, or table access
  token semantics.
- Making phone numbers unique across users.
- Printing a complete phone number in the AliPOS comment.
- Exposing customer phone data in table-inspection summaries that currently
  exclude customer PII.
- Changing AliPOS order retry, reconciliation, payment, or cancellation rules.
- Deploying to production or placing a live AliPOS order as part of the code
  implementation without separate authorization.

## Current Behavior

Telegram identity authentication and phone collection are currently separate:

1. `frontend/src/App.tsx` calls `bootstrapAuth()` on launch.
2. `frontend/src/stores/authStore.ts` exchanges valid Telegram `initData` for a
   JWT and hydrates `/users/me`.
3. First authentication creates a `users` row with Telegram identity fields,
   but no phone.
4. `ArtisanProfilePage` can call `Telegram.WebApp.requestContact()` and poll
   `/users/me` while `/api/webhooks/bot` persists the shared contact.
5. Checkout otherwise permits a first-time customer to type an arbitrary phone
   inline. That number is copied into the order's `delivery_info`, but it does
   not update the user profile.
6. AliPOS already receives the submitted phone in
   `deliveryInfo.phoneNumber`; the phone is not included in `comment`.

This permits an unverified checkout phone, produces inconsistent profile and
order contact data, and leaves phone collection until checkout instead of
making it a first-run requirement.

## Considered Approaches

### 1. Explicit Telegram verification with backend enforcement — selected

Add verification metadata, accept a verified phone only from a protected
Telegram contact webhook, block the customer shell, and derive order contact
data on the server. Existing phone values require one-time re-verification.

This adds a small migration and more tests, but it establishes an unambiguous
trust boundary and cannot be bypassed by a modified browser request.

### 2. Treat any non-empty profile phone as verified

This avoids a migration, but the existing profile API accepts a client-supplied
phone. A fabricated or historical unverified value would satisfy the gate, so
the application could not honestly describe the phone as Telegram-verified.

### 3. Frontend-only contact gate

This is the smallest visible change, but direct API calls and stale frontends
could continue creating orders with arbitrary phone numbers. It does not meet
the requirement that the phone be authoritative.

## Architecture

The feature has four focused boundaries:

1. **Authentication bootstrap** establishes the Telegram user and role.
2. **Customer phone gate** owns the native prompt, polling, and retry states.
3. **Phone verification backend** owns trust, normalization, and verification
   metadata.
4. **Order contact policy** enforces verification, creates an immutable
   snapshot, and formats the outbound AliPOS comment.

Table resolution remains independent. A valid QR start parameter continues to
resolve and save to the existing session-scoped table store while the phone
gate covers the customer UI. Once verification succeeds, the customer lands on
the already-resolved table menu rather than having to scan again.

## Data Model

Add four nullable verification columns to `users` and one provenance column to
`orders`:

```text
users.phone_verified_at TIMESTAMPTZ NULL
users.phone_verified_fingerprint VARCHAR(64) NULL
users.phone_verified_message_at TIMESTAMPTZ NULL
users.phone_verified_update_id BIGINT NULL
orders.contact_phone_verified BOOLEAN NOT NULL DEFAULT FALSE
```

Semantics:

- No phone or incomplete verification metadata: no verified phone is known.
- A phone with no matching fingerprint: a pre-launch value or a value changed by
  an older writer; the customer must share again.
- A phone, UTC verification timestamp, matching fingerprint, and accepted
  Telegram message-time/update-ID pair: the current profile phone was received
  from the protected Telegram contact webhook.

The fingerprint is SHA-256 over the stable Telegram user ID, a separator, and
the canonical phone. It is an integrity binding, not a password or a claim that
the phone is secret. This binding prevents an older application version from
changing `phone_number` while accidentally leaving the new release's verified
state valid.

The migration does not infer verification for any existing value. No existing
phone is deleted, but any test, operator, or pre-launch row without complete
matching metadata must complete the gate once.

All four verification fields are refreshed whenever the customer successfully
shares their current Telegram phone again. Historical orders remain unchanged.
The timestamp and order snapshot immutability are application invariants; the
database columns and JSON value are not inherently immutable.

`orders.contact_phone_verified` records whether that order's
`delivery_info.phoneNumber` snapshot came from a profile that satisfied the
full verification predicate. Keeping provenance outside `delivery_info`
prevents an internal flag from leaking into the AliPOS `deliveryInfo` payload.
Pre-release and manually created rows receive the safe database default
`false`.

## Authentication and Route Gating

When valid Telegram `initData` exists, authentication always runs. A previous
`manual_logout` marker must not suppress authentication on a new Telegram Mini
App launch, regardless of the eventual role. The application remains bound to
the Telegram account that opened the Mini App. Remove the customer logout
action because it cannot switch that Telegram identity. Staff/admin logout ends
the current in-app session, but the next Telegram launch authenticates again.

The route decision order is:

1. Authenticate Telegram `initData` and hydrate `/users/me`.
2. Resolve the authenticated role.
3. Route staff and admins through their existing role-specific shells.
4. For a customer, inspect `phone_verified`.
5. Render the customer routes only when it is true; otherwise render the
   full-screen phone gate.

Customer navigation, menu content, checkout, orders, profile, and table-mode
controls are not interactive behind the gate. This feature does not change the
authorization of existing public read/resolve endpoints; table resolution
remains public. The hard UI gate and order API invariant are the security
boundaries for this feature.

## Customer Phone Gate

Implement the gate as one focused component or hook-backed component rather
than duplicating contact logic across profile and checkout.

The gate has these states:

- **Authenticating:** existing role/auth loading shell.
- **Ready to request:** explains that a verified phone is required.
- **Native prompt open:** waits for Telegram's callback.
- **Verifying:** contact was shared and the app is polling `/users/me`.
- **Declined:** remains blocked and offers `Share phone` again.
- **Delayed:** polling ended without confirmation; offers `Check again` and
  `Share phone again`.
- **Unsupported:** `requestContact` is unavailable; asks the customer to update
  Telegram and reopen the Mini App.
- **Outside Telegram:** asks the customer to open the Mini App in Telegram.
- **Network/auth error:** shows a retry action without clearing table context.

All gate, checkout, profile, and error copy uses translation keys for every
locale supported by the implementation base; the feature does not introduce
hard-coded customer-facing English.

After authentication and profile hydration, the gate makes one best-effort
automatic `requestContact()` call per Mini App launch. The required `Share
phone` action remains visible so a client that requires a user gesture is never
stuck. Store the prompt-once guard outside a remounting component so React
StrictMode, route changes, and remounts cannot open the prompt twice. A declined
or failed prompt is never reopened automatically; subsequent attempts require a
customer tap.

When Telegram reports that the contact was shared, the gate checks the existing
profile endpoint immediately and then every 1.5 seconds, for at most ten total
requests. If none reports verification, the gate enters the explicit delayed
state. The UI unlocks only after the backend returns `phone_verified: true`, not
merely when Telegram's client callback returns success.

## Telegram Webhook Trust Boundary

The bot webhook is the only path that can set a phone as verified.

A contact update is accepted only when all of the following are true:

- `TELEGRAM_WEBHOOK_SECRET` is configured.
- The request contains the matching Telegram webhook secret header.
- The update contains an integer `update_id`, an integer `message.date`, a
  contact, and a sender.
- `message.from.id` equals `contact.user_id`.
- The authenticated Telegram user already exists.
- The phone can be normalized to `+` followed by 8–15 digits.
- The `(message.date, update_id)` pair sorts after the last accepted contact
  pair for that user.

The sender/contact equality check prevents a user from sharing another person's
contact card and assigning that phone to another profile. Lock the user row
while comparing the message-time/update-ID pair; this makes retries idempotent
and prevents an older or concurrently processed contact from overwriting a
newer phone. Message time is the primary ordering key because Telegram may
choose a random next `update_id` after at least one week without updates, as
documented in the official [Update contract](https://core.telegram.org/bots/api#update).
The update ID is only the same-second tie-breaker and replay identifier. The
authentication flow creates the user before the phone gate requests contact,
avoiding the normal first-run race in which an unknown user's contact would be
discarded.

Accepted updates set `phone_number`, the server receipt timestamp, the matching
fingerprint, the Telegram message timestamp, and the update ID in one
transaction. Replayed or older ordering pairs return `200` without changing
data. Rejected or incomplete updates do not alter user data. Logs include only
the update outcome and a masked internal user identifier needed for diagnosis,
never the full phone or the complete Telegram update.

If the server-side webhook secret is missing, the route returns `503` and does
not mark any phone verified. An invalid request secret returns `401`.
Structurally complete updates with a sender/contact mismatch return `200` as an
ignored Telegram update so they are not retried, but they do not alter user
data. Development and tests must configure a non-production secret explicitly
rather than relying on the current fail-open behavior.

## Profile API Contract

The authenticated user response adds:

```json
{
  "phone_number": "+998901234567",
  "phone_verified": true
}
```

The verification metadata does not need to be exposed to the browser. The
boolean is true only when the phone, timestamps, update ID, and recomputed
fingerprint all agree, so an inconsistent or older-writer row cannot unlock the
UI.

Authenticated profile updates can no longer set `phone_number`; a
`PUT /users/me` request that includes it returns `422`. Language and other
existing non-phone preferences remain writable. Sharing or changing a phone
always uses the same Telegram contact flow.

The profile page shows a masked, read-only number and an `Update through
Telegram` action. Updating repeats the native prompt and refreshes the verified
phone without altering previous order snapshots.

## Checkout Contract

Checkout no longer owns phone collection:

- Remove the editable phone input.
- Display the verified phone in masked, read-only form.
- Offer `Update through Telegram` rather than accepting typed replacement data.
- Do not block on address retrieval for table orders; retain the existing
  table/delivery distinction.
- Limit the optional customer note to 200 Unicode characters in both the
  frontend and `OrderCreate`; reject a longer note with `422` before pricing,
  payment, persistence, or AliPOS side effects.

Remove `phone_number` from `OrderCreate` and reject it as an unexpected field
with `422`. The new frontend omits it. A focused test must prove that a supplied
spoofed value is rejected before persistence, pricing, payment, or AliPOS side
effects.

## Order Enforcement and Contact Snapshot

After checking for an idempotent replay, but before pricing, payment creation,
or AliPOS submission for a new order, customer order creation evaluates the
same `phone_verified` predicate used by the profile response, including the
matching fingerprint and accepted update ID. This invariant applies to anyone
calling the customer order endpoint; staff/admin operational routes themselves
do not require customer phone verification.

If verification is incomplete, return HTTP `409` with a stable machine-readable
code:

```json
{
  "detail": {
    "code": "phone_verification_required",
    "message": "Share your phone through Telegram before placing an order."
  }
}
```

On success, the backend persists these separate local order fields:

```text
Order.delivery_info = {
  "clientName": "Customer Name",
  "phoneNumber": "+998901234567"
}
Order.contact_phone_verified = true
```

`contact_phone_verified` is an `orders` column, not part of the JSON object and
not an AliPOS request field. The separately composed outbound AliPOS
`deliveryInfo` contains `clientName` and the full `phoneNumber`, but never the
local provenance column.

The explicit order column distinguishes Telegram-verified snapshots from any
pre-release or manually created `delivery_info.phoneNumber` values. A verified
snapshot is authoritative for the order. A later profile phone change does not
modify it. AliPOS payloads and authorized staff order details use a verified
snapshot rather than the mutable current profile value.

The check occurs before creating local payment or external-order side effects.
An idempotency match for an existing order is handled first and is governed by
that order's original snapshot. If the existing order is still queued, any
submission path treats the snapshot as verified only when
`contact_phone_verified` is true; it does not consult the customer's current
profile or add a verified-looking phone header to an unverified snapshot. Idempotent
replay continues returning the original order.

## Phone Normalization and Masking

Telegram is the source of ownership verification; normalization establishes a
consistent stored representation:

1. Permit one optional leading `+`, digits, spaces, hyphens, and parentheses.
2. Reject letters or any other character instead of silently dropping it.
3. Remove the permitted visual separators and retain the digits.
4. Require 8–15 digits.
5. Store `+` followed by the digits.

For a 12-digit Uzbek number beginning with `998`, the outbound mask is:

```text
+998 90 *** 4567
```

It reveals the country code, two-digit operator prefix, and last four digits.
For another valid international number, the fallback always hides at least
three digits: reveal the last four digits and at most the first three, reducing
the visible prefix for short numbers as necessary. Separate the visible groups
with `***`. The masking helper is server-side and pure so the frontend cannot
choose what AliPOS receives.

## AliPOS Comment Composition

The full phone continues to use AliPOS's verified structured field:

```text
deliveryInfo.phoneNumber
```

For an order whose `contact_phone_verified` is true, the outbound free-form
comment is composed from the immutable order snapshot:

```text
Tel: +998 90 *** 4567
No onions, please
```

Rules:

- The first line is always `Tel: <masked phone>`.
- Add a newline and the customer's note only when the note is non-empty.
- Do not overwrite, prepend to, or otherwise mutate `Order.comment` in the
  local database.
- Rebuilding a payload for the same order produces the same phone line because
  it uses the order snapshot, not the current profile.
- The system-generated phone line never contains the full phone. A customer
  remains responsible for phone-like text they voluntarily type in their own
  note; the backend does not rewrite the locally stored note.
- An unverified pre-release row with `contact_phone_verified=false` keeps its historical
  comment behavior and does not gain a verified-looking masked phone line.

Existing AliPOS rules remain unchanged: the phone also remains in
`deliveryInfo.phoneNumber`, order creation is not automatically retried after an
unknown outcome, and table orders continue supplying their resolved `tableId`.
The formatter is unconditional for verified order snapshots. Automated tests
prove the exact outbound payload. Whether AliPOS visibly prints the line in a
particular operator layout remains an operational observation after deployment
and is not overstated as confirmed by unit tests.

## Staff and Admin Data

Where an authorized staff order response already exposes a customer phone, it
reads the immutable order snapshot when `contact_phone_verified` is true.
Unverified pre-release rows preserve the existing current-profile fallback and
must not present their snapshot as Telegram-verified.

This feature does not add customer identity or phone data to table-inspection
summary endpoints that intentionally exclude PII. Admin user search continues
under its existing authorization boundary and receives `phone_verified`; any
pre-launch phone it displays is labeled unverified rather than being represented as
a verified contact.

## Error Handling

- **Telegram identity authentication fails:** retain the existing retryable auth
  shell and do not render customer content.
- **Customer declines contact sharing:** remain gated; show a retry button.
- **Telegram reports shared but webhook is delayed:** poll for a bounded period,
  then show explicit check/share retry actions.
- **Webhook secret is missing or invalid:** do not update the phone or
  verification timestamp.
- **Sender and contact IDs differ:** ignore the contact without changing any
  user.
- **Phone normalization fails:** leave the customer unverified and permit a new
  Telegram share attempt.
- **Webhook ordering pair is replayed or older than the accepted pair:** return
  `200` without changing the current phone or verification metadata.
- **Customer note exceeds 200 characters:** return `422` before any order side
  effect.
- **Old Telegram client:** show update/reopen instructions; do not offer manual
  entry.
- **Order arrives from a manipulated frontend:** reject a request phone as an
  unexpected field with `422`; reject an otherwise valid order with
  `phone_verification_required` when the profile is unverified.
- **QR resolution succeeds while verification is pending:** retain the table
  context and reveal it after verification.
- **QR resolution fails while verification is pending:** retain the existing
  retryable table-entry behavior after verification.

## Test Strategy

### Backend

- Migration and model tests for the nullable user verification metadata,
  including Telegram message time, and the order provenance column's safe
  `false` default.
- User response tests for `phone_verified`, including fingerprint mismatch
  after an older writer changes the phone.
- Profile-update tests proving a browser cannot set a verified phone.
- Webhook tests for valid secret, missing secret, invalid secret, missing
  contact, missing sender, sender/contact mismatch, unknown user, normalization,
  successful verification, replayed/older ordering pairs, same-second tie
  breaking, a lower update ID after a newer message date, concurrent updates,
  and verified phone replacement.
- Order tests proving an unverified customer receives the stable `409` before
  side effects.
- Order tests proving a client-supplied phone is ignored.
- Request-schema tests proving browser-supplied phone fields receive `422`.
- Snapshot tests proving later profile changes do not alter an order phone and
  proving unverified snapshots do not gain verified provenance.
- AliPOS payload tests for the structured full phone, exact Uzbek mask, generic
  fallback mask with at least three hidden digits, optional customer note,
  200-character validation, unchanged stored comment, and unverified-row comment
  behavior.
- Staff response tests proving snapshot-first phone selection with an unverified
  fallback.

### Frontend

- Auth-store tests proving Telegram launch authentication is not suppressed by
  manual logout state.
- App-route tests for customer gating and staff/admin bypass.
- Gate tests for one automatic prompt per launch under React StrictMode and
  remounts, decline, manual retry, verifying state, polling success, polling
  timeout, check-again, unsupported Telegram, outside-Telegram, and network
  failure.
- Auth/gate tests proving there is no customer-content flash when a stale
  `manual_logout` marker exists.
- QR integration tests proving every QR start-parameter format supported by the
  implementation base resolves once and survives behind the gate. The target
  release currently expected by the product must cover both legacy `t_...` and
  issued numeric `t2_...` links through session storage and post-gate
  navigation.
- Checkout tests proving the phone is read-only/derived and omitted from the
  order request.
- Profile tests proving phone updates reuse the shared verification flow.
- Locale-catalog tests proving every new customer-facing key exists in all
  supported languages.

### Integrated verification

- Run the focused backend and frontend suites before the full suites.
- Exercise a controlled Telegram account in a non-production or separately
  authorized environment: first launch, decline, retry, share, gate unlock,
  refresh persistence, and QR table preservation.
- Inspect a controlled AliPOS payload or authorized test order only when live
  mutation is separately approved. Confirm the structured full phone and exact
  masked comment without exposing either value in logs or saved test output.

## Deployment

Use one coordinated pre-launch cutover:

1. Confirm the release base resolves the issued numeric `t2_...` links and
   retains legacy `t_...` compatibility.
2. Apply the additive migration.
3. Deploy the enforcing backend and gated frontend together. There is no
   request-phone compatibility mode and no feature activation flag.
4. Verify with a controlled Telegram customer that both QR formats survive the
   gate, a spoofed request phone is rejected, and the created AliPOS payload has
   the full structured phone plus the exact masked comment header.

The migration is additive and does not delete any pre-launch phone value. A
rollback restores the previous frontend and backend together; a later
roll-forward requires re-verification for any row whose fingerprint does not
match.

## Acceptance Criteria

- A first-time Telegram customer cannot see or use customer UI routes before
  sharing their own contact.
- Declining never unlocks the app and never causes an automatic prompt loop.
- The gate makes one best-effort automatic prompt attempt and always retains a
  visible manual share action.
- A valid QR/table context survives the entire auth and verification flow.
- Staff and admin role destinations remain unchanged and bypass the customer
  phone gate.
- Only a protected, self-contact Telegram webhook can mark a phone verified.
- Existing pre-launch unverified phone values require one-time re-verification.
- No browser-supplied phone can affect an order.
- Every new order snapshots the verified profile phone
  with explicit verified provenance.
- AliPOS receives the full verified snapshot in `deliveryInfo.phoneNumber`, and
  the system-generated comment header contains only the masked form.
- The Uzbek masked format is exactly `+998 90 *** 4567` for the corresponding
  canonical number.
- Customer notes of at most 200 characters remain unchanged in local
  persistence and follow the masked phone on a new AliPOS comment line.
- Unverified order snapshots never gain verified provenance or a verified-looking
  masked phone header.
- Full phone values do not enter application logs or PII-free table summaries.
- Focused and full backend/frontend tests pass.
