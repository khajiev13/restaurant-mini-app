# AliPOS Integration Skill Design

Date: 2026-07-12

## Summary

Create one project-local Codex skill named `alipos-integration`. The skill will
help future agents build, review, test, and design user interfaces for the
external AliPOS Integration API without inventing capabilities that have not
worked in this repository.

The skill will cover only operations with positive live evidence. It will also
contain a frontend UI/UX handoff for the verified hall-and-table directory.
Because no native reservation API was confirmed, the handoff will describe a
truthful read-only venue experience rather than a booking flow.

The skill is not a replacement for AliPOS vendor documentation. It is an
evidence-controlled project reference derived from:

- `docs/alipos/alipos-integration-api-2026-07-08.pdf`
- `notebooks/alipos_support_report_ru_uz.ipynb`
- `notebooks/alipos_table_booking_discovery.ipynb`
- `backend/app/services/alipos_api.py`
- `backend/app/routers/orders.py`
- `frontend/src/`

No credentials, access tokens, customer data, raw tenant identifiers, or
hardcoded tenant-specific payment identifiers will be copied into the skill.

## Goals

- Give agents a reliable quick reference for the external AliPOS operations
  that have worked live.
- Provide detailed delivery-order request and response guidance.
- Prevent hardcoded credentials, tenant IDs, menu IDs, table IDs, and payment
  IDs.
- Prevent automatic retries of uncertain order-creation requests.
- Clearly distinguish menu availability from table availability.
- Give frontend designers a concrete hall/table page brief that matches the
  current Telegram Mini App.
- Stop agents from inventing reservation, table-slot, capacity, in-place-order,
  cancellation, webhook, or delivery-completion behavior.
- Make the skill testable with realistic baseline and skill-enabled scenarios.

## Non-goals

- Documenting the app's internal `/api/staff/orders/*` delivery workflow.
- Implementing new backend or frontend features in this task.
- Calling AliPOS again while creating or evaluating the skill.
- Treating an operation as working because it appears only in code or a PDF.
- Publishing raw notebook outputs that contain customer, restaurant, order,
  hall, table, payment, or credential identifiers.
- Designing a reservation confirmation, booking history, rescheduling,
  cancellation, deposit, or reminder flow.

## Evidence rule

The skill's central rule is:

> A capability is "working" only when this repository contains a successful
> live AliPOS execution for that method and path family.

The vendor PDF may clarify the schema of a live-verified operation. It may not
promote a documented-only operation into the working matrix.

Code presence, `OPTIONS` responses, or speculative `404` probes are not
positive execution evidence.

## Verified external capability matrix

The following operations are eligible for the skill's working quick reference.

| Capability | Method and path | Positive evidence | Safe contract summary |
|---|---|---|---|
| OAuth | `POST /security/oauth/token` | Official credentials authenticated successfully | Form fields: `client_id`, `client_secret`, `grant_type=client_credentials`; response contains an access token |
| Restaurants | `GET /restaurants` | Live `200` | `places[]` with `id`, `title`, `address` |
| Payment methods | `GET /api/Integration/v1/paymentMethod/all` | Live `200` | Array of `id`, `title`, `isExternallyFiscalized` |
| Menu composition | `GET /api/Integration/v1/menu/{restaurantId}/composition` | Live `200` | Categories, items, schedules, and last-change marker |
| Menu availability | `GET /api/Integration/v1/menu/{restaurantId}/availability` | Live `200` | `items[]` and `modifiers[]`; both were empty in the observed run |
| Halls and tables | `GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` | Live `200` | `halls[]` and `tables[]`; one observed hall and 29 observed tables |
| Create delivery order | `POST /api/Integration/v1/order` | Two live delivery orders returned `result=OK` and an `orderId` | Delivery payload described below |
| Full order read | `GET /api/Integration/v1/order/{orderId}` | Multiple live `200` readbacks | Full order, delivery, payment, item, status, and order-number fields |
| Compact status read | `GET /api/Integration/v1/order/{orderId}/status` | Two live `200` responses | `comment`, `status`, `updatedAt` |

The skill will state that the observed menu-availability response is about menu
items and modifiers. It is not evidence of hall occupancy, table availability,
or bookable time slots.

## Capabilities excluded from the working reference

The skill will not provide implementation instructions for these operations:

- Native booking or reservation creation, retrieval, update, or cancellation.
- Table-slot or party-size availability.
- Table occupancy, capacity, geometry, amenities, or floor plans.
- `discriminator="inplace"` order creation with `tableId`.
- `DELETE /api/Integration/v1/order/{orderId}` cancellation.
- AliPOS order-status or stop-list webhooks.
- An AliPOS operation that marks an order delivered.
- Any route from the speculative booking/reservation families that returned
  `404` in the discovery run.

Some excluded operations appear in the vendor PDF, code, or method discovery.
They remain excluded because the project has no saved successful live execution
for them.

## Skill location and structure

Create the skill at:

```text
.agents/skills/alipos-integration/
├── SKILL.md
├── references/
│   ├── verified-capabilities.md
│   ├── delivery-orders.md
│   └── halls-tables-ui.md
└── evals/
    └── evals.json
```

This structure follows the repository's modular Multicard skill pattern while
avoiding its embedded-credential anti-pattern. `SKILL.md` will route agents to
the minimum relevant reference instead of loading every detailed schema for
every AliPOS task.

## Skill metadata

The skill name will be `alipos-integration`.

The description will trigger for:

- AliPOS and `alipos.uz` integrations.
- POS order synchronization.
- AliPOS delivery-order creation or status reads.
- Restaurant, menu, and payment-method discovery.
- Halls, tables, dine-in tables, table booking, and reservations.
- Frontend design involving AliPOS venue data.

Booking and reservation phrases must trigger the skill even though booking is
unsupported. This lets the skill prevent hallucinated endpoints.

The description will not summarize the full workflow. The skill body remains
the authoritative guidance.

## `SKILL.md` design

Keep `SKILL.md` concise and use it as a router. It will contain:

1. The evidence-first working-capability rule.
2. A compact verified endpoint matrix.
3. Task routing to the three reference files.
4. Credential and identifier safety rules.
5. Mutation and retry boundaries.
6. The unsupported-capability boundary.
7. A short implementation verification checklist.

The workflow will tell agents to:

1. Classify the request as capability lookup, delivery integration, or
   halls/tables UI work.
2. Read the corresponding reference file.
3. Resolve IDs dynamically from configuration or verified API responses.
4. Keep OAuth credentials and tokens server-side.
5. Use the backend as the only browser-facing integration boundary.
6. Implement only operations in the verified matrix.
7. State the limitation when a user requests an unsupported capability.
8. Verify method, path, payload, response handling, and user-facing claims.

## `verified-capabilities.md` design

This reference will be the factual source of truth. Each capability entry will
include:

- Method and path template.
- Verification date.
- Evidence source.
- Request fields where relevant.
- Safe response shape.
- Known semantics.
- Explicit limitations.

It will contain no raw IDs or real response values beyond non-sensitive counts
and field names.

The hall/table entry will describe:

```text
halls:  id, title, servicePercent
tables: id, hallId, title
```

The observed one-hall and 29-table result will be identified as evidence, not a
fixed product assumption.

## `delivery-orders.md` design

This reference will cover the complete live-proven delivery flow.

### Authentication

- Send form-encoded OAuth client credentials from the backend.
- Cache the token according to expiry without logging it.
- Send `Authorization: Bearer <token>` and `Accept: application/json`.
- Never expose AliPOS credentials or bearer tokens to the frontend.

### Dynamic prerequisite lookup

- Resolve the restaurant from trusted server configuration.
- Fetch menu composition before using item or modifier IDs.
- Fetch payment methods instead of relying on the legacy hardcoded `rahmat`
  identifier.
- Treat the observed `online-order` method as a POS payment classification, not
  a customer checkout provider.
- Use Multicard separately when a payment link, QR code, or wallet checkout is
  required.

### Delivery request shape

The reference will document this proven structure with placeholders only:

```json
{
  "discriminator": "delivery",
  "platform": "<2-20 character source>",
  "eatsId": "<stable unique local order reference>",
  "restaurantId": "<configured restaurant id>",
  "comment": "",
  "deliveryInfo": {
    "clientName": "<customer name>",
    "phoneNumber": "<customer phone>",
    "deliveryAddress": {
      "full": "<full address>",
      "latitude": "<latitude>",
      "longitude": "<longitude>"
    }
  },
  "paymentInfo": {
    "paymentId": "<resolved payment method id>",
    "itemsCost": 0,
    "total": 0,
    "deliveryFee": 0
  },
  "items": [
    {
      "id": "<resolved menu item id>",
      "quantity": 1,
      "price": 0,
      "modifications": []
    }
  ]
}
```

The successful response shape is `result` plus `orderId`.

### Order lifecycle

- Persist the local `eatsId` before sending the request.
- Persist the returned AliPOS `orderId` after confirmed success.
- Use the full-order read for reconciliation and detailed display.
- Use the compact status read for lightweight status refreshes.
- Treat status transitions as asynchronous. `NEW` and
  `ACCEPTED_BY_RESTAURANT` were observed live.
- Do not automatically retry `POST /order` after a timeout or unknown outcome;
  AliPOS idempotency behavior for `eatsId` is not proven.
- Do not claim that local staff delivery completion was synchronized to
  AliPOS.

## `halls-tables-ui.md` design

This reference will be a direct handoff to frontend UI/UX designers and React
implementers.

### Product truth

The current API supplies a static hall/table directory. It does not supply live
availability, reservations, occupancy, capacity, time slots, party size,
coordinates, or floor-plan geometry.

### Production page inventory

The skill will direct the designer to create only:

1. A `Halls & tables` entry card on the customer menu/home experience.
2. A mobile-first `/tables` directory page.
3. A table-information bottom sheet or dialog.

It will not request a booking form, confirmation page, booking history, or
reservation-management page.

### Navigation and visual fit

- Reuse `ArtisanLayout`, its top bar, colors, typography, and icons.
- Do not add a fifth bottom-navigation item.
- Enter through a secondary card or action from the customer menu.
- Use a focused back-navigation page. The existing bottom navigation may remain
  visible unless a sheet or focused subflow requires otherwise.
- Match the existing terracotta accent, white cards, `#f6f6f6` background,
  12-pixel card radius, and Telegram safe-area behavior.

### Directory behavior

- Show a persistent banner: `This is the restaurant's table list, not live
  availability. Online reservations are not available yet.`
- With one hall, show the hall title as a heading and avoid a redundant filter.
- With multiple halls, use horizontally scrollable accessible hall chips or
  tabs.
- Show `Service charge: {servicePercent}%` only when supplied.
- Group tables by `hallId` and sort table titles naturally.
- Render neutral table cards with table title and hall context.
- Let a table card open an information sheet.
- Do not show a selected, reserved, occupied, free, or available state.
- Do not expose raw hall or table IDs.
- Do not draw a floor plan.

### Information sheet

Show only:

- Table title.
- Hall title.
- Hall service percentage when present.
- `Live availability is not shown.`
- `This table cannot be reserved in the app yet.`
- A `Close` or `Back to menu` action.

An optional `Contact restaurant` action is allowed only when the application
already has a verified contact channel. Opening that channel must not be
presented as a successful reservation.

### Required states

- Loading skeletons for hall controls and table cards.
- Loaded directory.
- Empty restaurant response.
- Empty hall.
- Fetch failure with a manual retry.
- Cached list with a refresh-warning banner.
- Removed table handling.
- Authentication retry using the app's existing shell.

The page will not add its own retry loop because the existing Axios client
already retries an eligible transient `GET` once.

### Accessibility and responsive behavior

- Use semantic buttons and tabs rather than clickable `div` elements.
- Use at least 44-by-44-pixel touch targets.
- Move focus to the page heading after navigation.
- Trap and restore focus for the information sheet.
- Announce errors and refresh results through a polite live region.
- Never communicate state through color alone.
- Support long labels and larger system text.
- Test 320, 375, and 430-pixel widths.
- Test Uzbek, Russian, and English translations.
- Respect Telegram viewport and safe-area variables.

### Future capability gate

The skill will instruct designers not to activate these elements until a
verified backend contract exists:

- Date and time pickers.
- Party-size input.
- Availability or occupancy badges.
- Table selection for a submitted action.
- `Book`, `Reserve`, or `Use this table` actions.
- Booking confirmation and reservation numbers.
- Booking history, rescheduling, cancellation, reminders, or deposits.
- Dine-in ordering using `tableId`.

## Backend boundary for the UI

The frontend must not call AliPOS directly. A future implementation will need a
backend read-only proxy that:

- Authenticates to AliPOS server-side.
- Fetches halls and tables together.
- Returns only the fields required by the page.
- Does not leak raw credentials or tokens.
- Defines caching without converting cached inventory into availability.

The skill may describe this boundary but will not claim that the proxy already
exists. The current backend has no hall/table helper or frontend endpoint.

## Evaluation design

Store realistic evaluation prompts in `evals/evals.json`. Run baseline agents
without the skill before authoring the skill, then run the same prompts with the
skill.

Use these five scenarios:

1. Implement cash delivery-order creation and status polling.
2. Design an AliPOS table-booking page.
3. Use menu availability to mark tables occupied.
4. Create an in-place order with `tableId`.
5. List every currently supported AliPOS operation.

Objective assertions will verify that outputs:

- Use only verified method/path pairs.
- Include the required delivery payload fields.
- Keep credentials and AliPOS calls on the backend.
- Resolve payment and entity identifiers dynamically.
- Do not invent idempotency guarantees.
- Do not invent reservation or table-availability endpoints.
- Do not interpret menu availability as table availability.
- Do not teach cancellation, webhooks, in-place orders, or delivery completion
  as working.
- Produce neutral, truthful hall/table UI language.
- Include loading, empty, error, retry, accessibility, localization, and mobile
  states in the designer handoff.

## Verification and packaging

Before handoff:

1. Run baseline evaluation prompts without the skill and record failures.
2. Create the minimal skill and references that address those failures.
3. Run the same prompts with the skill.
4. Grade objective assertions and compare baseline versus skill-enabled output.
5. Check frontmatter, trigger description, paths, word counts, and links.
6. Scan the entire skill for credentials, tokens, raw UUIDs, phone numbers, and
   unsupported endpoint claims.
7. Package the skill only after the evaluation and review gates pass.

## Acceptance criteria

- The project contains one valid `alipos-integration` skill at the approved
  path.
- The skill triggers for AliPOS delivery and hall/table/booking requests.
- The working endpoint matrix contains exactly the nine verified operations.
- Delivery guidance contains a complete placeholder-only payload and safe
  lifecycle behavior.
- UI guidance produces a hall/table directory without implying booking or live
  availability.
- Unsupported operations are absent from implementation instructions and are
  explicitly blocked when users request them.
- No credentials, tokens, raw tenant IDs, customer data, or hardcoded payment
  IDs appear in the skill.
- Baseline-versus-skill evaluations show that the skill prevents unsupported
  AliPOS claims and produces the required frontend handoff.
