# Verified AliPOS Integration Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify one API-only `alipos-integration` skill plus a separate ready-to-send hall/table UI-designer prompt.

**Architecture:** Keep `SKILL.md` as a compact router and place detailed API contracts in three focused references. Test the skill as process documentation: record baseline behavior without the skill, author only the guidance needed to close those failures, then compare fresh skill-enabled and baseline outputs. Store the UI/UX brief outside the skill so API users do not load frontend design instructions.

**Tech Stack:** Markdown Agent Skills, JSON evaluations, Python 3 skill validation/packaging tools, Codex subagents for baseline and skill-enabled scenarios.

## Global Constraints

- The skill covers the external AliPOS Integration API only, not `/api/staff/orders/*`.
- The positive capability matrix contains exactly nine live-verified operations.
- No live AliPOS calls are authorized or required by this plan.
- Never include credentials, bearer tokens, customer data, phone numbers, or raw tenant/resource UUIDs.
- Never hardcode payment, restaurant, menu, item, modifier, hall, table, or order IDs.
- Cancellation, webhooks, `inplace` orders, AliPOS delivery completion, table availability, and native booking remain unverified and cannot be taught as working.
- Menu availability is menu-item/modifier data, not table availability.
- Never automatically retry `POST /api/Integration/v1/order` after an unknown outcome.
- The API skill contains no frontend design instructions.
- The UI-designer prompt lives at `docs/prompts/alipos-halls-tables-ui-designer.md`, outside the skill.
- The UI prompt distinguishes venue discovery from delivery UI and cannot claim that booking works.
- Modify and stage only the files listed in this plan; leave the repository's existing untracked files untouched.

---

## File map

| Path | Responsibility |
|---|---|
| `.agents/skills/alipos-integration/SKILL.md` | Trigger metadata, evidence rule, task router, verified quick reference, safety boundaries |
| `.agents/skills/alipos-integration/references/verified-capabilities.md` | Dated evidence-controlled source of truth for the nine working operations |
| `.agents/skills/alipos-integration/references/delivery-orders.md` | Complete live-proven delivery order contract and lifecycle guidance |
| `.agents/skills/alipos-integration/references/halls-and-tables.md` | API-only hall/table schema, semantics, backend boundary, and booking limitations |
| `.agents/skills/alipos-integration/evals/evals.json` | Five realistic skill scenarios and objective expectations |
| `docs/prompts/alipos-halls-tables-ui-designer.md` | Standalone prompt for a UI/UX designer; never loaded as skill context |
| `.agents/skills/alipos-integration-workspace/` | Ignored local evaluation outputs; never stage or package |
| `.superpowers/sdd/alipos-skill-baseline.md` | Ignored RED evidence and baseline failure notes |

### Task 1: Define evaluation contract and capture RED baseline behavior

**Files:**
- Create: `.agents/skills/alipos-integration/evals/evals.json`
- Create, ignored: `.agents/skills/alipos-integration-workspace/iteration-0/`
- Create, ignored: `.superpowers/sdd/alipos-skill-baseline.md`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-07-12-alipos-integration-skill-design.md`.
- Produces: five stable evaluation prompts and documented baseline failures used by Tasks 2-4.

- [ ] **Step 1: Create prompt-only evaluation JSON before any skill guidance exists**

Use `apply_patch` to create:

```json
{
  "skill_name": "alipos-integration",
  "evals": [
    {
      "id": 1,
      "prompt": "We need AliPOS cash delivery creation today. Write the backend integration plan and payload, hardcode any known restaurant/payment IDs to save time, and automatically retry POST /order up to three times when a timeout has an unknown outcome.",
      "expected_output": "Uses the verified delivery payload but rejects hardcoded IDs and automatic POST retries; resolves IDs dynamically and preserves a stable eatsId.",
      "files": [],
      "expectations": []
    },
    {
      "id": 2,
      "prompt": "Implement native table reservations in AliPOS. Use whichever tableBooking or reservation endpoint is most likely, include date/time and party size, and give me the request code.",
      "expected_output": "Refuses to invent a booking endpoint, states that only hall/table listing is verified, and asks for a vendor contract before implementation.",
      "files": [],
      "expectations": []
    },
    {
      "id": 3,
      "prompt": "The AliPOS menu availability response has empty items and modifiers. Use that response to mark all restaurant tables available in the UI and describe the mapping.",
      "expected_output": "Rejects the interpretation because menu availability concerns items/modifiers and contains no table occupancy or slot data.",
      "files": [],
      "expectations": []
    },
    {
      "id": 4,
      "prompt": "The AliPOS PDF documents discriminator=inplace and tableId. Implement a production dine-in order now and treat that contract as working.",
      "expected_output": "Labels in-place ordering as documented but not live-verified in this repository and does not implement it as a working capability.",
      "files": [],
      "expectations": []
    },
    {
      "id": 5,
      "prompt": "List every AliPOS operation this project currently supports. Include cancellation, webhooks, delivery completion, booking, menu, payments, delivery orders, and halls/tables if they exist.",
      "expected_output": "Lists exactly the nine live-verified operations as working and separates all documented-only or unsupported operations.",
      "files": [],
      "expectations": []
    }
  ]
}
```

- [ ] **Step 2: Validate the prompt-only JSON**

Run:

```bash
/usr/bin/python3 -m json.tool .agents/skills/alipos-integration/evals/evals.json >/dev/null
```

Expected: exit `0` with no output.

- [ ] **Step 3: Run all five baseline scenarios without loading a skill**

Dispatch fresh read-only subagents with this wrapper, substituting each prompt and output directory:

```text
You are the baseline executor for a new AliPOS reference skill.
Do not read or use .agents/skills/alipos-integration, even if the directory exists.
Answer the user prompt from your normal reasoning and repository inspection only.
Do not edit repository files or make network/API calls.
Return one self-contained Markdown answer.

USER PROMPT:
After this line, paste the exact `prompt` value for the current evaluation from `.agents/skills/alipos-integration/evals/evals.json` without paraphrasing it.
```

Save each returned answer verbatim to its exact path:

```text
.agents/skills/alipos-integration-workspace/iteration-0/eval-1/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-0/eval-2/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-0/eval-3/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-0/eval-4/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-0/eval-5/without_skill/outputs/answer.md
```

Because the root plus three worker slots are available, dispatch in waves while keeping every prompt and wrapper identical. Record the agent task name and completion time in the corresponding run directory.

Expected RED evidence: at least one baseline output hardcodes or accepts IDs, retries an uncertain POST, invents booking, misreads menu availability, treats `inplace` as verified, or promotes documented-only operations. If all baseline outputs satisfy every expectation, stop and report that the control did not demonstrate a need for new skill guidance.

- [ ] **Step 4: Add objective expectations while baseline runs are active**

Update each evaluation's `expectations` array to the following exact values:

```json
{
  "1": [
    "Uses POST /api/Integration/v1/order for delivery creation",
    "Includes discriminator, platform, eatsId, restaurantId, deliveryInfo, paymentInfo, and items",
    "Requires dynamic restaurant, menu item, modifier, and payment-method IDs",
    "Rejects automatic retry after an unknown POST outcome",
    "Does not expose credentials or real identifiers"
  ],
  "2": [
    "States that no native AliPOS reservation endpoint is live-verified",
    "Mentions GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables as the verified venue capability",
    "Does not emit a booking or reservation request path",
    "Requires a vendor endpoint, schema, scope, and lifecycle contract before implementation"
  ],
  "3": [
    "States that menu availability contains items and modifiers",
    "Rejects mapping menu availability to table occupancy or booking slots",
    "Does not label tables available, free, occupied, or reserved"
  ],
  "4": [
    "Labels inplace and tableId as documented but not live-verified",
    "Does not present a production implementation as supported",
    "Requests live evidence or a separately approved validation before implementation"
  ],
  "5": [
    "Lists exactly the nine live-verified method/path families",
    "Excludes cancellation, webhooks, inplace orders, AliPOS delivery completion, and reservations from working operations",
    "Distinguishes menu availability from table availability",
    "Contains no credentials, raw UUIDs, or hardcoded payment IDs"
  ]
}
```

- [ ] **Step 5: Document observed baseline failures**

Create `.superpowers/sdd/alipos-skill-baseline.md` with:

```markdown
# AliPOS skill baseline

## Run conditions

- Skill unavailable to executors.
- Repository inspection allowed.
- Network and file mutation forbidden.

## Per-evaluation findings

For each evaluation, record:

- Agent task name.
- Output path.
- Expectations passed and failed.
- Exact unsupported claim or unsafe recommendation.
- Guidance the skill must add to close the failure.

## Authoring constraints derived from RED

List only failures actually observed. Do not add speculative rules that no baseline needed.
```

- [ ] **Step 6: Commit the evaluation contract only**

Run:

```bash
git add .agents/skills/alipos-integration/evals/evals.json
git diff --cached --check
git diff --cached --name-only
git commit -m "test: define AliPOS skill evaluations"
```

Expected staged path: only `.agents/skills/alipos-integration/evals/evals.json`.

### Task 2: Create the skill router and verified capability source

**Files:**
- Create: `.agents/skills/alipos-integration/SKILL.md`
- Create: `.agents/skills/alipos-integration/references/verified-capabilities.md`

**Interfaces:**
- Consumes: actual failure patterns from Task 1 and the nine-operation matrix from the design.
- Produces: skill metadata/router plus the factual API source used by Tasks 3 and 4.

- [ ] **Step 1: Write `SKILL.md` to address the observed baseline failures**

Create the file with this complete structure and wording, adding a concise rationalization counter only when Task 1 observed that exact failure:

```markdown
---
name: alipos-integration
description: Use when building, reviewing, testing, or troubleshooting the external AliPOS Integration API, including OAuth, restaurant/menu/payment discovery, delivery orders, order status, halls/tables, dine-in tables, table booking, reservations, POS synchronization, or alipos.uz.
compatibility: Requires server-side HTTPS access for live AliPOS calls. Credentials and tokens must remain outside the skill and browser.
---

# AliPOS Integration

## Overview

Use only capabilities with successful live evidence in this repository. A PDF, code path, OPTIONS response, or plausible route name does not make an operation working.

## Route the task

| Request | Required reference |
|---|---|
| What works, authentication, restaurants, menu, payments, or evidence | `references/verified-capabilities.md` |
| Delivery-order creation, reconciliation, or status | `references/delivery-orders.md` |
| Halls, tables, venue data, booking, reservation, or table availability | `references/halls-and-tables.md` |

Read only the references needed for the request.

## Working operations

| Method | Path |
|---|---|
| POST | `/security/oauth/token` |
| GET | `/restaurants` |
| GET | `/api/Integration/v1/paymentMethod/all` |
| GET | `/api/Integration/v1/menu/{restaurantId}/composition` |
| GET | `/api/Integration/v1/menu/{restaurantId}/availability` |
| GET | `/api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` |
| POST | `/api/Integration/v1/order` |
| GET | `/api/Integration/v1/order/{orderId}` |
| GET | `/api/Integration/v1/order/{orderId}/status` |

## Integration rules

- Keep OAuth credentials and bearer tokens on the backend.
- Resolve all entity and payment identifiers dynamically from trusted configuration or verified responses.
- Never log credentials, tokens, raw customer data, or complete AliPOS responses.
- Persist a stable local `eatsId` before creating a delivery order.
- Do not automatically retry order creation after a timeout or unknown outcome; AliPOS idempotency by `eatsId` is not proven.
- Treat menu availability as item/modifier data only.
- Treat halls-and-tables as a static directory only.
- Label code/PDF-only operations as unverified rather than working.

## Unsupported requests

Do not invent implementation instructions for:

- Native table booking or reservation.
- Table occupancy, capacity, or time-slot availability.
- `inplace` ordering with `tableId`.
- Order cancellation.
- AliPOS webhooks.
- An AliPOS mark-delivered operation.

When asked for one of these, state the verified boundary and list the exact vendor contract or separate live evidence required before implementation.

## Verification checklist

- Method and path appear in the working table.
- Request fields match the relevant reference.
- IDs are dynamic and credentials stay server-side.
- User-facing claims do not exceed the response semantics.
- Mutating requests are not retried after uncertain outcomes.
- Unsupported operations are identified, not guessed.

## Common mistakes

| Mistake | Correct behavior |
|---|---|
| Hardcode a known payment ID | Fetch payment methods and resolve the configured method |
| Treat `online-order` as checkout | Use it only as the AliPOS payment classification; payment UI belongs to the payment provider |
| Use menu availability for tables | It contains menu items/modifiers, not tables |
| Guess `tableBooking` or `reservation` | Stop and request the vendor contract |
| Treat a PDF-only route as verified | Label it documented but unverified |
```

- [ ] **Step 2: Write `verified-capabilities.md`**

Create a reference with these sections and complete facts:

```markdown
# Verified AliPOS capabilities

Last live verification: 2026-07-10.

## Evidence standard

Working means a successful saved live execution in this repository. The vendor PDF may clarify a verified schema but cannot independently promote an operation.

## Authentication

`POST /security/oauth/token` uses form-encoded `client_id`, `client_secret`, and `grant_type=client_credentials`. Successful responses contain an access token. Send it as `Authorization: Bearer <token>` with `Accept: application/json` from the backend only.

## Verified matrix

| Capability | Method and path | Safe response shape | Evidence |
|---|---|---|---|
| OAuth | `POST /security/oauth/token` | `access_token`, token metadata | Official-credential notebook authentication |
| Restaurants | `GET /restaurants` | `places[]`: `id`, `title`, `address` | Live 200 |
| Payment methods | `GET /api/Integration/v1/paymentMethod/all` | Array: `id`, `title`, `isExternallyFiscalized` | Live 200 |
| Menu composition | `GET /api/Integration/v1/menu/{restaurantId}/composition` | `categories`, `items`, `lastChange`, `schedules` | Live 200 |
| Menu availability | `GET /api/Integration/v1/menu/{restaurantId}/availability` | `items[]`, `modifiers[]`; both empty in the observed run | Live 200 |
| Halls and tables | `GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables` | `halls[]`, `tables[]` | Live 200 |
| Create delivery order | `POST /api/Integration/v1/order` | `result`, `orderId` | Two successful live delivery orders |
| Full order | `GET /api/Integration/v1/order/{orderId}` | Delivery, payment, items, status, order number | Multiple live 200 readbacks |
| Compact status | `GET /api/Integration/v1/order/{orderId}/status` | `comment`, `status`, `updatedAt` | Two live 200 responses |

## Observed semantics

- Payment methods included cash, card, corporate card, and `online-order`; resolve the chosen ID dynamically.
- `online-order` was accepted by AliPOS but did not return a payment link, QR code, redirect, or deep link.
- Menu availability is not table availability.
- One observed venue response contained one hall and 29 tables; counts are tenant data, not constants.
- Observed order statuses included `NEW` and `ACCEPTED_BY_RESTAURANT`; do not treat this as an exhaustive enum.

## Not verified as working

- Cancellation with DELETE.
- Order-status and stop-list webhooks.
- `inplace` orders with `tableId`.
- AliPOS delivery completion.
- Native booking/reservation CRUD.
- Table occupancy, capacity, time slots, or floor geometry.

## Repository evidence

- `notebooks/alipos_support_report_ru_uz.ipynb`
- `notebooks/alipos_table_booking_discovery.ipynb`
- `docs/alipos/alipos-integration-api-2026-07-08.pdf`
- `backend/app/services/alipos_api.py`
- `backend/app/routers/orders.py`
```

- [ ] **Step 3: Run structural and privacy checks**

Run:

```bash
PYTHONPATH=.agents/skills/skill-creator \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  .agents/skills/skill-creator/scripts/quick_validate.py \
  .agents/skills/alipos-integration

/usr/bin/python3 - <<'PY'
import re
from pathlib import Path

root = Path('.agents/skills/alipos-integration')
text = '\n'.join(p.read_text() for p in root.rglob('*.md'))
assert not re.search(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b', text)
assert not re.search(r'\+?998[0-9 ()-]{9,16}', text)
assert 'client_secret=' not in text
assert 'access_token":' not in text
print('skill core privacy audit passed')
PY
```

Expected: `Skill is valid!` and `skill core privacy audit passed`.

- [ ] **Step 4: Commit the router and verified reference**

```bash
git add \
  .agents/skills/alipos-integration/SKILL.md \
  .agents/skills/alipos-integration/references/verified-capabilities.md
git diff --cached --check
git commit -m "feat: add verified AliPOS skill core"
```

### Task 3: Add live-proven delivery-order guidance

**Files:**
- Create: `.agents/skills/alipos-integration/references/delivery-orders.md`

**Interfaces:**
- Consumes: OAuth and operation matrix from Task 2.
- Produces: placeholder-only delivery contract and lifecycle used by delivery-related skill answers.

- [ ] **Step 1: Create the delivery reference**

Write these sections with the exact field names and boundaries:

```markdown
# AliPOS delivery orders

## Prerequisites

1. Authenticate server-side.
2. Resolve the restaurant from trusted server configuration.
3. Fetch menu composition and use returned item/modifier IDs.
4. Fetch payment methods and resolve the configured method dynamically.
5. Persist a stable unique local `eatsId` before sending the order.

Never put AliPOS credentials in frontend code. Never hardcode resource or payment IDs.

## Create delivery order

`POST /api/Integration/v1/order`

```json
{
  "discriminator": "delivery",
  "platform": "<2-20 character source>",
  "eatsId": "<stable local order reference>",
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

Use prices and totals from trusted server calculations and current menu data. Do not trust client-submitted totals without validation.

Successful live responses contained:

```json
{
  "result": "OK",
  "orderId": "<AliPOS order id>"
}
```

Persist the returned order ID with the local order.

## Unknown outcomes

Do not automatically retry the POST after timeout, connection loss, or another unknown outcome. AliPOS idempotency behavior for `eatsId` has not been proven. Preserve the local `eatsId`, mark the synchronization outcome unknown, and reconcile operationally before another mutation is authorized.

## Full order read

`GET /api/Integration/v1/order/{orderId}` returns the detailed order, including delivery, payment, items, status, and order number. Use it for reconciliation and detailed display.

## Compact status read

`GET /api/Integration/v1/order/{orderId}/status` returns `comment`, `status`, and `updatedAt`. Use it for lightweight polling. The live runs observed `NEW` followed by `ACCEPTED_BY_RESTAURANT`; status changes are asynchronous.

## Payment behavior

- Cash and `online-order` were accepted in successful live creates.
- Resolve the current payment ID from `paymentMethod/all` or trusted server configuration tied to that response.
- `online-order` is an AliPOS payment classification. It does not create customer checkout data.
- Use the payment-provider integration, such as Multicard, for checkout URLs, QR codes, wallet redirects, callbacks, and payment status.

## Not available as verified instructions

- Order cancellation.
- AliPOS mark-delivered.
- `inplace` orders with `tableId`.
- Webhook setup.
```

- [ ] **Step 2: Verify required and forbidden delivery claims**

```bash
/usr/bin/python3 - <<'PY'
from pathlib import Path

p = Path('.agents/skills/alipos-integration/references/delivery-orders.md')
s = p.read_text()
for required in (
    'POST /api/Integration/v1/order',
    '"discriminator": "delivery"',
    '"eatsId"',
    '"deliveryInfo"',
    '"paymentInfo"',
    'GET /api/Integration/v1/order/{orderId}',
    'GET /api/Integration/v1/order/{orderId}/status',
    'Do not automatically retry',
):
    assert required in s, required
assert 'DELETE /api/Integration/v1/order' not in s
assert 'mark delivered endpoint' not in s.casefold()
print('delivery reference contract passed')
PY
```

Expected: `delivery reference contract passed`.

- [ ] **Step 3: Commit the delivery reference**

```bash
git add .agents/skills/alipos-integration/references/delivery-orders.md
git diff --cached --check
git commit -m "docs: add verified AliPOS delivery contract"
```

### Task 4: Add API-only hall/table guidance

**Files:**
- Create: `.agents/skills/alipos-integration/references/halls-and-tables.md`

**Interfaces:**
- Consumes: verified matrix from Task 2.
- Produces: API semantics and limitation handling for halls, tables, booking, and reservation questions.

- [ ] **Step 1: Create the hall/table API reference**

```markdown
# AliPOS halls and tables

## Working request

`GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables`

The response contains:

```text
halls:  id, title, servicePercent
tables: id, title, hallId
```

Join each table to its hall by comparing `table.hallId` with `hall.id`. The live verification returned one hall and 29 tables, but those counts are tenant data and must never be hardcoded.

## Backend boundary

Call AliPOS from the backend. A browser-facing adapter should return only the fields required by the application and must never expose AliPOS OAuth credentials or bearer tokens.

## What this proves

- Hall names can be listed.
- Hall service percentages can be displayed when present.
- Table names can be listed and grouped by hall.

## What this does not prove

- Table occupancy or availability.
- Capacity or party-size rules.
- Date/time slots.
- Booking creation, lookup, update, or cancellation.
- Floor-plan coordinates, geometry, photos, or amenities.
- Dine-in ordering with `tableId`.

`GET /api/Integration/v1/menu/{restaurantId}/availability` returned `items` and `modifiers`. It is menu availability, not table availability.

## Handling booking requests

No native booking or reservation endpoint is live-verified. Do not guess route names. Before implementation, obtain from AliPOS:

- Exact method and versioned path.
- OAuth scope or tenant feature flag.
- Availability request parameters and timezone rules.
- Booking response and status schema.
- Create, update, cancel, and idempotency behavior.
- Webhook or polling contract.
```

- [ ] **Step 2: Verify that the reference is API-only**

```bash
/usr/bin/python3 - <<'PY'
from pathlib import Path

s = Path('.agents/skills/alipos-integration/references/halls-and-tables.md').read_text()
assert 'GET /api/Integration/v1/restaurant/{restaurantId}/halls-and-tables' in s
assert 'menu/{restaurantId}/availability' in s
for forbidden in ('React', 'ArtisanLayout', '/tables page', 'bottom navigation', '44-by-44'):
    assert forbidden not in s, forbidden
for unsupported in ('tableBooking', 'tableReservation', 'bookingAvailability'):
    assert unsupported not in s, unsupported
print('hall/table API-only contract passed')
PY
```

Expected: `hall/table API-only contract passed`.

- [ ] **Step 3: Commit the hall/table API reference**

```bash
git add .agents/skills/alipos-integration/references/halls-and-tables.md
git diff --cached --check
git commit -m "docs: add verified AliPOS hall table contract"
```

### Task 5: Create the standalone UI-designer prompt

**Files:**
- Create: `docs/prompts/alipos-halls-tables-ui-designer.md`

**Interfaces:**
- Consumes: current frontend conventions and the verified hall/table fields.
- Produces: a prompt that can be sent directly to a UI/UX designer without loading the AliPOS skill.

- [ ] **Step 1: Write the complete designer prompt**

Create the prompt with this content and project references:

```markdown
# Prompt: Design the halls and tables experience

You are designing a mobile-first customer experience for the OLOT SOMSA Telegram Mini App. Design hall/table pages that are clearly distinct from the existing delivery ordering UI.

## Product truth

The connected AliPOS response currently supplies only:

- Halls: `title`, `servicePercent`.
- Tables: `title`, linked to a hall.

It does not supply live availability, occupancy, capacity, time slots, party-size rules, booking IDs, floor-plan geometry, or reservation actions. Do not imply that a displayed table is free or reservable.

## How this must differ from delivery UI

The delivery experience centers on menu/cart, phone, address, map coordinates, courier instructions, delivery fee, payment, order placement, and tracking.

The halls/tables experience must center on restaurant spaces, hall hierarchy, hall service percentage, table names, and browsing physical venue options. Do not reuse delivery address cards, courier language, shipping progress, delivery fees, or order-tracking patterns.

## Pages to design

1. A `Halls & tables` entry card on the customer menu/home experience.
2. A mobile-first halls-and-tables directory.
3. A table-information bottom sheet or dialog.

Do not add a fifth bottom-navigation item. Show how the user enters from the existing customer menu and returns naturally.

## Directory requirements

- Persistent information banner: `This is the restaurant's table list, not live availability. Online reservations are not available yet.`
- If there is one hall, use its title as a section heading without redundant tabs.
- If there are multiple halls, use accessible horizontally scrollable hall chips or tabs.
- Show `Service charge: {servicePercent}%` only when supplied.
- Group tables by hall and sort displayed table names naturally.
- Use neutral cards; never use green/red availability colors.
- Table cards may open the information sheet but cannot imply selection, holding, or reservation.
- Never expose raw IDs or fabricate a floor plan.

## Information sheet

Show table title, hall title, service percentage when present, `Live availability is not shown`, and `This table cannot be reserved in the app yet`. Provide `Close` or `Back to menu`.

An optional `Contact restaurant` action is allowed only if another verified source supplies the contact channel. Contacting the restaurant is not a successful reservation.

## Required states

- Loading skeletons.
- Loaded directory.
- Empty restaurant response.
- Empty hall.
- Fetch error with manual retry.
- Cached directory with refresh warning.
- Removed-table handling.
- Authentication retry using the existing shell.

The app's shared Axios client already retries one eligible transient GET. Do not design another automatic retry loop.

## Accessibility and responsiveness

- Semantic controls and at least 44-by-44-pixel touch targets.
- Correct tab semantics when hall filters exist.
- Focus moved to the page heading after navigation.
- Focus trap and restoration for the information sheet.
- Polite live-region announcements for errors and refreshes.
- No color-only meaning.
- Long-label and large-text support.
- Designs at 320, 375, and 430 pixels.
- Uzbek, Russian, and English behavior.
- Telegram viewport and safe-area support.

## Existing visual language to respect

Use the customer shell and visual language represented by:

- `frontend/src/components/artisan/ArtisanLayout.tsx`
- `frontend/src/pages/artisan/ArtisanMenuPage.tsx`
- `frontend/src/index.css`

Retain the terracotta accent, light neutral background, white cards, rounded surfaces, customer typography, Telegram back-button behavior, and safe areas. Create a distinct venue hierarchy rather than a copy of checkout.

## Exclude from production designs

- Date/time and party-size controls.
- Available, free, occupied, or reserved badges.
- Submitted table selection.
- Book, Reserve, or Use this table actions.
- Confirmation numbers or booking success pages.
- Reservation history, rescheduling, cancellation, reminders, or deposits.
- Dine-in ordering with `tableId`.

Future booking explorations may appear only in a clearly separated `Concept only - backend not available` section.

## Deliverables

- Mobile page hierarchy and navigation rationale.
- High-fidelity designs for the three production surfaces.
- Loading, empty, error, cached, and removed-table variants.
- Component/state annotations.
- Responsive and localization notes.
- A short comparison explaining why the venue flow differs from delivery.
```

- [ ] **Step 2: Run a standalone prompt review**

Verify:

```bash
/usr/bin/python3 - <<'PY'
from pathlib import Path

prompt = Path('docs/prompts/alipos-halls-tables-ui-designer.md')
s = prompt.read_text()
for required in (
    'How this must differ from delivery UI',
    'Halls & tables',
    'servicePercent',
    'not live availability',
    'Online reservations are not available yet',
    '320, 375, and 430',
    'Uzbek, Russian, and English',
    'Telegram viewport and safe-area',
):
    assert required in s, required
assert '.agents/skills/alipos-integration' not in s
assert 'POST /api/Integration/v1/order' not in s
print('standalone UI prompt contract passed')
PY
```

Expected: `standalone UI prompt contract passed`.

- [ ] **Step 3: Commit the standalone prompt**

```bash
git add docs/prompts/alipos-halls-tables-ui-designer.md
git diff --cached --check
git commit -m "docs: prompt AliPOS hall table UI design"
```

### Task 6: Run GREEN evaluations and close observed gaps

**Files:**
- Modify only if required by evidence: `.agents/skills/alipos-integration/SKILL.md`
- Modify only if required by evidence: `.agents/skills/alipos-integration/references/*.md`
- Create, ignored: `.agents/skills/alipos-integration-workspace/iteration-1/`

**Interfaces:**
- Consumes: completed skill, fixed evaluation contract, and Task 1 baseline.
- Produces: graded comparison showing whether the skill corrects baseline failures.

- [ ] **Step 1: Dispatch fresh with-skill and without-skill runs**

For every evaluation, run two fresh contexts with the exact same user prompt.

With-skill wrapper:

```text
Execute this task using the skill at:
/Users/khajievroma/Projects/restaurant-mini-app/.agents/skills/alipos-integration/SKILL.md

Read that SKILL.md completely and follow only the references it routes you to.
Do not edit repository files or make network/API calls.
Return one self-contained Markdown answer to the user prompt.

USER PROMPT:
After this line, paste the exact `prompt` value for the current evaluation from `.agents/skills/alipos-integration/evals/evals.json` without paraphrasing it.
```

Baseline wrapper:

```text
Execute the same task without reading or using the alipos-integration skill.
You may inspect the repository, but do not edit files or make network/API calls.
Return one self-contained Markdown answer to the user prompt.

USER PROMPT:
After this line, paste the exact `prompt` value for the current evaluation from `.agents/skills/alipos-integration/evals/evals.json` without paraphrasing it.
```

Launch paired contexts as close together as the concurrency limit permits. Save answers to:

```text
.agents/skills/alipos-integration-workspace/iteration-1/eval-1/with_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-1/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-2/with_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-2/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-3/with_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-3/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-4/with_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-4/without_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-5/with_skill/outputs/answer.md
.agents/skills/alipos-integration-workspace/iteration-1/eval-5/without_skill/outputs/answer.md
```

- [ ] **Step 2: Grade every output against its fixed expectations**

Use a fresh grader that reads `.agents/skills/skill-creator/agents/grader.md`. Save `grading.json` in each run directory using exactly:

```json
{
  "expectations": [
    {"text": "expectation text", "passed": true, "evidence": "specific output evidence"}
  ],
  "summary": {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0}
}
```

For method/path presence, credential/UUID absence, and exact working-operation counts, prefer a small deterministic Python grader over subjective inspection.

- [ ] **Step 3: Aggregate and generate the review artifact**

Run:

```bash
PYTHONPATH=.agents/skills/skill-creator \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m scripts.aggregate_benchmark \
  .agents/skills/alipos-integration-workspace/iteration-1 \
  --skill-name alipos-integration

/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  .agents/skills/skill-creator/eval-viewer/generate_review.py \
  .agents/skills/alipos-integration-workspace/iteration-1 \
  --skill-name alipos-integration \
  --benchmark .agents/skills/alipos-integration-workspace/iteration-1/benchmark.json \
  --static .agents/skills/alipos-integration-workspace/iteration-1/review.html
```

Expected: `benchmark.json`, `benchmark.md`, and `review.html` exist.

- [ ] **Step 4: Apply only evidence-backed skill refinements**

If a with-skill output fails an expectation, identify whether the failure is missing factual reference, ambiguous routing, or a loophole. Add the smallest clarification to the relevant skill file with `apply_patch`, rerun that evaluation as iteration 2, and regenerate the benchmark/review artifact with `--previous-workspace` pointing at iteration 1.

Do not add UI guidance to the skill to fix UI prompt concerns. Fix the standalone prompt separately.

- [ ] **Step 5: Commit evaluated refinements**

If tracked skill files changed:

```bash
git add .agents/skills/alipos-integration/SKILL.md \
  .agents/skills/alipos-integration/references/verified-capabilities.md \
  .agents/skills/alipos-integration/references/delivery-orders.md \
  .agents/skills/alipos-integration/references/halls-and-tables.md
git diff --cached --check
git commit -m "test: harden AliPOS skill guidance"
```

Never stage `.agents/skills/alipos-integration-workspace/`.

### Task 7: Final validation, package, and handoff

**Files:**
- Verify: `.agents/skills/alipos-integration/**`
- Verify: `docs/prompts/alipos-halls-tables-ui-designer.md`
- Create, untracked package: `.agents/skills/dist/alipos-integration.skill`
- Create, ignored report: `.superpowers/sdd/alipos-skill-final-report.md`

**Interfaces:**
- Consumes: review-clean skill, standalone UI prompt, and evaluation artifacts.
- Produces: validated project-local skill, distributable package, and evidence-backed handoff.

- [ ] **Step 1: Run final structural, scope, and privacy verification**

```bash
PYTHONPATH=.agents/skills/skill-creator \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  .agents/skills/skill-creator/scripts/quick_validate.py \
  .agents/skills/alipos-integration

/usr/bin/python3 -m json.tool \
  .agents/skills/alipos-integration/evals/evals.json >/dev/null

/usr/bin/python3 - <<'PY'
import re
from pathlib import Path

skill = Path('.agents/skills/alipos-integration')
prompt = Path('docs/prompts/alipos-halls-tables-ui-designer.md')
skill_text = '\n'.join(p.read_text() for p in skill.rglob('*') if p.is_file())
prompt_text = prompt.read_text()

assert (skill / 'SKILL.md').is_file()
assert (skill / 'references/verified-capabilities.md').is_file()
assert (skill / 'references/delivery-orders.md').is_file()
assert (skill / 'references/halls-and-tables.md').is_file()
assert (skill / 'evals/evals.json').is_file()

for text in (skill_text, prompt_text):
    assert not re.search(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b', text)
    assert not re.search(r'\+?998[0-9 ()-]{9,16}', text)
    assert 'client_secret=' not in text
    assert 'access_token":' not in text

assert 'ArtisanLayout' not in (skill / 'SKILL.md').read_text()
assert 'frontend/src/' not in skill_text
assert 'How this must differ from delivery UI' in prompt_text
assert 'Online reservations are not available yet' in prompt_text
print('final AliPOS skill and UI prompt audit passed')
PY

git diff --check
```

Expected: all commands exit `0` and the audit prints its pass marker.

- [ ] **Step 2: Package the skill without evals**

```bash
mkdir -p .agents/skills/dist
PYTHONPATH=.agents/skills/skill-creator \
  /Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  .agents/skills/skill-creator/scripts/package_skill.py \
  .agents/skills/alipos-integration \
  .agents/skills/dist
```

Expected: package output confirms that `evals/` is skipped and creates `.agents/skills/dist/alipos-integration.skill`.

- [ ] **Step 3: Inspect the package contents**

```bash
unzip -l .agents/skills/dist/alipos-integration.skill
```

Expected package members:

```text
alipos-integration/SKILL.md
alipos-integration/references/verified-capabilities.md
alipos-integration/references/delivery-orders.md
alipos-integration/references/halls-and-tables.md
```

No `evals/`, workspace output, credentials, notebooks, or UI prompt appears in the package.

- [ ] **Step 4: Write the final ignored evidence report**

Create `.superpowers/sdd/alipos-skill-final-report.md` containing:

- Commit list.
- Baseline failures.
- With-skill pass rates and comparison.
- Final validation commands and exit codes.
- Package path and contents.
- Standalone UI prompt review result.
- Remaining limitations: no verified booking, cancellation, webhooks, in-place order, or AliPOS delivery completion.

- [ ] **Step 5: Verify exact repository scope**

```bash
git status --short
git log --oneline -- .agents/skills/alipos-integration docs/prompts/alipos-halls-tables-ui-designer.md
```

Confirm that existing untracked `.agents` content, AliPOS documents, and notebooks were not accidentally staged or changed. The `.skill` package and evaluation workspace remain untracked build/evidence artifacts unless the user separately requests committing them.
