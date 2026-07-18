# Raw Table QR PNG Package Design

**Date:** 2026-07-18

**Status:** Approved on 2026-07-18

## Goal

Deliver one folder of plain, print-ready QR-code PNG files that the restaurant
owner can place into a separate visual design. Scanning any file must open the
OLOT SOMSA Telegram Mini App with the correct live table context so the customer
can begin ordering.

## Relationship to the Numeric Table-Code Design

This specification narrows only the asset presentation and package format from
the approved numeric table-code design. The existing backend requirements remain
unchanged: customer table numbers come from the trailing digits in current AliPOS
table titles, new links use signed `t2_` start parameters, legacy signed links
remain compatible, and AliPOS UUIDs stay server-side.

Final QR files must be generated from the deployed admin manifest after the
numeric table-code release is verified. The generator must never invent a table
identifier, signature, or deep link locally from remembered values.

## Live Table Set

The read-only AliPOS directory was checked twice on 2026-07-18. It contained one
hall and 29 tables with customer numbers:

```text
1-8, 10-30
```

Table `9` is intentionally absent because waiters could confuse `6` and `9`.
Intentional gaps are valid. Generation always follows the current deployed
manifest rather than hardcoding a continuous range, and no file is created for a
number that is absent from that manifest.

## Output Contract

The delivered folder contains exactly one PNG per current manifest row and no
other files. It contains no PDF, ZIP, CSV, JSON, README, logo, table label, hall
name, instruction, or language text.

Files use zero-padded, naturally sortable names:

```text
table-01.png
table-02.png
...
table-08.png
table-10.png
...
table-30.png
```

No filename contains an AliPOS UUID, bearer token, access token, or other
internal identifier.

## Image Contract

Each PNG contains only a standard black QR symbol on an opaque white square:

- no embedded logo, caption, number, frame, color, transparency, or decoration;
- error-correction level Q;
- a white quiet zone at least four modules wide on every side;
- integer module scaling with nearest-neighbor rendering;
- at least 1200 pixels on each side so the owner can downscale it safely;
- lossless PNG encoding without resampling artifacts.

The owner may add the QR image to a separate four-language design. That later
design must preserve the complete white quiet zone and must not crop, stretch,
overlay, blur, or recolor the QR symbol.

## Data Flow

1. Confirm the public frontend and API health endpoints return HTTP `200`.
2. Confirm the deployed backend supports numeric table codes and signed `t2_`
   links.
3. Fetch the admin-only live table manifest without printing or persisting the
   administrator JWT.
4. Validate that every manifest code is numeric and unique; gaps are allowed.
5. Generate one raw PNG from each manifest row's exact `deep_link`.
6. Decode every PNG and compare the decoded text byte-for-byte with that
   manifest row's `deep_link`.
7. Resolve every signed link through the deployed API and compare only the safe
   table number and title with the corresponding manifest row.
8. Copy only the verified PNG files into the delivered folder.

If health checks fail, the deployed release is stale, the manifest is ambiguous,
any QR fails to decode, or any resolved table differs from its manifest row, no
folder is delivered.

## Verification and Safety

Automated verification covers:

- rejection of duplicate, non-numeric, missing, or mismatched manifest codes;
- acceptance of the intentional missing number `9`;
- one output PNG for every and only every manifest row;
- exact filename-to-table-number mapping;
- image mode, quiet zone, minimum dimensions, and lossless output;
- byte-for-byte QR decode equality with the signed deep link;
- deployed resolver agreement for every table;
- absence of credentials, tokens, UUIDs, and non-PNG files from the output
  folder.

The workflow performs no AliPOS order creation, cancellation, booking, or table
mutation. A controlled Telegram scan smoke test may open one verified link, but
it must not place an order without separate authorization.

## Success Criteria

- The delivered folder contains 29 PNG files when the live manifest remains
  `1-8, 10-30`, with no `table-09.png`.
- Every PNG independently decodes to its exact signed Telegram deep link.
- Every link resolves to the table number represented by its filename.
- A customer scan opens the correct OLOT SOMSA table context.
- The folder contains no design copy or supporting artifacts, leaving all visual
  composition to the restaurant owner.
