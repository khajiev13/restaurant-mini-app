# Home Host Clean Cutover Design

**Goal:** Run the restaurant Mini App on SSH host `home`, using the latest
verified `origin/prod` source and a fresh PostgreSQL database, without depending
on SSH host `restaurant`.

## Current State

- `home` is reachable and already has Docker Compose, the restaurant source,
  provider configuration in `.env`, stopped restaurant containers, and an old
  PostgreSQL volume.
- The existing `home` checkout is an old, modified `prod` checkout at
  `fb9b8e5`; it must not be updated in place because doing so would mix local
  host edits with current production source.
- A refreshed local Git view identifies `cbd8213` as the current exact tip of
  both `origin/main` and `origin/prod`.
- The developer checkout at `02716f3` is divergent from `origin/prod` and is
  not a deployment candidate.
- `restaurant` is currently unreachable over SSH, and the public restaurant
  hostname returns Cloudflare HTTP 530.
- There are no active users and no production data needs to be retained. The
  new PostgreSQL instance must therefore start empty and initialize from the
  repository migrations/schema.

## Deployment Architecture

The cutover will replace the stopped `home` deployment with a clean checkout of
the exact `origin/prod` candidate. The existing `.env` supplies the external
AliPOS, Multicard, Telegram, Cloudflare, and map-provider configuration. Secret
values must never be printed. Configuration is validated by key presence and
runtime health only.

The existing source directory, `.env`, and PostgreSQL volume will be archived
before replacement. The archive is rollback material only; its database must
not be attached to the new stack. The old Compose containers and named data
volume will then be removed, a fresh checkout will take the canonical
`~/apps/restaurant-mini-app` path, and Docker Compose will create a new
PostgreSQL volume during startup.

Only the restaurant stack is in scope. Existing BitAgent files, containers,
volumes, services, and public hostname on `home` remain untouched.

## Release Flow

1. Refresh Git refs and record the exact `origin/prod` candidate SHA. The
   currently approved candidate is `cbd82133d4a00dc545e611bb04bd07519509454d`.
2. Confirm the candidate is the remote `prod` tip and that the source checkout
   contains no host-local modifications.
3. Create a timestamped recovery directory on `home` containing:
   - the existing source tree and its tracked diff;
   - a protected copy of `.env`;
   - a compressed, read-only archive of the old PostgreSQL volume;
   - the previous container and image identities without environment values.
4. Remove only the stopped restaurant Compose containers and old restaurant
   data volumes. Do not remove BitAgent resources or use a broad Docker prune.
5. Install a clean exact-`origin/prod` checkout at
   `~/apps/restaurant-mini-app`, restore `.env` with restrictive permissions,
   and validate all configuration keys required by the current source.
6. Generate only missing application-owned random secrets. Provider IDs,
   provider secrets, tokens, public URLs, and database credentials are reused
   from the protected configuration rather than guessed or rotated.
7. Build and start the full restaurant Compose stack. Use ordinary Docker build
   networking first; use host networking only if a bounded diagnostic confirms
   the known Docker-only DNS failure pattern.
8. Let PostgreSQL initialize from scratch, then confirm the current schema is
   present before exposing the application as healthy.
9. Start the Cloudflare connector from `home`, register the Telegram webhook
   once, and set the Telegram menu button to the established public URL.

## Old Host Isolation

The `restaurant` host is offline during the initial cutover, so it cannot serve
traffic at that time. SSH access will be retried during and after deployment.
When it becomes reachable, only its restaurant Compose stack and the restaurant
portion of its supervisor will be disabled. BitAgent and unrelated Windows/WSL
services will remain unchanged.

Until that cleanup succeeds, the old host must not be treated as permanently
decommissioned: if it powers on, its stored Cloudflare connector could rejoin
the tunnel. This residual condition is reported explicitly if it remains after
the cutover.

## Failure Handling and Rollback

- No public success claim is made until both local and public health checks pass.
- If build or startup fails before the public connector is healthy, keep the
  failed new stack stopped and preserve its logs without secret-bearing output.
- Restore the archived source directory and `.env` only if needed for diagnosis.
  The archived database is recovery evidence, not the default rollback target,
  because the approved deployment intentionally starts from scratch.
- Never delete unrelated volumes, run a broad Docker prune, print `.env`, rotate
  provider credentials, or change BitAgent to recover this application.

## Acceptance Criteria

- `home` has a clean checkout whose `HEAD` equals the recorded `origin/prod`
  candidate.
- The running backend and frontend images were built from that exact checkout.
- PostgreSQL uses a newly created volume and the expected current schema.
- `restaurant_postgres`, `restaurant_backend`, `restaurant_frontend`,
  `restaurant_caddy`, and `restaurant_cloudflared` are running and healthy with
  restart count zero after a bounded stability observation.
- `http://127.0.0.1:8080/healthz` and `/api/health` return HTTP 200 on `home`.
- `https://restaurant.labtutor.app/healthz` and `/api/health` return HTTP 200.
- Telegram reports the expected webhook URL, zero pending updates, and no last
  delivery error, without exposing the bot token.
- The Telegram menu button points to `https://restaurant.labtutor.app/`.
- A bounded backend log scan contains no startup, database, webhook, AliPOS, or
  Multicard error markers.
- BitAgent resources on `home` are unchanged.
- The old `restaurant` deployment is disabled, or its continuing unreachability
  and possible future tunnel reconnection are stated as the only remaining
  cutover risk.
