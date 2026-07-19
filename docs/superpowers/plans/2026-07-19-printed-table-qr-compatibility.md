# Printed Table QR Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 29 already printed table QR stickers automatically restore the matching table context on the current production deployment without weakening QR validation.

**Architecture:** Keep current-secret HMAC verification first, then accept only deployment-configured historical code/signature pairs for syntactically valid `t2_` parameters. Parse the configuration once at application startup, inject the typed mapping into `TableAccessService`, and leave legacy `t_`, manual-number, table-directory, and order behavior unchanged.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, pytest, Docker Compose, Telegram Mini App deep links.

## Global Constraints

- Preserve the 29 printed sticker payloads exactly; do not regenerate or replace stickers.
- Never accept an arbitrary unsigned table number from a `t2_` start parameter.
- Keep `TABLE_ACCESS_SECRET` unchanged and use it for future QR manifests.
- Keep compatibility signatures deployment-specific and out of repository source.
- Reject malformed configuration at startup.
- Do not modify AliPOS IDs, table numbers, database schema/data, frontend, Caddy, Cloudflare, or BitAgent.
- Deploy from an exact commit that passed the complete backend suite and Ruff.

---

### Task 1: Add strict compatibility parsing and resolution

**Files:**
- Modify: `backend/app/services/table_access_service.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/tables.py`
- Modify: `backend/tests/test_table_access_service.py`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Produces: `parse_numeric_qr_compat_signatures(value: str) -> dict[str, frozenset[str]]`.
- Extends: `TableAccessService(..., numeric_qr_compat_signatures: Mapping[str, Collection[str]] | None = None)`.
- Consumes: optional `Settings.table_qr_compat_signatures` from `TABLE_QR_COMPAT_SIGNATURES`.

- [ ] **Step 1: Write failing parser and resolution tests**

Add tests that demonstrate the intended public contracts:

```python
def test_numeric_qr_compat_config_parses_exact_pairs():
    assert parse_numeric_qr_compat_signatures(
        "1:ABCDEFGHIJKL,10:MNOPQRSTUVWX"
    ) == {
        "1": frozenset({"ABCDEFGHIJKL"}),
        "10": frozenset({"MNOPQRSTUVWX"}),
    }


def test_printed_numeric_qr_signature_is_accepted_for_its_exact_code():
    service = TableAccessService(
        secret="current-secret",
        bot_username="olotsomsa_zakaz_bot",
        numeric_qr_compat_signatures={"12": frozenset({"ABCDEFGHIJKL"})},
    )
    assert service.parse_start_param("t2_12_ABCDEFGHIJKL") == ParsedTableEntry(
        code="12",
        legacy=False,
    )


def test_printed_numeric_qr_signature_cannot_select_another_code():
    service = TableAccessService(
        secret="current-secret",
        bot_username="olotsomsa_zakaz_bot",
        numeric_qr_compat_signatures={"12": frozenset({"ABCDEFGHIJKL"})},
    )
    with pytest.raises(InvalidTableEntry, match="Invalid table QR"):
        service.parse_start_param("t2_13_ABCDEFGHIJKL")
```

Parametrize malformed configuration for empty entries, leading-zero codes,
oversized codes, missing separators, invalid signature length/characters, and
duplicate exact pairs. Retain the existing tests proving current `qr2` and
legacy `t_` behavior.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run inside the Python 3.12 backend test image:

```bash
pytest tests/test_table_access_service.py -q
```

Expected: collection or assertion failures because the parser and constructor
parameter do not exist.

- [ ] **Step 3: Implement the minimal service behavior**

In `table_access_service.py`, validate the comma-separated configuration with
the existing numeric/signature grammar and return immutable signature sets.
Inject the mapping into `TableAccessService`. In the numeric parse branch,
accept when either the current HMAC signature or one of the exact signatures
configured for the parsed code matches using `hmac.compare_digest`.

Do not change the legacy parse branch or downstream directory resolution.

- [ ] **Step 4: Wire configuration at startup**

Add this Pydantic setting:

```python
table_qr_compat_signatures: str = ""
```

Parse and inject it when the table router constructs `TableAccessService`:

```python
numeric_qr_compat_signatures=parse_numeric_qr_compat_signatures(
    settings.table_qr_compat_signatures
),
```

An invalid value must raise during application import/startup.

- [ ] **Step 5: Document the migration-only setting**

Add `TABLE_QR_COMPAT_SIGNATURES=` to `.env.example`. Document that values are
exact public signatures from already printed QRs, that normal HMAC verification
remains primary, and that the setting must never be replaced with a wildcard or
unsigned-code bypass.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run:

```bash
pytest tests/test_table_access_service.py -q
ruff check app tests
```

Expected: all focused tests pass and Ruff exits zero.

- [ ] **Step 7: Run the complete backend suite**

Run:

```bash
pytest -q
```

Expected: the complete suite passes with no failures.

- [ ] **Step 8: Commit the implementation**

Stage only the six Task 1 files and commit:

```bash
git commit -m "fix: preserve printed table QR signatures"
```

### Task 2: Build the exact production compatibility configuration

**Files:**
- Consume: `/Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs/table-*.png`
- Create temporarily: a mode-600 configuration line outside the repository.

**Interfaces:**
- Produces: one `TABLE_QR_COMPAT_SIGNATURES=` line containing exactly 29 unique code/signature pairs.
- Validates: trusted Telegram bot, `t2_` grammar, filename/code agreement, exact inventory `1-8,10-30`.

- [ ] **Step 1: Decode and validate all source PNGs**

Use `zxing-cpp` to decode every source PNG. Reject any unexpected filename,
bot username, start-parameter format, duplicate code/signature pair, filename
mismatch, or inventory mismatch. Do not print the resulting configuration line.

- [ ] **Step 2: Prove the current deployment rejects representative stickers**

POST the exact decoded entries for tables `1`, `10`, and `30` to
`/api/tables/resolve`. Expected before deployment: HTTP 400 `Invalid table QR`.

- [ ] **Step 3: Save the validated line as a protected temporary deployment input**

Write exactly one newline-terminated environment assignment with mode `600`.
Record only pair count and source payload hashes in logs; do not display access
tokens returned by successful resolver calls.

### Task 3: Push, verify, and deploy the backend-only hotfix

**Files:**
- Update on `home`: `/home/khajiev13/apps/restaurant-mini-app/.env`
- Preserve on `home`: timestamped mode-600 `.env` backup.

**Interfaces:**
- Consumes: exact tested commit and 29-pair compatibility configuration.
- Produces: healthy production backend that resolves printed stickers.

- [ ] **Step 1: Push the hotfix branch and verify exact-SHA CI**

Push `codex/printed-qr-compat`, then wait for the CI workflow attached to that
exact commit. Stop before production mutation if CI fails or is absent.

- [ ] **Step 2: Back up and update production configuration safely**

On `home`, create a timestamped mode-600 `.env` backup. Replace an existing
`TABLE_QR_COMPAT_SIGNATURES` line or append it once from the protected temporary
input. Validate that exactly one non-empty setting exists without printing it.

- [ ] **Step 3: Pin the production checkout to the tested commit**

Fetch the branch, detach at the exact CI-passing SHA, confirm a clean tracked
tree, and verify the `.env` remains mode `600`.

- [ ] **Step 4: Build and recreate only the backend**

Run:

```bash
docker compose build backend
docker compose up -d --no-deps --force-recreate backend
```

If Docker-only DNS fails with the previously identified bridge overlap, rebuild
only the backend with `docker build --network host` and then recreate it. Do not
restart other services.

- [ ] **Step 5: Verify production behavior**

Require all of the following:

- local and public `/healthz` and `/api/health` return HTTP 200;
- exact printed entries for tables `1`, `10`, and `30` return HTTP 200 and their
  matching safe `manual_code`/`table_title`;
- a one-character signature mutation returns HTTP 400;
- the backend is healthy with restart count zero;
- PostgreSQL, frontend, Caddy, Cloudflare, and BitAgent identities/status remain
  unchanged.

- [ ] **Step 6: Update `prod` only after production acceptance**

Fast-forward `origin/prod` to the exact deployed hotfix SHA only when the remote
tip still equals the pre-deployment candidate. Do not force-push.

- [ ] **Step 7: Roll back if any acceptance check fails**

Restore the `.env` backup, detach the checkout at the previous SHA, rebuild and
recreate only the backend, then verify health and the expected pre-fix HTTP 400
behavior. Preserve failure logs without secret values.
