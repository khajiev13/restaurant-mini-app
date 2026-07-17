# Numeric Table Codes and QR Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace customer-facing six-character manual table codes with the physical table number, preserve old signed QR links, and deliver a decoded, verified QR package for every live table.

**Architecture:** The backend derives one canonical numeric code from the trailing digits in each live AliPOS table title and validates the complete directory before resolving anything. New QR links use a versioned `t2_` HMAC format, while the legacy `t_` verifier remains available only for old signed links. The frontend accepts numeric input, and a standalone PEP 723 script turns the deployed admin manifest into PNG, PDF, CSV, JSON, verification, and ZIP artifacts.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, httpx, pytest, React 19, TypeScript 5.7, Zustand 5, React Router 6, Vitest, Testing Library, i18next, Pillow, qrcode, zxing-cpp, uv, Docker Compose, Cloudflare Tunnel.

## Global Constraints

- The manual code is the trailing ASCII digit sequence from the AliPOS table title, normalized by removing leading zeroes; `000` becomes `0`.
- The source digit sequence and submitted manual input must contain one to six digits.
- Numeric codes must be unique across all halls. Missing, malformed, or duplicate codes make the whole customer table directory unavailable with HTTP `503`.
- New QR parameters use `t2_<numeric-code>_<signature>` and the `qr2` HMAC purpose.
- Existing signed `t_<six-character-code>_<signature>` links remain supported with the original `qr` HMAC purpose.
- The table access secret is not rotated, and raw AliPOS table or hall identifiers never appear in customer responses, logs, or QR assets.
- Manual code input is digits-only, uses a numeric keyboard, accepts one to six digits, and submits the canonical code.
- QR artifacts are generated only from the deployed admin manifest after both public OLOT SOMSA health checks return HTTP `200`.
- Every generated PNG must decode byte-for-byte to the corresponding manifest `deep_link` before packaging.
- The separate BitAgent outage is out of scope for this plan.
- No database migration is required.

## File Structure

- Modify `backend/app/services/table_access_service.py`: numeric-code extraction, strict directory validation, versioned QR signing/parsing, legacy compatibility, and canonical resolution.
- Modify `backend/app/routers/tables.py`: map invalid live directory state to HTTP `503` on resolve, restore, and manifest routes.
- Modify `backend/tests/test_table_access_service.py`: pure directory, signing, resolution, and compatibility tests.
- Modify `backend/tests/api/test_tables.py`: customer-safe API behavior, `t2_` manifest output, legacy QR compatibility, and `503` tests.
- Modify `frontend/src/components/artisan/TableCodeSheet.tsx`: numeric input and canonical submission.
- Modify `frontend/src/components/artisan/TableCodeSheet.test.tsx`: input behavior tests.
- Modify `frontend/src/stores/tableOrderStore.ts`: defensive numeric normalization.
- Modify `frontend/src/stores/__tests__/tableOrderStore.test.ts`: numeric request and privacy tests.
- Modify `frontend/src/App.tsx` and `frontend/src/App.test.tsx`: recognize both `t2_` and legacy `t_` table entries.
- Modify `frontend/src/i18n/locales/en.json`, `ru.json`, and `uz.json`: table-number copy.
- Create `scripts/generate_table_qr_assets.py`: validate the live manifest, optionally verify every numeric code against the deployed API, render and decode labels, build the PDF, and package artifacts.
- Create `tests/scripts/test_generate_table_qr_assets.py`: offline generator and package verification.
- Modify `README.md`: numeric-code behavior and exact generation commands.

---

### Task 1: Canonical Numeric Codes and Strict Directory Validation

**Files:**
- Modify: `backend/app/services/table_access_service.py:13-88`
- Modify: `backend/tests/test_table_access_service.py:1-43`

**Interfaces:**
- Consumes: `alipos_api.get_halls_and_tables() -> dict` with `halls` and `tables` arrays.
- Produces: `manual_code_from_title(title: str) -> str`, `InvalidTableDirectory`, and `TableDirectoryEntry.manual_code: str`.
- Produces: `get_table_directory() -> list[TableDirectoryEntry]` that returns a complete validated snapshot or raises `InvalidTableDirectory`.

- [ ] **Step 1: Write failing extraction and validation tests**

Extend the imports in `backend/tests/test_table_access_service.py`, add these
cases, and update `_entry()` with `manual_code="12"`. Leave the existing legacy
six-character test in place until Task 2 replaces it:

```python
from unittest.mock import AsyncMock, patch

from app.services.table_access_service import (
    InvalidTableDirectory,
    InvalidTableEntry,
    TableAccessService,
    TableDirectoryEntry,
    get_table_directory,
    manual_code_from_title,
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Stol 1", "1"),
        ("Table 12", "12"),
        ("Stol 007", "7"),
        ("VIP Stol 25", "25"),
        ("Stol 000", "0"),
    ],
)
def test_manual_code_uses_trailing_table_number(title, expected):
    assert manual_code_from_title(title) == expected


@pytest.mark.parametrize("title", ["Stol", "Stol 1234567", "Stol 12 VIP", ""])
def test_manual_code_rejects_titles_without_one_to_six_trailing_digits(title):
    with pytest.raises(InvalidTableDirectory):
        manual_code_from_title(title)


@pytest.mark.asyncio
async def test_directory_rejects_duplicate_numeric_codes_across_halls():
    other_hall_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    other_table_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Asosiy zal", "servicePercent": 10},
            {"id": str(other_hall_id), "title": "Terrace", "servicePercent": 15},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stol 12", "hallId": str(HALL_ID)},
            {"id": str(other_table_id), "title": "Table 012", "hallId": str(other_hall_id)},
        ],
    }

    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        with pytest.raises(InvalidTableDirectory, match="Duplicate table number 12"):
            await get_table_directory()
```

- [ ] **Step 2: Run the focused tests and confirm they fail for the new behavior**

Run:

```bash
cd backend
uv run --no-project --python 3.12 --with-requirements requirements-dev.txt pytest tests/test_table_access_service.py -q
```

Expected: collection fails because `InvalidTableDirectory`, `manual_code_from_title`, and `TableDirectoryEntry.manual_code` do not exist yet.

- [ ] **Step 3: Implement numeric extraction and complete-directory validation**

In `backend/app/services/table_access_service.py`, replace the current permissive directory parser with these definitions and equivalent complete validation:

```python
_TABLE_NUMBER_RE = re.compile(r"([0-9]+)\s*$")


class InvalidTableDirectory(RuntimeError):
    pass


def manual_code_from_title(title: str) -> str:
    match = _TABLE_NUMBER_RE.search(title.strip())
    if match is None or len(match.group(1)) > 6:
        raise InvalidTableDirectory(
            f"Table title has no one-to-six digit trailing number: {title!r}"
        )
    return str(int(match.group(1)))


@dataclass(frozen=True)
class TableDirectoryEntry:
    table_id: uuid.UUID
    table_title: str
    hall_id: uuid.UUID
    hall_title: str
    service_percent: Decimal
    manual_code: str


async def get_table_directory() -> list[TableDirectoryEntry]:
    payload = await alipos_api.get_halls_and_tables()
    if not isinstance(payload, dict):
        raise InvalidTableDirectory("Table directory payload is not an object")
    raw_halls = payload.get("halls")
    raw_tables = payload.get("tables")
    if not isinstance(raw_halls, list) or not isinstance(raw_tables, list):
        raise InvalidTableDirectory("Table directory arrays are missing")

    halls: dict[uuid.UUID, tuple[str, Decimal]] = {}
    for hall in raw_halls:
        try:
            hall_id = uuid.UUID(str(hall["id"]))
            hall_title = str(hall.get("title") or "")
            service_percent = Decimal(str(hall.get("servicePercent") or 0))
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidTableDirectory("Hall directory entry is invalid") from exc
        if hall_id in halls:
            raise InvalidTableDirectory("Duplicate hall identifier")
        halls[hall_id] = (hall_title, service_percent)

    entries: list[TableDirectoryEntry] = []
    table_ids: set[uuid.UUID] = set()
    manual_codes: set[str] = set()
    for table in raw_tables:
        try:
            table_id = uuid.UUID(str(table["id"]))
            hall_id = uuid.UUID(str(table["hallId"]))
            table_title = str(table.get("title") or "")
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidTableDirectory("Table directory entry is invalid") from exc
        if table_id in table_ids:
            raise InvalidTableDirectory("Duplicate table identifier")
        hall = halls.get(hall_id)
        if hall is None:
            raise InvalidTableDirectory(f"Table has unknown hall: {table_title!r}")
        manual_code = manual_code_from_title(table_title)
        if manual_code in manual_codes:
            raise InvalidTableDirectory(f"Duplicate table number {manual_code}")

        table_ids.add(table_id)
        manual_codes.add(manual_code)
        hall_title, service_percent = hall
        entries.append(
            TableDirectoryEntry(
                table_id=table_id,
                table_title=table_title,
                hall_id=hall_id,
                hall_title=hall_title,
                service_percent=service_percent,
                manual_code=manual_code,
            )
        )
    return entries
```

Do not log the raw payload. Exceptions may name a table title or normalized number but never an AliPOS UUID or credential.

- [ ] **Step 4: Run the focused tests and verify the validated mapping passes**

Run:

```bash
cd backend
uv run --no-project --python 3.12 --with-requirements requirements-dev.txt pytest tests/test_table_access_service.py -q
```

Expected: all extraction and directory-validation tests pass. The unchanged
legacy signing test also remains green until Task 2 replaces it.

- [ ] **Step 5: Commit the directory mapping**

```bash
git add backend/app/services/table_access_service.py backend/tests/test_table_access_service.py
git commit -m "feat: derive numeric table codes"
```

---

### Task 2: Versioned QR Links, Legacy Compatibility, and API Failures

**Files:**
- Modify: `backend/app/services/table_access_service.py:91-251`
- Modify: `backend/app/routers/tables.py:16-100`
- Modify: `backend/tests/test_table_access_service.py`
- Modify: `backend/tests/api/test_tables.py`

**Interfaces:**
- Consumes: `TableDirectoryEntry.manual_code` and the complete validated directory from Task 1.
- Produces: `ParsedTableEntry(code: str, legacy: bool)`.
- Produces: `TableAccessService.build_start_param(entry: TableDirectoryEntry) -> str` for new `t2_` links.
- Produces: `TableAccessService.build_legacy_start_param(table_id: UUID) -> str` only for compatibility tests and controlled migration support.
- Produces: `TableAccessService.resolve_manual_code(...)` and `resolve_start_param(...)` with customer-safe `TableResolution` results.

- [ ] **Step 1: Write failing versioned-signature and legacy-resolution tests**

In `backend/tests/test_table_access_service.py`, replace the old `build_manual_code` assertions with:

```python
def test_numeric_start_parameter_round_trips_with_qr2_signature():
    service = _service()

    start_param = service.build_start_param(_entry())
    parsed = service.parse_start_param(start_param)

    assert start_param.startswith("t2_12_")
    assert parsed.code == "12"
    assert parsed.legacy is False


def test_tampered_numeric_start_parameter_is_rejected():
    service = _service()
    start_param = service.build_start_param(_entry())
    replacement = "0" if start_param[-1] != "0" else "1"

    with pytest.raises(InvalidTableEntry, match="Invalid table QR"):
        service.parse_start_param(start_param[:-1] + replacement)


def test_legacy_signed_qr_still_resolves_to_current_numeric_context():
    service = _service()
    start_param = service.build_legacy_start_param(TABLE_ID)

    resolution = service.resolve_start_param(start_param, [_entry()])

    assert start_param.startswith("t_")
    assert resolution.table_title == "Stol 12"
    assert resolution.manual_code == "12"


@pytest.mark.parametrize("code", ["12", "000012"])
def test_numeric_manual_code_normalizes_and_resolves(code):
    resolution = _service().resolve_manual_code(code, [_entry()])
    assert resolution.manual_code == "12"
```

In `backend/tests/api/test_tables.py`, update the manifest assertions to require `manual_code == "12"` and a deep link beginning with `https://t.me/olotsomsa_zakaz_bot?startapp=t2_12_`. Add one API test that submits `{"code": "000012"}` and one that submits `build_legacy_start_param(TABLE_ID)` as `entry`; both must return table 12 with `manual_code == "12"` and no raw UUIDs.

For new-link test setup, import `Decimal` and `TableDirectoryEntry`, then define:

```python
DIRECTORY_ENTRY = TableDirectoryEntry(
    table_id=TABLE_ID,
    table_title="Stol 12",
    hall_id=HALL_ID,
    hall_title="Asosiy zal",
    service_percent=Decimal("10"),
    manual_code="12",
)
```

Use `table_access.build_start_param(DIRECTORY_ENTRY)` anywhere the API test needs
a valid new QR entry. Use `table_access.build_legacy_start_param(TABLE_ID)` only
for the legacy compatibility case.

Add an invalid-directory API test using two tables whose titles normalize to `12`. The resolve endpoint must return:

```python
assert response.status_code == 503
assert response.json()["detail"] == "Table directory is temporarily unavailable"
assert str(TABLE_ID) not in response.text
```

- [ ] **Step 2: Run focused service tests and confirm the versioned interfaces are missing**

Run:

```bash
cd backend
uv run --no-project --python 3.12 --with-requirements requirements-dev.txt pytest tests/test_table_access_service.py -q
```

Expected: failures for missing `build_legacy_start_param`, `resolve_start_param`, `resolve_manual_code`, and the new `build_start_param` signature.

- [ ] **Step 3: Implement new and legacy signing paths**

In `backend/app/services/table_access_service.py`, retain the Crockford alphabet and replace the old code/start-parameter constants and methods with:

```python
_SUBMITTED_NUMERIC_CODE_RE = re.compile(r"^[0-9]{1,6}$")
_NUMERIC_START_PARAM_RE = re.compile(
    r"^t2_((?:0|[1-9][0-9]{0,5}))_([A-Za-z0-9_-]{12})$"
)
_LEGACY_START_PARAM_RE = re.compile(
    r"^t_([0-9A-HJKMNP-TV-Z]{6})_([A-Za-z0-9_-]{12})$"
)


@dataclass(frozen=True)
class ParsedTableEntry:
    code: str
    legacy: bool


def _normalize_submitted_code(value: str) -> str:
    digits = value.strip()
    if _SUBMITTED_NUMERIC_CODE_RE.fullmatch(digits) is None:
        raise InvalidTableEntry("Table code was not found")
    return str(int(digits))
```

Replace `build_manual_code`, `build_start_param`, and `parse_start_param` with:

```python
def build_legacy_manual_code(self, table_id: uuid.UUID) -> str:
    number = int.from_bytes(self._digest("manual", table_id.hex)[:4], "big") >> 2
    chars: list[str] = []
    for _ in range(6):
        number, remainder = divmod(number, len(_CROCKFORD_ALPHABET))
        chars.append(_CROCKFORD_ALPHABET[remainder])
    return "".join(reversed(chars))

def build_start_param(self, entry: TableDirectoryEntry) -> str:
    signature = _b64encode(self._digest("qr2", entry.manual_code)[:9])
    return f"t2_{entry.manual_code}_{signature}"

def build_legacy_start_param(self, table_id: uuid.UUID) -> str:
    code = self.build_legacy_manual_code(table_id)
    signature = _b64encode(self._digest("qr", code)[:9])
    return f"t_{code}_{signature}"

def parse_start_param(self, value: str) -> ParsedTableEntry:
    normalized = value.strip()
    numeric_match = _NUMERIC_START_PARAM_RE.fullmatch(normalized)
    if numeric_match is not None:
        code, received_signature = numeric_match.groups()
        expected_signature = _b64encode(self._digest("qr2", code)[:9])
        if hmac.compare_digest(received_signature, expected_signature):
            return ParsedTableEntry(code=code, legacy=False)
        raise InvalidTableEntry("Invalid table QR")

    legacy_match = _LEGACY_START_PARAM_RE.fullmatch(normalized)
    if legacy_match is None:
        raise InvalidTableEntry("Invalid table QR")
    code, received_signature = legacy_match.groups()
    expected_signature = _b64encode(self._digest("qr", code)[:9])
    if not hmac.compare_digest(received_signature, expected_signature):
        raise InvalidTableEntry("Invalid table QR")
    return ParsedTableEntry(code=code, legacy=True)
```

Add one private resolution builder so every path reports the current numeric code:

```python
def _resolution_for(
    self,
    entry: TableDirectoryEntry,
    *,
    expires_at: datetime.datetime | None = None,
) -> TableResolution:
    return TableResolution(
        table_title=entry.table_title,
        hall_title=entry.hall_title,
        service_percent=entry.service_percent,
        manual_code=entry.manual_code,
        access_token=self.issue_access_token(entry, expires_at=expires_at),
    )

def resolve_manual_code(
    self,
    code: str,
    directory: list[TableDirectoryEntry],
) -> TableResolution:
    normalized = _normalize_submitted_code(code)
    entry = next((item for item in directory if item.manual_code == normalized), None)
    if entry is None:
        raise InvalidTableEntry("Table code was not found")
    return self._resolution_for(entry)

def resolve_start_param(
    self,
    value: str,
    directory: list[TableDirectoryEntry],
) -> TableResolution:
    parsed = self.parse_start_param(value)
    if parsed.legacy:
        entry = next(
            (
                item
                for item in directory
                if self.build_legacy_manual_code(item.table_id) == parsed.code
            ),
            None,
        )
    else:
        entry = next(
            (item for item in directory if item.manual_code == parsed.code),
            None,
        )
    if entry is None:
        raise InvalidTableEntry("Table code was not found")
    return self._resolution_for(entry)
```

Update `resolve`, `restore`, and `manifest` exactly along these boundaries:

```python
async def resolve(self, entry: str | None, code: str | None) -> TableResolution:
    directory = await get_table_directory()
    if entry is not None:
        return self.resolve_start_param(entry, directory)
    return self.resolve_manual_code(code or "", directory)

# In restore(), use:
return self._resolution_for(entry, expires_at=expires_at)

# In manifest(), use the current entry:
start_param = self.build_start_param(entry)
# and emit manual_code=entry.manual_code
```

- [ ] **Step 4: Return generic `503` responses for an invalid directory**

Import `InvalidTableDirectory` in `backend/app/routers/tables.py`, define the public detail once, and catch it separately from customer input errors:

```python
TABLE_DIRECTORY_UNAVAILABLE = "Table directory is temporarily unavailable"


def _directory_unavailable(exc: InvalidTableDirectory) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=TABLE_DIRECTORY_UNAVAILABLE,
    )
```

Apply this pattern to all three routes:

```python
try:
    resolved = await table_access.resolve(body.entry, body.code)
except InvalidTableDirectory as exc:
    raise _directory_unavailable(exc) from exc
except InvalidTableEntry as exc:
    # Preserve the existing 404 for unknown codes and 400 for malformed QR input.
```

For `restore_table`, catch `InvalidTableDirectory` before `InvalidTableEntry`. For `get_table_manifest`, wrap `table_access.manifest()` and convert only `InvalidTableDirectory` to `503`; authorization behavior remains unchanged.

- [ ] **Step 5: Run backend service and API tests**

First run the database-free service tests:

```bash
cd backend
uv run --no-project --python 3.12 --with-requirements requirements-dev.txt pytest tests/test_table_access_service.py -q
```

Then run the PostgreSQL-backed API tests in the Compose network:

```bash
docker compose run --rm --build backend sh -lc 'pip install --no-cache-dir -r requirements-dev.txt && pytest tests/api/test_tables.py -q'
```

Expected: both commands pass. The manifest contains `t2_12_`, legacy signed QR resolution passes, duplicate numeric codes return `503`, and no response contains the fixture UUIDs.

- [ ] **Step 6: Commit backend signing and API behavior**

```bash
git add backend/app/services/table_access_service.py backend/app/routers/tables.py backend/tests/test_table_access_service.py backend/tests/api/test_tables.py
git commit -m "feat: add versioned numeric table links"
```

---

### Task 3: Numeric Customer Entry and `t2_` Telegram Handling

**Files:**
- Modify: `frontend/src/components/artisan/TableCodeSheet.tsx:1-155`
- Modify: `frontend/src/components/artisan/TableCodeSheet.test.tsx`
- Modify: `frontend/src/stores/tableOrderStore.ts:104-111`
- Modify: `frontend/src/stores/__tests__/tableOrderStore.test.ts:22-49`
- Modify: `frontend/src/App.tsx:126-143`
- Modify: `frontend/src/App.test.tsx:361-408`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/uz.json`

**Interfaces:**
- Consumes: `POST /api/tables/resolve` accepting numeric `code` or signed `entry` from Task 2.
- Produces: canonical one-to-six-digit requests and app routing for both `t2_` and legacy `t_` parameters.

- [ ] **Step 1: Write failing numeric-entry tests**

Replace the existing TableCodeSheet test with these behaviors:

```tsx
it('keeps one to six digits and submits the canonical table number', async () => {
  const user = userEvent.setup();
  const resolveCode = vi.fn().mockResolvedValue(undefined);
  const onClose = vi.fn();
  render(
    <TableCodeSheet
      open
      onClose={onClose}
      onResolve={resolveCode}
      resolving={false}
      error={null}
    />,
  );

  const input = screen.getByRole('textbox');
  expect(input).toHaveAttribute('inputmode', 'numeric');
  expect(input).toHaveAttribute('pattern', '[0-9]*');

  await user.type(input, '00a1-2b34567');
  expect(input).toHaveValue('001234');
  await user.click(screen.getByRole('button', { name: /confirm|tasdiqlash/i }));

  expect(resolveCode).toHaveBeenCalledWith('1234');
  expect(onClose).toHaveBeenCalledTimes(1);
});

it('keeps confirmation disabled until at least one digit exists', () => {
  render(
    <TableCodeSheet
      open
      onClose={vi.fn()}
      onResolve={vi.fn()}
      resolving={false}
      error={null}
    />,
  );
  expect(screen.getByRole('button', { name: /confirm|tasdiqlash/i })).toBeDisabled();
});
```

Update the store test to call `resolveCode('00a1-2')`, assert `resolveTable({code: '12'})`, and keep the existing assertions proving the manual code and raw IDs are not persisted in session storage.

In `frontend/src/App.test.tsx`, change the primary table start-parameter fixture to `t2_12_q1w2e3r4t5y6` and add a second test proving `t_A7K2P9_q1w2e3r4t5y6` still calls `resolveEntry` once.

- [ ] **Step 2: Run focused frontend tests and confirm the current six-character behavior fails**

Run:

```bash
cd frontend
npm test -- src/components/artisan/TableCodeSheet.test.tsx src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx
```

Expected: the current component removes letters but still requires exactly six Crockford characters, uses `inputMode="text"`, and ignores `t2_`.

- [ ] **Step 3: Implement numeric normalization in the component and store**

In `TableCodeSheet.tsx`, use these helpers:

```tsx
function normalizeCode(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6);
}

function canonicalizeCode(value: string): string {
  return value.replace(/^0+(?=\d)/, '');
}
```

Change submission and input behavior:

```tsx
if (code.length === 0 || resolving) return;
await onResolve(canonicalizeCode(code));

<input
  id="table-code"
  autoFocus
  autoComplete="off"
  inputMode="numeric"
  pattern="[0-9]*"
  enterKeyHint="done"
  value={code}
  onChange={(event) => setCode(normalizeCode(event.target.value))}
  placeholder="12"
/>
```

Replace every `code.length === 6` button state with `code.length > 0` while retaining the `resolving` guard.

In `tableOrderStore.ts`, normalize defensively before calling the API:

```tsx
resolveCode: async (code) => {
  const digits = code.replace(/\D/g, '').slice(0, 6);
  const normalized = digits.replace(/^0+(?=\d)/, '');
  await resolveAndStore(resolveTable({ code: normalized }), set);
},
```

- [ ] **Step 4: Recognize versioned and legacy table parameters**

Change the App condition without altering order-return behavior:

```tsx
const isTableStartParam = startParam.startsWith('t2_') || startParam.startsWith('t_');
if (isTableStartParam) {
  navigate('/', { replace: true });
  void resolveTableEntry(startParam).catch(() => {
    // The menu exposes a retryable manual-number fallback.
  });
}
```

- [ ] **Step 5: Update localized table-number copy**

Set the table entry strings to:

```json
// en.json
"enter_code_hint": "Enter your table number",
"enter_code": "Enter table number",
"enter_short": "Enter number",
"code_title": "Enter table number",
"code_description": "Enter the table number printed beside the QR.",
"code_label": "Table number"
```

```json
// ru.json
"enter_code_hint": "Введите номер стола",
"enter_code": "Ввести номер стола",
"enter_short": "Ввести номер",
"code_title": "Введите номер стола",
"code_description": "Введите номер стола, напечатанный рядом с QR.",
"code_label": "Номер стола"
```

```json
// uz.json
"enter_code_hint": "Stol raqamini kiriting",
"enter_code": "Stol raqamini kiritish",
"enter_short": "Raqam kiritish",
"code_title": "Stol raqamini kiriting",
"code_description": "QR yonida ko'rsatilgan stol raqamini kiriting.",
"code_label": "Stol raqami"
```

Update the component's Uzbek fallback strings to match `uz.json`.

- [ ] **Step 6: Run focused tests, type checking, and linting**

Run:

```bash
cd frontend
npm test -- src/components/artisan/TableCodeSheet.test.tsx src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx
npm run typecheck
npm run lint
```

Expected: all commands pass, `t2_` and `t_` both resolve, and numeric input submits canonical values.

- [ ] **Step 7: Commit the frontend behavior**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/artisan/TableCodeSheet.tsx frontend/src/components/artisan/TableCodeSheet.test.tsx frontend/src/stores/tableOrderStore.ts frontend/src/stores/__tests__/tableOrderStore.test.ts frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/uz.json
git commit -m "feat: accept numeric table numbers"
```

---

### Task 4: Verified QR Asset Generator

**Files:**
- Create: `scripts/generate_table_qr_assets.py`
- Create: `tests/scripts/test_generate_table_qr_assets.py`
- Modify: `README.md:264-273`

**Interfaces:**
- Consumes: a JSON file containing either the admin API wrapper `{success, data}` or the raw manifest array.
- Optional input: `--verify-api https://restaurant.labtutor.app/api`, which resolves every numeric code and compares safe table/hall fields before rendering.
- Produces: `<output>/png/*.png`, `<output>/manifest.json`, `<output>/manifest.csv`, `<output>/verification.json`, `<output>/all-table-qr-codes.pdf`, and sibling `<output>.zip`.
- Uses no application credentials. The admin JWT is used only by the separate manifest download command.

- [ ] **Step 1: Write failing generator tests**

Create `tests/scripts/test_generate_table_qr_assets.py`:

```python
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
import zxingcpp
from PIL import Image

SCRIPT = Path(__file__).parents[2] / "scripts" / "generate_table_qr_assets.py"
SPEC = importlib.util.spec_from_file_location("generate_table_qr_assets", SCRIPT)
assert SPEC and SPEC.loader
qr_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qr_assets)


def manifest():
    return {
        "success": True,
        "data": [
            {
                "table_title": "Stol 2",
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "manual_code": "2",
                "start_param": "t2_2_abcdefghijkl",
                "deep_link": "https://t.me/olotsomsa_zakaz_bot?startapp=t2_2_abcdefghijkl",
            },
            {
                "table_title": "Stol 12",
                "hall_title": "Asosiy zal",
                "service_percent": 10,
                "manual_code": "12",
                "start_param": "t2_12_mnopqrstuvwx",
                "deep_link": "https://t.me/olotsomsa_zakaz_bot?startapp=t2_12_mnopqrstuvwx",
            },
        ],
    }


def test_generate_package_renders_decodable_sorted_assets(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(manifest()), encoding="utf-8")
    output = tmp_path / "table-qr-codes"

    rows = qr_assets.load_manifest(source)
    zip_path = qr_assets.generate_package(rows, output)

    pngs = sorted((output / "png").glob("*.png"))
    assert [path.name[:6] for path in pngs] == ["000002", "000012"]
    decoded = [zxingcpp.read_barcode(Image.open(path)).text for path in pngs]
    assert decoded == [row["deep_link"] for row in rows]
    assert (output / "all-table-qr-codes.pdf").stat().st_size > 0
    assert json.loads((output / "verification.json").read_text())["verified_count"] == 2
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "manifest.json" in names
    assert "manifest.csv" in names
    assert "all-table-qr-codes.pdf" in names
    assert len([name for name in names if name.startswith("png/")]) == 2


def test_manifest_rejects_duplicate_or_mismatched_codes(tmp_path):
    payload = manifest()
    payload["data"][1]["manual_code"] = "2"
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate manual code"):
        qr_assets.load_manifest(source)


def test_api_verification_compares_only_safe_table_fields(monkeypatch):
    row = manifest()["data"][0]
    response = {
        "success": True,
        "data": {
            "table_title": row["table_title"],
            "hall_title": row["hall_title"],
            "manual_code": row["manual_code"],
            "access_token": "must-not-be-written-to-artifacts",
        },
    }
    monkeypatch.setattr(
        qr_assets.urllib.request,
        "urlopen",
        lambda request, timeout: io.StringIO(json.dumps(response)),
    )

    qr_assets.verify_api([row], "https://restaurant.labtutor.app/api")
```

- [ ] **Step 2: Run the generator tests and confirm the script is absent**

Run:

```bash
uv run --no-project --python 3.12 --with pytest --with 'qrcode[pil]>=8,<9' --with 'Pillow>=11,<13' --with 'zxing-cpp>=2.2,<3' pytest tests/scripts/test_generate_table_qr_assets.py -q
```

Expected: collection fails because `scripts/generate_table_qr_assets.py` does not exist.

- [ ] **Step 3: Implement strict manifest validation and API verification**

Create the script with PEP 723 metadata and these exact boundaries:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "qrcode[pil]>=8,<9",
#   "Pillow>=11,<13",
#   "zxing-cpp>=2.2,<3",
# ]
# ///

import argparse
import csv
import json
import re
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qrcode
import zxingcpp
from PIL import Image, ImageDraw, ImageFont

CODE_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")
SAFE_FIELDS = (
    "table_title",
    "hall_title",
    "service_percent",
    "manual_code",
    "start_param",
    "deep_link",
)


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest must contain at least one table")

    validated: list[dict] = []
    seen_codes: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Manifest row is not an object")
        row = {field: raw.get(field) for field in SAFE_FIELDS}
        if not all(isinstance(row[field], str) for field in SAFE_FIELDS if field != "service_percent"):
            raise ValueError("Manifest row has missing text fields")
        code = row["manual_code"]
        if CODE_RE.fullmatch(code) is None:
            raise ValueError(f"Invalid manual code: {code!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate manual code: {code}")

        parsed = urlparse(row["deep_link"])
        start_param = parse_qs(parsed.query).get("startapp", [None])[0]
        if parsed.scheme != "https" or parsed.netloc != "t.me":
            raise ValueError("Deep link must use https://t.me")
        if start_param != row["start_param"]:
            raise ValueError(f"Deep link/start parameter mismatch for table {code}")
        if not row["start_param"].startswith(f"t2_{code}_"):
            raise ValueError(f"Start parameter/code mismatch for table {code}")

        seen_codes.add(code)
        validated.append(row)

    return sorted(
        validated,
        key=lambda row: (
            row["hall_title"].casefold(),
            int(row["manual_code"]),
            row["table_title"].casefold(),
        ),
    )


def verify_api(rows: list[dict], api_base: str) -> None:
    endpoint = api_base.rstrip("/") + "/tables/resolve"
    for row in rows:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"code": row["manual_code"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
        data = payload.get("data", {})
        safe_actual = (
            data.get("table_title"),
            data.get("hall_title"),
            data.get("manual_code"),
        )
        safe_expected = (
            row["table_title"],
            row["hall_title"],
            row["manual_code"],
        )
        if safe_actual != safe_expected:
            raise ValueError(f"Deployed resolver mismatch for table {row['manual_code']}")
```

The verifier must never persist or print the returned access token.

- [ ] **Step 4: Implement labels, QR decoding, PDF pagination, and ZIP output**

Continue the script with these functions:

```python
FONT_REGULAR_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
FONT_BOLD_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


def _font_path(candidates: tuple[Path, ...]) -> Path:
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise RuntimeError("A supported Arial or DejaVu Sans font is required")
    return path


def _center(draw, text: str, font, y: int, width: int, fill: str = "#161616") -> None:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) / 2, y), text, font=font, fill=fill)


def _slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value).strip("-").lower()
    return slug or "table"


def render_card(row: dict, destination: Path) -> None:
    width, height = 1200, 1500
    regular = _font_path(FONT_REGULAR_CANDIDATES)
    bold = _font_path(FONT_BOLD_CANDIDATES)
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)

    _center(draw, "OLOT SOMSA", ImageFont.truetype(str(bold), 70), 55, width, "#8F2D20")
    _center(draw, row["hall_title"], ImageFont.truetype(str(regular), 42), 150, width)
    _center(draw, row["table_title"], ImageFont.truetype(str(bold), 76), 215, width)

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=18,
        border=4,
    )
    qr.add_data(row["deep_link"])
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_image.thumbnail((900, 900), Image.Resampling.NEAREST)
    canvas.paste(qr_image, ((width - qr_image.width) // 2, 330))

    _center(
        draw,
        "Stol raqami / Номер стола",
        ImageFont.truetype(str(regular), 42),
        1250,
        width,
    )
    _center(
        draw,
        row["manual_code"],
        ImageFont.truetype(str(bold), 112),
        1310,
        width,
        "#8F2D20",
    )
    canvas.save(destination, format="PNG", optimize=True)


def build_pdf(cards: list[Path], destination: Path) -> None:
    pages: list[Image.Image] = []
    page_width, page_height = 2480, 3508
    cell_width, cell_height = page_width // 2, page_height // 2
    for offset in range(0, len(cards), 4):
        page = Image.new("RGB", (page_width, page_height), "white")
        for index, path in enumerate(cards[offset : offset + 4]):
            card = Image.open(path).convert("RGB")
            card.thumbnail((1120, 1500), Image.Resampling.LANCZOS)
            column, row = index % 2, index // 2
            x = column * cell_width + (cell_width - card.width) // 2
            y = row * cell_height + (cell_height - card.height) // 2
            page.paste(card, (x, y))
        pages.append(page)
    pages[0].save(
        destination,
        "PDF",
        resolution=300,
        save_all=True,
        append_images=pages[1:],
    )


def generate_package(rows: list[dict], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=False)
    png_dir = output / "png"
    png_dir.mkdir()
    cards: list[Path] = []
    for row in rows:
        filename = (
            f"{int(row['manual_code']):06d}-"
            f"{_slug(row['hall_title'])}-{_slug(row['table_title'])}.png"
        )
        destination = png_dir / filename
        render_card(row, destination)
        decoded = zxingcpp.read_barcode(Image.open(destination))
        if decoded is None or decoded.text != row["deep_link"]:
            raise ValueError(f"QR decode mismatch for table {row['manual_code']}")
        cards.append(destination)

    (output / "manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SAFE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output / "verification.json").write_text(
        json.dumps({"verified_count": len(rows)}, indent=2) + "\n",
        encoding="utf-8",
    )
    build_pdf(cards, output / "all-table-qr-codes.pdf")

    zip_path = output.with_suffix(".zip")
    if zip_path.exists():
        raise FileExistsError(zip_path)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output))
    return zip_path
```

Add this CLI. It accepts required `--manifest` and `--output` paths plus optional
`--verify-api`; it prints only the count and output paths, never deep links or
access tokens:

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-api")
    args = parser.parse_args()

    rows = load_manifest(args.manifest)
    if args.verify_api:
        verify_api(rows, args.verify_api)
    zip_path = generate_package(rows, args.output)
    print(f"verified_tables={len(rows)}")
    print(f"output_directory={args.output}")
    print(f"zip_archive={zip_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the generator tests and inspect rendered output**

Run:

```bash
uv run --no-project --python 3.12 --with pytest --with 'qrcode[pil]>=8,<9' --with 'Pillow>=11,<13' --with 'zxing-cpp>=2.2,<3' pytest tests/scripts/test_generate_table_qr_assets.py -q
```

Expected: both tests pass and every fixture PNG decodes to its fixture deep link.

Open the fixture PDF using the PDF workflow during execution and verify that text is not clipped, QR quiet zones remain white, and the two-by-two A4 layout has no overlap.

- [ ] **Step 6: Document the operator workflow**

Replace the QR generation paragraph in `README.md` with:

````markdown
Manual entry uses the trailing table number from the AliPOS title: `Stol 12`
uses code `12`. Codes must be unique across all halls. New QR links use signed
`t2_` parameters; already printed signed `t_` links remain compatible.

After deploying and verifying the public app, download the admin manifest without
printing the JWT:

```bash
test -n "$ADMIN_JWT"
curl -fsS -H "Authorization: Bearer $ADMIN_JWT" \
  https://restaurant.labtutor.app/api/tables/manifest \
  -o /private/tmp/olot-table-manifest.json
```

Generate and verify the assets outside the repository:

```bash
uv run --script scripts/generate_table_qr_assets.py \
  --manifest /private/tmp/olot-table-manifest.json \
  --verify-api https://restaurant.labtutor.app/api \
  --output /private/tmp/olot-table-qr-codes
```
````

- [ ] **Step 7: Commit the generator and documentation**

```bash
git add scripts/generate_table_qr_assets.py tests/scripts/test_generate_table_qr_assets.py README.md
git commit -m "feat: generate verified table QR assets"
```

---

### Task 5: Full Regression Verification

**Files:**
- Verify only; fix only failures caused by Tasks 1-4.

**Interfaces:**
- Consumes: completed backend, frontend, and generator tasks.
- Produces: a locally verified release candidate commit with no generated production artifacts committed.

- [ ] **Step 1: Run the complete backend suite and linter**

Run:

```bash
docker compose run --rm --build backend sh -lc 'pip install --no-cache-dir -r requirements-dev.txt && ruff check . && pytest -q'
```

Expected: Ruff exits zero and the complete backend suite passes.

- [ ] **Step 2: Run the complete frontend quality gates**

Run:

```bash
cd frontend
npm run test
npm run typecheck
npm run lint
npm run build
```

Expected: all tests pass, TypeScript and ESLint exit zero, and Vite produces the production build.

- [ ] **Step 3: Re-run the standalone generator suite**

Run:

```bash
uv run --no-project --python 3.12 --with pytest --with 'qrcode[pil]>=8,<9' --with 'Pillow>=11,<13' --with 'zxing-cpp>=2.2,<3' pytest tests/scripts/test_generate_table_qr_assets.py -q
```

Expected: all generator tests pass.

- [ ] **Step 4: Audit the final diff and commit any test-caused corrections**

Run:

```bash
git diff --check
git status --short
git log -5 --oneline
```

Expected: no whitespace errors, only intended feature files are tracked, production manifests/PNGs/PDFs/ZIPs are absent from Git, and the recent commits correspond to Tasks 1-4. If a scoped correction was required, commit only its files with `git commit -m "fix: complete numeric table code verification"`.

---

### Task 6: Restore OLOT SOMSA, Deploy, and Deliver All Live QR Codes

**Files:**
- Read: `commands.md`
- Generate outside Git: `/Users/khajievroma/.codex/visualizations/2026/07/17/019f7013-ecc9-78f2-b9ce-fb48558c55d4/table-qr-codes-2026-07-17/`
- Generate outside Git: sibling ZIP archive.

**Interfaces:**
- Consumes: a release commit that passed Task 5, the authorized `restaurant` SSH alias, the existing deployment `.env`, and an admin JWT held only in the environment.
- Produces: a healthy deployed Mini App and verified downloadable QR artifacts for every table in the live manifest.

- [ ] **Step 1: Reproduce the reported outage at public and host boundaries**

Run the public checks separately:

```bash
curl -sS -o /dev/null -w 'restaurant frontend -> HTTP %{http_code}\n' --max-time 15 https://restaurant.labtutor.app/healthz
curl -sS -o /dev/null -w 'restaurant API -> HTTP %{http_code}\n' --max-time 15 https://restaurant.labtutor.app/api/health
```

Then check the host:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 restaurant hostname
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker ps'
ssh restaurant 'wsl.exe -d Ubuntu -u root -- tail -n 80 /var/log/restaurant-stack-supervisor.log'
```

Expected: evidence identifies whether the failure is host/Tailscale, WSL/Docker, an unhealthy application container, or the Cloudflare tunnel. Do not change anything until this boundary is known.

- [ ] **Step 2: Apply only the matching safe recovery action**

If SSH works but the stacks are stopped, run:

```bash
ssh restaurant 'schtasks.exe /Run /TN \RestaurantWSLApps'
```

If application containers are healthy but the public endpoints return Cloudflare `530` or `1033`, restart only the restaurant tunnel:

```bash
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker restart restaurant_cloudflared'
```

If SSH times out and both public checks remain unavailable, stop: the Windows host must be powered on locally, connected to the internet, and reconnected to the authorized Tailscale network. Do not restart PostgreSQL, shut down WSL, prune Docker, or edit secrets.

- [ ] **Step 3: Publish and deploy the verified release commit**

Push the current reviewed branch and record the exact release commit locally:

```bash
git push -u origin codex/staff-delivery-phase-1
git rev-parse HEAD
git log -1 --oneline
```

On the restaurant host, preserve a clean-failure boundary: confirm the checkout is clean, fetch the pushed commit, check it out, then rebuild only this stack. Use the exact commit printed above; do not use a moving branch name for the deployed revision.

```bash
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app status --short'
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app fetch origin'
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- bash -lc "cd /home/khajiev13/apps/restaurant-mini-app && git checkout --detach \"$(git rev-parse origin/codex/staff-delivery-phase-1)\""'
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc "cd /home/khajiev13/apps/restaurant-mini-app && docker compose up -d --build backend frontend caddy cloudflared"'
```

The command deliberately refuses to overwrite a dirty server checkout.

- [ ] **Step 4: Verify the deployed revision and public health**

Run:

```bash
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app log -1 --oneline'
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker ps'
curl -fsS https://restaurant.labtutor.app/healthz -o /dev/null
curl -fsS https://restaurant.labtutor.app/api/health -o /dev/null
```

Expected: the server commit matches the release commit, application containers are healthy, and both public checks exit zero.

- [ ] **Step 5: Download the live admin manifest without exposing credentials**

Load the admin JWT into the shell environment from the authenticated admin session; never place it in a command-line argument, file committed to Git, or tool output. Then run:

```bash
test -n "$ADMIN_JWT"
curl -fsS -H "Authorization: Bearer $ADMIN_JWT" \
  https://restaurant.labtutor.app/api/tables/manifest \
  -o /private/tmp/olot-table-manifest.json
```

Validate only counts and public labels in terminal output; do not print the complete manifest:

```bash
jq '{count: (.data | length), halls: ([.data[].hall_title] | unique), codes: [.data[].manual_code]}' /private/tmp/olot-table-manifest.json
```

Expected: every `manual_code` is canonical numeric text and appears once.

- [ ] **Step 6: Generate, decode, and package every live QR**

Run:

```bash
uv run --script scripts/generate_table_qr_assets.py \
  --manifest /private/tmp/olot-table-manifest.json \
  --verify-api https://restaurant.labtutor.app/api \
  --output /Users/khajievroma/.codex/visualizations/2026/07/17/019f7013-ecc9-78f2-b9ce-fb48558c55d4/table-qr-codes-2026-07-17
```

Expected: the script reports the live table count, resolves every numeric code against production, decodes every PNG to its exact manifest link, creates the printable PDF, and creates the sibling ZIP.

- [ ] **Step 7: Visually inspect the final PDF and perform one Telegram smoke test**

Use the PDF workflow to render every page and check for clipped titles, insufficient QR quiet zones, overlaps, missing cards, or unreadable fallback numbers. Compare the number of cards with `verification.json`.

Open one generated QR link through Telegram as a controlled customer and confirm that the displayed hall and table match the printed label. Do not place an order unless the release owner separately authorizes a live order test.

- [ ] **Step 8: Deliver the verified artifacts**

Provide clickable links to:

- the sibling ZIP containing all PNGs and manifests;
- `all-table-qr-codes.pdf` for printing;
- the output directory when individual PNG access is useful.

Report the exact verified table count and public health result. Do not claim BitAgent was fixed or include any JWT, access token, AliPOS UUID, or raw vendor response.
