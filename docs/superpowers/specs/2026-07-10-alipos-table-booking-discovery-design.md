# AliPOS Table Booking Discovery Notebook Design

**Date:** 2026-07-10

## Context

The July 8 AliPOS Integration API document confirms a read endpoint for halls
and tables, but it does not document table availability or reservation
operations. Existing project notebooks exercise authentication, payment
methods, menus, order creation, and order lookup. They do not probe halls,
tables, availability, or booking routes, and some of them contain cells that can
create real orders.

The repository `.env` contains the official AliPOS client credentials and the
deployed restaurant ID. Verification on 2026-07-10 showed that the saved
notebook test orders use that same restaurant ID; no alternate restaurant ID
exists in the project notebooks. The user explicitly authorized strictly
read-only probes against the deployed restaurant. This requires a second,
deployment-specific opt-in flag in addition to the general live-read flag.

## Goal

Create and execute a dedicated notebook that safely discovers the available
AliPOS hall, table, and booking-related read surface. The notebook will produce
a sanitized summary of confirmed, unsupported, and ambiguous routes without
creating or modifying any AliPOS resource.

## Non-goals

- Creating, changing, or canceling a reservation.
- Creating or changing an order.
- Testing payment or Multicard mutations.
- Mutating any deployed restaurant resource.
- Persisting access tokens, full API responses, or customer data.
- Refactoring the backend AliPOS integration.

## Chosen Approach

Create `notebooks/alipos_table_booking_discovery.ipynb` as an isolated probe
notebook. This is safer than extending an existing notebook because existing
notebooks contain order-creation cells and saved sensitive output. It is more
reviewable than a standalone script because the route inventory, sanitized
responses, and conclusions remain together.

The notebook will use only Python standard-library HTTP and JSON facilities so
it does not depend on the currently broken local Jupyter launcher. A supported
Python kernel or notebook execution library will be selected during
implementation and verified before the live run.

## Credentials and Identifier Guard

The notebook will load these values from the ignored project `.env`:

- `ALIPOS_API_BASE_URL`
- `ALIPOS_API_CLIENT_ID`
- `ALIPOS_API_CLIENT_SECRET`
- `ALIPOS_RESTAURANT_ID`, used as the explicitly authorized read target

The restaurant and test-order ID candidates will be copied from the saved test
execution in `notebooks/alipos_support_report_ru_uz.ipynb` into a clearly
labeled configuration cell. The order IDs must be outputs of that notebook's
test-order cells. Their literal values will not appear in the design document
or final prose report.

Before authentication or probing, the notebook will enforce all of these
conditions:

1. The restaurant ID is present and has the expected identifier shape.
2. The deployed restaurant ID is present.
3. If the target equals the deployed restaurant ID,
   `ALLOW_DEPLOYED_ALIPOS_READS=1` is required.
4. The API base URL uses HTTPS and matches the configured AliPOS host.
5. Live probing is enabled only when `ALLOW_LIVE_ALIPOS_READS=1`. Both live
   flags are off by default in the saved notebook.

If any guard fails, the notebook stops before making a network request.

## Request Safety Boundary

The authentication request is the only permitted `POST`; it targets the
documented OAuth token endpoint and its token is held only in memory.

All discovery traffic after authentication is restricted by a single request
helper to `GET` and `OPTIONS`. The helper rejects `POST`, `PUT`, `PATCH`, and
`DELETE` before constructing a request. Requests run sequentially with at least
250 milliseconds between them, a 15-second timeout, no automatic retries, and a
hard budget of 120 post-authentication requests including `OPTIONS`. Redirects
to a different host are rejected.

The notebook will not execute existing notebooks or reuse their order-creation
helpers.

## Probe Stages

### 1. Documented baseline

Probe the vendor-documented read routes first:

- `GET /restaurants`
- `GET /api/Integration/v1/paymentMethod/all`
- `GET /api/Integration/v1/menu/{dummy_restaurant_id}/composition`
- `GET /api/Integration/v1/restaurant/{dummy_restaurant_id}/halls-and-tables`

The halls-and-tables response supplies candidate dummy hall and table IDs for
later route templates. If it fails or returns no identifiers, ID-dependent
routes are skipped and labeled accordingly.

### 2. Known order reads

For dummy order IDs already present in notebook test data, probe:

- `GET /api/Integration/v1/order/{dummy_order_id}`
- `GET /api/Integration/v1/order/{dummy_order_id}/status`

Only response status and sanitized structure are retained.

### 3. Booking and availability discovery

Build a curated route matrix from the previously recorded AliPOS probe notes.
It will cover singular, plural, camel-case, kebab-case, and known localized
booking terms, including:

- `reservation`, `reservations`, `reserve`, and `reserves`
- `booking` and `bookings`
- `tableReservation` and `table-reservation`
- `tableBooking` and `table-booking`
- `availability`, `table-availability`, and status variants
- `bron`
- `table`, `tables`, `hall`, `halls`, `floor`, and `floors`

For each term, the matrix will deduplicate and test these route shapes:

- `/api/Integration/v1/{term}`
- `/api/Integration/v1/{term}/{dummy_restaurant_id}`
- `/api/Integration/v1/restaurant/{dummy_restaurant_id}/{term}`
- `/api/Integration/v1/menu/{dummy_restaurant_id}/{term}`

When the documented baseline returns a dummy hall or table ID, the matrix will
also substitute that ID into the second route shape and append it to the
restaurant-scoped route shape. ID-dependent routes are omitted when the
corresponding dummy ID is unavailable. Every rendered route is requested at
most once with `GET`; `OPTIONS` is used only to clarify `404` or `405` responses
and capture an `Allow` header. The request-budget guard truncates the matrix
deterministically if the complete set would exceed 120 requests.

## Response Sanitization and Classification

The notebook will never print request authorization headers or token responses.
A recursive redactor will remove or mask values associated with tokens,
secrets, credentials, phone numbers, addresses, coordinates, customer names,
email addresses, cards, and other payment fields.

For each route, the retained result contains only:

- normalized route template;
- HTTP method;
- status code;
- latency;
- content type;
- `Allow` header, when present;
- top-level JSON type and field names;
- collection counts;
- masked identifier fingerprints needed to correlate halls and tables;
- a short sanitized error description.

Hall and table titles and service percentages may be shown because they are
needed to validate the documented response, but their identifiers remain
masked in displayed output. Full raw responses remain only in process memory
for the duration of the run and are not written to disk.

Results are classified as:

- **confirmed**: successful read with a usable response shape;
- **unsupported**: `404` or an explicit method response excluding reads;
- **unauthorized/forbidden**: `401` or `403`;
- **invalid test data**: a validation response tied to a dummy ID;
- **ambiguous**: redirects, server failures, non-JSON successes, or other
  responses that require vendor clarification;
- **skipped**: a required dummy identifier was unavailable.

## Notebook Layout

1. Purpose, warnings, and non-mutation guarantee.
2. Imports and `.env` key loader.
3. Saved test-ID configuration and two-key deployed-read guard.
4. Redaction, route rendering, and result classification helpers.
5. Synthetic self-checks for method blocking, identifier guards, route
   rendering, and redaction.
6. OAuth authentication with token output suppressed.
7. Documented baseline probes.
8. Dummy order read probes.
9. Booking and availability route matrix.
10. Sanitized result table and Markdown conclusion.

## Error Handling

- Configuration and safety failures stop execution before network access.
- Authentication failure stops all API probes and prints only status plus a
  redacted message.
- A route-level timeout or HTTP error is captured as one result and does not
  abort unrelated read probes.
- Rate limiting stops the remaining live matrix instead of retrying.
- Unexpected redirects, HTML responses, and malformed JSON are classified as
  ambiguous without printing their full bodies.

## Verification

Before the live run:

1. Statically inspect every request call and confirm the method allowlist.
2. Run synthetic checks proving mutating methods are rejected.
3. Run synthetic checks proving the deployed restaurant ID is rejected unless
   both explicit live-read flags are enabled.
4. Run redaction checks with fake tokens, phone numbers, addresses, and payment
   data.
5. Execute a dry run that renders the route inventory without network access.

For the live run, enable the environment flag only for the execution process,
execute the notebook top to bottom once, and then inspect all saved outputs for
credentials or personal data. The saved notebook must return to a safe default
with live probing disabled.

## Deliverables

- `notebooks/alipos_table_booking_discovery.ipynb`
- Sanitized executed outputs inside that notebook.
- A concise final report describing confirmed endpoints, response shapes,
  unsupported route families, ambiguities, and the remaining questions for
  AliPOS support.

## Success Criteria

- The official AliPOS credentials authenticate successfully without being
  displayed or persisted.
- No request after authentication uses a mutating HTTP method.
- The deployed restaurant ID is sent only when both explicit live-read flags
  are enabled, and only in `GET`/`OPTIONS` requests.
- Documented halls-and-tables behavior is verified against dummy/test data.
- Booking and availability route candidates receive a reproducible status and
  classification.
- No access token, credential, full customer record, or payment data appears in
  notebook output.
- The result clearly states whether native AliPOS booking or availability can
  be confirmed.
