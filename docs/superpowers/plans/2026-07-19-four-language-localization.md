# Four-Language Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every shipped customer, staff, and admin surface deterministic and complete in Uzbek, Russian, English, and Simplified Chinese, with no accidental cross-language fallback or raw backend/provider text.

**Architecture:** A canonical four-value locale model is shared conceptually across the React client and FastAPI server. The frontend owns strict interface catalogs and render-time error/status translation; the backend validates locale input, returns stable error codes, and overlays reviewed AliPOS content translations by provider ID only at browser response boundaries. Automated catalog, AST, route, provider, and CI gates prevent regressions.

**Tech Stack:** React 19, TypeScript 5.7, i18next 25, react-i18next 16, Zustand 5, Axios, Vitest, Testing Library, TypeScript compiler API, FastAPI, Pydantic 2, SQLAlchemy async, httpx, pytest, Ruff.

## Global Constraints

- The source design is `docs/superpowers/specs/2026-07-19-four-language-localization-design.md`.
- The supported application locale codes are exactly `uz`, `ru`, `en`, and `zh`; `zh` means Simplified Chinese.
- Do not add runtime machine translation, Traditional Chinese, or a fifth locale.
- Do not translate user names, phone numbers, usernames, user-entered addresses/comments, order numbers, table codes, identifiers, or Yandex-returned geographic text.
- Keep AliPOS IDs, source names, prices, availability, modifier identity, and outgoing order payloads unchanged. Apply localized display values only to browser-facing copies.
- Do not display raw FastAPI validation text, backend `detail` strings, provider payloads, exception text, or unknown enum values.
- Do not use inline i18next default strings. A production `t()` call may pass interpolation values, but not fallback copy.
- Do not configure a cross-language i18next fallback. Missing keys are test/build failures.
- Preserve existing table/QR, payment, staff permission, order lifecycle, and deployment behavior except for their user-facing labels and structured error envelopes.
- Preserve all unrelated dirty-worktree files. Stage and commit only paths named by the current task.
- Use the repository `karpathy-guidelines` skill for surgical implementation, `vercel-react-best-practices` for React changes, and `alipos-integration` for Task 9.
- Run each RED command before implementation and confirm the expected failure. Run the corresponding GREEN command before committing.
- For a new module, create only a compile-valid stub before its first test; RED must be an assertion failure, never a missing-module/import failure.
- Every command block starts at the repository root unless the block itself changes directory. Every frontend command block repeats the Node/npm PATH export from Task 0, and every backend test command runs through the non-production wrapper created there.

---

## File Structure

### Frontend locale kernel and enforcement

- Create `frontend/src/i18n/locale.ts`: canonical locale type, metadata, normalizer, and initial-preference resolver.
- Create `frontend/src/i18n/resources.ts`: typed four-resource registry.
- Modify `frontend/src/i18n/index.ts`: initialize i18next without cross-language fallback and synchronize the document language.
- Create `frontend/src/i18n/errors.ts`: semantic API/network error resolver.
- Create `frontend/src/i18n/status.ts`: exhaustive order/payment/role translation-key mappings.
- Create `frontend/src/i18n/locales/zh.json`: complete Simplified Chinese catalog.
- Modify `frontend/src/i18n/locales/{uz,ru,en}.json`: fill missing copy, remove leakage, and keep exact key parity.
- Create `frontend/src/i18n/__tests__/{locale,catalog,errors,status}.test.ts`: locale and catalog contracts.
- Create `frontend/src/test/renderWithLocale.tsx`: component-test helper that uses real resources.
- Create `frontend/src/i18n/__tests__/support/sourceAudit.ts`: TypeScript-aware user-visible-literal and inline-default audit engine.
- Create `frontend/src/i18n/__tests__/support/sourceAuditConfig.ts`: single shared dynamic-key, literal-allowance, UI-sink, and shipped-extension configuration.
- Create `frontend/src/i18n/__tests__/{sourceAudit,sourceAudit.integration}.test.ts`: focused fixtures and repository-wide enforcement.

### Frontend behavior and surfaces

- Create `frontend/src/components/LanguageSelector.tsx`: shared four-option selector.
- Create `frontend/src/services/localePreference.ts`: optimistic locale persistence with exact rollback behavior.
- Modify `frontend/src/services/api.ts`: canonical `Accept-Language` header and structured error typing.
- Modify `frontend/src/stores/{authStore,menuStore,cartStore,tableOrderStore}.ts`: semantic errors, server preference application, and localized menu/cart reconciliation.
- Modify `frontend/src/utils/{format,loadYmaps3}.ts`: four-locale formatting and Yandex provider mapping.
- Modify all shipped customer, staff, and admin components/pages listed in Tasks 6–8.
- Modify `frontend/index.html` and `frontend/src/index.css`: runtime document language and CJK-capable system fonts.

### Backend locale, error, and content boundaries

- Create `backend/app/localization/locale.py`: backend locale type, normalizer, `Accept-Language` parser, and FastAPI dependency.
- Create `backend/app/localization/errors.py`: stable browser-facing error codes and HTTP exception helper.
- Create `backend/app/localization/content.py`: reviewed AliPOS catalog loader, overlay functions, and completeness audit.
- Create `backend/app/localization/alipos_content.json`: locale maps keyed only by current AliPOS category/item/modifier/hall/table IDs.
- Create `backend/app/services/telegram_menu_service.py`: global/per-chat Telegram button localization.
- Create `backend/scripts/audit_alipos_localization.py`: verified read-only live catalog comparison.
- Modify auth, user, menu, table, order, address, staff, admin, geocoding, and response-builder code named below.
- Add focused backend tests under `backend/tests/localization/` and update existing API/service tests that currently assert English detail strings.

---

### Task 0: Bootstrap the reproducible local test toolchain

**Files:**
- Create: `backend/scripts/with_test_env.sh`
- Create: `backend/tests/test_test_environment.py`
- Modify: `.github/workflows/ci.yml`
- Create only ignored local directory `backend/.venv/` when absent.

- [ ] **Step 1: Make Node and npm available in the current shell**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
node --version
npm --version
```

Expected: Node 22 or newer and npm 10 or newer. The export prepends the bundled runtime without removing Homebrew or other existing tools. Repeat this exact line in every frontend command block.

- [ ] **Step 2: Create the ignored backend environment and install the locked test inputs**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python --version
backend/.venv/bin/python -m pytest --version
backend/.venv/bin/ruff --version
```

Expected: Python 3.12, pytest, and Ruff are available. If `backend/.venv/bin/python` already exists, skip only the `venv` creation command and still run the requirements installation so the environment matches `requirements-dev.txt`. Do not stage or commit `.venv`.

- [ ] **Step 3: Create one explicit non-production backend test wrapper**

Create executable `backend/scripts/with_test_env.sh` with exactly:

```bash
#!/usr/bin/env bash
set -euo pipefail

export TESTING=1
export LOCAL_TEST_WRAPPER=1
export TELEGRAM_BOT_TOKEN=test_token
export TELEGRAM_WEBHOOK_SECRET=test_webhook_secret
export TABLE_ACCESS_SECRET=test_table_access_secret
export ALIPOS_API_CLIENT_ID=test_client
export ALIPOS_API_CLIENT_SECRET=test_secret
export ALIPOS_RESTAURANT_ID=00000000-0000-4000-8000-000000000001
export POSTGRES_USER=restaurant_i18n_test
export POSTGRES_PASSWORD=restaurant_i18n_test
export POSTGRES_DB=restaurant_i18n_test
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=55432
export JWT_SECRET=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

exec "$@"
```

This wrapper contains test-only dummy values and must never source the repository's production `.env`. The AliPOS restaurant value must be a syntactically valid, non-production UUID because menu tests call `uuid.UUID(settings.alipos_restaurant_id)`. Add `backend/tests/test_test_environment.py` with a module-level skip unless `LOCAL_TEST_WRAPPER == "1"`, then assert `settings.postgres_host == "127.0.0.1"`, `settings.postgres_port == 55432`, `settings.postgres_db == "restaurant_i18n_test"`, `settings.telegram_bot_token == "test_token"`, and `settings.alipos_restaurant_id == "00000000-0000-4000-8000-000000000001"`. The skip keeps the repository's existing CI PostgreSQL service valid while the explicit Task 0 command proves this local harness. In `.github/workflows/ci.yml`, replace the invalid test-only `ALIPOS_RESTAURANT_ID: test-id` with the same dummy UUID so full CI exercises the same valid shape. Make the script executable now with `chmod +x backend/scripts/with_test_env.sh` and stage it in Step 5.

- [ ] **Step 4: Start an isolated disposable PostgreSQL and prove connectivity**

Do not start, stop, or reuse the repository's production Compose `postgres` service. Start a dedicated container with an explicit name, loopback-only port, test credentials, and tmpfs storage:

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
if docker inspect restaurant_i18n_test_postgres >/dev/null 2>&1; then
  docker start restaurant_i18n_test_postgres >/dev/null
else
  docker run --name restaurant_i18n_test_postgres --rm -d --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=restaurant_i18n_test -e POSTGRES_PASSWORD=restaurant_i18n_test -e POSTGRES_DB=restaurant_i18n_test -p 127.0.0.1:55432:5432 postgres:16
fi
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  docker exec restaurant_i18n_test_postgres pg_isready -U restaurant_i18n_test -d restaurant_i18n_test && break
  test "$attempt" -lt 15
  sleep 1
done
backend/scripts/with_test_env.sh backend/.venv/bin/python -c "import asyncio, asyncpg; connection = asyncio.run(asyncpg.connect(user='restaurant_i18n_test', password='restaurant_i18n_test', database='restaurant_i18n_test', host='127.0.0.1', port=55432)); print(connection.get_server_version())"
```

Expected: `pg_isready` reports accepting connections and the asyncpg proof exits zero. The named container is disposable and isolated from `restaurant_postgres`; stop it after Task 12 with `docker stop restaurant_i18n_test_postgres`.

- [ ] **Step 5: Prove the existing runners start and commit the test harness**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/test_test_environment.py -q
scripts/with_test_env.sh .venv/bin/python -m pytest --collect-only -q
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- --help
cd ..
git add backend/scripts/with_test_env.sh backend/tests/test_test_environment.py .github/workflows/ci.yml
git commit -m "test: add isolated backend test harness"
```

Expected: the environment contract passes, all backend tests collect, and Vitest prints help without a module-resolution failure.

---

### Task 1: Build the canonical frontend locale kernel and fourth resource

**Files:**
- Create: `frontend/src/i18n/locale.ts`
- Create: `frontend/src/i18n/resources.ts`
- Create: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/{uz,ru,en}.json`
- Create: `frontend/src/i18n/__tests__/locale.test.ts`
- Create: `frontend/src/i18n/__tests__/catalog.test.ts`
- Modify: `frontend/src/i18n/index.ts`
- Modify: `frontend/index.html`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/src/utils/format.ts`
- Modify: `frontend/src/utils/__tests__/format.test.ts`

**Interfaces:**

```ts
export const SUPPORTED_LOCALES = ['uz', 'ru', 'en', 'zh'] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: AppLocale = 'uz';
export const APP_LOCALE_STORAGE_KEY = 'i18nextLng';

export interface LocaleDefinition {
  code: AppLocale;
  labelKey:
    | 'profile.language_uz'
    | 'profile.language_ru'
    | 'profile.language_en'
    | 'profile.language_zh';
  intl: 'uz-UZ' | 'ru-RU' | 'en-US' | 'zh-CN';
  documentLang: 'uz' | 'ru' | 'en' | 'zh-CN';
  yandexMaps: 'ru_RU' | 'en_US';
  yandexGeocoder: 'ru' | 'en';
  resource: Record<string, unknown>;
}

export function normalizeLocale(value: unknown): AppLocale | null;
export function resolveInitialLocale(input: {
  stored?: unknown;
  telegram?: unknown;
  browser?: unknown;
}): AppLocale;

// Exported by i18n/index.ts, not locale.ts.
export function getActiveLocale(): AppLocale;
export async function changeAppLocale(value: unknown): Promise<AppLocale>;
```

`locale.ts` owns only the locale types, JSON-backed registry, normalizer, and pure initial resolver. It imports the four JSON files directly. `resources.ts` derives the i18next resource object from `LOCALE_DEFINITIONS`. `index.ts` imports those two modules, owns the configured i18next singleton, and exports `getActiveLocale()`/`changeAppLocale()`. This direction prevents a locale-kernel/i18next circular import.

- [ ] **Step 1: Add compile-only stubs, then write failing locale tests**

Create `locale.ts` with the exported tuple/types, make `normalizeLocale()` return `null`, and make `resolveInitialLocale()` return `DEFAULT_LOCALE`. Add the two runtime exports to the existing `index.ts`; temporarily return the default without changing i18next. Create `resources.ts` with only the current three resources and create `zh.json` as `{}`. These are compile stubs, not implementation.

In `locale.test.ts`, table-test these exact outcomes:

```ts
expect(normalizeLocale('uz')).toBe('uz');
expect(normalizeLocale('RU-ru')).toBe('ru');
expect(normalizeLocale('en_US')).toBe('en');
expect(normalizeLocale('zh-CN')).toBe('zh');
expect(normalizeLocale('zh-Hans-CN')).toBe('zh');
expect(normalizeLocale('zh-TW')).toBe('zh');
expect(normalizeLocale('en--US')).toBeNull();
expect(normalizeLocale('zh-')).toBeNull();
expect(normalizeLocale('ru_@')).toBeNull();
expect(normalizeLocale(' fr-FR ')).toBeNull();
expect(normalizeLocale('')).toBeNull();
expect(normalizeLocale(null)).toBeNull();

expect(resolveInitialLocale({ stored: 'ru', telegram: 'zh-CN', browser: 'en-US' })).toBe('ru');
expect(resolveInitialLocale({ stored: 'fr', telegram: 'zh-CN', browser: 'en-US' })).toBe('zh');
expect(resolveInitialLocale({ stored: 'fr', telegram: 'de', browser: 'en-US' })).toBe('en');
expect(resolveInitialLocale({ stored: 'fr', telegram: 'de', browser: 'es-ES' })).toBe('uz');
```

- [ ] **Step 2: Write the failing catalog-shape test**

Import all resources and assert:

```ts
expect(Object.keys(resources).sort()).toEqual(['en', 'ru', 'uz', 'zh']);
expect([...flatten(resources.uz.translation).keys()].sort())
  .toEqual([...flatten(resources.ru.translation).keys()].sort());
expect([...flatten(resources.uz.translation).keys()].sort())
  .toEqual([...flatten(resources.en.translation).keys()].sort());
expect([...flatten(resources.uz.translation).keys()].sort())
  .toEqual([...flatten(resources.zh.translation).keys()].sort());
```

The helper must compare sorted key sets separately from values, require every leaf to be a non-empty string, and require the same `{{interpolationToken}}` set for a given key in all four locales.

Also require locale purity. For every leaf, reject a value that is byte-for-byte identical in two locales unless an exact `{key, locales, value, reason}` allowance names a proper brand, acronym, or numeric/punctuation-only value. Start with no namespace-wide allowances. After stripping interpolation tokens and exact allowed brands, Russian alphabetic copy must contain Cyrillic and Chinese alphabetic copy must contain a Han character; Uzbek and English copy must not contain Cyrillic or Han. These checks supplement human review and catch copied English leaves such as `Retry`, `Home`, or `Online` even though their keys exist.

- [ ] **Step 3: Run the focused tests and verify RED**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/locale.test.ts src/i18n/__tests__/catalog.test.ts
```

Expected: assertion failures for regional normalization and the empty/incomplete Chinese resource; no import or module-resolution error.

- [ ] **Step 4: Implement the pure registry and resolver**

Use this exact metadata:

```ts
export const LOCALE_DEFINITIONS: Record<AppLocale, LocaleDefinition> = {
  uz: { code: 'uz', labelKey: 'profile.language_uz', intl: 'uz-UZ', documentLang: 'uz', yandexMaps: 'ru_RU', yandexGeocoder: 'ru', resource: uz },
  ru: { code: 'ru', labelKey: 'profile.language_ru', intl: 'ru-RU', documentLang: 'ru', yandexMaps: 'ru_RU', yandexGeocoder: 'ru', resource: ru },
  en: { code: 'en', labelKey: 'profile.language_en', intl: 'en-US', documentLang: 'en', yandexMaps: 'en_US', yandexGeocoder: 'en', resource: en },
  zh: { code: 'zh', labelKey: 'profile.language_zh', intl: 'zh-CN', documentLang: 'zh-CN', yandexMaps: 'en_US', yandexGeocoder: 'en', resource: zh },
};
```

Define this single registry in `locale.ts`; derive `resources.ts`, selector options, formatter metadata, document language, provider mapping, API headers, and tests from it. Do not reconstruct `profile.language_${code}` elsewhere.

`normalizeLocale` must trim, lowercase, and change `_` to `-`, then validate the entire normalized tag against `^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$` before reading its primary subtag. It returns only the four allowed primary values and treats every syntactically valid `zh-*` input as `zh` per the approved design. Malformed tags such as `en--US`, `zh-`, and `ru_@` are rejected rather than silently reduced to a supported primary language. Task 2 uses the same fixtures to guarantee frontend/backend parity.

- [ ] **Step 5: Add the complete initial Chinese catalog and typed resource registry**

Translate every existing leaf in `en.json` into reviewed Simplified Chinese. Do not copy English or Russian values into `zh.json`; proper brand names and numeric placeholders are the only allowed unchanged text. Before the Task 1 GREEN gate, also correct every existing purity finding in the Uzbek, Russian, and English catalogs, including identical/leaked checkout placeholders and Uzbek `payment_methods.card`/`payment_methods.rahmat`; these are translated interface phrases, not brands, so they must not be allowlisted or deferred to Task 6. Add `profile.language_zh` to all four catalogs with these active-language labels:

| Locale | `profile.language_uz` | `profile.language_ru` | `profile.language_en` | `profile.language_zh` |
|---|---|---|---|---|
| `uz` | `O'zbekcha` | `Ruscha` | `Inglizcha` | `Soddalashtirilgan xitoycha` |
| `ru` | `Узбекский` | `Русский` | `Английский` | `Китайский (упрощённый)` |
| `en` | `Uzbek` | `Russian` | `English` | `Simplified Chinese` |
| `zh` | `乌兹别克语` | `俄语` | `英语` | `简体中文` |

Also replace the locale-specific `common.currency_uz`, `common.currency_ru`, and `common.currency_en` scheme with one `common.currency` key in every catalog: `so'm`, `сум`, `UZS`, and `苏姆` respectively.

In the same step, update `formatPrice()` and its tests to normalize the requested locale, use `LOCALE_DEFINITIONS[locale].intl`, and resolve the single `common.currency` key through `i18n.getFixedT(locale)`. Never read currency from whichever resource happens to be globally active when an explicit locale argument was supplied. This prevents an intermediate release from rendering removed dynamic currency keys or a currency word from another locale.

- [ ] **Step 6: Initialize i18next without the detector or fallback chain**

Configure `supportedLngs: [...SUPPORTED_LOCALES]`, `load: 'languageOnly'`, `fallbackLng: false`, `returnNull: false`, and the result of `resolveInitialLocale`. Read Telegram language from `window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code`, then navigator language. On `languageChanged`, normalize once, persist the canonical value, and update `document.documentElement.lang` from `LOCALE_DEFINITIONS`.

Implement `getActiveLocale()` as `normalizeLocale(i18n.resolvedLanguage ?? i18n.language) ?? DEFAULT_LOCALE`. Implement `changeAppLocale(value)` by normalizing once, defaulting unsupported input to Uzbek, awaiting `i18n.changeLanguage(locale)`, and returning the canonical locale; the shared `languageChanged` listener performs the one local-storage/document update.

Add runtime tests proving an unsupported stored value is repaired to `uz`, a regional stored value is rewritten canonically, and `changeAppLocale('zh-CN')` stores `zh` while setting `<html lang="zh-CN">`. Add an English-only sentinel to an isolated test instance and prove `uz`, `ru`, and `zh` cannot resolve it.

Remove the unused detector and update the lockfile with:

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm uninstall i18next-browser-languagedetector --legacy-peer-deps
```

Change the static HTML declaration to `<html lang="uz">` so pre-JavaScript content does not falsely claim English.

- [ ] **Step 7: Verify GREEN and commit**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/locale.test.ts src/i18n/__tests__/catalog.test.ts
npm run typecheck
cd ..
git add frontend/src/i18n/locale.ts frontend/src/i18n/resources.ts frontend/src/i18n/index.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json frontend/src/i18n/__tests__/locale.test.ts frontend/src/i18n/__tests__/catalog.test.ts frontend/src/utils/format.ts frontend/src/utils/__tests__/format.test.ts frontend/index.html frontend/package.json frontend/package-lock.json
git commit -m "feat: add canonical four-language locale kernel"
```

---

### Task 2: Validate locales on the backend and honor them on every browser request

**Files:**
- Create: `backend/app/localization/__init__.py`
- Create: `backend/app/localization/locale.py`
- Create: `backend/tests/localization/test_locale.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/routers/users.py`
- Modify: `backend/tests/api/test_auth.py`
- Create: `backend/tests/api/test_users.py`
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/services/api.test.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/authStore.ts`
- Modify: `frontend/src/stores/__tests__/authStore.test.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/i18n/locales/{uz,ru,en,zh}.json`

**Interfaces:**

```python
import re
from typing import Literal, TypeAlias, cast

AppLocale: TypeAlias = Literal["uz", "ru", "en", "zh"]
SUPPORTED_LOCALES: tuple[AppLocale, ...] = ("uz", "ru", "en", "zh")
DEFAULT_LOCALE: AppLocale = "uz"
LOCALE_TAG_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")

def normalize_locale(value: object) -> AppLocale | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("_", "-")
    if LOCALE_TAG_PATTERN.fullmatch(normalized) is None:
        return None
    primary = normalized.split("-", 1)[0]
    if primary not in SUPPORTED_LOCALES:
        return None
    return cast(AppLocale, primary)

def parse_accept_language(value: str | None) -> AppLocale | None:
    candidates: list[tuple[float, int, AppLocale]] = []
    for position, raw_entry in enumerate((value or "").split(",")):
        parts = [part.strip() for part in raw_entry.split(";")]
        locale = normalize_locale(parts[0])
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.lower().startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0
        if locale is not None and 0.0 < quality <= 1.0:
            candidates.append((quality, -position, locale))
    return max(candidates)[2] if candidates else None

def choose_locale(header: str | None, saved: object = None) -> AppLocale:
    return parse_accept_language(header) or normalize_locale(saved) or DEFAULT_LOCALE
```

Expose `PublicLocaleDep`, which chooses a valid header or Uzbek, and `UserLocaleDep`, which chooses a valid header, then the authenticated user's valid saved preference, then Uzbek. Both dependencies set `Content-Language` to the resolved canonical code. The canonical frontend header is always one code, but the parser must safely accept regional tags, quality values, and comma-separated browser-style input.

Use these concrete FastAPI signatures so dependency ordering and response headers are unambiguous:

```python
async def get_public_locale(
    response: Response,
    accept_language: Annotated[
        str | None,
        Header(alias="Accept-Language"),
    ] = None,
) -> AppLocale:
    locale = choose_locale(accept_language)
    response.headers["Content-Language"] = locale
    return locale

async def get_user_locale(
    response: Response,
    current_user: CurrentUserDep,
    accept_language: Annotated[
        str | None,
        Header(alias="Accept-Language"),
    ] = None,
) -> AppLocale:
    locale = choose_locale(accept_language, current_user.language)
    response.headers["Content-Language"] = locale
    return locale

PublicLocaleDep = Annotated[AppLocale, Depends(get_public_locale)]
UserLocaleDep = Annotated[AppLocale, Depends(get_user_locale)]
```

Test the dependencies through a tiny FastAPI router that consumes each alias, not by calling dependency functions directly; this proves FastAPI supplies `Response`, authentication, and the header in the intended order. In real routes, FastAPI reuses the endpoint's existing `CurrentUserDep`/`DbDep` results when `UserLocaleDep` depends on the same functions, so locale resolution must not issue a second authentication query.

- [ ] **Step 1: Add compile-only backend locale stubs, then write failing normalization, auth-bootstrap, and validation tests**

Create `backend/app/localization/__init__.py` and a compile-valid `locale.py` exporting the declared aliases/functions/dependencies. Return `None` from pure parsers and `DEFAULT_LOCALE` from selectors/dependencies until Step 4; set no header yet. The tests below must therefore fail assertions, not import collection.

Cover exact/regional/case/underscore values, `zh-*`, unsupported values, and a weighted header. Required assertions include:

```python
assert normalize_locale(" RU-ru ") == "ru"
assert normalize_locale("zh-Hans-CN") == "zh"
assert normalize_locale("fr-FR") is None
assert normalize_locale("en--US") is None
assert normalize_locale("zh-") is None
assert normalize_locale("ru_@") is None
assert parse_accept_language("fr-FR, zh-CN;q=0.9, en;q=0.8") == "zh"
assert parse_accept_language(None) is None
assert choose_locale(None, "ru-RU") == "ru"
assert choose_locale(None, "fr") == "uz"
```

In `test_auth.py`, assert a new Telegram user with `language_code="zh-cn"` persists `language == "zh"`, an unsupported code persists `uz`, and an existing user's saved locale is not overwritten. In `test_users.py`, assert `PUT /api/users/me` accepts only the four canonical codes and rejects `fr` with 422.

Add dependency tests proving a public request without a header resolves `uz`, an authenticated request without a header resolves the user's valid saved locale, an explicit valid header wins, and every localized dependency sets the matching `Content-Language` response header.

- [ ] **Step 2: Write failing frontend request/auth tests**

Assert the Axios interceptor sends the active canonical locale as `Accept-Language`. Extend auth-store tests so both `authenticate()` and `refreshMe()` apply a valid server locale, while an invalid legacy locale is never passed to `i18n.changeLanguage` and triggers a best-effort repair with the current canonical locale. Add `App.test.tsx` assertions that the bootstrap/auth error and Retry action use semantic keys and rerender in the new locale without repeating the failed request.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/localization/test_locale.py tests/api/test_auth.py tests/api/test_users.py -q
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/stores/__tests__/authStore.test.ts src/services/api.test.ts src/App.test.tsx
```

Expected: FAIL because locale validation, request locale, header propagation, refresh synchronization, and legacy repair do not exist.

- [ ] **Step 4: Implement backend normalization and schema boundaries**

Make `UserUpdate.language` an optional `AppLocale`. Make `UserResponse.language` `AppLocale | None` with a `mode="before"` validator that returns `normalize_locale(value)` so invalid legacy data is reported as `null` rather than breaking the response or entering i18next. Implement the two locale dependencies and their `Content-Language` header behavior in the same module.

On user creation only, set:

```python
language = normalize_locale(user_data.get("language_code")) or DEFAULT_LOCALE
```

Do not change an existing user's saved preference during later Telegram authentication.

- [ ] **Step 5: Add the canonical frontend header and server-preference application**

Type `User.language` as `AppLocale | null`. Set `config.headers['Accept-Language'] = getActiveLocale()` in the Axios request interceptor. Extract one auth-store helper used by both authentication paths:

```ts
async function applyServerPreference(user: User): Promise<void> {
  const serverLocale = normalizeLocale(user.language);
  if (serverLocale) {
    await changeAppLocale(serverLocale);
    return;
  }
  await updateMe({ language: getActiveLocale() }).catch(() => undefined);
}
```

Keep auth failures semantic (`auth.role_verification_failed`) rather than storing English sentences. Add that key and `common.retry` to all four catalogs, and make `App.tsx` translate the semantic message and Retry button at render time.

- [ ] **Step 6: Verify GREEN and commit**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/localization/test_locale.py tests/api/test_auth.py tests/api/test_users.py -q
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/stores/__tests__/authStore.test.ts src/services/api.test.ts src/App.test.tsx
npm run typecheck
cd ..
git add backend/app/localization/__init__.py backend/app/localization/locale.py backend/app/schemas/user.py backend/app/routers/auth.py backend/app/routers/users.py backend/tests/localization/test_locale.py backend/tests/api/test_auth.py backend/tests/api/test_users.py frontend/src/services/api.ts frontend/src/services/api.test.ts frontend/src/types/api.ts frontend/src/stores/authStore.ts frontend/src/stores/__tests__/authStore.test.ts frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json
git commit -m "feat: normalize and propagate application locale"
```

---

### Task 3: Add the shared selector with persistence and rollback

**Files:**
- Create: `frontend/src/components/LanguageSelector.tsx`
- Create: `frontend/src/components/LanguageSelector.test.tsx`
- Create: `frontend/src/services/localePreference.ts`
- Create: `frontend/src/services/localePreference.test.ts`
- Modify: `frontend/src/pages/artisan/ArtisanProfilePage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanProfilePage.test.tsx`
- Modify: `frontend/src/pages/staff/StaffProfilePage.tsx`
- Modify: `frontend/src/pages/staff/StaffProfilePage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/artisan/TableContextBar.tsx`
- Modify: `frontend/src/components/artisan/TableContextBar.test.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.tsx`
- Create: `frontend/src/pages/artisan/ArtisanMenuPage.test.tsx`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/menuStore.ts`
- Modify: `frontend/src/stores/cartStore.ts`
- Modify: `frontend/src/stores/tableOrderStore.ts`
- Modify: `frontend/src/stores/__tests__/menuStore.test.ts`
- Modify: `frontend/src/stores/__tests__/cartStore.test.ts`
- Modify: `frontend/src/stores/__tests__/tableOrderStore.test.ts`
- Modify: `frontend/src/i18n/locales/{uz,ru,en,zh}.json`

**Interfaces:**

```ts
export interface LocalePreferenceDependencies {
  isAuthenticated(): boolean;
  save(locale: AppLocale): Promise<void>;
  refreshMenu(): Promise<MenuData>;
  reconcileCart(items: MenuItem[]): void;
  maskCartLocalizedContent(): void;
  refreshTableContext(): Promise<void>;
}

export async function changeLocalePreference(
  next: AppLocale,
  dependencies?: LocalePreferenceDependencies,
): Promise<void>;

export interface LanguageSelectorProps {
  onLocaleCommitted?: () => void | Promise<void>;
}
```

- [ ] **Step 1: Add compile-only selector/orchestration stubs, then write failing tests using real resources**

Create a selector that renders no options and a `changeLocalePreference()` stub that resolves without side effects. Export the declared interfaces so tests compile; do not add implementation behavior before RED.

For each active locale, render the component and assert exactly four radios, one checked radio, and the translated labels from the table in Task 1. Assert selecting `zh` changes the interface immediately and saves canonical `zh`, not `zh-CN`. Render `StaffProfilePage` once with a staff user and once with an admin user to prove both roles reach the same shared selector.

- [ ] **Step 2: Write failing persistence/rollback tests**

Test these exact sequences:

1. unauthenticated change: apply locale, persist locally, skip profile API, refresh menu and any active table context;
2. authenticated success: apply locale, persist locally, save profile, refresh menu and any active table context, then reconcile cart names without changing ID/quantity/price;
3. profile save failure: restore previous i18next locale and previous local-storage value, do not refresh menu or table context, reject with semantic code `profile.language_save_error`;
4. menu refresh failure after a successful profile save: keep the new locale/profile value, set `menu=null`, mark the menu unloaded, replace every cart item/modifier display name with `null`, and render only the new locale's generic item/menu-load labels while retaining IDs, quantity, price, selections, and availability;
5. table refresh failure after a successful profile save: keep the new locale/profile value and the table access token/service percentage/re-resolution handle, replace `tableTitle`/`hallTitle` with `null`, and render only new-locale generic table/hall labels;
6. order-history callback failure after the profile save: keep the committed local/server locale and let the order page expose its own localized load error; never reinterpret it as a language-save failure or roll back;
7. English to Chinese with menu and table refresh failures: rendered menu, cart, table context, and persisted session context contain no prior English display label;
8. successful Chinese menu refresh omits a cart item ID that was present in English: remove that unmatched entry through the existing availability reconciliation, retain all matched entries with their commercial fields, and show only the Chinese `menu.cart_adjusted` notice—never the old English item name;
9. delayed profile order-history race: the initial English request starts, a Chinese refetch starts after commit, Chinese resolves first, English resolves last, and only Chinese order/item/modifier/table/hall display data remains.

Run the save-failure case once with a prior stored locale and once with no storage entry. Rollback restores the exact previous string when present and removes the key when it was previously absent; it must not manufacture a different local preference.

Also write two race tests: start delayed English menu/table requests, change to Chinese, resolve the Chinese requests first and the English requests last, and assert both stores retain only the Chinese responses. A save-failure rollback must not start either refresh and must retain the prior-language data.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/components/LanguageSelector.test.tsx src/services/localePreference.test.ts src/pages/artisan/ArtisanProfilePage.test.tsx src/stores/__tests__/menuStore.test.ts src/stores/__tests__/cartStore.test.ts src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx src/components/artisan/TableContextBar.test.tsx src/pages/artisan/ArtisanCheckoutPage.test.tsx src/pages/artisan/ArtisanMenuPage.test.tsx
```

- [ ] **Step 4: Implement the orchestration and shared selector**

Render options exclusively from `SUPPORTED_LOCALES`; never hardcode a second locale list. Resolve each label through `LOCALE_DEFINITIONS[code].labelKey`; never reconstruct `profile.language_${code}`. The selector owns a localized saving state and localized retryable error, but no English constant.

Add `profile.language_saving`, `profile.language_save_error`, `menu.load_error`, `common.item`, `common.modifier`, `table.current_table`, and `table.current_hall` to all four catalogs before rendering them. The generic/error keys are required for stale-data masking and must be fully translated. The approved save-failure behavior is rollback: do not retain the failed selection locally. Use these exact failure messages so the copy matches the behavior: `Tilni saqlab bo'lmadi. Avvalgi til tiklandi.`, `Не удалось сохранить язык. Предыдущий язык восстановлен.`, `Could not save the language. The previous language was restored.`, and `无法保存语言，已恢复之前的语言。`.

Make `menuStore.refreshMenu()` return the loaded `MenuData` on success and reject with its semantic `menu.load_error` key on failure. Track `loadedLocale` and a monotonic request sequence; reuse cached data only for the same locale and discard any response whose captured locale/sequence is no longer current. On failure for the current sequence, clear `menu`, set `loaded=false`, set `loadedLocale=null`, and keep only that semantic key. `ArtisanMenuPage` translates the key at render time in this task, so no raw key or captured old-language sentence appears before Task 5 generalizes the state to `LocalizedMessage`. Reconcile every existing cart entry from the refreshed item map using stable item/modifier IDs, replacing localized item `name`/`description` and selected modifier display names while retaining quantity, current server price, availability, modifier identity, and selections.

Define `LocalizedModifierSelection` as `{ id: string; name: string | null; quantity: number; price: number }` and `CartItem` as `Omit<MenuItem, 'name' | 'description'> & { name: string | null; description: string | null; modifications?: LocalizedModifierSelection[]; quantity: number }` so failure masking is type-correct. `maskCartLocalizedContent()` sets only item and selected-modifier display names/descriptions to `null`; cart renderers use `t('common.item')` and `t('common.modifier')` for null values. It must never remove or alter an ID, selection, quantity, price, or availability field.

Extend persisted `TableContext` with nullable `tableTitle`/`hallTitle`, `loadedLocale`, `manualCode`, and a safe `refreshHandle` union of `{kind:'code', value:string}` or `{kind:'order', value:string}`. `resolveEntry()` stores the response's `manual_code` as the code handle; `resolveCode()` stores its normalized code; `restoreOrder()` stores the order ID. `refreshTableContext()` re-resolves only that retained handle, uses its own monotonic sequence/locale guard, and on current-request failure persists the context with both localized titles set to `null` while retaining the token/service percentage/handle. When session data was saved under a different locale, hydration masks its titles and rewrites the sanitized null-title context to session storage before exposing it; `App.tsx` then calls the same refresh method after locale/auth bootstrap. No untrusted or expired QR entry is persisted for re-resolution.

After a locale save/local-only commit, run menu and table refreshes with `Promise.allSettled`. Reconcile cart only from a successful same-locale menu response; mask cart content when the current menu refresh fails. A refresh failure is post-commit and therefore never enters the profile-save rollback branch.

On a successful menu response, feed its item list through the existing availability reconciliation before relabeling. An existing cart entry whose stable ID is absent from the localized response is removed (the current missing/unavailable behavior) and triggers the render-time localized `menu.cart_adjusted` notice; it may not survive with an old-language name. Matched entries retain IDs, quantities, prices, selections, and availability while receiving current-locale display copy.

- [ ] **Step 5: Replace both profile implementations**

Use the shared component in the customer profile, including its logged-out state, and in the staff profile. Admins use the staff shell/profile route, so the same component covers admin without a third copy.

The customer profile passes an `onLocaleCommitted` callback that refetches its already-visible order history so item, modifier, table, and hall display names change immediately. Route both its initial `getOrders()` and this refetch through one helper that captures `getActiveLocale()` plus a monotonic request sequence; commit `orders` only when both still match at resolution. This prevents an initial/delayed English response from overwriting a newer Chinese response. Call the callback only after a successful authenticated save (or immediately for an unauthenticated local change), never after rollback. Invoke it after the locale-sensitive store refresh has settled; catch no error as a save error, because the profile's order-history section must retain the committed locale and expose its own localized load state.

- [ ] **Step 6: Verify GREEN and commit**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/components/LanguageSelector.test.tsx src/services/localePreference.test.ts src/pages/artisan/ArtisanProfilePage.test.tsx src/pages/staff/StaffProfilePage.test.tsx src/stores/__tests__/menuStore.test.ts src/stores/__tests__/cartStore.test.ts src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx src/components/artisan/TableContextBar.test.tsx src/pages/artisan/ArtisanCheckoutPage.test.tsx src/pages/artisan/ArtisanMenuPage.test.tsx
npm run typecheck
cd ..
git add frontend/src/components/LanguageSelector.tsx frontend/src/components/LanguageSelector.test.tsx frontend/src/services/localePreference.ts frontend/src/services/localePreference.test.ts frontend/src/pages/artisan/ArtisanProfilePage.tsx frontend/src/pages/artisan/ArtisanProfilePage.test.tsx frontend/src/pages/staff/StaffProfilePage.tsx frontend/src/pages/staff/StaffProfilePage.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/artisan/TableContextBar.tsx frontend/src/components/artisan/TableContextBar.test.tsx frontend/src/pages/artisan/ArtisanCheckoutPage.tsx frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx frontend/src/pages/artisan/ArtisanMenuPage.tsx frontend/src/pages/artisan/ArtisanMenuPage.test.tsx frontend/src/types/api.ts frontend/src/stores/menuStore.ts frontend/src/stores/cartStore.ts frontend/src/stores/tableOrderStore.ts frontend/src/stores/__tests__/menuStore.test.ts frontend/src/stores/__tests__/cartStore.test.ts frontend/src/stores/__tests__/tableOrderStore.test.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json
git commit -m "feat: share persistent four-language selector"
```

---

### Task 4: Replace browser-facing backend prose with stable error codes

**Files:**
- Create: `backend/app/localization/errors.py`
- Create: `backend/tests/localization/test_errors.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/middleware/telegram_auth.py`
- Modify: `backend/app/services/permissions.py`
- Modify: `backend/app/services/admin_user_service.py`
- Modify: `backend/app/services/staff_delivery_service.py`
- Modify: `backend/app/services/table_access_service.py`
- Modify: `backend/app/services/order_service.py`
- Modify: `backend/app/services/menu_catalog_service.py`
- Modify: `backend/app/routers/{auth,addresses,admin,geocoding,menu,orders,staff,tables,users}.py`
- Modify: `backend/tests/api/{test_auth,test_users,test_addresses,test_admin_users,test_menu,test_orders_create,test_orders_status,test_staff_delivery,test_tables}.py`
- Create: `backend/tests/api/test_geocoding.py`
- Modify: `backend/tests/{test_admin_user_service,test_menu_catalog_service,test_order_service,test_table_access_service}.py`

**Interfaces:**

```python
class BrowserErrorCode(StrEnum):
    VALIDATION_FAILED = "validation_failed"
    AUTH_FAILED = "auth_failed"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    ADDRESS_NOT_FOUND = "address_not_found"
    INVALID_TABLE_QR = "invalid_table_qr"
    TABLE_CODE_NOT_FOUND = "table_code_not_found"
    TABLE_TOKEN_INVALID = "table_token_invalid"
    TABLE_TOKEN_EXPIRED = "table_token_expired"
    TABLE_UNAVAILABLE = "table_unavailable"
    TABLE_ORDER_NOT_FOUND = "table_order_not_found"
    CART_CONFLICT = "cart_conflict"
    DELIVERY_ADDRESS_NOT_FOUND = "delivery_address_not_found"
    DELIVERY_ADDRESS_REQUIRED = "delivery_address_required"
    DELIVERY_COORDINATES_REQUIRED = "delivery_coordinates_required"
    ORDER_NOT_FOUND = "order_not_found"
    ORDER_SUBMISSION_FAILED = "order_submission_failed"
    ORDER_NOT_CANCELLABLE = "order_not_cancellable"
    ORDER_STATUS_UNAVAILABLE = "order_status_unavailable"
    ORDER_CANCELLATION_FAILED = "order_cancellation_failed"
    PAYMENT_METHOD_UNAVAILABLE = "payment_method_unavailable"
    PAYMENT_CHECKOUT_FAILED = "payment_checkout_failed"
    PAYMENT_SWITCH_NOT_ALLOWED = "payment_switch_not_allowed"
    PAYMENT_SWITCH_FAILED = "payment_switch_failed"
    PAYMENT_RETRY_NOT_ALLOWED = "payment_retry_not_allowed"
    GEOCODING_UNAVAILABLE = "geocoding_unavailable"
    STAFF_ORDER_NOT_FOUND = "staff_order_not_found"
    STAFF_ORDER_TAKEN = "staff_order_taken"
    STAFF_ACTIVE_ORDER_EXISTS = "staff_active_order_exists"
    STAFF_NOT_ASSIGNED = "staff_not_assigned"
    STAFF_ORDER_CANCELLED = "staff_order_cancelled"
    STAFF_ORDER_NOT_READY = "staff_order_not_ready"
    USER_NOT_FOUND = "user_not_found"
    INVALID_ROLE = "invalid_role"
    FINAL_ADMIN_REQUIRED = "final_admin_required"
    CONTENT_UNAVAILABLE = "content_unavailable"
    UNKNOWN = "unknown"

def error_detail(code: BrowserErrorCode, **params: object) -> dict[str, object]:
    return {"code": code.value, "params": params}

def api_error(status_code: int, code: BrowserErrorCode, **params: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error_detail(code, **params))
```

**Required browser error matrix:**

| Browser operation/branch | HTTP | `detail.code` |
|---|---:|---|
| `POST /auth/telegram`, invalid Telegram init data | 401 | `auth_failed` |
| Any authenticated route, absent/malformed/expired JWT or missing user | 401 | `unauthorized` |
| Staff/admin permission check | 403 | `forbidden` |
| Any FastAPI/Pydantic request validation failure | 422 | `validation_failed` |
| `PUT/DELETE /addresses/{id}`, owned address absent | 404 | `address_not_found` |
| `POST /tables/resolve`, malformed/signed QR | 400 | `invalid_table_qr` |
| `POST /tables/resolve`, manual code absent | 404 | `table_code_not_found` |
| Order creation, malformed table access token | 400 | `table_token_invalid` |
| Order creation, expired table access token | 400 | `table_token_expired` |
| Order creation/restore, provider table absent | 400 on create; 409 on restore | `table_unavailable` |
| `POST /tables/restore/{id}`, order absent/expired/not owned | 404 | `table_order_not_found` |
| `POST /tables/restore/{id}`, token-expiry race after the eligibility query | 409 | `table_token_expired` |
| Order creation, priced cart changed | 409 | `cart_conflict` with only `params.changes` |
| Order creation, selected delivery address absent | 400 | `delivery_address_not_found` |
| Order creation, delivery address omitted | 400 | `delivery_address_required` |
| Order creation, map coordinates omitted | 400 | `delivery_coordinates_required` |
| Customer order/detail/status/switch/retry/cancel, order absent | 404 | `order_not_found` |
| Order creation or cash-switch provider submission rejected | 502 | `order_submission_failed` |
| Requested AliPOS payment method absent | 502 | `payment_method_unavailable` |
| Online checkout creation failed before a safe order response | 502 | `payment_checkout_failed` |
| Customer cancellation violates lifecycle | 409 | `order_not_cancellable` |
| Customer cancellation provider result unknown | 502 | `order_cancellation_failed` |
| Cash switch violates lifecycle | 409 | `payment_switch_not_allowed` |
| Cash switch cannot confirm invoice cancellation | 502 | `payment_switch_failed` |
| Online payment retry violates lifecycle | 409 | `payment_retry_not_allowed` |
| Reverse geocode/suggest provider failure | 502 | `geocoding_unavailable` |
| Menu fetch/pricing or table-directory provider failure | 503 | `content_unavailable` |
| Staff order absent or hidden by availability rules | 404 | `staff_order_not_found` |
| Staff already has another active delivery | 409 | `staff_active_order_exists` |
| Another staff member already took the order | 409 | `staff_order_taken` |
| Staff reads/completes another assignee's order | 403 | `staff_not_assigned` |
| Staff refresh cannot verify current provider status | 503 | `order_status_unavailable` |
| Staff order is no longer ready/payment-eligible | 409 | `staff_order_not_ready` |
| Staff attempts to complete a cancelled order | 409 | `staff_order_cancelled` |
| Admin target user absent | 404 | `user_not_found` |
| Defensive admin-service role value outside the schema allowlist | 422 | `invalid_role` |
| Admin attempts to demote the final admin | 409 | `final_admin_required` |
| Unexpected browser-route exception after logging | 500 | `unknown` |

All entries except `cart_conflict` have empty `params`. `cart_conflict.params.changes` retains the existing typed cart-change records needed for reconciliation; it contains IDs, quantities, prices, and availability only, never exception/provider prose.

Keep two existing non-error behaviors unchanged: customer order-status polling suppresses an AliPOS refresh failure and returns the cached status with 200, and invoice creation failures persist/return `PAYMENT_REVIEW` or `PAYMENT_FAILED` order state rather than raising `PaymentCheckoutError`. Preserve `payment_method_unavailable` as the nested public cause when submission wrapping would otherwise collapse it to `order_submission_failed`.

- [ ] **Step 1: Add a compile-only error-envelope stub, then write failing contract tests for every user-visible route family**

Create `errors.py` with the complete `BrowserErrorCode` enum and make `error_detail()`/`api_error()` return the `UNKNOWN` envelope regardless of input. This keeps collection valid while every code-specific assertion below remains RED.

Parameterize the existing API fixtures and assert browser-facing failures have exactly:

```python
assert response.json()["detail"] == {"code": expected_code, "params": expected_params}
assert raw_provider_message not in response.text
```

Add a FastAPI request-validation test that sends an invalid role/order/table payload and expects `validation_failed`, with no Pydantic message in the body. Keep webhook-only operational endpoints out of this browser contract.

- [ ] **Step 2: Run focused API tests and verify RED**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/localization/test_errors.py tests/api/test_auth.py tests/api/test_users.py tests/api/test_addresses.py tests/api/test_admin_users.py tests/api/test_menu.py tests/api/test_orders_create.py tests/api/test_orders_status.py tests/api/test_staff_delivery.py tests/api/test_tables.py tests/api/test_geocoding.py -q
```

- [ ] **Step 3: Implement the shared envelope and validation handler**

Register a `RequestValidationError` handler that returns status 422 and `{"detail":{"code":"validation_failed","params":{}}}`. Register a final `Exception` handler that logs the traceback internally and returns status 500 with `unknown`; it must not include exception text in the response. Do not echo field values or validation prose.

Replace string comparisons with semantic exception attributes. For example, `InvalidTableEntry` must carry `code: BrowserErrorCode`; routers use that code directly instead of comparing `str(exc)` to English text. Give order-service exception classes fixed public codes while retaining detailed internal exception/log text.

- [ ] **Step 4: Convert authentication, permission, and customer routes**

Convert authentication middleware, auth, address, menu, table, order, and geocoding branches according to the matrix. Wrap menu-catalog and table-directory provider failures once at their service boundary as `content_unavailable`, then map that semantic exception in `/menu`, `/tables`, and `/orders`; do not repeat broad provider catches in each router. Preserve HTTP statuses. Put only safe structured values needed for interpolation or client behavior in `params`; keep cart `changes` structured, but never place exception/provider prose there. Run the auth/address/menu/order/table/geocoding subset before continuing.

- [ ] **Step 5: Convert staff and admin routes**

Replace staff-delivery and admin-user HTTP prose at the service boundary using the matrix. Preserve internal exception/log text for diagnostics, but never pass it to `HTTPException.detail`. Run the staff/admin API and service subsets before the combined gate.

- [ ] **Step 6: Verify raw provider text suppression and GREEN**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/localization/test_errors.py tests/api/test_auth.py tests/api/test_users.py tests/api/test_addresses.py tests/api/test_admin_users.py tests/api/test_menu.py tests/api/test_orders_create.py tests/api/test_orders_status.py tests/api/test_staff_delivery.py tests/api/test_tables.py tests/api/test_geocoding.py tests/test_admin_user_service.py tests/test_menu_catalog_service.py tests/test_order_service.py tests/test_table_access_service.py -q
.venv/bin/ruff check app/localization app/main.py app/middleware/telegram_auth.py app/routers app/services tests/localization
cd ..
git add backend/app/localization/errors.py backend/app/main.py backend/app/middleware/telegram_auth.py backend/app/services/permissions.py backend/app/services/admin_user_service.py backend/app/services/menu_catalog_service.py backend/app/services/staff_delivery_service.py backend/app/services/table_access_service.py backend/app/services/order_service.py backend/app/routers/auth.py backend/app/routers/addresses.py backend/app/routers/admin.py backend/app/routers/geocoding.py backend/app/routers/menu.py backend/app/routers/orders.py backend/app/routers/staff.py backend/app/routers/tables.py backend/app/routers/users.py backend/tests/localization/test_errors.py backend/tests/api/test_auth.py backend/tests/api/test_users.py backend/tests/api/test_addresses.py backend/tests/api/test_admin_users.py backend/tests/api/test_menu.py backend/tests/api/test_orders_create.py backend/tests/api/test_orders_status.py backend/tests/api/test_staff_delivery.py backend/tests/api/test_tables.py backend/tests/api/test_geocoding.py backend/tests/test_admin_user_service.py backend/tests/test_menu_catalog_service.py backend/tests/test_order_service.py backend/tests/test_table_access_service.py
git commit -m "refactor: return stable localized error codes"
```

---

### Task 5: Resolve errors and statuses semantically in the frontend

**Files:**
- Create: `frontend/src/i18n/errors.ts`
- Create: `frontend/src/i18n/status.ts`
- Create: `frontend/src/i18n/__tests__/errors.test.ts`
- Create: `frontend/src/i18n/__tests__/status.test.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/{authStore,menuStore,tableOrderStore}.ts`
- Modify: `frontend/src/stores/__tests__/{authStore,menuStore,tableOrderStore}.test.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.test.tsx`
- Modify: `frontend/src/components/artisan/TableCodeSheet.tsx`
- Modify: `frontend/src/components/artisan/TableCodeSheet.test.tsx`
- Modify: `frontend/src/i18n/locales/{uz,ru,en,zh}.json`

**Interfaces:**

```ts
export interface LocalizedMessage {
  key: string;
  values?: Record<string, string | number>;
}

export interface ApiErrorDetail {
  code: string;
  params: Record<string, unknown>;
}

export const API_ERROR_TRANSLATION_KEYS: readonly string[];
export const ORDER_STATUS_TRANSLATION_KEYS: readonly string[];
export const PAYMENT_STATUS_TRANSLATION_KEYS: readonly string[];
export const SYNC_STATUS_TRANSLATION_KEYS: readonly string[];
export const REFUND_STATUS_TRANSLATION_KEYS: readonly string[];
export const ROLE_TRANSLATION_KEYS: readonly string[];

export function getApiErrorDetail(error: unknown): ApiErrorDetail | null;

export function resolveApiError(
  error: unknown,
  fallbackKey: string,
): LocalizedMessage;

export type UnknownStatusReporter = (event: {
  kind: 'order' | 'payment' | 'sync' | 'refund' | 'role';
  value: string;
}) => void;

export function orderStatusKey(
  status: string | null | undefined,
  reportUnknown?: UnknownStatusReporter,
): string;
export function paymentStatusKey(
  status: string | null | undefined,
  reportUnknown?: UnknownStatusReporter,
): string;
export function syncStatusKey(
  status: string | null | undefined,
  reportUnknown?: UnknownStatusReporter,
): string;
export function refundStatusKey(
  status: string | null | undefined,
  reportUnknown?: UnknownStatusReporter,
): string;
export function roleKey(
  role: string | null | undefined,
  reportUnknown?: UnknownStatusReporter,
): string;
```

- [ ] **Step 1: Add compile-only resolver/status stubs, then write failing error-resolution tests**

Create `errors.ts` and `status.ts` with the declared exports. Return the provided fallback from `resolveApiError()` and only the generic unknown keys from the status/role functions; do not inspect responses or report unknowns yet.

Assert known `{detail:{code,params}}` responses become `errors.<code>` plus only code-specific whitelisted primitive interpolation values. Assert string `detail`, array validation errors, HTML errors, timeouts, unknown codes, and raw provider text all become the supplied generic fallback and never enter the returned message. `getApiErrorDetail()` may expose typed `cart_conflict.params.changes` to the existing cart-reconciliation branch, but `resolveApiError()` must never copy that nested structure into translation values or rendered text.

Before implementation, update `App.test.tsx`, `ArtisanMenuPage.test.tsx`, and `TableCodeSheet.test.tsx` with failing consumer assertions: make a semantic error visible in English, switch the singleton to Chinese, and require the already-visible error and Retry/action label to rerender in Chinese without repeating the request. These tests must fail on the current string state/props, before the components are changed.

- [ ] **Step 2: Write failing exhaustive status tests**

Enumerate every currently supported order/payment/refund/sync/staff state. Inject a reporter spy and prove each new unknown non-empty enum produces one secret-safe `{kind, value}` event while the UI receives only the generic translation key. Required unknown behavior:

Use this exact finite fixture and key mapping:

| Kind | Provider values | Translation key |
|---|---|---|
| order | `NEW`, `PAID_AWAITING_RESTAURANT` | `status.placed` |
| order | `AWAITING_PAYMENT` | `status.awaiting_payment` |
| order | `PAYMENT_FAILED` | `status.payment_failed` |
| order | `PAYMENT_REVIEW` | `status.payment_review` |
| order | `ACCEPTED_BY_RESTAURANT` | `status.preparing` |
| order | `READY` | `status.ready` |
| order | `TAKEN_BY_COURIER` | `status.on_the_way` |
| order | `DELIVERED` | `status.delivered` |
| order | `CANCELED`, `CANCELLED` | `status.cancelled` |
| order | `SYNC_UNKNOWN` | `status.sync_unknown` |
| order | `SUBMISSION_FAILED` | `status.submission_failed` |
| payment | `pending` | `payment.state_pending` |
| payment | `paid` | `payment.state_paid` |
| payment | `failed` | `payment.state_failed` |
| payment | `invoice_unknown` | `payment.state_invoice_unknown` |
| payment | `expired` | `payment.state_expired` |
| payment | `cancelled` | `payment.state_cancelled` |
| payment | `refund_pending` | `payment.state_refund_pending` |
| payment | `refund_failed` | `payment.state_refund_failed` |
| payment | `refunded` | `payment.state_refunded` |
| sync | `awaiting_payment` | `sync.awaiting_payment` |
| sync | `queued` | `sync.queued` |
| sync | `sending` | `sync.sending` |
| sync | `synced` | `sync.synced` |
| sync | `failed` | `sync.failed` |
| sync | `unknown` | `sync.provider_unknown` |
| refund | `queued` | `refund.queued` |
| refund | `sending` | `refund.sending` |
| refund | `failed` | `refund.failed` |
| refund | `unknown` | `refund.provider_unknown` |
| refund | `refunded` | `refund.refunded` |
| role | `customer` | `roles.customer` |
| role | `staff` | `roles.staff` |
| role | `admin` | `roles.admin` |

Any other non-empty value maps by kind to `status.unknown`, `payment.state_unknown`, `sync.unknown`, `refund.unknown`, or `roles.unknown` and emits one reporter event. Null, undefined, and empty input map to the same generic key without a report.

```ts
expect(orderStatusKey('TAKEN_BY_COURIER')).toBe('status.on_the_way');
expect(orderStatusKey('NEW_PROVIDER_STATE')).toBe('status.unknown');
expect(paymentStatusKey('NEW_PROVIDER_STATE')).toBe('payment.state_unknown');
expect(syncStatusKey('NEW_PROVIDER_STATE')).toBe('sync.unknown');
expect(refundStatusKey('NEW_PROVIDER_STATE')).toBe('refund.unknown');
expect(roleKey('owner')).toBe('roles.unknown');
```

- [ ] **Step 3: Run focused tests and verify RED**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/errors.test.ts src/i18n/__tests__/status.test.ts src/stores/__tests__/authStore.test.ts src/stores/__tests__/menuStore.test.ts src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx src/pages/artisan/ArtisanMenuPage.test.tsx src/components/artisan/TableCodeSheet.test.tsx
```

- [ ] **Step 4: Implement resolvers, semantic stores, and their current consumers**

Stores retain `LocalizedMessage | null`, never translated prose. Components call `t(message.key, message.values)` at render time so an already-visible error changes language immediately. Remove all raw `response.data.detail` rendering and English allowlists.

Change `AuthRetryShell`, the `ArtisanMenuPage` menu error, and `TableCodeSheet.error` to accept/render `LocalizedMessage | null` in this same task, satisfying the already-failing consumer tests from Step 1. Do not leave string-compatible union props as a bridge; `npm run typecheck` must remain green at this task boundary.

The error/status modules export the exact readonly translation-key sets declared above, and their mappings must be derived from or checked against those sets so the audit configuration cannot drift from runtime behavior. The status mapper owns a default reporter that emits only the status kind and raw enum value to the existing developer console/logger; it must not include an API response or customer data. Tests inject `UnknownStatusReporter` and assert one report for an unknown non-empty value and no report for `null`, `undefined`, or an empty value.

Add every `errors.*`, every mapped order/payment/sync/refund status plus its localized unknown key, and `roles.*` to all four resources in the same commit. Include precise reviewed translations; do not use a generic English value in Uzbek, Russian, or Chinese.

- [ ] **Step 5: Verify GREEN and commit**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/errors.test.ts src/i18n/__tests__/status.test.ts src/stores/__tests__/authStore.test.ts src/stores/__tests__/menuStore.test.ts src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx src/pages/artisan/ArtisanMenuPage.test.tsx src/components/artisan/TableCodeSheet.test.tsx src/i18n/__tests__/catalog.test.ts
npm run typecheck
cd ..
git add frontend/src/i18n/errors.ts frontend/src/i18n/status.ts frontend/src/i18n/__tests__/errors.test.ts frontend/src/i18n/__tests__/status.test.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json frontend/src/types/api.ts frontend/src/stores/authStore.ts frontend/src/stores/menuStore.ts frontend/src/stores/tableOrderStore.ts frontend/src/stores/__tests__/authStore.test.ts frontend/src/stores/__tests__/menuStore.test.ts frontend/src/stores/__tests__/tableOrderStore.test.ts frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/pages/artisan/ArtisanMenuPage.tsx frontend/src/pages/artisan/ArtisanMenuPage.test.tsx frontend/src/components/artisan/TableCodeSheet.tsx frontend/src/components/artisan/TableCodeSheet.test.tsx
git commit -m "feat: localize semantic errors and statuses"
```

---

### Task 5A: Build the source audit before migrating UI surfaces

**Files:**
- Create: `frontend/src/i18n/__tests__/support/sourceAudit.ts`
- Create: `frontend/src/i18n/__tests__/support/sourceAuditConfig.ts`
- Create: `frontend/src/i18n/__tests__/sourceAudit.test.ts`
- Create: `frontend/src/i18n/__tests__/sourceAudit.scope.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/tsconfig.json`

**Interfaces:**

```ts
export type AuditSurface =
  | 'translation-call'
  | 'jsx-text'
  | 'html-attribute'
  | 'component-prop'
  | 'semantic-identifier'
  | 'ui-call';

export interface SourceFile {
  path: string;
  text: string;
}

export interface DynamicKeyContract {
  file: string;
  expression: string;
  allowedKeys: readonly string[];
}

export interface LiteralAllowance {
  file: string;
  line: number;
  surface: AuditSurface;
  value: string;
  reason: string;
}

export interface SourceAuditOptions {
  sources: readonly SourceFile[];
  localeKeys: ReadonlySet<string>;
  dynamicKeyContracts: readonly DynamicKeyContract[];
  literalAllowances: readonly LiteralAllowance[];
  uiAttributes: ReadonlySet<string>;
  uiComponentProps: ReadonlySet<string>;
  uiCallSinks: ReadonlySet<string>;
}

export type AuditFinding =
  | { kind: 'parse-error'; file: string; line: number; column: number; value: string }
  | { kind: 'missing-static-key'; file: string; line: number; column: number; value: string }
  | { kind: 'inline-default-value'; file: string; line: number; column: number; value: string }
  | { kind: 'uncontracted-dynamic-key'; file: string; line: number; column: number; value: string }
  | { kind: 'missing-dynamic-key'; file: string; line: number; column: number; value: string }
  | { kind: 'raw-api-detail-access'; file: string; line: number; column: number; value: string }
  | { kind: 'hard-coded-ui-text'; file: string; line: number; column: number; value: string; surface: AuditSurface };

export function auditLocalizationSources(
  options: SourceAuditOptions,
): readonly AuditFinding[];
export function formatAuditFindings(findings: readonly AuditFinding[]): string;
```

`sourceAuditConfig.ts` is the single owned configuration module. It exports `DYNAMIC_KEY_CONTRACTS`, `LITERAL_ALLOWANCES`, `UI_ATTRIBUTES`, `UI_COMPONENT_PROPS`, `UI_CALL_SINKS`, and `SHIPPED_SOURCE_EXTENSIONS` (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`). Scoped and repository-wide runners import these exports; no runner duplicates an inline list.

- [ ] **Step 1: Install test-only Node types and add a compile-only audit stub**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm install --save-dev @types/node@^22 --legacy-peer-deps
```

Add `node` to `compilerOptions.types`. Create `sourceAudit.ts` with the exact exported types above; its temporary `auditLocalizationSources()` returns `[]` and `formatAuditFindings()` returns an empty string. Create a compile-valid `sourceAuditConfig.ts` exporting the declared arrays/sets with the exact UI lists from Step 2 and initially empty contracts/allowances. These are only to make the RED tests compile.

- [ ] **Step 2: Write focused failing AST fixture tests**

Build in-memory `.tsx` fixtures that require findings for:

- literal and no-substitution-template `t()` keys missing from the supplied key set;
- `t(key, 'fallback copy')` and `t(key, { defaultValue: 'fallback copy' })`;
- an unregistered dynamic `t(expression)` and a registered family containing a missing key;
- direct Axios/FastAPI `.response.data.detail` member access outside `src/i18n/errors.ts`;
- alphabetic JSX text in English, Uzbek, Russian, and Chinese;
- rendered string/template branches in JSX expressions;
- string-valued `aria-label`, `aria-description`, `alt`, `placeholder`, and `title` attributes;
- string-valued `actionLabel`, `backTitle`, `description`, `emptyText`, `error`, `label`, `message`, `notice`, `soldOutLabel`, `toast`, and `title` JSX props/object-literal fields (covering UI config arrays/maps and Zustand state updates before they reach JSX);
- string literals assigned to identifiers ending in `_COPY`, `_DESCRIPTION`, `_DETAILS`, `_EMPTY`, `_ERROR`, `_LABEL`, `_MESSAGE`, `_PLACEHOLDER`, `_TEXT`, or `_TITLE`;
- literal arguments to `alert`, `window.alert`, `confirm`, `window.confirm`, `showAlert`, `showConfirm`, `showToast`, `tgAlert`, `setToast`, `setError`, `setMessage`, `setActionError`, `setCartNotice`, `setDeliveryError`, `setMapError`, and `setPageError`.

Add negative fixtures proving the engine ignores CSS/style values, route/API URLs, enum and icon identifiers, test/data IDs, source comments, developer-only `console.*`/`Error(...)` text, punctuation/numbers, and exact approved brands. Approve `OLOT SOMSA`, `/orders`, `receipt_long`, and `#fff` using individual `LiteralAllowance` entries with exact file, line, surface, value, and reason; never create a whole-file exemption.

- [ ] **Step 3: Run the fixture tests and verify RED assertions**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/sourceAudit.test.ts
```

Expected: assertion failures because the compile stub returns no findings, with no import, parse, or type error.

- [ ] **Step 4: Implement the TypeScript-aware engine and scoped runner**

Use the installed TypeScript compiler API, not regular expressions, to parse production `.ts/.tsx/.js/.jsx/.mjs`. Static `t()` keys must be string literals or no-substitution templates and must exist in `localeKeys`. Any other expression must match one exact `DynamicKeyContract`; expand every `allowedKey` and verify it exists. Treat the second string argument and either top-level or nested `defaultValue` as forbidden inline defaults. Reject direct member/element access to Axios/FastAPI `response.data.detail` everywhere except the exact centralized parser file `src/i18n/errors.ts`; callers consume `getApiErrorDetail()` or `resolveApiError()` instead.

Inspect rendered JSX text/expressions and the exact UI attributes, component props/object fields, and call sinks listed above. Use Unicode letter classification (`/\p{L}/u`) for literal content so Cyrillic, Latin, and Han text are treated equally; regex may classify a parsed literal but may not replace the TypeScript AST traversal. Sort findings by `file`, `line`, `column`, `kind`, then `value`, and format each as `file:line:column kind value` so CI output is actionable.

`sourceAudit.scope.test.ts` reads a required comma-separated `I18N_AUDIT_PATHS` environment variable, recursively loads only production files whose extension is in `SHIPPED_SOURCE_EXTENSIONS`, and fails with `formatAuditFindings()`. When the variable is absent, declare the suite skipped; Task 11 supplies the always-on repository-wide integration test.

Seed the scoped runner with these exact dynamic contracts:

- `src/components/artisan/ArtisanLayout.tsx` `item.labelKey`: `nav.menu`, `nav.orders`, `nav.cart`, `nav.profile`;
- `src/components/staff/StaffLayout.tsx` `item.labelKey`: `staff.nav.admin`, `staff.nav.orders`, `staff.nav.profile`;
- `src/components/staff/StaffOrderTabs.tsx` `tab.labelKey`: `staff.tabs.available`, `staff.tabs.active`, `staff.tabs.completed`;
- `src/pages/artisan/ArtisanCheckoutPage.tsx` ``payment_methods.${pm.key}``: `payment_methods.cash`, `payment_methods.rahmat`;
- `src/pages/artisan/ArtisanOrderStatusPage.tsx` `step.labelKey`: `status.placed`, `status.preparing`, `status.ready`, `status.on_the_way`;
- `src/components/LanguageSelector.tsx` `option.labelKey`: the four `LocaleDefinition.labelKey` values;
- `src/App.tsx` `authError.key`: `API_ERROR_TRANSLATION_KEYS` plus `auth.role_verification_failed`;
- `src/pages/artisan/ArtisanMenuPage.tsx` `menuError.key`: `API_ERROR_TRANSLATION_KEYS` plus `menu.load_error`;
- `src/components/artisan/TableCodeSheet.tsx` `tableError.key`: `API_ERROR_TRANSLATION_KEYS` plus `table.lookup_error`.

Import the exported readonly key sets from `src/i18n/errors.ts` and `src/i18n/status.ts` when building these arrays; do not hand-copy them. Later render sites must use a stable variable/expression name and add one exact contract in `sourceAuditConfig.ts` in their owning task.

If a later task introduces another dynamic family, extend this list with its exact expression and finite allowed keys in that same task.

- [ ] **Step 5: Verify the engine GREEN and commit**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/sourceAudit.test.ts
npm run typecheck
cd ..
git add frontend/src/i18n/__tests__/support/sourceAudit.ts frontend/src/i18n/__tests__/support/sourceAuditConfig.ts frontend/src/i18n/__tests__/sourceAudit.test.ts frontend/src/i18n/__tests__/sourceAudit.scope.test.ts frontend/package.json frontend/package-lock.json frontend/tsconfig.json
git commit -m "test: add localization source audit engine"
```

---

### Task 6: Migrate every customer-controlled word and accessible label

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/components/artisan/{ArtisanLayout,MapPickerOverlay,TableCodeSheet,TableContextBar}.tsx`
- Modify: `frontend/src/components/artisan/{TableCodeSheet,TableContextBar}.test.tsx`
- Modify: `frontend/src/pages/artisan/{ArtisanCheckoutPage,ArtisanMenuPage,ArtisanOrdersPage,ArtisanOrderStatusPage,ArtisanProfilePage}.tsx`
- Modify: `frontend/src/pages/artisan/{ArtisanCheckoutPage,ArtisanOrdersPage,ArtisanOrderStatusPage,ArtisanProfilePage}.test.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.test.tsx`
- Create: `frontend/src/test/renderWithLocale.tsx`
- Modify: `frontend/src/i18n/__tests__/support/sourceAuditConfig.ts`
- Modify: `frontend/src/i18n/locales/{uz,ru,en,zh}.json`
- Modify: `frontend/src/types/api.ts`
- Modify: `backend/app/schemas/address.py`
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/routers/addresses.py`
- Modify: `database/init.sql`
- Create: `database/migrations/2026-07-19-address-label-default.sql`
- Modify: `backend/tests/api/test_addresses.py`
- Create: `backend/tests/test_database_migrations.py`

**Mandatory catalog additions:**

- `common`: `retry`, `cancel`, `item`, `unknown`, `avatar_alt`, `close`.
- `auth`: verify the previously introduced `role_verification_failed`.
- `menu`: verify the Task 3 `load_error`; add `retry`, `add_item_aria`, `available_in_cart`.
- `checkout`: `title`, `not_logged_in_desc`, `payment_method_label`, `items_label`, `placing_order`.
- `profile`: `not_logged_in_title`, `not_logged_in_desc`, `login_button`, `logout`, `default_address_label`, `address_entrance_short`, `address_floor_short`, `address_apartment_short`; verify the previously introduced language-saving keys.
- `status`: verify the Task 5 `delivered` and `unknown` keys on customer render sites; do not create a second status family.
- `order`: change `order_number` into a complete `{{number}}` sentence in all four locales.
- `table`: add `service_percent` with `{{percent}}` rather than concatenating a translated fragment and `%`.
- `a11y`: `profile_image`, `brand_logo`, `back`, `close_dialog`.

- [ ] **Step 1: Add compile/file stubs and replace translation mocks with the real four-resource helper**

Export two deliberately different helpers from `renderWithLocale.tsx`:

- `renderWithIsolatedLocale(ui, locale)` creates an isolated i18next instance with exactly one active resource and `fallbackLng: false`; it is only for non-mutating component snapshots. It sets `document.documentElement.lang` from the locale definition before render and restores the previous value during cleanup.
- `renderWithAppLocale(ui, locale)` awaits the real singleton `changeAppLocale(locale)`, renders with the production provider, and restores the previous singleton locale, document language, and storage value during cleanup. Use it for stores, the Axios interceptor, `LanguageSelector`, and any integration whose behavior calls `getActiveLocale()`.

Parameterize representative bootstrap, table, menu, checkout, order list/detail, map, and profile renders across `SUPPORTED_LOCALES` with the appropriate helper. Task 1 separately proves the singleton's production language-change listener.

Create the dated migration file initially as the valid no-op `SELECT 1;` so the migration test can open/execute it before implementation. Create the empty test module and real render helper before adding assertions; RED must not be a missing-file/import failure.

- [ ] **Step 2: Add failing assertions for every audited leak**

Assert the selected resource supplies Retry/Cancel/login/logout, checkout headings/actions, profile address abbreviations/statuses, item fallbacks, menu add-button accessible names, image alternatives, map controls, table dialog labels, and unknown status. Remove tests that accept either Uzbek or English via regex.

Add the address API/migration assertions described in Step 5 now, before changing the model/schema/SQL. The no-op migration and missing provenance field must fail semantic assertions.

- [ ] **Step 3: Run customer tests and verify RED**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/api/test_addresses.py tests/test_database_migrations.py -q
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
I18N_AUDIT_PATHS="src/App.tsx,src/components/artisan,src/pages/artisan" npm run test -- src/i18n/__tests__/sourceAudit.scope.test.ts
npm run test -- src/App.test.tsx src/components/artisan src/pages/artisan
```

Expected: the scoped audit fails with the customer literals/defaults enumerated by file and line; the render tests fail on missing or leaked copy.

- [ ] **Step 4: Add reviewed values to all four catalogs**

Close every item from the original 28-key missing-reference audit, accounting for keys already introduced in Tasks 2–5, and let the catalog/source tests determine the final exact set. Task 1 already corrected every pre-existing catalog-purity leak; this task adds and reviews only the newly introduced customer keys and any source-linked copy defects exposed while migrating these surfaces. Keep brand names unchanged only where they are proper names.

- [ ] **Step 5: Remove every inline default and hardcoded customer string**

Use interpolation for complete sentences and accessible labels. Examples:

```tsx
aria-label={t('menu.add_item_aria', { item: product.name })}
{t('checkout.placing_order')}
{t(orderStatusKey(order.status))}
{t('order.order_number', { number: displayedOrderNumber })}
{t('table.service_percent', { percent: tableContext.servicePercent })}
```

Do not translate or replace actual user-entered address labels. Add `label_is_system_default: bool` to the address model/response and `label_is_system_default BOOLEAN NOT NULL DEFAULT FALSE` to the fresh schema. New-address input defaults to an empty label; the router stores `label=""` plus `label_is_system_default=True` only when the submitted label is blank, and stores any nonblank user label—including an explicitly typed `Home`—verbatim with the flag false. The frontend renders `profile.default_address_label` only when the flag is true or the stored label is blank; it never writes the translated default back into an input or API payload.

Create the dated, idempotent production migration with exactly:

```sql
ALTER TABLE addresses
    ADD COLUMN IF NOT EXISTS label_is_system_default BOOLEAN;
UPDATE addresses
SET label_is_system_default = (label = 'Home')
WHERE label_is_system_default IS NULL;
ALTER TABLE addresses
    ALTER COLUMN label_is_system_default SET DEFAULT FALSE;
ALTER TABLE addresses
    ALTER COLUMN label_is_system_default SET NOT NULL;
ALTER TABLE addresses ALTER COLUMN label SET DEFAULT '';
```

The old application did not record provenance, so the one-time migration classifies pre-migration exact `Home` values as the known historical system sentinel without rewriting their text; every other label remains custom. Because the update touches only rows where the new column is null, rerunning the migration cannot reclassify a future explicit `Home` label stored with `false`.

This intentionally accepts one narrow historical ambiguity: an old user-entered label that was exactly `Home` is indistinguishable from the old application default and is classified as the legacy system sentinel. New explicit `Home` values are unambiguous because the application always writes the provenance flag as false.

In `test_database_migrations.py`, recreate the old column shape inside the PostgreSQL test transaction, insert a legacy `Home`, execute the migration, and assert it is marked true and the label default is empty. Then insert an explicit `Home` with the flag false, execute the migration a second time, and assert it remains false; also inspect `is_nullable` and both column defaults. API tests prove omitted/blank labels store `""` plus true while an explicit `Home` stores `Home` plus false. Frontend tests prove the former follows the active locale and the latter remains verbatim user content.

Extend `sourceAuditConfig.ts` in this task with exact contracts for `src/pages/artisan/ArtisanOrdersPage.tsx` `orderStatusTranslationKey` and `src/pages/artisan/ArtisanOrderStatusPage.tsx` `orderStatusTranslationKey` using `ORDER_STATUS_TRANSLATION_KEYS`, plus `src/pages/artisan/ArtisanOrderStatusPage.tsx` `paymentStatusTranslationKey` using `PAYMENT_STATUS_TRANSLATION_KEYS`. Use those stable local variable names in the components.

- [ ] **Step 6: Verify customer GREEN, catalog parity, and commit**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/api/test_addresses.py tests/test_database_migrations.py -q
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
I18N_AUDIT_PATHS="src/App.tsx,src/components/artisan,src/pages/artisan" npm run test -- src/i18n/__tests__/sourceAudit.scope.test.ts
npm run test -- src/App.test.tsx src/components/artisan src/pages/artisan src/i18n/__tests__/catalog.test.ts
npm run typecheck
cd ..
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/artisan/ArtisanLayout.tsx frontend/src/components/artisan/MapPickerOverlay.tsx frontend/src/components/artisan/TableCodeSheet.tsx frontend/src/components/artisan/TableContextBar.tsx frontend/src/components/artisan/TableCodeSheet.test.tsx frontend/src/components/artisan/TableContextBar.test.tsx frontend/src/pages/artisan/ArtisanCheckoutPage.tsx frontend/src/pages/artisan/ArtisanMenuPage.tsx frontend/src/pages/artisan/ArtisanOrdersPage.tsx frontend/src/pages/artisan/ArtisanOrderStatusPage.tsx frontend/src/pages/artisan/ArtisanProfilePage.tsx frontend/src/pages/artisan/ArtisanCheckoutPage.test.tsx frontend/src/pages/artisan/ArtisanMenuPage.test.tsx frontend/src/pages/artisan/ArtisanOrdersPage.test.tsx frontend/src/pages/artisan/ArtisanOrderStatusPage.test.tsx frontend/src/pages/artisan/ArtisanProfilePage.test.tsx frontend/src/test/renderWithLocale.tsx frontend/src/i18n/__tests__/support/sourceAuditConfig.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json frontend/src/types/api.ts backend/app/schemas/address.py backend/app/models/models.py backend/app/routers/addresses.py database/init.sql database/migrations/2026-07-19-address-label-default.sql backend/tests/api/test_addresses.py backend/tests/test_database_migrations.py
git commit -m "feat: localize every customer interface surface"
```

**Release dependency:** `database/migrations/*.sql` is not auto-applied by this repository. Before starting the new backend against any existing database, the release operator must apply and inspect this migration explicitly:

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < database/migrations/2026-07-19-address-label-default.sql
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT column_name, is_nullable, column_default FROM information_schema.columns WHERE table_name = '\''addresses'\'' AND column_name IN ('\''label'\'', '\''label_is_system_default'\'') ORDER BY column_name;"'
```

Expected: both commands exit zero, `label_is_system_default` is non-null with default `false`, and `label` has the empty-string default. If deployment is not part of the implementation session, record this as a release blocker rather than claiming the running database is ready.

---

### Task 7: Migrate every staff-controlled word and accessible label

**Files:**
- Modify: `frontend/src/components/staff/{ConfirmDeliveredSheet,StaffLayout,StaffOrderCard,StaffOrderTabs,StaffPaymentBlock}.tsx`
- Modify: `frontend/src/components/staff/StaffLayout.test.tsx`
- Create: `frontend/src/components/staff/{ConfirmDeliveredSheet,StaffOrderCard,StaffOrderTabs,StaffPaymentBlock}.test.tsx`
- Modify: `frontend/src/pages/staff/{StaffOrderDetailPage,StaffOrdersPage,StaffProfilePage}.tsx`
- Modify: `frontend/src/pages/staff/{StaffOrderDetailPage,StaffOrdersPage,StaffProfilePage}.test.tsx`
- Modify: `frontend/src/utils/format.ts`
- Modify: `frontend/src/utils/__tests__/format.test.ts`
- Modify: `frontend/src/i18n/__tests__/support/sourceAuditConfig.ts`
- Modify: `frontend/src/i18n/locales/{uz,ru,en,zh}.json`

**Mandatory `staff.*` families:**

- `nav`: `orders`, `profile`, `admin`, `staff_navigation`, `admin_navigation`.
- `tabs`: `available`, `active`, `completed`, `orders_aria`.
- `orders`: `loading`, `load_error`, `refresh`, `available_empty`, `active_label`, `active_empty`, `completed_empty`, `view_available`, `delivered_error`, `customer`, `call_customer`, `open_map`, `order_items`, `mark_delivered`.
- `order`: `order_number`, `item_fallback`, `cash_on_delivery`, `paid_online`, `active_delivery`, `take_order`, `taking`, `delivered`, `delivery_time`, `ready_for_pickup`, `delivery_order`, `back`, `back_aria`.
- `payment`: `title`, `collect_amount`, `paid_online`, `cash_on_delivery`, `card_completed`, `online_payment`.
- `delivery_confirm`: `title`, `description`, `cash_collected`, `submitting`, `confirm`, `cancel`.
- `profile`: `title`, `loading`, `load_error`, `retry`, `telegram_staff`.
- `duration`: `minutes`, `hours`, `hours_minutes` with interpolation tokens matching in all locales.

- [ ] **Step 1: Parameterize staff and duration tests across all four real resources**

Cover staff shell/nav, three tabs, order card, payment block, confirmation sheet, active/available/completed states, detail view, and profile. Assert accessible names as well as visible copy.

Add `durationMessage(totalMinutes: number): LocalizedMessage` to `format.ts`. Unit-test the three exact numeric shapes: under one hour returns `duration.minutes` with `{minutes}`, an exact hour returns `duration.hours` with `{hours}`, and a mixed value returns `duration.hours_minutes` with both values. Components translate the returned message at render time; the helper never returns an English fragment.

- [ ] **Step 2: Run staff tests and verify RED**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
I18N_AUDIT_PATHS="src/components/staff,src/pages/staff" npm run test -- src/i18n/__tests__/sourceAudit.scope.test.ts
npm run test -- src/components/staff src/pages/staff src/utils/__tests__/format.test.ts
```

Expected: the scoped audit fails on current staff literals/defaults and the focused renders fail on missing localized states.

- [ ] **Step 3: Add the exact key families and migrate components**

Replace uppercase/raw role labels with `t(roleKey(user.role))`. Replace hand-built `min`, `h`, and `m` fragments with one complete localized duration selected by the numeric shape. Translate cash-collection sentences with amount interpolation; do not concatenate translated fragments around the amount.

Extend `sourceAuditConfig.ts` with these exact stable-expression contracts: `src/pages/staff/StaffProfilePage.tsx` `roleTranslationKey` uses `ROLE_TRANSLATION_KEYS`; `src/components/staff/StaffPaymentBlock.tsx` `paymentStatusTranslationKey` uses `PAYMENT_STATUS_TRANSLATION_KEYS`; `src/components/staff/StaffOrderCard.tsx` assigns `durationMessage(...)` to `durationLabel` and contracts `durationLabel.key` to `duration.minutes`, `duration.hours`, and `duration.hours_minutes`; `src/pages/staff/StaffOrdersPage.tsx` `staffError.key` and `src/components/staff/ConfirmDeliveredSheet.tsx` `deliveryError.key` use `API_ERROR_TRANSLATION_KEYS` plus their literal `staff.orders.load_error`/`staff.orders.delivered_error` fallbacks. Rename the confirmation prop to `deliveryError` so the declared expression is exact. The scoped audit must fail any differently named or uncontracted dynamic expression.

- [ ] **Step 4: Remove verbatim conflict/error rendering**

Use `resolveApiError` for take/deliver/load failures. No staff component may inspect English server prose to decide behavior.

- [ ] **Step 5: Verify staff GREEN and commit**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
I18N_AUDIT_PATHS="src/components/staff,src/pages/staff" npm run test -- src/i18n/__tests__/sourceAudit.scope.test.ts
npm run test -- src/components/staff src/pages/staff src/utils/__tests__/format.test.ts src/i18n/__tests__/catalog.test.ts src/i18n/__tests__/errors.test.ts src/i18n/__tests__/status.test.ts
npm run typecheck
cd ..
git add frontend/src/components/staff/ConfirmDeliveredSheet.tsx frontend/src/components/staff/StaffLayout.tsx frontend/src/components/staff/StaffOrderCard.tsx frontend/src/components/staff/StaffOrderTabs.tsx frontend/src/components/staff/StaffPaymentBlock.tsx frontend/src/components/staff/ConfirmDeliveredSheet.test.tsx frontend/src/components/staff/StaffLayout.test.tsx frontend/src/components/staff/StaffOrderCard.test.tsx frontend/src/components/staff/StaffOrderTabs.test.tsx frontend/src/components/staff/StaffPaymentBlock.test.tsx frontend/src/pages/staff/StaffOrderDetailPage.tsx frontend/src/pages/staff/StaffOrdersPage.tsx frontend/src/pages/staff/StaffProfilePage.tsx frontend/src/pages/staff/StaffOrderDetailPage.test.tsx frontend/src/pages/staff/StaffOrdersPage.test.tsx frontend/src/pages/staff/StaffProfilePage.test.tsx frontend/src/utils/format.ts frontend/src/utils/__tests__/format.test.ts frontend/src/i18n/__tests__/support/sourceAuditConfig.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json
git commit -m "feat: localize every staff interface surface"
```

---

### Task 8: Migrate every admin-controlled word and accessible label

**Files:**
- Modify: `frontend/src/pages/admin/AdminUsersPage.tsx`
- Modify: `frontend/src/pages/admin/AdminUsersPage.test.tsx`
- Modify: `frontend/src/services/adminApi.ts`
- Modify: `frontend/src/services/adminApi.test.ts`
- Modify: `frontend/src/i18n/__tests__/support/sourceAuditConfig.ts`
- Modify: `frontend/src/i18n/locales/{uz,ru,en,zh}.json`

**Mandatory `admin.users.*` keys:** `title`, `staff_roles`, `search_label`, `search_placeholder`, `searching`, `search`, `role_for`, `save_role`, `saving_role`, `role_saved`, `no_users`, `no_phone`, `load_error`, `save_error`, `final_admin_error`.

- [ ] **Step 1: Write failing four-locale admin render and error tests**

Use real resources and assert the heading, search label/placeholder/button/state, role dialog accessible name, translated role options, save success/error, empty state, and no-phone fallback in every locale. Assert a raw backend `detail` string is never rendered.

- [ ] **Step 2: Run tests and verify RED**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
I18N_AUDIT_PATHS="src/pages/admin,src/services/adminApi.ts" npm run test -- src/i18n/__tests__/sourceAudit.scope.test.ts
npm run test -- src/pages/admin/AdminUsersPage.test.tsx src/services/adminApi.test.ts
```

Expected: the scoped audit fails on current admin literals/defaults and the focused tests fail on untranslated or raw-detail states.

- [ ] **Step 3: Add reviewed catalog values and migrate the page**

Use `roleKey` for all role names and `resolveApiError` for every failure. Preserve user names, usernames, and phone values verbatim as content.

Assign dynamic results to stable names and extend `sourceAuditConfig.ts`: `src/pages/admin/AdminUsersPage.tsx` `roleTranslationKey` uses `ROLE_TRANSLATION_KEYS`, and the same file's `adminError.key` uses `API_ERROR_TRANSLATION_KEYS` plus `admin.users.load_error`, `admin.users.save_error`, and `admin.users.final_admin_error`.

- [ ] **Step 4: Verify GREEN and commit**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
I18N_AUDIT_PATHS="src/pages/admin,src/services/adminApi.ts" npm run test -- src/i18n/__tests__/sourceAudit.scope.test.ts
npm run test -- src/pages/admin/AdminUsersPage.test.tsx src/services/adminApi.test.ts src/i18n/__tests__/catalog.test.ts
npm run typecheck
cd ..
git add frontend/src/pages/admin/AdminUsersPage.tsx frontend/src/pages/admin/AdminUsersPage.test.tsx frontend/src/services/adminApi.ts frontend/src/services/adminApi.test.ts frontend/src/i18n/__tests__/support/sourceAuditConfig.ts frontend/src/i18n/locales/uz.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json frontend/src/i18n/locales/zh.json
git commit -m "feat: localize every admin interface surface"
```

---

### Task 9: Localize AliPOS content by stable ID without changing ordering data

> **Required additional skill:** Use the repository `alipos-integration` skill and its verified menu plus halls/tables read-only operations. Saved snapshots are hints, not release evidence.

**Files:**
- Create: `backend/app/localization/content.py`
- Create: `backend/app/localization/alipos_content.json`
- Create: `backend/scripts/audit_alipos_localization.py`
- Create: `backend/tests/localization/test_content.py`
- Create: `backend/tests/localization/test_content_audit.py`
- Modify: `backend/app/services/menu_catalog_service.py`
- Modify: `backend/app/services/table_access_service.py`
- Modify: `backend/app/schemas/order.py`
- Modify: `backend/app/routers/{menu,orders,staff,tables}.py`
- Modify: `backend/tests/{test_menu_catalog_service,test_order_service,test_table_access_service}.py`
- Modify: `backend/tests/api/{test_menu,test_orders_create,test_orders_status,test_staff_delivery,test_tables}.py`
- Modify: `frontend/src/stores/{menuStore,cartStore}.ts`
- Modify: `frontend/src/stores/__tests__/{menuStore,cartStore}.test.ts`
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/types/staff.ts`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.tsx`
- Modify: `frontend/src/pages/artisan/ArtisanMenuPage.test.tsx`
- Modify: `frontend/src/pages/artisan/{ArtisanOrdersPage,ArtisanOrderStatusPage}.tsx`
- Modify: `frontend/src/pages/artisan/{ArtisanOrdersPage,ArtisanOrderStatusPage}.test.tsx`
- Modify: `frontend/src/components/staff/StaffOrderCard.tsx`
- Modify: `frontend/src/components/staff/StaffOrderCard.test.tsx`
- Modify: `frontend/src/pages/staff/{StaffOrdersPage,StaffOrderDetailPage}.tsx`
- Modify: `frontend/src/pages/staff/{StaffOrdersPage,StaffOrderDetailPage}.test.tsx`

**Catalog schema:**

```json
{
  "categories": {
    "3bcb298b-19f3-45ad-8d36-711b06d66de3": {
      "sourceName": "Baliqlar",
      "uz": "Baliqlar",
      "ru": "Рыба",
      "en": "Fish",
      "zh": "鱼类"
    }
  },
  "items": {
    "10efc08b-f752-400e-b836-8e3599b71520": {
      "sourceName": "Qovirilgan baliq",
      "sourceDescription": "",
      "name": {
        "uz": "Qovurilgan baliq",
        "ru": "Жареная рыба",
        "en": "Fried fish",
        "zh": "炸鱼"
      },
      "description": {"uz": "", "ru": "", "en": "", "zh": ""}
    }
  },
  "modifiers": {
    "33333333-3333-4333-8333-333333333333": {
      "sourceName": "Qo'shimcha piyoz",
      "name": {
        "uz": "Qo'shimcha piyoz",
        "ru": "Дополнительный лук",
        "en": "Extra onion",
        "zh": "加洋葱"
      }
    }
  },
  "halls": {
    "11111111-1111-4111-8111-111111111111": {
      "sourceTitle": "Asosiy zal",
      "uz": "Asosiy zal",
      "ru": "Главный зал",
      "en": "Main hall",
      "zh": "主厅"
    }
  },
  "tables": {
    "22222222-2222-4222-8222-222222222222": {
      "sourceTitle": "1-stol",
      "uz": "1-stol",
      "ru": "Стол 1",
      "en": "Table 1",
      "zh": "1号桌"
    }
  }
}
```

The category/item IDs above are known saved-snapshot examples. The modifier/hall/table UUIDs are explicitly synthetic test examples and must not be copied into the production catalog. `sourceName`, `sourceDescription`, and `sourceTitle` are audit-only fingerprints of the current AliPOS value; browser overlays never read or return them.

**Interfaces:**

- `localize_menu(menu: dict[str, object], locale: AppLocale) -> dict[str, object]` returns a deep-copied browser payload.
- `localize_order_items(items: list[dict], locale: AppLocale) -> list[dict]` uses item/modifier IDs, never saved names.
- `localize_hall_title(hall_id: object, locale: AppLocale) -> str | None` and `localize_table_title(table_id: object, locale: AppLocale) -> str | None` return no source-language fallback for non-Uzbek locales.
- `audit_catalog(menu: dict, directory: dict) -> list[CatalogIssue]` returns deterministic entity-kind/ID/field/locale issues without provider payload text.
- `IdenticalContentAllowance(kind, entity_id, field, value, locales, reason)` permits only one exact stable-ID field containing a verified brand/acronym unchanged across named locales; no kind-wide allowance exists.

Frontend response types use this concrete historical-display shape:

```ts
export interface LocalizedOrderModifier {
  id: string;
  name: string | null;
  quantity: number;
  price: number;
}

export interface OrderModifierInput {
  id: string;
  name?: string | null;
  quantity: number;
  price: number;
}

export interface OrderItem {
  id: string;
  name: string | null;
  quantity: number;
  price: number;
  modifications: LocalizedOrderModifier[];
}
```

`StaffOrderItem.name` is also `string | null`, and `StaffOrderItem.modifications` is `LocalizedOrderModifier[]`; retain its existing optional ID/price only where the backend response genuinely permits them. `CreateOrderPayload.items[].modifications` is `OrderModifierInput[]`, eliminating the remaining `unknown[]`. The Task 3 cart modifier shape is structurally compatible but remains a cart type, not an unsafe alias.

- [ ] **Step 1: Add compile-only content/audit stubs, then write failing pure overlay tests with fixed IDs**

Create valid modules and `{ "categories": {}, "items": {}, "modifiers": {}, "halls": {}, "tables": {} }`. The overlay stubs return deep copies without translation, lookup stubs return `None`, the audit stub returns an empty list, and the CLI accepts `--help`; assertions below provide RED without an import/JSON failure.

Use synthetic UUIDs and assert all four locales change only `name`, `description`, hall title, and table title. Assert IDs, prices, sort order, images, availability, quantities, and modifier IDs remain byte-for-byte equal. Assert the original input is not mutated.

- [ ] **Step 2: Write failing drift and completeness tests**

Require every current category/item/modifier/hall/table ID and every required field to have four keys. Compare every live AliPOS name/description/title with its audit-only source fingerprint and report a deterministic source-drift issue even when the stable ID is unchanged; translation review must update the fingerprint and all affected locale values together. Apply the same locale-purity rules as the interface catalogs: reject identical non-empty values across locales unless an exact `IdenticalContentAllowance` names that stable ID/field/value with a reason; require Cyrillic in reviewed Russian prose and Han characters in reviewed Chinese prose after removing allowed brands/placeholders. An intentionally empty description in all four locales is valid. For non-Uzbek menu responses, an unknown ID is omitted and a warning records only its provider ID. In historical order items, retain the line/ID/quantity/price and typed modifier IDs/quantity/prices but set each missing item or modifier display name to `None` so the frontend uses `common.item`/`common.modifier`. Add customer/staff render tests proving null item/modifier names become the active locale's generic labels and neither `undefined`, `null`, nor a source name is rendered. For a requested non-Uzbek table context with missing content, return HTTP 503 with `content_unavailable` rather than source-language text.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/localization/test_content.py tests/localization/test_content_audit.py tests/test_menu_catalog_service.py tests/test_order_service.py tests/test_table_access_service.py tests/api/test_menu.py tests/api/test_orders_create.py tests/api/test_orders_status.py tests/api/test_staff_delivery.py tests/api/test_tables.py -q
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/pages/artisan/ArtisanOrdersPage.test.tsx src/pages/artisan/ArtisanOrderStatusPage.test.tsx src/components/staff/StaffOrderCard.test.tsx src/pages/staff/StaffOrdersPage.test.tsx src/pages/staff/StaffOrderDetailPage.test.tsx
npm run typecheck
```

- [ ] **Step 4: Implement the immutable response-boundary overlay**

`price_cart()` and outgoing AliPOS payload construction must continue reading the unlocalized provider menu. Apply `localize_menu()` only after availability is calculated for `/api/menu`. Build localized order/staff responses from copies of stored snapshots by their item/modifier IDs. Localize table/hall context using `Order.table_id` and `Order.hall_id`; never match by mutable source title.

Add `table_id` and `hall_id` to the internal `TableResolution` dataclass so `/tables/resolve` can localize by stable ID, but continue omitting both IDs from the customer-safe `TableContextResponse`. Assert the access token, manual code, service percentage, and public response shape are otherwise unchanged across locales.

Replace `ArtisanMenuPage` category-artwork selection by localized-name substring with a stable category-ID-to-artwork map. The same provider category ID must select the same artwork in Uzbek, Russian, English, and Chinese; display names must never control behavior.

Public menu and table-resolution routes accept `PublicLocaleDep`; authenticated order, table-restore, admin table-manifest, and staff routes accept `UserLocaleDep`. The manifest localizes only hall/table display titles and leaves QR/manual codes, IDs, and deep links unchanged. The explicit validated `Accept-Language` value controls response presentation, while an authenticated request without that header uses the valid saved preference.

- [ ] **Step 5: Capture one deterministic live report before authoring copy**

Give the CLI these exact read-only modes: `--live --snapshot-only --report-json PATH`, `--live --only category:UUID`, `--live --only directory`, and final unfiltered `--live`. Snapshot-only always writes the normalized deterministic provider snapshot and exits zero even when the repository catalog is empty/incomplete; it never declares completeness. Every filtered or unfiltered non-snapshot mode exits nonzero for any catalog, drift, or purity issue. Capture the current menu composition plus halls/tables once into `/tmp/alipos-localization-report.json`; subsequent filtered authoring checks read the live endpoint again and compare its `lastChange`/ID sets to that captured report. If either changes mid-task, discard the report and restart Step 5 so translations are never authored against a mixed snapshot.

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
docker compose build backend
docker compose run --rm --no-deps -v /tmp:/host-tmp backend python scripts/audit_alipos_localization.py --live --snapshot-only --report-json /host-tmp/alipos-localization-report.json
```

This is the one deliberate credentialed command family: Compose injects the configured AliPOS secrets into the one-off container without printing or sourcing them into the host shell. It performs only the read operations required by the `alipos-integration` skill. Never log headers, tokens, or raw provider payloads.

- [ ] **Step 6: Author and verify category/item/modifier content in bounded batches**

First populate the five known saved-snapshot category branches, but retain a branch only if its ID is present in the captured live report:

1. fish `3bcb298b-19f3-45ad-8d36-711b06d66de3`;
2. tea `33cf66d7-863d-4988-95d8-5c642340a345`;
3. meals `c0da9c7c-9acd-4133-9a82-ac987d1ae57b`;
4. samsa `72c2eaba-2e42-4fa7-8df6-ae581632e8a8`;
5. drinks `b87fb00e-09d9-4b7f-963f-e903dd3d4dc6`.

For each live category, author its category label, every member item name/description, and every reachable modifier before moving to the next. After each branch, rebuild the working-tree backend image and run `docker compose run --rm --no-deps backend python scripts/audit_alipos_localization.py --live --only category:<that-id>`; require zero issues. If the report has another current category ID, append it as its own sixth-or-later batch; never fold an unknown branch into a generic fallback.

Populate reviewed Uzbek, Russian, English, and Simplified Chinese values. Preserve proper brands such as Coca-Cola, Fanta, Cappy, Borjomi, Telegram, AliPOS, Multicard, and OLOT SOMSA. Keep all four descriptions empty when the provider description is intentionally empty; do not invent marketing copy.

- [ ] **Step 7: Author and verify halls/tables as a separate batch**

Populate every captured hall and table ID, rebuild the working-tree backend image, then run `docker compose run --rm --no-deps backend python scripts/audit_alipos_localization.py --live --only directory` and require zero issues. Table numbers/IDs remain source identity; only their display titles are localized.

The known saved snapshot currently hints at 5 categories and 56 items, but implementation must not treat those counts as current truth. The catalog cannot be accepted until the live report returns zero issues.

- [ ] **Step 8: Verify localized responses and untouched provider payloads**

Add spies around AliPOS order submission and assert the exact source names and stable IDs sent before this task are still sent after it. Assert the four browser menu responses have equal IDs/prices/availability and locale-specific display values.

- [ ] **Step 9: Verify GREEN, live completeness, and commit**

```bash
cd backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/localization/test_content.py tests/localization/test_content_audit.py tests/test_menu_catalog_service.py tests/test_order_service.py tests/test_table_access_service.py tests/api/test_menu.py tests/api/test_orders_create.py tests/api/test_orders_status.py tests/api/test_staff_delivery.py tests/api/test_tables.py -q
cd ..
docker compose build backend
docker compose run --rm --no-deps backend python scripts/audit_alipos_localization.py --live
cd backend
.venv/bin/ruff check app/localization/content.py scripts/audit_alipos_localization.py tests/localization
cd ../frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/stores/__tests__/menuStore.test.ts src/stores/__tests__/cartStore.test.ts src/pages/artisan/ArtisanMenuPage.test.tsx src/pages/artisan/ArtisanOrdersPage.test.tsx src/pages/artisan/ArtisanOrderStatusPage.test.tsx src/components/staff/StaffOrderCard.test.tsx src/pages/staff/StaffOrdersPage.test.tsx src/pages/staff/StaffOrderDetailPage.test.tsx
npm run typecheck
cd ..
git add backend/app/localization/content.py backend/app/localization/alipos_content.json backend/scripts/audit_alipos_localization.py backend/tests/localization/test_content.py backend/tests/localization/test_content_audit.py backend/app/services/menu_catalog_service.py backend/app/services/table_access_service.py backend/app/schemas/order.py backend/app/routers/menu.py backend/app/routers/orders.py backend/app/routers/staff.py backend/app/routers/tables.py backend/tests/test_menu_catalog_service.py backend/tests/test_order_service.py backend/tests/test_table_access_service.py backend/tests/api/test_menu.py backend/tests/api/test_orders_create.py backend/tests/api/test_orders_status.py backend/tests/api/test_staff_delivery.py backend/tests/api/test_tables.py frontend/src/types/api.ts frontend/src/types/staff.ts frontend/src/stores/menuStore.ts frontend/src/stores/cartStore.ts frontend/src/stores/__tests__/menuStore.test.ts frontend/src/stores/__tests__/cartStore.test.ts frontend/src/pages/artisan/ArtisanMenuPage.tsx frontend/src/pages/artisan/ArtisanMenuPage.test.tsx frontend/src/pages/artisan/ArtisanOrdersPage.tsx frontend/src/pages/artisan/ArtisanOrdersPage.test.tsx frontend/src/pages/artisan/ArtisanOrderStatusPage.tsx frontend/src/pages/artisan/ArtisanOrderStatusPage.test.tsx frontend/src/components/staff/StaffOrderCard.tsx frontend/src/components/staff/StaffOrderCard.test.tsx frontend/src/pages/staff/StaffOrdersPage.tsx frontend/src/pages/staff/StaffOrdersPage.test.tsx frontend/src/pages/staff/StaffOrderDetailPage.tsx frontend/src/pages/staff/StaffOrderDetailPage.test.tsx
git commit -m "feat: localize AliPOS content by stable id"
```

---

### Task 10: Localize formatting, Yandex mappings, document metadata, and Telegram buttons

**Files:**
- Modify: `frontend/src/utils/format.ts`
- Modify: `frontend/src/utils/__tests__/format.test.ts`
- Modify: `frontend/src/utils/loadYmaps3.ts`
- Create: `frontend/src/utils/loadYmaps3.test.ts`
- Modify: `frontend/src/components/artisan/MapPickerOverlay.tsx`
- Modify: `frontend/src/components/artisan/ArtisanLayout.tsx`
- Modify: `frontend/src/components/artisan/ArtisanLayout.test.tsx`
- Create: `backend/app/services/telegram_menu_service.py`
- Create: `backend/tests/test_telegram_menu_service.py`
- Modify: `backend/app/services/yandex_geocoder.py`
- Create: `backend/tests/test_yandex_geocoder.py`
- Modify: `backend/app/routers/{auth,users,geocoding}.py`
- Modify: `backend/tests/api/{test_auth,test_users}.py`
- Modify: `backend/tests/api/test_geocoding.py`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/services/api.test.ts`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/artisan.css`
- Modify: `start.sh`

**Required provider mapping:**

| App locale | `Intl` | Yandex Maps | Yandex Geocoder/Suggest |
|---|---|---|---|
| `uz` | `uz-UZ` | `ru_RU` | `ru` |
| `ru` | `ru-RU` | `ru_RU` | `ru` |
| `en` | `en-US` | `en_US` | `en` |
| `zh` | `zh-CN` | `en_US` | `en` |

**Yandex loader lifecycle:**

```ts
export type YandexMapsLocale = 'ru_RU' | 'en_US';

export interface YMaps3Lease {
  api: YMaps3Api;
  providerLocale: YandexMapsLocale;
  release(): void;
}

export function acquireYmaps3(locale: AppLocale): Promise<YMaps3Lease>;
export function resetYmaps3LoaderForTests(): void;
```

`MapPickerOverlay` owns one lease for one mounted `YMap`. Its effect cleanup calls `map.destroy()` first and the idempotent `lease.release()` second. The loader tracks the active provider locale, in-flight generation, and lease count. A request for the other provider group waits while an old lease exists; when the count reaches zero, it removes the old script and `window.ymaps3`, invalidates stale callbacks, and appends exactly one script for the requested locale. Uzbek/Russian leases may share `ru_RU`; English/Chinese leases may share `en_US`. `resetYmaps3LoaderForTests()` force-increments the generation, rejects/clears queued acquires, zeros counters/cache, removes the script, and deletes `window.ymaps3`; production code never calls it.

**Telegram service:**

```python
MENU_BUTTON_TEXT: dict[AppLocale, str] = {
    "uz": "Menyuni ochish",
    "ru": "Открыть меню",
    "en": "Open Menu",
    "zh": "打开菜单",
}

async def set_localized_chat_menu_button(
    chat_id: int,
    locale: AppLocale,
    client: httpx.AsyncClient | None = None,
) -> bool:
    public_url = settings.public_app_url.strip().rstrip("/")
    if chat_id <= 0 or not settings.telegram_bot_token or not public_url:
        logger.warning("Telegram menu button update skipped: invalid configuration")
        return False
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        response = await active_client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/setChatMenuButton",
            json={
                "chat_id": chat_id,
                "menu_button": {
                    "type": "web_app",
                    "text": MENU_BUTTON_TEXT[locale],
                    "web_app": {"url": f"{public_url}/"},
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            logger.warning("Telegram menu button update was rejected")
            return False
        return True
    except (httpx.HTTPError, ValueError):
        logger.warning("Telegram menu button update failed")
        return False
    finally:
        if owns_client:
            await active_client.aclose()
```

The service builds the web-app URL only from `settings.public_app_url.rstrip('/') + '/'`; if the token or public app URL is absent, it returns `False` after a secret-safe warning. It sends the positive validated Telegram user ID as `chat_id` and never logs the bot-token URL or response body. A caller-owned `httpx.AsyncClient` is not closed; an internally created client is.

- [ ] **Step 1: Add the compile-only provider-service stub, then write failing four-locale formatter tests**

Create `telegram_menu_service.py` with the exact constants/signature above and a temporary `return False` body. Keep the existing Yandex loader callable until the lifecycle tests are written; add compile exports for the lease/reset API without changing behavior so RED comes from assertions.

Cover price, date, date-time, and duration for every canonical locale plus representative regional input. Assert `zh` uses `zh-CN` numerals/date order and `common.currency == 苏姆`. Avoid brittle whitespace assertions by comparing normalized output or `Intl.formatToParts()`. Before implementation, add the failing `ArtisanLayout.test.tsx` contract that requires both exported inline font stacks, rendered layout styles, `index.css`, and `artisan.css` to contain the ordered CJK-capable fallback sequence from Step 7.

- [ ] **Step 2: Write failing Yandex mapping, lifecycle, and raw-error suppression tests**

Assert the exact mapping table above on both client and server. Assert `zh-CN` never maps to Russian. Exercise the lease API with fake scripts/APIs: same-group callers share one script; releasing one of two leases does not unload it; a cross-group acquire stays pending while the old map lease is active; after `destroy()` and final `release()`, the old script/global disappear before the new script is appended; a stale old-script callback cannot win; release is idempotent; and the test reset returns module/DOM/global state to empty. Add an unmount-before-resolution case: `MapPickerOverlay` unmounts while `acquireYmaps3()` is pending, the promise later resolves, the lease is immediately released, and no `YMap` is constructed or used. Assert backend geocoding failures return `geocoding_unavailable` and omit provider text.

- [ ] **Step 3: Write failing Telegram button tests**

Per-chat labels are exactly:

| Locale | Button text |
|---|---|
| `uz` | `Menyuni ochish` |
| `ru` | `Открыть меню` |
| `en` | `Open Menu` |
| `zh` | `打开菜单` |

Assert `setChatMenuButton` receives the authenticated user's positive private-dialog ID, the exact `MENU_BUTTON_TEXT` value, and `settings.public_app_url` normalized to one trailing slash. Telegram documents `chat_id` here as the target private chat and documents Bot API user dialog IDs as the unchanged user ID; never use a group/channel ID from untrusted client state. See `https://core.telegram.org/bots/api#setchatmenubutton` and `https://core.telegram.org/api/bots/ids#user-ids`. Patch the service in auth/user API tests and assert authentication queues `(validated_user_id, resolved_locale)` after commit, while a successful language update queues `(current_user.telegram_id, body.language)`. Assert missing config, HTTP failure, malformed JSON, and Telegram `ok: false` are logged without token/customer detail and do not fail authentication or preference persistence.

- [ ] **Step 4: Run focused tests and verify RED**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/utils/__tests__/format.test.ts src/utils/loadYmaps3.test.ts src/components/artisan/ArtisanLayout.test.tsx
cd ../backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/test_yandex_geocoder.py tests/test_telegram_menu_service.py tests/api/test_auth.py tests/api/test_users.py tests/api/test_geocoding.py -q
```

- [ ] **Step 5: Implement formatting and the ref-counted Yandex lease**

All formatter entry points normalize through the locale registry and use its `intl` value. Replace the old unkeyed `loadYmaps3()` singleton with the exact `acquireYmaps3()` lease contract above. `MapPickerOverlay` captures the normalized active locale in its map effect dependencies, destroys/releases the old map before acquiring another provider group, and never renders loader/provider exception text. The effect owns a `cancelled` flag: if cleanup runs before acquisition resolves, the promise continuation immediately calls the resolved lease's idempotent `release()` and returns without constructing a map; otherwise cleanup destroys the map first and releases its lease second.

- [ ] **Step 6: Implement server-side Yandex locale ownership**

Change frontend calls to `reverseGeocode(lat, lng)` and `suggestAddress(text, lat, lng)`; neither may send a `lang` query. The geocoding routers accept `locale: UserLocaleDep`, and `yandex_geocoder.reverse_geocode(..., locale: AppLocale)` / `suggest(..., locale: AppLocale)` map only through `{"uz":"ru", "ru":"ru", "en":"en", "zh":"en"}`. Delete the old arbitrary-string normalizers/allowlists so a client cannot select another provider locale. Preserve Yandex-returned place/address text unchanged as the documented provider-content exception.

- [ ] **Step 7: Implement Telegram and CJK presentation**

Add `BackgroundTasks` to `telegram_auth()` and `update_me()`. Queue `set_localized_chat_menu_button` only after the database commit succeeds: after every successful authentication with the resolved saved/new-user locale, and after a successful request that actually supplied `body.language`. The background task's boolean result never changes the API response. In `start.sh`, change only the deployment-wide default text from `Open Menu` to `OLOT SOMSA`.

Add a local system stack including `-apple-system`, `BlinkMacSystemFont`, `"PingFang SC"`, `"Microsoft YaHei"`, `"Noto Sans CJK SC"`, and `sans-serif`; do not add a font download. Update both exported inline stacks in `ArtisanLayout.tsx`: keep `"Plus Jakarta Sans"` first for `headline` and `"Manrope"` first for `body`, then append the same CJK-capable system fallbacks. Apply the same fallback sequence in `index.css` and `artisan.css`. `ArtisanLayout.test.tsx` statically asserts both exported stacks contain every fallback in order and that rendered inline styles use those exports, preventing the global CSS from being bypassed.

- [ ] **Step 8: Verify GREEN and commit**

```bash
cd frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/utils/__tests__/format.test.ts src/utils/loadYmaps3.test.ts src/components/artisan/ArtisanLayout.test.tsx
npm run typecheck
cd ../backend
scripts/with_test_env.sh .venv/bin/python -m pytest tests/test_yandex_geocoder.py tests/test_telegram_menu_service.py tests/api/test_auth.py tests/api/test_users.py tests/api/test_geocoding.py -q
.venv/bin/ruff check app/services/telegram_menu_service.py app/services/yandex_geocoder.py app/routers/auth.py app/routers/users.py app/routers/geocoding.py tests/test_telegram_menu_service.py tests/test_yandex_geocoder.py tests/api/test_geocoding.py
cd ..
git add frontend/src/utils/format.ts frontend/src/utils/__tests__/format.test.ts frontend/src/utils/loadYmaps3.ts frontend/src/utils/loadYmaps3.test.ts frontend/src/components/artisan/MapPickerOverlay.tsx frontend/src/components/artisan/ArtisanLayout.tsx frontend/src/components/artisan/ArtisanLayout.test.tsx frontend/src/services/api.ts frontend/src/services/api.test.ts frontend/src/index.css frontend/src/artisan.css backend/app/services/telegram_menu_service.py backend/tests/test_telegram_menu_service.py backend/app/services/yandex_geocoder.py backend/tests/test_yandex_geocoder.py backend/app/routers/auth.py backend/app/routers/users.py backend/app/routers/geocoding.py backend/tests/api/test_auth.py backend/tests/api/test_users.py backend/tests/api/test_geocoding.py start.sh
git commit -m "feat: localize providers formatting and telegram"
```

---

### Task 11: Enforce catalog usage and reject hardcoded shipped copy

**Files:**
- Create: `frontend/src/i18n/__tests__/support/repositoryAudit.ts`
- Create: `frontend/src/i18n/__tests__/support/routeSmokeMatrix.tsx`
- Create: `frontend/src/i18n/__tests__/sourceAudit.integration.test.ts`
- Create: `frontend/src/i18n/__tests__/routeSmoke.test.tsx`
- Modify: `frontend/src/i18n/__tests__/catalog.test.ts`
- Modify: `frontend/package.json`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add compile-only repository/matrix stubs, then write failing integration tests**

`repositoryAudit.ts` temporarily exports `loadShippedSources()` as `[]` and `createRepositoryAuditOptions()` with empty sources. `routeSmokeMatrix.tsx` temporarily exports an empty `ROUTE_SMOKE_CASES` tuple. These are compile stubs only.

Write `sourceAudit.integration.test.ts` to assert the inventory contains known shipped files from customer, staff, and admin trees before asserting `auditLocalizationSources(...)` returns no findings. Write `routeSmoke.test.tsx` to require every exact case in the matrix below and run every case for all four `SUPPORTED_LOCALES`. The inventory and case-count assertions create deterministic RED failures while the stubs are empty.

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/sourceAudit.integration.test.ts src/i18n/__tests__/routeSmoke.test.tsx
```

- [ ] **Step 2: Implement the repository loader and always-on audit options**

Recursively load every extension in `SHIPPED_SOURCE_EXTENSIONS` (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`) under `src`, excluding tests, mocks, declarations, styles, test support, and generated files. Import the exact dynamic contracts, per-node literal allowances, UI attributes, component props, and call sinks from the single `sourceAuditConfig.ts` created in Task 5A and extended by Tasks 6–10. Do not duplicate those lists or add a broader allowance to make integration pass. `createRepositoryAuditOptions()` supplies the flattened four-catalog key set.

- [ ] **Step 3: Implement the exact route/state matrix with real resources**

Use singleton-backed `renderWithAppLocale`, `MemoryRouter`, real resources, real stores, the real Axios interceptor, and MSW response fixtures. The isolated helper is forbidden here because it would let rendered copy and request/storage locale diverge. The matrix is finite and named:

| Case ID | Route/surface | Required states |
|---|---|---|
| `bootstrap-retry` | `/` App shell | unauthenticated retry/error |
| `customer-menu` | `/` | loaded, empty, load error, cart notice |
| `customer-table` | `/` table sheet | entry, resolving, structured error, context bar |
| `customer-checkout` | `/checkout` | delivery, table, address/map, submit error |
| `customer-orders` | `/order` | loading, empty, loaded, structured error |
| `customer-order-detail` | `/order/:orderId` | every known plus unknown order/payment state |
| `customer-profile` | `/profile` | logged in/out, addresses, language selector |
| `staff-orders` | `/staff/orders` | available, active, completed, empty, load/take error |
| `staff-order-detail` | `/staff/orders/:orderId` | payment, take, delivery confirmation/error |
| `staff-profile` | `/profile` with staff role | loaded, error, language selector |
| `admin-profile` | `/profile` with admin role | translated admin nav/a11y, language selector |
| `admin-users` | `/admin/users` | search, empty, role edit, success, structured error |

Before every case, run one explicit reset helper: `server.resetHandlers()`, clear request captures, `localStorage.clear()`, `sessionStorage.clear()`, restore the singleton/document to Uzbek, then partially reset (without replacing actions) auth `{token:null,user:null,isAuthenticated:false,isLoading:false,hasHydratedUser:true,hasResolvedInitialAuth:true,authError:null}`, menu `{menu:null,loading:false,loaded:false,loadedLocale:null,error:null}`, cart `{items:[]}`, and table `{context:null,isResolving:false,error:null}`. Apply the case fixture only after that reset and then await `changeAppLocale(locale)`. Execute the named matrix once in declared order and once in reverse order to prove cases do not depend on leaked singleton/store/session state.

For every case and locale, assert `<html lang>` equals the registry value, every request observed by MSW has exact `Accept-Language: <locale>`, exactly one language radio is checked on surfaces containing the selector, no raw catalog key or backend/provider detail is visible, and every interactive element plus meaningful image has a non-empty accessible name. Use sentinel provider errors and unknown enums in fixtures and assert only localized generic copy is visible.

- [ ] **Step 4: Extend catalog tests to call-site invariants**

Keep Task 1's exact registry/key/non-empty/interpolation checks. Add assertions that all static and contracted dynamic call-site keys exist in every catalog and that runtime i18next configuration still has no cross-language fallback.

- [ ] **Step 5: Add scripts and CI gates**

Add:

```json
"audit:i18n": "vitest run src/i18n/__tests__/catalog.test.ts src/i18n/__tests__/sourceAudit.integration.test.ts"
```

In the frontend CI job, run in this order after `npm ci --legacy-peer-deps`: typecheck, lint, i18n audit, tests, production build. Keep backend Ruff/tests unchanged and ensure the new localization tests are discovered by the existing full pytest command.

- [ ] **Step 6: Verify zero findings and commit only the enforcement layer**

If the integration audit finds production copy, stop this task. Return the finding to its owning Task 6, 7, 8, 9, or 10 scope, run that task's scoped RED/GREEN command, and commit the correction with that owning task before restarting Task 11. Do not stage production-source corrections in the enforcement commit, and do not expand the allowlist merely to obtain green.

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run audit:i18n
npm run test -- src/i18n/__tests__/sourceAudit.test.ts src/i18n/__tests__/sourceAudit.integration.test.ts src/i18n/__tests__/catalog.test.ts src/i18n/__tests__/routeSmoke.test.tsx
npm run lint
npm run typecheck
npm run build
cd ..
git add frontend/src/i18n/__tests__/support/repositoryAudit.ts frontend/src/i18n/__tests__/support/routeSmokeMatrix.tsx frontend/src/i18n/__tests__/sourceAudit.integration.test.ts frontend/src/i18n/__tests__/routeSmoke.test.tsx frontend/src/i18n/__tests__/catalog.test.ts frontend/package.json .github/workflows/ci.yml
git commit -m "test: enforce complete localized interface copy"
```

---

### Task 12: Run the full four-language release audit

**Files:**
- No files. This task is verification-only.

- [ ] **Step 1: Run all backend acceptance checks**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/backend
scripts/with_test_env.sh .venv/bin/python -m pytest -q
.venv/bin/ruff check .
cd ..
docker compose build backend
docker compose run --rm --no-deps backend python scripts/audit_alipos_localization.py --live
```

Expected: all tests pass, Ruff passes, and the verified live menu plus hall/table audit reports zero missing IDs/fields/locales.

- [ ] **Step 2: Run all frontend acceptance checks**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app/frontend
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run typecheck
npm run lint
npm run audit:i18n
npm run test
npm run build
```

Expected: every command exits zero; production build contains all four locale resources.

- [ ] **Step 3: Run a route-by-locale smoke matrix**

From `/Users/khajievroma/Projects/restaurant-mini-app/frontend`, run:

```bash
export PATH="/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
npm run test -- src/i18n/__tests__/routeSmoke.test.tsx
```

The test uses the singleton-backed resource helper, reset stores, the real locale header interceptor, and MSW fixtures to exercise these representative surfaces for each of `uz`, `ru`, `en`, and `zh`:

1. unauthenticated bootstrap/retry and customer profile selector;
2. customer menu/cart/table dialog/checkout/map/address;
3. customer order history and every known plus unknown status/payment state;
4. staff available/active/completed/detail/payment/delivery confirmation/profile;
5. admin profile selector/nav plus user search/role edit/success/error/empty state.

For each render, assert `<html lang>` matches the locale definition, no raw translation key is visible, no raw backend/provider detail is visible, and all accessible names are non-empty. On profile/selector cases, additionally assert exactly one language radio is selected and it matches the active canonical locale.

- [ ] **Step 4: Run the release-environment-only visual gate**

This is deliberately not a local unauthenticated-browser command: Telegram Mini App authentication requires signed Telegram `initData`. Before the release session, provision and record three dedicated Telegram test identities in the release log as `I18N_CUSTOMER_TELEGRAM_ID`, `I18N_STAFF_TELEGRAM_ID`, and `I18N_ADMIN_TELEGRAM_ID`; verify their database roles are exactly customer, staff, and admin. Launch `${PUBLIC_APP_URL}/` through the bot's Web App button while signed into each corresponding test account, use the in-app selector to visit `uz`, `ru`, `en`, and `zh`, and walk `/`, `/checkout`, `/order`, `/profile`, `/staff/orders`, and `/admin/users` only where that role has access.

Create an artifact directory with `RESTAURANT_I18N_VISUAL_DIR="$(mktemp -d /tmp/restaurant-i18n-visual-audit-2026-07-19.XXXXXX)"` and record that resolved path in the release log. At a 390x844 viewport, capture one screenshot per named Task 11 matrix case and locale there, named `<role>-<locale>-<case-id>.png`. Check Chinese wrapping/glyph fallback, long Russian labels, Uzbek copy corrections, dialogs, placeholders, toasts, and screen-reader names. Geographic suggestions may remain in Yandex's Russian/English provider language; all application controls around them must match the selected locale. If the three signed test identities or a deployed `PUBLIC_APP_URL` are unavailable, report the visual release gate as blocked; do not substitute direct local URLs or claim production visual readiness. The automated Task 11 route matrix remains the deterministic implementation gate.

- [ ] **Step 5: Review the final diff for scope and accidental leakage**

```bash
cd /Users/khajievroma/Projects/restaurant-mini-app
git status --short
git diff --check
git diff --stat 3211808..HEAD
rg -n "defaultValue" frontend/src --glob '!**/__tests__/**' --glob '!**/*.test.*'
rg -n "response.*detail|data.*detail" frontend/src/components frontend/src/pages frontend/src/stores --glob '!**/*.test.*'
rg -n '"text"[[:space:]]*:[[:space:]]*"Open Menu"' start.sh
```

Expected: no whitespace errors, no production inline fallback copy, no component/page/store raw-detail rendering, and no deployment-wide English Telegram default. The legitimate English per-chat translation remains tested in `telegram_menu_service.py`, outside this deployment-default check.

- [ ] **Step 6: Stop the isolated test database after all checks**

```bash
docker stop restaurant_i18n_test_postgres
```

Expected: only the disposable `restaurant_i18n_test_postgres` container stops and removes itself; the production `restaurant_postgres` service remains untouched.

- [ ] **Step 7: Close only after every acceptance check is green**

If any check finds a defect, do not edit or commit under Task 12. Return to the owning task, reproduce the defect with that task's focused test/audit, make the correction there, and rerun Tasks 11 and 12 in full. Task 12 creates no commit and is complete only when Steps 1–6 pass without correction.

---

## Completion Evidence

The feature is complete only when all of the following evidence exists in the same worktree:

- exact `uz/ru/en/zh` registry and deterministic preference tests;
- four equal, non-empty, interpolation-compatible, locale-purity-checked catalogs;
- no production inline defaults or unapproved user-visible literals;
- shared selector success and rollback tests for customer/staff/admin access;
- backend locale validation and canonical `Accept-Language` tests;
- structured error tests proving raw server/provider text suppression;
- four-locale customer, staff, and admin render tests using real resources;
- formatter, Yandex, Telegram, and document-language tests;
- verified live AliPOS catalog audit with zero missing category/item/modifier/hall/table translations;
- proof that AliPOS outgoing IDs, prices, source identity, and order behavior did not change;
- passing backend pytest/Ruff and frontend typecheck/lint/audit/test/build commands.
