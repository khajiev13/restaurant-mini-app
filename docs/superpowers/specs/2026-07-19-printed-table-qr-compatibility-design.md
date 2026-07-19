# Printed Table QR Compatibility Design

**Date:** 2026-07-19

**Status:** Approved by the user on 2026-07-19

## Problem

The 29 table stickers already printed and attached in the restaurant contain
signed Telegram Mini App start parameters in the form
`t2_<table-number>_<signature>`. They were generated and verified before the
restaurant application moved to the `home` host. During that cutover a new
`TABLE_ACCESS_SECRET` was created. The current backend therefore rejects the
printed signatures as `Invalid table QR`, although entering the same table
number manually still resolves correctly.

The stickers cannot be replaced. The application must restore compatibility
without accepting guessed or modified QR parameters.

## Chosen Approach

Keep normal HMAC verification as the primary path. If and only if that check
fails for a syntactically valid `t2_` parameter, compare the supplied signature
against a deployment-configured allowlist for the same normalized table code.
The allowlist contains the exact code/signature pairs decoded from the 29
printed production QR PNGs.

The compatibility list is configuration rather than repository data because it
belongs to this restaurant's physical sticker deployment. QR signatures are
public values printed on tables, not credentials. The current
`TABLE_ACCESS_SECRET` remains the signer for future manifests and QR codes.

## Configuration Contract

Add `TABLE_QR_COMPAT_SIGNATURES`, an optional comma-separated string of exact
`<code>:<12-character-base64url-signature>` entries. Empty configuration means
no compatibility entries.

Configuration parsing must fail closed:

- codes use canonical numeric form: `0` or a non-zero digit followed by at most
  five digits;
- signatures contain exactly 12 URL-safe base64 characters;
- an exact code/signature pair cannot appear twice;
- malformed or empty entries raise a startup configuration error;
- more than one historical signature for a code is allowed so a future
  controlled migration does not require a new format.

## Resolution Flow

1. Parse the `t2_` parameter with the existing strict regular expression.
2. Compute and constant-time compare the signature using the current
   `TABLE_ACCESS_SECRET`.
3. If current verification fails, constant-time compare only against configured
   compatibility signatures for that exact table code.
4. Accept the table code when either check succeeds.
5. Reject malformed parameters, unknown signatures, and a valid signature
   replayed under a different table code.
6. Preserve existing legacy `t_` behavior unchanged.

Manual table-number entry, table-directory resolution, access-token issuance,
AliPOS identifiers, checkout, and ordering behavior are unchanged.

## Deployment

Decode the existing source PNGs and build the configuration line without
printing secrets. Back up the production `.env`, add the compatibility setting,
deploy the exact tested backend commit, and recreate only the backend service.
Do not rebuild or restart PostgreSQL, frontend, Caddy, Cloudflare, or BitAgent.

## Verification

Automated tests prove:

- current HMAC signatures still work;
- an exact configured printed signature works;
- the same signature cannot select a different code;
- unknown and malformed entries fail closed;
- legacy `t_` QR behavior is unchanged.

Release verification must confirm:

- the full backend test suite and Ruff pass;
- production health remains HTTP 200;
- at least tables `1`, `10`, and `30` resolve from their exact printed QR
  payloads to the matching safe table title/code;
- an altered signature still returns HTTP 400;
- backend restart count remains zero after a bounded observation.

## Rollback

Restore the timestamped `.env` backup, return the production checkout to the
previous exact SHA, rebuild/recreate only the backend, and repeat the health and
negative QR checks. No database rollback is required.
