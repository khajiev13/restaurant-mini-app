# AliPOS Integration Skill Design

Date: 2026-07-12

## Summary

Create one project-local Codex skill named `alipos-integration`. The skill will
help future agents build, review, test, and design user interfaces for the
external AliPOS Integration API without inventing capabilities that have not
worked in this repository.

The skill will cover only operations with positive live evidence. Frontend
design guidance will not be part of the skill. Instead, the task will also
produce a standalone prompt for a UI/UX designer. That prompt will describe
the hall/table pages, their behavior, and how the venue experience must differ
from the existing delivery UI.

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
- Produce a separate frontend-designer prompt for a hall/table experience that
  matches the current Telegram Mini App and is visually distinct from delivery.
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
- Loading frontend design instructions as part of the API skill.
- Presenting reservation confirmation, booking history, rescheduling,
  cancellation, deposits, or reminders as currently working behavior.

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
│   └── halls-and-tables.md
└── evals/
    └── evals.json
```

This structure follows the repository's modular Multicard skill pattern while
avoiding its embedded-credential anti-pattern. `SKILL.md` will route agents to
the minimum relevant reference instead of loading every detailed schema for
every AliPOS task.

Create the separate designer prompt at:

```text
docs/prompts/alipos-halls-tables-ui-designer.md
```

The prompt is a project artifact, not a bundled skill reference. Agents using
the API skill will not load UI instructions unless the user separately asks to
work with the designer prompt.

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
3. Task routing to the three API reference files.
4. Credential and identifier safety rules.
5. Mutation and retry boundaries.
6. The unsupported-capability boundary.
7. A short implementation verification checklist.

The workflow will tell agents to:

1. Classify the request as capability lookup, delivery integration, or
   hall/table API work.
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

## `halls-and-tables.md` design

This skill reference will document the live-verified external API contract,
not frontend design.

It will include:

- `GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables`.
- The top-level `halls` and `tables` collections.
- Hall fields `id`, `title`, and `servicePercent`.
- Table fields `id`, `title`, and `hallId`.
- The relationship between a table's `hallId` and its parent hall.
- The observed one-hall and 29-table counts as dated evidence only.
- Server-side credential handling and a recommended backend read proxy.
- The distinction between static directory data and live availability.

It will explicitly say that the API response does not contain:

- Occupancy or availability.
- Capacity or party size.
- Reservation time slots.
- Booking identifiers or booking state.
- Floor-plan coordinates, geometry, photos, or amenities.

The reference will not prescribe React components, routes, page layouts, or UI
copy. Those belong only in the separate designer prompt.

## Standalone UI-designer prompt design

Create `docs/prompts/alipos-halls-tables-ui-designer.md` as a ready-to-send
prompt for a frontend UI/UX designer. It will be understandable without loading
the AliPOS skill.

### Designer objective

Ask the designer to create a distinct dine-in venue-discovery experience using
only the static hall/table fields currently available. The result should not
look or behave like a renamed delivery checkout.

### Required comparison with delivery UI

The prompt will explain that the current delivery UI centers on:

- Menu and cart.
- Customer phone number.
- Delivery address and map coordinates.
- Courier instructions.
- Delivery fee and payment method.
- Delivery order placement and tracking.

The hall/table experience must instead center on:

- Restaurant spaces and hall hierarchy.
- Service percentage at hall level.
- Table names grouped by hall.
- Browsing and understanding physical venue options.
- Clear disclosure that live availability and reservations are unavailable.

The designer must not reuse delivery-specific address, courier, shipping,
delivery-fee, or order-tracking patterns on the venue pages.

### Pages to design

The prompt will request:

1. A `Halls & tables` entry card on the customer menu/home experience.
2. A mobile-first `/tables` directory page.
3. A table-information bottom sheet or dialog.

It will ask the designer to show how these pages fit the current Telegram Mini
App without adding a fifth bottom-navigation item.

### Directory behavior

The prompt will require:

- A persistent banner: `This is the restaurant's table list, not live
  availability. Online reservations are not available yet.`
- One hall rendered as a section heading without redundant filter controls.
- Multiple halls rendered as accessible, horizontally scrollable chips or tabs.
- `Service charge: {servicePercent}%` shown only when supplied.
- Tables grouped by `hallId` and naturally sorted by their displayed titles.
- Neutral table cards that open an information sheet.
- No raw hall or table IDs.
- No fabricated floor plan.

### Information sheet

The prompt will request only:

- Table title.
- Hall title.
- Service percentage when present.
- `Live availability is not shown.`
- `This table cannot be reserved in the app yet.`
- A `Close` or `Back to menu` action.

An optional `Contact restaurant` action may be designed only when another
verified source supplies the contact channel. It cannot imply a completed
reservation.

### Required states

- Loading skeletons.
- Loaded directory.
- Empty restaurant response.
- Empty hall.
- Fetch failure with manual retry.
- Cached list with refresh warning.
- Removed-table handling.
- Authentication retry using the existing application shell.

The prompt will note that the existing Axios client already performs one
eligible transient `GET` retry, so the page should not add another automatic
retry loop.

### Accessibility and responsive behavior

- Semantic buttons and tabs rather than clickable `div` elements.
- Minimum 44-by-44-pixel touch targets.
- Focus moved to the page heading after navigation.
- Correct focus trap and restoration for the information sheet.
- Polite live-region announcements for failures and refreshed content.
- No information communicated by color alone.
- Support for long names and larger system text.
- Designs for 320, 375, and 430-pixel widths.
- Uzbek, Russian, and English content behavior.
- Telegram viewport and safe-area support.

### Unsupported future controls

The designer prompt will identify these as unavailable and exclude them from
the current production flow:

- Date and time pickers.
- Party-size input.
- Availability, free, occupied, or reserved badges.
- A submitted table-selection action.
- `Book`, `Reserve`, or `Use this table` buttons.
- Booking confirmation or reservation numbers.
- Booking history, rescheduling, cancellation, reminders, and deposits.
- Dine-in ordering with `tableId`.

If the designer explores future booking concepts, those frames must be labeled
concept-only and kept separate from the production-ready directory.

### Backend truth included in the prompt

The prompt will tell the designer that the browser cannot call AliPOS directly.
A future implementation needs a server-side read proxy that returns the halls
and tables together. The current backend and frontend do not yet expose that
proxy, so the designer should define data/loading states without claiming the
feature is already connected.

## Evaluation design

Store realistic evaluation prompts in `evals/evals.json`. Run baseline agents
without the skill before authoring the skill, then run the same prompts with the
skill.

Use these five scenarios:

1. Implement cash delivery-order creation and status polling.
2. Implement native table reservations using AliPOS.
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

Evaluate the standalone designer prompt separately with a read-only review
checklist. The reviewer will confirm that the prompt:

- Is not stored inside the skill directory or referenced as required skill
  context.
- Clearly differentiates hall/table browsing from delivery checkout.
- Requests only the approved production pages and states.
- Excludes active reservation and dine-in-order controls.
- Includes accessibility, localization, mobile, Telegram, and backend-boundary
  requirements.

## Verification and packaging

Before handoff:

1. Run baseline evaluation prompts without the skill and record failures.
2. Create the minimal skill and references that address those failures.
3. Run the same prompts with the skill.
4. Grade objective assertions and compare baseline versus skill-enabled output.
5. Check frontmatter, trigger description, paths, word counts, and links.
6. Scan the entire skill for credentials, tokens, raw UUIDs, phone numbers, and
   unsupported endpoint claims.
7. Review the standalone designer prompt against its own checklist.
8. Package the skill only after the evaluation and review gates pass.

## Acceptance criteria

- The project contains one valid `alipos-integration` skill at the approved
  path.
- The skill triggers for AliPOS delivery and hall/table/booking requests.
- The working endpoint matrix contains exactly the nine verified operations.
- Delivery guidance contains a complete placeholder-only payload and safe
  lifecycle behavior.
- The skill contains API guidance only and does not bundle frontend design
  instructions.
- A standalone designer prompt explains the hall/table pages and how their
  information architecture differs from delivery UI.
- The standalone prompt does not imply booking or live table availability.
- Unsupported operations are absent from implementation instructions and are
  explicitly blocked when users request them.
- No credentials, tokens, raw tenant IDs, customer data, or hardcoded payment
  IDs appear in the skill.
- Baseline-versus-skill evaluations show that the skill prevents unsupported
  AliPOS claims.
