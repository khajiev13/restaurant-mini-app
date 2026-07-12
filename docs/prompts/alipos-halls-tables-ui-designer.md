# Prompt: Design the halls and tables experience

You are designing a mobile-first customer experience for the OLOT SOMSA Telegram Mini App. Design hall/table pages that are clearly distinct from the existing delivery ordering UI.

## Product truth

The verified AliPOS hall/table relationship contract includes:

- Halls: `id`, `title`, `servicePercent`.
- Tables: `id`, `title`, `hallId`.

The `id` and `hallId` values are implementation-only relationship fields. Never display them. The production UI may show hall and table titles, plus the service percentage when supplied.

It does not supply live availability, occupancy, capacity, time slots, party-size rules, booking IDs, floor-plan geometry, or reservation actions. Do not imply that a displayed table is free or reservable.

## Implementation boundary

The browser cannot call AliPOS directly. A future implementation requires a server-side read proxy that returns halls and tables together. The current backend and frontend do not expose this proxy, so define data, loading, empty, and error states without claiming that the feature is connected today.

## How this must differ from delivery UI

The delivery experience centers on menu/cart, phone, address, map coordinates, courier instructions, delivery fee, payment, order placement, and tracking.

The halls/tables experience must center on restaurant spaces, hall hierarchy, hall service percentage, table names, and browsing physical venue options. Do not reuse delivery address cards, courier language, shipping progress, delivery fees, or order-tracking patterns.

## Pages to design

1. A `Halls & tables` entry card on the customer menu/home experience.
2. A mobile-first `/tables` directory page.
3. A table-information bottom sheet or dialog.

Do not add a fifth bottom-navigation item. Show how the user enters from the existing customer menu and returns naturally.

## Directory requirements

- Persistent information banner: `This is the restaurant's table list, not live availability. Online reservations are not available yet.`
- If there is one hall, use its title as a section heading without redundant tabs.
- If there are multiple halls, use accessible horizontally scrollable hall chips or tabs.
- Show `Service charge: {servicePercent}%` only when supplied.
- Group tables by the implementation-only `hallId` relationship and sort displayed table names naturally.
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
