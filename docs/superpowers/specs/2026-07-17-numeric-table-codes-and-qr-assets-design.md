# Numeric Table Codes and QR Asset Package Design

**Date:** 2026-07-17

**Status:** Approved on 2026-07-17

## Goal

Make manual table entry easy for restaurant customers by using the number already
printed on the physical table, while preserving signed Telegram QR links. After
the change is deployed and the OLOT SOMSA Mini App is healthy, generate and
deliver a verified QR asset package for every current AliPOS table.

## Scope

This change covers:

- deriving a numeric customer-facing code from each AliPOS table title;
- resolving numeric codes without exposing raw AliPOS identifiers;
- keeping existing signed QR links usable during migration;
- changing the customer code-entry sheet to digits-only input;
- generating labeled PNG files, a printable PDF, and a ZIP archive for all live
  tables after deployment;
- verifying the OLOT SOMSA public app and generated QR destinations before the
  assets are delivered.

Restoring or changing the separate BitAgent application is not part of this
feature. Its outage can be diagnosed independently. The OLOT SOMSA application
must be restored because it is the destination of the table QR codes.

## Chosen Approach

The manual code is the physical table number represented by the trailing digit
sequence in the AliPOS table title:

| AliPOS table title | Customer code |
|---|---:|
| `Stol 1` | `1` |
| `Table 12` | `12` |
| `Stol 007` | `7` |
| `VIP Stol 25` | `25` |

The normalized code contains one to six ASCII digits. Leading zeroes are
removed, except that a title ending in only zeroes maps to `0`.

This automatic mapping is preferred over a separate configuration file because
the physical table number already exists in the live AliPOS directory. It avoids
a second mapping that operators would need to maintain whenever tables change.

Two alternatives were rejected:

- **Table number plus a checksum**, such as `12-47`, would reduce casual
  guessing but would reintroduce unnecessary typing.
- **The existing six-character HMAC-derived code** is stable and difficult to
  guess but does not meet the usability goal.

Using a predictable table number is a deliberate usability trade-off. The QR
entry remains signed, while a manually entered number can be guessed. Order
creation still requires an authenticated Telegram customer and the normal order
confirmation flow.

## Backend Design

### Directory model

`TableDirectoryEntry` gains the normalized manual code derived from the table
title. Code extraction happens while building the current hall/table directory,
so manifest generation, manual resolution, QR resolution, restoration, and order
validation all use one canonical mapping.

The raw AliPOS table and hall UUIDs remain server-side. Customer responses still
contain only titles, service percentage, the manual code, and a signed access
token.

### Directory validation

The complete directory is validated before it is used:

- every table title must end in a digit sequence;
- every normalized code must be one to six digits;
- normalized codes must be unique across every hall;
- duplicate table or hall identifiers must also be rejected.

Missing or duplicate numeric codes are configuration errors. The service must
not silently assign a different number, choose the first duplicate, or publish a
partial manifest. Customer-facing API responses use HTTP `503` with a generic
table-directory-unavailable message; server logs may identify the affected table
titles but must not log credentials, bearer tokens, or a raw AliPOS response.

### New QR entries

New Telegram start parameters use an explicit second version:

```text
t2_<numeric-code>_<HMAC-signature>
```

The HMAC uses the existing table-access secret, a version-specific `qr2` signing
purpose, and constant-time signature comparison. No secret rotation is required.
A new QR for table `12` therefore contains a signed `t2_12_...` start parameter
and resolves to the current unique directory entry with code `12`.

Versioning prevents an all-numeric legacy six-character code from being confused
with a new six-digit table number.

### Legacy compatibility

The backend continues to recognize the existing signed six-character Crockford
`t_...` QR start parameters. Legacy lookup recomputes the old HMAC-derived code
for each current table identifier and resolves it only after signature
validation.

The new customer interface advertises and accepts numeric codes only. Legacy
alphanumeric manual codes are retained server-side solely so already printed,
signed QR links can continue to open the correct table during migration.

Tampered signatures, unknown numeric codes, unknown legacy codes, and removed
tables remain rejected. Changing the table-access secret would invalidate both
old and new QR signatures and is not part of this rollout.

## Frontend Design

The existing table-code sheet remains the entry point. Its input changes to:

- accept digits only;
- use the phone's numeric keyboard;
- accept one to six digits instead of requiring six characters;
- normalize leading zeroes before submission;
- enable confirmation when at least one valid digit is present;
- show an example such as `12` rather than `A7K2P9`.

Localized guidance changes from “enter the six-character code” to “enter the
table number printed next to the QR.” Existing resolving, close, and error states
remain unchanged.

No new page, admin editor, database table, or customer-visible AliPOS identifier
is introduced.

The app-level Telegram start-parameter handler recognizes both new `t2_` table
entries and legacy `t_` table entries, then sends either form to the existing
resolver endpoint. Order-return parameters remain unchanged.

## Data Flow

### Manual entry

1. The customer opens the table-code sheet and enters the printed table number.
2. The frontend normalizes and submits the numeric code to
   `POST /api/tables/resolve`.
3. The backend loads and validates the current AliPOS hall/table directory.
4. The unique numeric code resolves to the server-side table identifier.
5. The backend returns the existing safe table context and short-lived signed
   access token.
6. Checkout continues through the existing authenticated table-order flow.

### QR entry

1. Telegram opens the Mini App with a signed `t2_<code>_<signature>` or legacy
   `t_<code>_<signature>` start parameter.
2. The frontend sends the start parameter to the same resolver.
3. The backend validates the signature before directory resolution.
4. New numeric and legacy six-character entries converge on the same safe table
   context response.

## QR Asset Package

Assets are generated only from the admin-only live manifest after the new
backend is deployed and the public OLOT SOMSA health checks pass.

Each table receives one PNG label containing:

- OLOT SOMSA identification;
- hall title;
- prominent table title and numeric manual code;
- the QR encoding the manifest's exact Telegram `deep_link`;
- short fallback text instructing the customer to enter the printed number.

The delivery package contains:

- one consistently named PNG per table;
- a printable A4 PDF containing all table labels;
- the user-safe manifest as CSV and JSON;
- a ZIP archive containing the PNGs and manifests.

Files are ordered naturally by hall and numeric table code. Filenames are
sanitized and prefixed with the numeric code so that printing and placement are
unambiguous.

## Verification

### Automated tests

Backend tests cover:

- extraction from representative table titles;
- leading-zero normalization;
- the `0` edge case;
- missing digits and codes longer than six digits;
- duplicate codes across the same or different halls;
- numeric manual resolution;
- new numeric QR signature validation and tamper rejection;
- unambiguous separation of `t2_` and legacy `t_` entries;
- legacy signed QR compatibility;
- customer-safe manifest and resolve responses.

Frontend tests cover:

- digits-only normalization;
- numeric keyboard configuration;
- one-to-six-digit submission;
- leading-zero normalization;
- rejection of empty input and input longer than six digits;
- updated localized guidance and example.

Focused tests are followed by the complete backend and frontend test suites,
frontend type checking, linting, and production build.

### Deployment and artifact checks

Before delivering the QR package:

1. Verify the public OLOT SOMSA frontend and API health endpoints return HTTP
   `200`.
2. Verify the running deployment contains the numeric-code change.
3. Fetch the current admin manifest and confirm every live directory table is
   represented exactly once.
4. Decode every generated QR image and compare its content byte-for-byte with
   the corresponding manifest `deep_link`.
5. Resolve every numeric manual code against the deployed API.
6. Open at least one generated link through Telegram and confirm that the shown
   hall and table match the printed label.

If the public app is unavailable, the manifest is ambiguous, any QR fails to
decode, or any table resolves incorrectly, the package is not released.

## Rollout and Compatibility

1. Implement and test the backend mapping and legacy compatibility.
2. Implement and test the numeric customer input.
3. Deploy the OLOT SOMSA application without rotating secrets.
4. Restore and verify the public application if its infrastructure is offline.
5. Generate the live manifest and QR package.
6. Verify every QR and numeric code.
7. Deliver the package for printing and replace old labels when convenient.

New numeric QR labels must not be printed before the new backend is verified,
because the previous backend accepts only six-character codes. Existing signed
QR labels remain usable after the new deployment, which allows a gradual
physical replacement.

## Success Criteria

- A customer at `Stol 12` can enter `12` and receive the correct table context.
- Numeric codes are unique and deterministic from the current live directory.
- New signed QR codes open the correct table in the OLOT SOMSA Mini App.
- Existing signed QR codes remain usable during migration.
- No raw AliPOS identifier appears in customer-visible responses or printed
  assets.
- Every current table has one decoded, verified PNG and is included in the PDF
  and ZIP package.
- No QR package is delivered while the destination application is unavailable.
