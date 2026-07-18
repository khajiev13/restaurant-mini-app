# Production Webhook Startup Recovery Design

**Date:** 2026-07-18

**Status:** Approved in conversation on 2026-07-18

## Goal

Restore the current production application at `restaurant.labtutor.app` on the
`restaurant` host, release the existing `origin/prod` functionality, and keep
the restaurant backend healthy across container restarts without including the
numeric table-code or QR-asset work.

## Confirmed Production State

The release base is the exact `origin/prod` commit
`ccaa757e49b83b4024d34c42ef4e5d07a3caa467`. The numeric table-code and QR-asset
branch at `527d3c9` is explicitly excluded.

The live host is in a partial deployment state:

- the production checkout is detached at `81489d1`;
- the restaurant backend image was built from the newer production line;
- `restaurant_backend` repeatedly restarts;
- the restaurant frontend, Caddy, PostgreSQL, and Cloudflare tunnel remain up;
- the separate BitAgent stack remains healthy;
- the Telegram webhook is already configured for the expected public URL, has
  no pending updates or delivery error, and the production webhook secret has a
  valid shape;
- backend logs show one Uvicorn worker completing startup while another worker
  fails during Telegram webhook registration.

The failure is caused by registering the same Telegram webhook independently
from both Uvicorn worker startup hooks. The current fail-closed behavior turns a
redundant or concurrent registration failure in either worker into a complete
backend restart.

## Scope

This recovery includes:

- a surgical webhook startup ownership fix on top of the exact production base;
- complete local and CI verification of the production candidate;
- reconciliation of the detached production checkout to the exact candidate;
- a backend-only production image rebuild and container recreation;
- verification of existing customer, staff, and administrator behavior;
- compatibility with the existing Windows scheduled task, WSL supervisor,
  Docker Compose stack, Caddy origin, and Cloudflare tunnel.

This recovery excludes:

- every commit unique to `codex/numeric-table-codes-qr-assets`;
- live QR manifest or printable asset generation;
- database schema additions or new migrations;
- frontend feature changes;
- secret rotation;
- PostgreSQL, Caddy, tunnel, or BitAgent rebuilds;
- unrelated refactoring or infrastructure tuning.

## Chosen Approach

Telegram webhook registration becomes a single container-entrypoint operation.
The backend container performs the existing secret-safe, fail-closed
registration once and only then replaces the entrypoint process with the
existing two-worker Uvicorn command. FastAPI workers no longer register the
webhook during application startup.

This keeps the intended security property from the production branch: when a
webhook secret is configured, a failed registration prevents the candidate
backend from becoming healthy. It removes only the accidental multi-worker
duplication. Both Uvicorn workers and all existing application behavior remain
otherwise unchanged.

Two alternatives were rejected:

- reducing Uvicorn from two workers to one would avoid the immediate race but
  would reduce concurrency and leave external provider setup coupled to every
  application worker startup;
- rebuilding the complete stack would recreate healthy services and expand the
  production failure surface without helping the backend-only root cause.

## Application Design

### Webhook service

The existing webhook inspection, payload construction, provider call,
validation, and secret-safe logging move from `backend/app/main.py` into a
focused webhook module. Its observable behavior remains unchanged:

- missing public URL or bot token is a no-op outside configured production;
- the expected URL is `<public-base>/api/webhooks/bot`;
- the configured secret is sent only in the provider request body;
- provider responses must have HTTP success and JSON `ok: true`;
- provider bodies, bot tokens, and webhook secrets are never logged;
- a configured-secret registration failure raises the existing sanitized
  `telegram_webhook_registration_failed` error;
- empty-secret failure remains non-fatal for development compatibility.

No Telegram secret value, provider response body, or new configuration value is
stored on disk.

### Container entrypoint

A small Python entrypoint performs these steps:

1. run the asynchronous webhook registration function exactly once;
2. if it succeeds or is a permitted no-op, replace the process with the current
   Uvicorn command and its two workers;
3. if fail-closed registration raises, exit non-zero without starting Uvicorn.

The Dockerfile starts this entrypoint instead of starting Uvicorn directly.
Using process replacement preserves Docker signal delivery and the existing
graceful shutdown behavior.

### FastAPI startup

`backend/app/main.py` no longer registers Telegram during FastAPI startup.
Payment recovery, provider reconciliation, expiry handling, middleware,
routers, and health endpoints are not changed.

## Runtime Data Flow

```text
Docker starts restaurant_backend
  -> Python container entrypoint
  -> one Telegram setWebhook request with current URL and secret
  -> validated provider success
  -> exec current two-worker Uvicorn command
  -> both FastAPI workers start without Telegram configuration writes
  -> backend health check succeeds
  -> existing Caddy and Cloudflare tunnel serve the API
```

Telegram continues to deliver updates to the same public endpoint with the same
secret header. The existing webhook route validates that header exactly as it
does on the production branch.

## Error Handling

The entrypoint retains fail-closed behavior for a configured production secret.
The container may restart according to the existing Compose policy, but there
is no second worker racing the registration request. Logs retain only the
existing sanitized failure category.

Deployment stops if the single-owner registration still fails. The operator
then checks provider reachability, non-secret configuration shape, and current
webhook status without printing secret values. The deployment must not weaken
webhook authentication, clear the secret, rotate credentials, or expose raw
provider responses as a recovery shortcut.

## Verification

### Automated verification

Tests must prove:

- the container entrypoint invokes webhook registration once before Uvicorn;
- Uvicorn is not executed when fail-closed registration raises;
- successful or permitted no-op registration executes the unchanged two-worker
  Uvicorn command;
- importing and starting the FastAPI app does not register the webhook;
- all existing webhook response, changed-secret, URL, allowed-update, and
  secret-safe logging tests continue to pass;
- the backend Docker image uses the new entrypoint;
- the complete backend test suite and Ruff pass;
- the complete frontend test, type-check, lint, and production-build gates pass
  against the exact candidate even though no frontend file changes.

No test may call the live Telegram API or use production credentials.

### Release verification

Before production changes, pin and record the exact pre-release production SHA,
candidate SHA, running image IDs, current database schema state, supervisor
state, and any deploy-watcher state. Verify that the candidate is the exact
production base plus only the approved recovery changes and this documentation.

The production database is checked against the four migrations already present
on `origin/prod`. No new migration is introduced. Any missing existing migration
is applied through its idempotent release procedure before the candidate backend
starts; table rows or customer data are never printed.

The exact candidate must pass repository CI before deployment. The Windows
scheduled task and any WSL deploy watcher are paused only for the bounded
cutover so they cannot race the manual checkout or backend recreation.

Production deployment then:

1. tags or otherwise records the current backend image for rollback;
2. fast-forwards the clean production checkout to the exact candidate SHA;
3. builds the backend image once;
4. recreates only `restaurant_backend` without rebuilding or recreating
   PostgreSQL, frontend, Caddy, Cloudflare, or BitAgent;
5. waits for the backend health check;
6. confirms the running container uses the candidate backend image;
7. resumes the existing supervisor and deploy watcher only after an equal-SHA
   no-op check.

Post-deployment checks cover:

- local `http://127.0.0.1:8080/healthz` and `/api/health`;
- public `https://restaurant.labtutor.app/healthz` and `/api/health`;
- the Telegram webhook URL, pending count, and delivery-error status without
  revealing credentials;
- a controlled customer authorization denial and controlled staff/admin read
  checks for the existing production routes;
- stable backend restart count and health over a bounded observation window;
- continued BitAgent public health;
- exact source SHA and immutable backend image identity.

## Rollback

Rollback uses the recorded pre-release backend image and pre-release checkout
SHA. If the candidate backend does not become healthy or any acceptance check
fails:

1. keep PostgreSQL, frontend, Caddy, tunnel, and BitAgent untouched;
2. restore the recorded backend image without rebuilding it;
3. reconcile the production checkout to the recorded rollback commit through a
   non-force production fast-forward or the repository's prepared rollback
   mechanism;
4. verify local and public health before resuming automation.

No rollback step deletes volumes, rotates secrets, force-pushes Git history, or
rebuilds an old image from a mutable checkout.

## Success Criteria

- `origin/prod` functionality plus only the webhook startup recovery is deployed.
- No numeric table-code or QR-asset commit is included.
- `restaurant_backend` is healthy and no longer restarts because of concurrent
  webhook registration.
- Exactly one webhook registration phase occurs per backend container start.
- Both Uvicorn workers start successfully.
- Existing customer, staff, and administrator routes retain their production
  authorization and read/write boundaries.
- PostgreSQL data, the healthy frontend, Caddy, Cloudflare tunnel, and BitAgent
  are preserved.
- Local and public restaurant health checks remain HTTP 200 throughout the
  bounded stability observation after cutover.
- The deployed checkout SHA and backend image match the tested candidate.
