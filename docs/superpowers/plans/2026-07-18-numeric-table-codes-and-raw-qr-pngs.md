# Numeric Table Codes and Raw QR PNGs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let customers enter the physical table number, keep existing signed table QR links compatible, and deliver one verified raw PNG QR per live AliPOS table with no file for the intentionally absent table 9.

**Architecture:** The backend derives one canonical numeric code from the trailing digits in every AliPOS table title and rejects the complete directory when that mapping is malformed or ambiguous. New QR links use signed `t2_` parameters while legacy signed `t_` parameters continue to resolve. A standalone generator consumes only the deployed admin manifest, verifies public health and every signed resolver result, renders undecorated QR symbols into a staging directory, decodes them, and atomically delivers a PNG-only folder.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, pytest, React 19, TypeScript 5.7, Zustand 5, Vitest, Testing Library, i18next, qrcode 8, Pillow 11+, zxing-cpp 2.2+, Docker, PostgreSQL 16.

## Global Constraints

- AliPOS table and hall IDs remain UUID strings internally; only the customer-facing manual code becomes numeric.
- The manual code is the trailing ASCII digit sequence from the AliPOS table title, normalized by removing leading zeroes; `000` becomes `0`.
- The source digit sequence and submitted manual input contain one to six digits.
- Numeric codes are globally unique across all halls. Missing, malformed, or duplicate codes make the whole customer table directory unavailable with HTTP `503`.
- Numeric gaps are valid. The live set is currently `1-8, 10-30`; table `9` is intentionally absent and no continuity rule may be added.
- New QR parameters use `t2_<numeric-code>_<signature>` with the `qr2` HMAC purpose.
- Existing signed `t_<six-character-code>_<signature>` links remain supported with the original `qr` HMAC purpose.
- The table-access secret is not rotated. Raw AliPOS UUIDs, credentials, bearer tokens, and table access tokens never appear in customer-visible output, logs, filenames, or delivered files.
- The customer manual field accepts digits only, uses a numeric keyboard, accepts one to six digits, and submits the canonical code. This restriction does not apply to internal identifiers or unrelated inputs.
- The delivered folder contains exactly one PNG per current deployed manifest row and no PDF, ZIP, CSV, JSON, README, label, caption, language text, logo, frame, or decoration.
- Delivered filenames are `table-01.png`, `table-02.png`, and so on with a minimum width of two digits; no absent manifest code gets a file.
- Each PNG is an opaque white square containing only a black QR symbol, error-correction level Q, a quiet zone of at least four modules, integer module scaling, and dimensions of at least 1200 by 1200 pixels.
- Every PNG decodes byte-for-byte to its manifest row's exact `deep_link`, and every signed `t2_` entry resolves through the deployed API to the matching safe table number and title before delivery.
- Generation occurs only after both `https://restaurant.labtutor.app/healthz` and `https://restaurant.labtutor.app/api/health` return HTTP `200` and the numeric release is deployed.
- No database migration, AliPOS write, order placement, cancellation, booking, or table mutation is part of this work.

## File Structure

- Modify `backend/app/services/table_access_service.py`: canonical numeric extraction, strict directory validation, versioned QR signing/parsing, legacy compatibility, and safe resolution.
- Modify `backend/app/routers/tables.py`: map invalid live directory state to generic HTTP `503` responses.
- Modify `backend/tests/test_table_access_service.py`: pure extraction, directory, signature, resolution, and compatibility coverage.
- Modify `backend/tests/api/test_tables.py`: customer-safe API behavior, `t2_` manifest output, legacy compatibility, and `503` privacy.
- Modify `frontend/src/components/artisan/TableCodeSheet.tsx` and its test: numeric input and canonical submission.
- Modify `frontend/src/stores/tableOrderStore.ts` and its test: defensive numeric normalization.
- Modify `frontend/src/App.tsx` and its test: handle both `t2_` and legacy `t_` table start parameters without changing order-return handling.
- Modify `frontend/src/i18n/locales/en.json`, `ru.json`, and `uz.json`: existing app copy for table-number entry; no copy is rendered into QR PNGs.
- Create `scripts/download_table_manifest.py`: download the admin manifest with an environment-held JWT, direct HTTP `200` only, no redirects, and no overwrite.
- Create `tests/scripts/test_download_table_manifest.py`: offline redirect, credential, direct-response, and no-overwrite tests.
- Create `scripts/generate_table_qr_pngs.py`: strict manifest/deployment verification, raw rendering, decode verification, and atomic PNG-only delivery.
- Create `tests/scripts/test_generate_table_qr_pngs.py`: offline generator, deployment-verifier, gap, image, and fail-closed tests.
- Modify `backend/requirements-dev.txt`: add generator/test-only image and decoder dependencies.
- Modify `README.md`: numeric table behavior and the exact PNG-only operator workflow.

---

### Task 1: Canonical Numeric Codes and Strict Directory Validation

**Files:**
- Modify: `backend/app/services/table_access_service.py`
- Modify: `backend/tests/test_table_access_service.py`

**Interfaces:**
- Consumes: `alipos_api.get_halls_and_tables() -> dict` containing `halls` and `tables` arrays.
- Produces: `InvalidTableDirectory(RuntimeError)`.
- Produces: `manual_code_from_title(title: str) -> str`.
- Produces: `TableDirectoryEntry.manual_code: str`.
- Produces: `get_table_directory() -> list[TableDirectoryEntry]`, returning one complete validated snapshot or raising `InvalidTableDirectory`.

- [ ] **Step 1: Write failing extraction, duplicate, and gap tests**

Update `_entry()` to pass `manual_code="12"`, import `AsyncMock`, `patch`, `InvalidTableDirectory`, `get_table_directory`, and `manual_code_from_title`, then add:

```python
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
def test_manual_code_rejects_missing_or_oversized_trailing_number(title):
    with pytest.raises(InvalidTableDirectory):
        manual_code_from_title(title)


@pytest.mark.asyncio
async def test_directory_accepts_numeric_gaps_including_missing_nine():
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Zal", "servicePercent": 10},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stoll 8", "hallId": str(HALL_ID)},
            {
                "id": "22222222-2222-4222-8222-222222222222",
                "title": "Stoll 10",
                "hallId": str(HALL_ID),
            },
        ],
    }
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        directory = await get_table_directory()
    assert [entry.manual_code for entry in directory] == ["8", "10"]


@pytest.mark.asyncio
async def test_directory_rejects_duplicate_numeric_codes_across_halls():
    other_hall_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Zal", "servicePercent": 10},
            {"id": str(other_hall_id), "title": "Terrace", "servicePercent": 15},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stoll 12", "hallId": str(HALL_ID)},
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "title": "Table 012",
                "hallId": str(other_hall_id),
            },
        ],
    }
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        with pytest.raises(InvalidTableDirectory, match="Duplicate table number 12"):
            await get_table_directory()
```

Add exact fail-closed cases instead of silently dropping records:

```python
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.__setitem__("halls", {}),
        lambda payload: payload.__setitem__("tables", {}),
        lambda payload: payload["halls"].__setitem__(0, "not-an-object"),
        lambda payload: payload["halls"][0].__setitem__("id", "not-a-uuid"),
        lambda payload: payload["halls"].append(dict(payload["halls"][0])),
        lambda payload: payload["tables"].__setitem__(0, "not-an-object"),
        lambda payload: payload["tables"][0].__setitem__("id", "not-a-uuid"),
        lambda payload: payload["tables"].append(
            {
                **payload["tables"][0],
                "title": "Stoll 13",
            }
        ),
        lambda payload: payload["tables"][0].__setitem__(
            "hallId", "55555555-5555-4555-8555-555555555555"
        ),
    ],
    ids=[
        "halls-not-array",
        "tables-not-array",
        "hall-not-object",
        "malformed-hall-id",
        "duplicate-hall-id",
        "table-not-object",
        "malformed-table-id",
        "duplicate-table-id",
        "unknown-hall-id",
    ],
)
@pytest.mark.asyncio
async def test_directory_rejects_malformed_or_ambiguous_records(mutate):
    payload = {
        "halls": [
            {"id": str(HALL_ID), "title": "Zal", "servicePercent": 10},
        ],
        "tables": [
            {"id": str(TABLE_ID), "title": "Stoll 12", "hallId": str(HALL_ID)},
        ],
    }
    mutate(payload)
    with patch(
        "app.services.table_access_service.alipos_api.get_halls_and_tables",
        new=AsyncMock(return_value=payload),
    ):
        with pytest.raises(InvalidTableDirectory):
            await get_table_directory()
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd backend
.venv/bin/dotenv -f /Users/khajievroma/Projects/restaurant-mini-app/.env run -- .venv/bin/python -m pytest tests/test_table_access_service.py -q
```

Expected: collection fails because `InvalidTableDirectory`, `manual_code_from_title`, and `TableDirectoryEntry.manual_code` do not exist.

- [ ] **Step 3: Implement extraction and complete-directory validation**

Add `import re`, import `InvalidOperation` beside `Decimal`, replace the permissive directory parser, and add the field to the directory entry:

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
    for raw_hall in raw_halls:
        if not isinstance(raw_hall, dict):
            raise InvalidTableDirectory("Hall directory entry is invalid")
        try:
            hall_id = uuid.UUID(str(raw_hall["id"]))
            hall_title = str(raw_hall.get("title") or "")
            service_percent = Decimal(str(raw_hall.get("servicePercent") or 0))
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise InvalidTableDirectory("Hall directory entry is invalid") from exc
        if hall_id in halls:
            raise InvalidTableDirectory("Duplicate hall identifier")
        halls[hall_id] = (hall_title, service_percent)

    entries: list[TableDirectoryEntry] = []
    table_ids: set[uuid.UUID] = set()
    manual_codes: set[str] = set()
    for raw_table in raw_tables:
        if not isinstance(raw_table, dict):
            raise InvalidTableDirectory("Table directory entry is invalid")
        try:
            table_id = uuid.UUID(str(raw_table["id"]))
            hall_id = uuid.UUID(str(raw_table["hallId"]))
            table_title = str(raw_table.get("title") or "")
        except (KeyError, TypeError, ValueError) as exc:
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

Do not log the payload or UUIDs. Do not add a contiguous-range or special-case-9 check.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command again. Expected: all service tests pass, including the explicit `8, 10` gap case.

- [ ] **Step 5: Commit the validated numeric directory**

```bash
git add backend/app/services/table_access_service.py backend/tests/test_table_access_service.py
git commit -m "feat: derive numeric table codes"
```

---

### Task 2: Versioned QR Links, Legacy Compatibility, and Generic API Failures

**Files:**
- Modify: `backend/app/services/table_access_service.py`
- Modify: `backend/app/routers/tables.py`
- Modify: `backend/tests/test_table_access_service.py`
- Modify: `backend/tests/api/test_tables.py`

**Interfaces:**
- Consumes: `TableDirectoryEntry.manual_code` and validated directories from Task 1.
- Produces: `ParsedTableEntry(code: str, legacy: bool)`.
- Produces: `build_start_param(entry: TableDirectoryEntry) -> str` for new links.
- Produces: `build_legacy_start_param(table_id: UUID) -> str` for compatibility tests and controlled migration.
- Produces: `resolve_manual_code(...)` and `resolve_start_param(...)`, both returning the existing customer-safe `TableResolution`.

- [ ] **Step 1: Write failing signing, compatibility, normalization, manifest, and `503` tests**

Replace the old UUID-derived manual-code expectations with:

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


def test_legacy_signed_qr_resolves_to_current_numeric_context():
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

In `backend/tests/api/test_tables.py`, define a `TableDirectoryEntry` fixture with `manual_code="12"`. Update the new-link setup to use `table_access.build_start_param(DIRECTORY_ENTRY)`, require manifest `manual_code == "12"`, and require `deep_link` to start with `https://t.me/olotsomsa_zakaz_bot?startapp=t2_12_`. Add API cases for `{"code": "000012"}`, a valid legacy `entry`, a tampered new entry, and two titles that normalize to `12`. The duplicate-directory response must be:

```python
assert response.status_code == 503
assert response.json()["detail"] == "Table directory is temporarily unavailable"
assert str(TABLE_ID) not in response.text
```

Exercise the same generic `503` mapping for resolve, restore, and manifest while retaining existing authorization behavior.

- [ ] **Step 2: Run the focused service tests and verify RED**

Run the Task 1 focused command. Expected: failures for missing `ParsedTableEntry`, `build_legacy_start_param`, `resolve_start_param`, `resolve_manual_code`, and the new `build_start_param` signature.

- [ ] **Step 3: Implement numeric and legacy signing paths**

Retain `_CROCKFORD_ALPHABET`, add these constants and definitions, and replace the old code/start methods:

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

Add one shared resolution builder and explicit manual/signed resolvers:

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
        matches = [
            item
            for item in directory
            if self.build_legacy_manual_code(item.table_id) == parsed.code
        ]
        if len(matches) > 1:
            raise InvalidTableDirectory("Duplicate legacy table code")
    else:
        matches = [item for item in directory if item.manual_code == parsed.code]
    if len(matches) != 1:
        raise InvalidTableEntry("Table code was not found")
    return self._resolution_for(matches[0])

async def resolve(self, entry: str | None, code: str | None) -> TableResolution:
    directory = await get_table_directory()
    if entry is not None:
        return self.resolve_start_param(entry, directory)
    return self.resolve_manual_code(code or "", directory)
```

Change `restore()` to return `_resolution_for(entry, expires_at=expires_at)`. In `manifest()`, use `build_start_param(entry)`, emit `entry.manual_code`, and sort by `int(entry.manual_code)` before creating rows.

- [ ] **Step 4: Map invalid directories to generic HTTP `503`**

Import `InvalidTableDirectory` in `backend/app/routers/tables.py`, define:

```python
TABLE_DIRECTORY_UNAVAILABLE = "Table directory is temporarily unavailable"


def _directory_unavailable(exc: InvalidTableDirectory) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=TABLE_DIRECTORY_UNAVAILABLE,
    )
```

Catch `InvalidTableDirectory` before `InvalidTableEntry` in resolve and restore. Wrap `table_access.manifest()` after `require_admin()` and convert only `InvalidTableDirectory` to `503`. Preserve resolve's existing 404 for an unknown code, 400 for malformed/tampered QR, restore's 409 for an unavailable table, and manifest authorization.

- [ ] **Step 5: Run service and PostgreSQL-backed API tests**

Run the service command from Task 1, then with the isolated test database listening on `127.0.0.1:55432` run:

```bash
cd backend
.venv/bin/dotenv -f /Users/khajievroma/Projects/restaurant-mini-app/.env run -- env POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest tests/api/test_tables.py -q
```

Expected: both commands pass; the manifest emits signed `t2_12_` links, old signed `t_` links still resolve, ambiguous numeric directories return generic `503`, and fixture UUIDs are absent from responses.

- [ ] **Step 6: Commit backend signing and API behavior**

```bash
git add backend/app/services/table_access_service.py backend/app/routers/tables.py backend/tests/test_table_access_service.py backend/tests/api/test_tables.py
git commit -m "feat: add versioned numeric table links"
```

---

### Task 3: Numeric Customer Entry and `t2_` Telegram Handling

**Files:**
- Modify: `frontend/src/components/artisan/TableCodeSheet.tsx`
- Modify: `frontend/src/components/artisan/TableCodeSheet.test.tsx`
- Modify: `frontend/src/stores/tableOrderStore.ts`
- Modify: `frontend/src/stores/__tests__/tableOrderStore.test.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/uz.json`

**Interfaces:**
- Consumes: `POST /api/tables/resolve` accepting canonical numeric `code` or signed `entry` from Task 2.
- Produces: numeric requests and routing for both `t2_` and legacy `t_` parameters.

- [ ] **Step 1: Write failing numeric-entry and start-parameter tests**

Replace the component's six-character behavior tests with:

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

Update the store test to call `resolveCode('00a1-2')`, assert `resolveTable({code: '12'})`, and retain the privacy assertions for session storage. Change the primary App fixture to `t2_12_q1w2e3r4t5y6`, add a legacy `t_A7K2P9_q1w2e3r4t5y6` case, and keep `order_` behavior unchanged.

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run:

```bash
cd frontend
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/vitest/vitest.mjs run src/components/artisan/TableCodeSheet.test.tsx src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx
```

Expected: the current text keyboard/six-character rules fail and `t2_` is ignored.

- [ ] **Step 3: Implement numeric normalization and submission**

In `TableCodeSheet.tsx`, add:

```tsx
function normalizeCode(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6);
}

function canonicalizeCode(value: string): string {
  return value.replace(/^0+(?=\d)/, '');
}
```

Submit only when `code.length > 0 && !resolving`, pass `canonicalizeCode(code)`, and configure the input exactly as follows while retaining the component's existing styling and error/resolving states:

```tsx
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

In `tableOrderStore.ts`, normalize defensively:

```tsx
resolveCode: async (code) => {
  const digits = code.replace(/\D/g, '').slice(0, 6);
  const normalized = digits.replace(/^0+(?=\d)/, '');
  await resolveAndStore(resolveTable({ code: normalized }), set);
},
```

- [ ] **Step 4: Recognize both table start-parameter versions**

Use this branch without altering the existing `order_` branch:

```tsx
const isTableStartParam = startParam.startsWith('t2_') || startParam.startsWith('t_');
if (isTableStartParam) {
  navigate('/', { replace: true });
  void resolveTableEntry(startParam).catch(() => {
    // The menu exposes a retryable manual-number fallback.
  });
}
```

- [ ] **Step 5: Update existing app copy, not the QR images**

Use these exact values in the existing locale keys:

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

Update the component's Uzbek fallback strings to the same wording. Do not add Chinese or any other text to generated QR files; the user is doing visual design separately.

- [ ] **Step 6: Run focused tests, type checking, and linting**

Run:

```bash
cd frontend
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/vitest/vitest.mjs run src/components/artisan/TableCodeSheet.test.tsx src/stores/__tests__/tableOrderStore.test.ts src/App.test.tsx
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/typescript/bin/tsc --noEmit
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/eslint/bin/eslint.js .
```

Expected: all commands pass and only the customer manual field is numeric-only.

- [ ] **Step 7: Commit the frontend behavior**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/components/artisan/TableCodeSheet.tsx frontend/src/components/artisan/TableCodeSheet.test.tsx frontend/src/stores/tableOrderStore.ts frontend/src/stores/__tests__/tableOrderStore.test.ts frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/uz.json
git commit -m "feat: accept numeric table numbers"
```

---

### Task 4: Strict Raw PNG Generator and Operator Documentation

**Files:**
- Create: `scripts/download_table_manifest.py`
- Create: `tests/scripts/test_download_table_manifest.py`
- Create: `scripts/generate_table_qr_pngs.py`
- Create: `tests/scripts/test_generate_table_qr_pngs.py`
- Modify: `backend/requirements-dev.txt`
- Modify: `README.md`

**Interfaces:**
- Downloads: the admin manifest only through `scripts/download_table_manifest.py`, which reads `ADMIN_JWT` from the environment, accepts only a direct HTTP `200`, rejects redirects, logs no credential or response body, and refuses to overwrite its output file.
- Consumes: a JSON file containing either `{ "success": true, "data": [...] }` from the deployed admin manifest or the raw manifest array.
- Consumes: `--public-base https://restaurant.labtutor.app` and the required trusted `--bot-username`; verifies `/healthz`, `/api/health`, and every signed `entry` at `/api/tables/resolve` before rendering.
- Produces: one output directory containing only verified `table-XX.png` files.
- Uses no application credential. The admin JWT is used only by the separate manifest-download command.

- [ ] **Step 1: Add test-only image dependencies and write failing downloader/generator tests**

Append these exact lines to `backend/requirements-dev.txt`:

```text
qrcode[pil]>=8,<9
Pillow>=11,<13
zxing-cpp>=2.2,<3
```

Create `tests/scripts/test_download_table_manifest.py` with offline coverage for redirect rejection, a direct HTTP `200`, refusal before network when the output exists, missing `ADMIN_JWT`, and the absence of credential or response-body logging. Create `tests/scripts/test_generate_table_qr_pngs.py` with fixtures for codes `1`, `8`, `10`, and `30`, canonical `t2_` parameters with twelve-character signatures, and exact deep links for the required trusted bot. Cover these exact generator behaviors:

```python
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import zxingcpp
from PIL import Image

SCRIPT = Path(__file__).parents[2] / "scripts" / "generate_table_qr_pngs.py"
SPEC = importlib.util.spec_from_file_location("generate_table_qr_pngs", SCRIPT)
assert SPEC and SPEC.loader
qr_pngs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qr_pngs)


def manifest_rows():
    rows = []
    for code, signature in (
        ("1", "aaaaaaaaaaaa"),
        ("8", "bbbbbbbbbbbb"),
        ("10", "cccccccccccc"),
        ("30", "dddddddddddd"),
    ):
        start_param = f"t2_{code}_{signature}"
        rows.append(
            {
                "table_title": f"Stoll {code}",
                "hall_title": "Zal",
                "manual_code": code,
                "start_param": start_param,
                "deep_link": (
                    "https://t.me/olotsomsa_zakaz_bot?startapp=" + start_param
                ),
            }
        )
    return rows


def test_gap_manifest_generates_only_raw_verified_pngs(tmp_path):
    output = tmp_path / "table-qr-pngs"
    rows = qr_pngs.validate_manifest_rows(manifest_rows())
    result = qr_pngs.generate_verified_png_folder(rows, output)

    assert result == output
    assert [path.name for path in sorted(output.iterdir())] == [
        "table-01.png",
        "table-08.png",
        "table-10.png",
        "table-30.png",
    ]
    assert not (output / "table-09.png").exists()
    for row, path in zip(rows, sorted(output.iterdir()), strict=True):
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.mode == "RGB"
            assert image.width == image.height
            assert image.width >= 1200
            assert image.getpixel((0, 0)) == (255, 255, 255)
            assert "transparency" not in image.info
            assert set(image.getdata()) <= {(0, 0, 0), (255, 255, 255)}
            decoded = zxingcpp.read_barcode(image)
        assert decoded is not None
        assert decoded.text == row["deep_link"]

    assert qr_pngs.QUIET_ZONE_MODULES >= 4


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[0].pop("manual_code"),
        lambda rows: rows[0].__setitem__("manual_code", "A1"),
        lambda rows: rows[0].__setitem__("manual_code", "01"),
        lambda rows: rows[1].__setitem__("manual_code", "1"),
        lambda rows: rows[0].__setitem__("table_title", "Stoll 2"),
        lambda rows: rows[0].__setitem__("start_param", "t_AAAAAA_aaaaaaaaaaaa"),
        lambda rows: rows[0].__setitem__("start_param", "t2_2_aaaaaaaaaaaa"),
        lambda rows: rows[0].__setitem__(
            "deep_link",
            "https://t.me/olotsomsa_zakaz_bot?startapp=t2_2_aaaaaaaaaaaa",
        ),
    ],
)
def test_manifest_rejects_missing_duplicate_or_mismatched_codes(mutate):
    rows = manifest_rows()
    mutate(rows)
    with pytest.raises(ValueError):
        qr_pngs.validate_manifest_rows(rows)


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def test_deployment_verification_uses_signed_entries_and_safe_fields(monkeypatch):
    rows = qr_pngs.validate_manifest_rows(manifest_rows())
    requests = []

    def fake_urlopen(request, timeout):
        assert timeout == 20
        requests.append(request)
        if request.full_url.endswith(("/healthz", "/api/health")):
            return FakeResponse(b"ok")
        submitted = json.loads(request.data)
        assert set(submitted) == {"entry"}
        row = next(item for item in rows if item["start_param"] == submitted["entry"])
        return FakeResponse(
            json.dumps(
                {
                    "success": True,
                    "data": {
                        "manual_code": row["manual_code"],
                        "table_title": row["table_title"],
                        "hall_title": "ignored safe field",
                        "access_token": "must-not-be-persisted-or-printed",
                    },
                }
            ).encode()
        )

    monkeypatch.setattr(qr_pngs.urllib.request, "urlopen", fake_urlopen)
    qr_pngs.verify_deployment(rows, "https://restaurant.labtutor.app")
    resolver_requests = [request for request in requests if request.data is not None]
    assert [json.loads(request.data) for request in resolver_requests] == [
        {"entry": row["start_param"]} for row in rows
    ]


def test_decode_failure_leaves_no_delivery_folder(tmp_path, monkeypatch):
    output = tmp_path / "table-qr-pngs"
    monkeypatch.setattr(
        qr_pngs.zxingcpp,
        "read_barcode",
        lambda image: SimpleNamespace(text="wrong destination"),
    )
    with pytest.raises(ValueError, match="QR decode mismatch"):
        qr_pngs.generate_verified_png_folder(
            qr_pngs.validate_manifest_rows(manifest_rows()),
            output,
        )
    assert not output.exists()


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "table-qr-pngs"
    output.mkdir()
    with pytest.raises(FileExistsError):
        qr_pngs.generate_verified_png_folder(
            qr_pngs.validate_manifest_rows(manifest_rows()),
            output,
        )
```

Add these file-boundary cases:

```python
@pytest.mark.parametrize("wrapped", [False, True])
def test_load_manifest_accepts_raw_or_success_wrapper(tmp_path, wrapped):
    rows = manifest_rows()
    payload = {"success": True, "data": rows} if wrapped else rows
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    assert qr_pngs.load_manifest(source) == qr_pngs.validate_manifest_rows(rows)


@pytest.mark.parametrize("field", ["access_token", "table_id", "hall_id"])
def test_manifest_rejects_sensitive_fields(field):
    rows = manifest_rows()
    rows[0][field] = "must-not-enter-the-generator"
    with pytest.raises(ValueError, match="sensitive"):
        qr_pngs.validate_manifest_rows(rows)
```

- [ ] **Step 2: Install the declared dependencies and verify RED**

Run:

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest tests/scripts/test_download_table_manifest.py tests/scripts/test_generate_table_qr_pngs.py -q
```

Expected: collection fails because `scripts/download_table_manifest.py` and `scripts/generate_table_qr_pngs.py` do not exist.

- [ ] **Step 3: Implement the hardened downloader and strict manifest/deployed-resolver verification**

Create `scripts/download_table_manifest.py` with the downloader boundaries described above, then create the generator with these constants and boundaries:

```python
import argparse
import json
import math
import re
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qrcode
import zxingcpp
from PIL import Image

CODE_RE = re.compile(r"^(?:0|[1-9][0-9]{0,5})$")
TITLE_CODE_RE = re.compile(r"([0-9]+)\s*$")
START_PARAM_RE = re.compile(
    r"^t2_((?:0|[1-9][0-9]{0,5}))_([A-Za-z0-9_-]{12})$"
)
REQUIRED_TEXT_FIELDS = (
    "table_title",
    "hall_title",
    "manual_code",
    "start_param",
    "deep_link",
)
SENSITIVE_FIELDS = {"access_token", "table_id", "hall_id", "jwt", "token"}
MIN_SIDE_PIXELS = 1200
QUIET_ZONE_MODULES = 4


def _title_code(title: str) -> str:
    match = TITLE_CODE_RE.search(title.strip())
    if match is None or not 1 <= len(match.group(1)) <= 6:
        raise ValueError("Table title has no valid trailing number")
    return str(int(match.group(1)))


def validate_manifest_rows(rows: object) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest must contain at least one table")
    validated: list[dict] = []
    seen_codes: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Manifest row is not an object")
        if SENSITIVE_FIELDS.intersection(raw):
            raise ValueError("Manifest row contains a sensitive field")
        if any(not isinstance(raw.get(field), str) for field in REQUIRED_TEXT_FIELDS):
            raise ValueError("Manifest row has missing text fields")

        code = raw["manual_code"]
        if CODE_RE.fullmatch(code) is None:
            raise ValueError(f"Invalid manual code: {code!r}")
        if code in seen_codes:
            raise ValueError(f"Duplicate manual code: {code}")
        if _title_code(raw["table_title"]) != code:
            raise ValueError(f"Table title/code mismatch for table {code}")

        start_match = START_PARAM_RE.fullmatch(raw["start_param"])
        if start_match is None or start_match.group(1) != code:
            raise ValueError(f"Start parameter/code mismatch for table {code}")
        parsed = urlparse(raw["deep_link"])
        query = parse_qs(parsed.query, keep_blank_values=True)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "t.me"
            or not parsed.path.strip("/")
            or parsed.fragment
            or set(query) != {"startapp"}
            or query["startapp"] != [raw["start_param"]]
        ):
            raise ValueError(f"Deep link/start parameter mismatch for table {code}")

        seen_codes.add(code)
        validated.append({field: raw[field] for field in REQUIRED_TEXT_FIELDS})
    return sorted(validated, key=lambda row: int(row["manual_code"]))


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(payload, dict) and payload.get("success") is not True:
        raise ValueError("Manifest response was not successful")
    return validate_manifest_rows(rows)
```

Add network helpers that never print response bodies:

```python
def _read_response(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=20) as response:
        if getattr(response, "status", 200) != 200:
            raise ValueError("Deployed endpoint did not return HTTP 200")
        return response.read()


def verify_deployment(rows: list[dict], public_base: str) -> None:
    base = public_base.rstrip("/")
    for health_url in (f"{base}/healthz", f"{base}/api/health"):
        _read_response(urllib.request.Request(health_url, method="GET"))

    endpoint = f"{base}/api/tables/resolve"
    for row in rows:
        request = urllib.request.Request(
            endpoint,
            data=json.dumps({"entry": row["start_param"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        payload = json.loads(_read_response(request))
        data = payload.get("data") if isinstance(payload, dict) else None
        actual = (
            data.get("manual_code") if isinstance(data, dict) else None,
            data.get("table_title") if isinstance(data, dict) else None,
        )
        expected = (row["manual_code"], row["table_title"])
        if (
            not isinstance(payload, dict)
            or payload.get("success") is not True
            or actual != expected
        ):
            raise ValueError(f"Deployed resolver mismatch for table {row['manual_code']}")
```

- [ ] **Step 4: Implement raw integer-scaled rendering and atomic delivery**

Add:

```python
def render_raw_qr(deep_link: str) -> Image.Image:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=1,
        border=QUIET_ZONE_MODULES,
    )
    qr.add_data(deep_link)
    qr.make(fit=True)
    total_modules = qr.modules_count + 2 * QUIET_ZONE_MODULES
    qr.box_size = math.ceil(MIN_SIDE_PIXELS / total_modules)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def generate_verified_png_folder(rows: list[dict], output: Path) -> Path:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".table-qr-", dir=output.parent) as temp_dir:
        staging = Path(temp_dir) / "delivery"
        staging.mkdir()
        for row in rows:
            destination = staging / f"table-{int(row['manual_code']):02d}.png"
            render_raw_qr(row["deep_link"]).save(destination, format="PNG", optimize=True)
            with Image.open(destination) as image:
                if (
                    image.format != "PNG"
                    or image.mode != "RGB"
                    or image.width != image.height
                    or image.width < MIN_SIDE_PIXELS
                ):
                    raise ValueError(f"Invalid PNG for table {row['manual_code']}")
                decoded = zxingcpp.read_barcode(image)
            if decoded is None or decoded.text != row["deep_link"]:
                raise ValueError(f"QR decode mismatch for table {row['manual_code']}")

        expected_names = {
            f"table-{int(row['manual_code']):02d}.png" for row in rows
        }
        actual_names = {path.name for path in staging.iterdir() if path.is_file()}
        if actual_names != expected_names or any(path.is_dir() for path in staging.iterdir()):
            raise ValueError("PNG delivery folder contents do not match the manifest")
        staging.replace(output)
    return output
```

Add this CLI. It prints only the verified count and directory path:

```python
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--public-base", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = load_manifest(args.manifest)
    verify_deployment(rows, args.public_base)
    output = generate_verified_png_folder(rows, args.output)
    print(f"verified_pngs={len(rows)}")
    print(f"output_directory={output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run publication-tooling tests and verify GREEN**

Run:

```bash
backend/.venv/bin/python -m pytest tests/scripts/test_download_table_manifest.py tests/scripts/test_generate_table_qr_pngs.py -q
```

Expected: all downloader, validation, trusted-bot, gap, health/resolver, image, decode, staging-cleanup, and no-overwrite tests pass.

- [ ] **Step 6: Document the exact PNG-only workflow**

Replace the README's six-character QR paragraph and update the endpoint description. Document that `Stoll 12` uses manual code `12`, new links use signed `t2_`, legacy signed `t_` links remain compatible, and gaps such as the intentional missing `9` are valid. Include:

```bash
test -n "$ADMIN_JWT"
test ! -e /private/tmp/olot-table-manifest.json
test ! -e /private/tmp/olot-table-qr-pngs
backend/.venv/bin/python scripts/download_table_manifest.py \
  --output /private/tmp/olot-table-manifest.json

backend/.venv/bin/python scripts/generate_table_qr_pngs.py \
  --manifest /private/tmp/olot-table-manifest.json \
  --public-base https://restaurant.labtutor.app \
  --bot-username olotsomsa_zakaz_bot \
  --output /private/tmp/olot-table-qr-pngs
```

State explicitly that both output paths must be new and neither tool overwrites an existing file or directory. The JWT remains environment-held and the output directory contains only raw black-on-white PNGs; it contains no manifest, text, PDF, ZIP, or design elements.

- [ ] **Step 7: Commit the generator and documentation**

```bash
git add scripts/download_table_manifest.py tests/scripts/test_download_table_manifest.py scripts/generate_table_qr_pngs.py tests/scripts/test_generate_table_qr_pngs.py backend/requirements-dev.txt README.md
git commit -m "feat: generate verified raw table QR PNGs"
```

---

### Task 5: Full Regression Verification

**Files:**
- Verify only; modify only failures caused by Tasks 1-4.

**Interfaces:**
- Consumes: completed backend, frontend, and generator tasks.
- Produces: one release-candidate commit with no production manifests or PNGs tracked in Git.

- [ ] **Step 1: Run the complete backend suite and linter against an isolated test database**

With the disposable PostgreSQL test container on `127.0.0.1:55432`, run:

```bash
cd backend
.venv/bin/python -m ruff check .
.venv/bin/dotenv -f /Users/khajievroma/Projects/restaurant-mini-app/.env run -- env POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 .venv/bin/python -m pytest -q
```

Expected: Ruff exits zero and the complete suite passes without touching an existing application database.

- [ ] **Step 2: Run complete frontend quality gates**

Run:

```bash
cd frontend
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/vitest/vitest.mjs run
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/typescript/bin/tsc --noEmit
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/eslint/bin/eslint.js .
/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/vite/bin/vite.js build
```

Expected: all tests and static checks pass and Vite completes the production build.

- [ ] **Step 3: Re-run the standalone publication-tooling suite**

```bash
backend/.venv/bin/python -m pytest tests/scripts/test_download_table_manifest.py tests/scripts/test_generate_table_qr_pngs.py -q
```

Expected: all downloader and generator tests pass.

- [ ] **Step 4: Audit the release diff**

```bash
git diff --check
git status --short
git log -6 --oneline
```

Expected: only the intended source, test, and documentation files are tracked; `frontend/node_modules`, `.env`, `.venv`, live manifests, and production PNG folders are absent from commits. Commit only a scoped correction caused by the feature with `git commit -m "fix: complete numeric table QR verification"`.

---

### Task 6: Deploy the Reviewed Commit and Deliver the Live PNG Folder

**Files:**
- Generate outside Git: `/Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs/`
- Temporary outside Git: `/private/tmp/olot-table-manifest.json`

**Interfaces:**
- Consumes: the final reviewed commit on `codex/numeric-table-qr-pngs`, the authorized `restaurant` SSH alias, the deployed `.env`, and an admin JWT held only in an authenticated process environment.
- Produces: a healthy deployed numeric-table release and one verified PNG-only folder from the current live manifest.

- [ ] **Step 1: Check public and host boundaries without mutation**

```bash
curl -fsS https://restaurant.labtutor.app/healthz -o /dev/null
curl -fsS https://restaurant.labtutor.app/api/health -o /dev/null
ssh -o BatchMode=yes -o ConnectTimeout=10 restaurant hostname
ssh restaurant 'wsl.exe -d Ubuntu -u root -- docker ps --format "table {{.Names}}\t{{.Status}}"'
```

Expected: both public endpoints return HTTP `200`, SSH succeeds, and no secret-bearing process arguments are listed. If WSL/Docker is stalled, use the previously established `WslService` and `\\RestaurantWSLApps` recovery path; do not inspect broad process listings or print tunnel arguments.

- [ ] **Step 2: Push and deploy the exact reviewed commit**

```bash
git push -u origin codex/numeric-table-qr-pngs
git rev-parse HEAD
```

Confirm the production checkout is clean, fetch, check out the exact commit printed above in detached mode, then rebuild only this application stack:

```bash
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app status --short'
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app fetch origin'
ssh restaurant "wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app checkout --detach $(git rev-parse HEAD)"
ssh restaurant 'wsl.exe -d Ubuntu -u root -- bash -lc "cd /home/khajiev13/apps/restaurant-mini-app && docker compose up -d --build backend frontend caddy cloudflared"'
```

Never use a moving branch name for the deployed revision and never overwrite a dirty server checkout.

- [ ] **Step 3: Verify deployed revision and public health**

```bash
ssh restaurant 'wsl.exe -d Ubuntu -u khajiev13 -- git -C /home/khajiev13/apps/restaurant-mini-app rev-parse HEAD'
curl -fsS https://restaurant.labtutor.app/healthz -o /dev/null
curl -fsS https://restaurant.labtutor.app/api/health -o /dev/null
```

Expected: the remote revision exactly equals the reviewed commit and both endpoints return HTTP `200`.

- [ ] **Step 4: Download the admin manifest without exposing the JWT**

Place the authenticated admin JWT only in the current shell environment. The manifest path must be new because the downloader refuses to overwrite an existing file. Then run:

```bash
test -n "$ADMIN_JWT"
test ! -e /private/tmp/olot-table-manifest.json
backend/.venv/bin/python scripts/download_table_manifest.py \
  --output /private/tmp/olot-table-manifest.json
jq '{count: (.data | length), codes: [.data[].manual_code]}' /private/tmp/olot-table-manifest.json
```

Expected when the live directory is unchanged: count `29`, codes `1-8, 10-30`, every code unique, and no `9`. Do not print the complete manifest, JWT, signatures, or access tokens.

- [ ] **Step 5: Generate and verify the live folder**

```bash
test ! -e /Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs
backend/.venv/bin/python scripts/generate_table_qr_pngs.py \
  --manifest /private/tmp/olot-table-manifest.json \
  --public-base https://restaurant.labtutor.app \
  --bot-username olotsomsa_zakaz_bot \
  --output /Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs
```

Expected: `verified_pngs=29` when the live set is unchanged. The output folder must be new because the generator refuses to overwrite an existing directory. It contains `table-01.png` through `table-08.png` and `table-10.png` through `table-30.png`, with no `table-09.png` and no non-PNG file. Any health, manifest, signed-resolver, image, or decode failure leaves no delivered folder.

- [ ] **Step 6: Deliver the folder and remove the temporary manifest**

After verifying the output count and names, delete only the temporary manifest:

```bash
rm -f /private/tmp/olot-table-manifest.json
```

Provide the clickable output-folder link, the exact verified count, the deployed commit, and the two public health results. Do not claim an order was placed or that unrelated applications were changed.
