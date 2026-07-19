# Four-Language Localization Design

**Date:** 2026-07-19

## Goal

Make every application-controlled, user-facing surface consistently available
in Uzbek, Russian, English, and Simplified Chinese. Once a locale is selected,
the application must not silently display another locale because a translation
key, formatter branch, error mapping, or accessibility label is missing.

The supported application locale codes are exactly:

- `uz` — Uzbek;
- `ru` — Russian;
- `en` — English;
- `zh` — Simplified Chinese, displayed as `简体中文` when Chinese is active.

## Current problems

The existing three JSON catalogs each contain 158 leaf keys, but production
source references at least 28 additional keys that are absent from every
catalog. Those calls supply inline defaults, usually English, so missing
translations are rendered as English even when Uzbek or Russian is selected.

English and Uzbek literals also bypass i18next across customer, staff, and
admin components. These include navigation, buttons, loading and empty states,
order statuses, address abbreviations, accessibility text, confirmation
dialogs, and staff delivery/payment workflows. Some state stores hold English
messages, and some screens render English backend `detail` strings verbatim.

Locale input is currently unbounded. Browser, local-storage, and server values
are accepted without normalization or a supported-locale allowlist. Regional
values such as `en-US` can leave every language radio unchecked or select
English formatting accidentally. The authenticated refresh path also does not
consistently apply the stored server preference.

AliPOS returns a single `name` and `description` for each category and item,
and a single title for each hall and table. It does not return locale-keyed
content. Order snapshots preserve those source names. Yandex map and geocoder
responses also have a narrower language set than the application and do not
offer Chinese geocoder output.

## Selected approach

Use a deterministic, repository-owned localization system. Keep interface copy
in four strict frontend catalogs, return stable language-neutral error codes
from user-facing backend operations, and maintain a reviewed AliPOS content
catalog keyed by stable provider IDs. Do not translate content at runtime with
an external machine-translation service.

This approach is selected because it is predictable during ordering, testable
before release, and does not add latency, cost, or nondeterministic menu text.
An interface-only change is rejected because it would leave menu, hall, and
table content in the source language. Runtime machine translation is rejected
because mistranslated product names are unsafe and difficult to review.

## Scope

### Application-controlled copy

The four catalogs cover every visible and assistive string in the shipped
frontend, including:

- application bootstrap, authentication retry, and route loading states;
- customer navigation, menu, cart, table entry, checkout, map controls, order
  history, order status, payment, profile, address, and confirmation flows;
- staff shell, navigation, tabs, order cards, order detail, payment handling,
  delivery confirmation, loading, empty, failure, and profile states;
- admin navigation, user search, role editing, success, empty, validation, and
  failure states;
- placeholders, labels, tooltips, image alternatives, `aria-label` values,
  dialog names, screen-reader-only text, and confirmation prompts;
- known order, payment, refund, synchronization, staff-delivery, and role
  labels;
- dates, times, durations, quantities, prices, currency names, and interpolated
  sentences;
- the Telegram Mini App menu-button label controlled by this application.

The language selector is available to customer, staff, and admin roles through
a shared component. Its four option names are translated into the currently
active language rather than intentionally leaving `English` visible in every
locale. Flags may remain as non-text visual aids.

### Provider-owned business content

The current AliPOS categories, products, product descriptions, halls, and
tables are translated in a repository-owned catalog keyed by their stable
AliPOS IDs. Product and company brand names such as OLOT SOMSA, Coca-Cola,
Fanta, Telegram, AliPOS, and Multicard remain proper names inside otherwise
localized copy.

The AliPOS source strings remain unchanged for server-to-provider requests and
internal reconciliation. Localization is applied only at the browser-facing
response boundary, so translating a name cannot change order identity,
pricing, availability, or the payload accepted by AliPOS.

### Content that is not translated

The application does not rewrite genuine user or geographic data:

- customer and staff names, usernames, and phone numbers;
- user-entered address labels, full addresses, comments, and courier
  instructions;
- order numbers, table codes, identifiers, and numeric values;
- geographic names and address suggestions returned by Yandex.

These values are content rather than interface copy. All labels, explanations,
errors, and controls surrounding them remain in the selected application
locale. Yandex map and geocoder failures must never expose raw provider text.

Internal logs, source comments, test fixtures, developer documentation,
unshipped HTML prototypes, CSS values, routes, icon identifiers, enum values,
and API field names are outside user-facing localization scope.

## Canonical locale model

The frontend owns a single locale registry used by i18next, the language
selector, formatting helpers, document metadata, API headers, and tests. Each
entry contains:

- the canonical code (`uz`, `ru`, `en`, or `zh`);
- its translated display-name key;
- its `Intl` locale (`uz-UZ`, `ru-RU`, `en-US`, or `zh-CN`);
- the document language value;
- the closest supported Yandex UI/geocoder locale;
- the associated translation resource.

One pure normalizer handles browser, Telegram, server, and local-storage input.
It trims whitespace, compares case-insensitively, accepts `-` and `_` regional
separators, and reduces recognized regional forms to the canonical code.
`zh`, `zh-CN`, and other `zh-*` values resolve to the supported Simplified
Chinese locale. Unsupported, empty, or malformed values resolve to `uz` only
when there is no prior valid explicit preference.

i18next is configured with the exact supported-locale list and no
cross-language fallback. Production calls do not contain inline `defaultValue`
copy. A missing key is a build/test failure rather than permission to borrow a
word from English or Uzbek.

## Preference resolution and persistence

Before authentication, the initial locale is resolved in this order:

1. a valid explicit local preference;
2. Telegram's normalized `language_code`, when available;
3. the normalized browser locale;
4. Uzbek.

For a new authenticated user, the backend stores the normalized Telegram
locale when it is supported and otherwise stores Uzbek. Existing users retain
their saved preference; a later Telegram language change does not silently
overwrite a deliberate application choice.

Once the authenticated profile loads, its valid saved preference is
authoritative and is applied in both the authentication and stored-token
refresh paths. An invalid legacy server value is ignored: the app retains its
already-resolved valid initial locale, attempts to repair the profile with that
canonical value, and never passes the invalid value directly to i18next.

When a user selects another language:

1. the interface changes immediately;
2. the canonical code is saved locally;
3. `PUT /users/me` saves the same canonical code;
4. the current menu and other locale-sensitive data are refreshed;
5. the backend attempts to update that user's Telegram menu button to the same
   locale.

If server persistence fails, the interface and local-storage preference both
roll back to the previous locale and a localized retryable message is shown.
This prevents the device and profile from silently disagreeing across
sessions.

The backend validates language updates against the same four values. The
existing database field can hold `zh`; invalid legacy database values are
normalized at the application boundary without an unrelated schema rewrite.

## Frontend translation catalogs

Keep one JSON resource per locale and add `zh.json`. The catalogs use the same
key tree and contain non-empty strings at every leaf. Existing Uzbek and
Russian copy is reviewed for English leakage, inconsistent terminology, and
obvious spelling problems rather than merely copying the current values.

Dynamic grammar uses i18next interpolation and pluralization. Components pass
values such as product name, amount, count, minutes, percentage, or order
number to a complete translated sentence. They do not concatenate translated
fragments in an order that assumes English grammar.

Status and role identifiers remain language-neutral program values. Exhaustive
mapping functions convert all supported values to translation keys. Unknown
provider states map to a localized generic state and are recorded internally;
raw enums such as `TAKEN_BY_COURIER` never appear in the interface.

State stores retain semantic error identifiers rather than pretranslated text.
Translation happens during render so an already-visible error changes when the
locale changes.

The selected locale also updates `document.documentElement.lang`. The font
stack includes local CJK-capable system fonts such as PingFang SC, Microsoft
YaHei, or Noto Sans CJK SC so Chinese glyphs do not depend on downloading a new
web font.

## Backend error contract

User-facing backend failures use stable codes and optional structured
parameters, for example:

```json
{
  "detail": {
    "code": "table_not_found",
    "params": {}
  }
}
```

The frontend maps known codes to `errors.<code>` in the active catalog. Unknown
codes, FastAPI validation responses, network failures, and unexpected server
errors map to a localized generic message based on the operation and status.
The frontend never displays raw `detail`, exception text, or provider payloads.

This contract is required for the customer table/order/address flows, staff
delivery flows, and admin user-role flows that currently surface English
details. Internal-only webhook authentication and operational diagnostics may
remain English because they are not rendered to a user.

Provider errors are logged in the existing secret-safe manner and translated
to an application-owned error code before crossing the browser API boundary.

## AliPOS content localization

The catalog contains locale maps for category, item, hall, and table IDs. Item
entries include `name` and `description`; an intentionally empty source
description remains empty in all locales rather than inventing marketing copy.

Browser API requests send the canonical locale in `Accept-Language`. Public
menu access uses that validated header, while authenticated endpoints may also
consult the saved profile preference. The explicit validated request locale
controls response presentation so the newly selected language takes effect
without a stale-response race.

The backend overlays translated display values when returning:

- menu categories, products, and modifiers;
- cart reconciliation responses;
- order history and order-detail item snapshots, using stable item/modifier
  IDs rather than the stored source name;
- table and hall context.

The menu store refetches after a locale change. Existing cart entries reconcile
their display names by stable ID without changing quantity, price, or selected
modifiers.

A release-time catalog audit compares the current AliPOS composition and
halls-and-tables directory with all four catalog branches. A release is not
accepted while any current visible ID or required field lacks a translation.
Saved snapshots are hints only; IDs and current content are rechecked through
the verified read-only AliPOS operations before release.

If AliPOS adds an untranslated ID after deployment, a non-Uzbek response does
not expose the source-language name. The affected entry is omitted from the
localized menu, a secret-safe warning records only its provider ID, and the
catalog audit reports the drift. Once all four translations are supplied, the
entry appears normally. The normal release path must therefore keep all current
items translated so this safeguard is exceptional.

## Yandex behavior

Yandex map controls and all application overlays are localized by this
application. The loader uses the closest provider-supported locale: Russian
for Uzbek/Russian and English for English/Chinese. Geocoder and suggestion
requests use the same explicit mapping.

Yandex-returned place names and addresses are not machine-translated. This is
an explicit provider-data exception because Yandex Geocoder does not offer a
Chinese response locale. Raw provider errors are converted to stable
application codes and localized by the frontend.

## Telegram menu button

The deployment-wide default Telegram menu-button text becomes the
language-neutral brand `OLOT SOMSA` instead of English `Open Menu`. After a
user's locale is known, the backend attempts to set that chat's menu-button
label to the corresponding reviewed translation during authentication and
after a preference change. Failure to customize the Telegram button does not
block the saved in-app preference, but it is logged without tokens or customer
details.

## Testing and enforcement

### Catalog contract tests

Automated tests must:

- assert the locale registry contains exactly `uz`, `ru`, `en`, and `zh`;
- flatten all four JSON resources and require identical key sets;
- require every translation leaf to be a non-empty string;
- require interpolation variable sets to match across locales;
- extract static production `t('literal.key')` calls and require every key in
  every locale;
- explicitly enumerate dynamic key families such as navigation, payment
  methods, language options, and status steps;
- reject production `t(key, defaultValue)` calls;
- reject unapproved user-visible JSX text and literal `placeholder`, `title`,
  meaningful `alt`, and accessibility attributes through a TypeScript-aware
  source audit.

The hard-coded-string audit allowlist is narrow and explicit: brands, routes,
icons, enums, data attributes, and non-user-facing developer strings. It does
not exempt a whole file or role-based application area.

### Locale behavior tests

Table-driven tests cover exact and regional locale normalization, stale or
unsupported local values, Telegram/browser detection, authenticated profile
application, stored-token refresh, server validation, selector persistence,
rollback on save failure, and all four selector options.

Each customer, staff, and admin route receives a representative render test in
all four locales. Tests use real translation resources rather than mocks that
return English defaults or raw keys. Visible text and accessible names must
come from the selected resource.

Formatter tests cover prices, dates, date-times, durations, and interpolation
for all four locales and regional input forms. The Chinese path must use
`zh-CN` formatting and a reviewed Chinese currency label.

### Error and provider tests

Backend and frontend tests cover:

- every user-visible stable error code and the localized generic fallback;
- rejection/normalization of unsupported saved languages;
- suppression of raw backend, AliPOS, Yandex, and validation messages;
- exhaustive known-status mapping and a localized unknown-status path;
- AliPOS catalog completeness for every checked category, item, modifier,
  hall, and table ID;
- localized menu and order responses without changing source IDs or pricing;
- safe handling of catalog drift;
- Yandex provider-locale mapping;
- language-neutral and per-user Telegram menu-button behavior.

### Verification commands

The implementation is not complete until the relevant backend tests and these
frontend checks pass together:

```bash
cd frontend
npm run typecheck
npm run lint
npm run test
npm run build
```

The repository CI must run the localization contract tests and must not omit
the build from its acceptance path.

## Success criteria

- Customer, staff, and admin users can select Uzbek, Russian, English, or
  Simplified Chinese.
- The selected locale survives refresh, authentication, and a new session and
  is persisted as the same canonical value locally and on the backend.
- Every shipped application-controlled word, sentence, accessible label,
  status, error, placeholder, and confirmation is present in all four
  resources.
- No locale borrows inline English or another language because a key is
  missing.
- The current AliPOS menu, hall, and table content has reviewed translations in
  all four locales, while AliPOS identity, availability, and pricing remain
  unchanged.
- Product names in cart, checkout, order history, order detail, staff views,
  and admin-related order surfaces agree with the active locale.
- Unsupported or regional locale values resolve deterministically and exactly
  one language option is selected.
- Dates, times, durations, prices, and currency labels use the active locale,
  including `zh-CN`.
- Raw backend or provider text never appears in a customer, staff, or admin
  interface.
- Yandex geographic text is the only documented provider-language exception;
  the surrounding map interface remains fully localized.
- Automated tests fail for missing keys, catalog drift, inline defaults,
  unsupported locale leakage, and unapproved hard-coded user-facing text.
- Type checking, linting, frontend tests, frontend production build, and the
  relevant backend test suite all pass.

## Non-goals

- Translating user-entered content or geographic/provider place names.
- Adding Traditional Chinese or a fifth locale.
- Adding a runtime machine-translation dependency.
- Changing menu prices, stock handling, table codes, QR behavior, payment
  calculations, staff permissions, order lifecycle, or deployment topology.
- Refactoring unrelated frontend styles or backend services.
