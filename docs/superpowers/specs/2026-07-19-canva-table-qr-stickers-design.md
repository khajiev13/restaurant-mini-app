# Canva Table QR Stickers Design

## Objective

Create a compact, print-ready Canva design for OLOT SOMSA table ordering. The
design will use the existing production QR PNGs without modifying their encoded
data or quiet zones. Each physical table receives one A7 portrait sticker with
its matching QR code, table number, and ordering instructions in Uzbek,
Russian, English, and Simplified Chinese.

## Approved Visual Direction

The approved direction is **Clean Minimal**:

- white background for maximum QR contrast and economical printing;
- compact OLOT SOMSA wordmark at the upper left;
- prominent table identifier at the upper right;
- large centered black-and-white QR code;
- one short orange divider below the QR;
- four centered instruction lines beneath the divider;
- no decorative imagery, gradients, shadows, textures, or marks around the QR.

The card uses only four colors:

- white: `#FFFFFF`;
- near-black: `#101314`;
- OLOT teal: `#07393D`;
- orange accent: `#F47B20`.

## Physical Format

- Finished size: A7 portrait, `74 × 105 mm`.
- QR display size: `62 × 62 mm`, including the QR PNG's original white quiet
  zone.
- Minimum safe margin: `4 mm` from the finished edge.
- Background: solid white to the page edge.
- The design must remain legible when printed at actual size and must not depend
  on lamination, metallic ink, or specialty paper.

If the print provider requires bleed, Canva may add a `3 mm` bleed using the
same solid white background. Bleed must not enlarge, crop, or reposition the QR
or move any content outside the approved finished-size safe area.

## Page Layout

From top to bottom, every page contains:

1. `OLOT SOMSA` at the upper left in teal, uppercase, compact bold sans serif,
   with restrained letter spacing.
2. `TABLE NN` at the upper right, where `NN` is the two-digit physical table
   number and the number is visually dominant.
3. The matching production QR PNG centered at `62 × 62 mm`.
4. A short centered orange divider.
5. The four ordering instructions, centered in this fixed order:
   - Uzbek: `Buyurtma berish uchun skanerlang`
   - Russian: `Сканируйте, чтобы заказать`
   - English: `Scan to order`
   - Simplified Chinese: `扫码点餐`
6. A very small, low-contrast footer: `OLOT SOMSA • TABLE ORDERING`.

The Uzbek and Russian lines use the same regular or medium weight. The English
line is bold and teal. The Chinese line is the largest instruction line and is
bold near-black. Typography must use Canva fonts that fully support Latin,
Cyrillic, and Simplified Chinese; a clean sans-serif family with a compatible
CJK fallback is required.

## QR Integrity Rules

The QR is functional content, not decoration. For every page:

- use the matching source PNG as supplied;
- preserve its square aspect ratio and original white quiet zone;
- do not crop, recolor, round, mask, distort, compress, stylize, or place a logo
  over it;
- do not place borders, text, icons, or background color inside its bounds;
- scale it uniformly to the approved physical size;
- keep it on a pure white background;
- verify the exported result decodes to the same deep link as the source PNG.

## Table Batch

The source directory is:

`/Users/khajievroma/.codex/visualizations/2026/07/18/019f743f-91fb-7643-91e8-416ef880162e/table-qr-pngs`

The Canva design contains exactly 29 pages, one for each supplied QR:

- tables `01` through `08`;
- tables `10` through `30`.

Table `09` is not present and must not be fabricated. Each page number, visible
table number, source filename, and embedded QR must agree exactly.

## Canva Production Workflow

1. Create one editable A7 portrait master page in Canva using the approved
   Clean Minimal layout.
2. Import the OLOT SOMSA branding asset only for palette/reference purposes;
   the final compact header uses the text wordmark rather than the large
   illustrative square logo.
3. Import the 29 production QR PNGs as image assets.
4. Duplicate the master to 29 pages.
5. Populate each page with the matching two-digit table number and QR asset.
6. Inspect page alignment, type fit, and QR size across the complete batch.
7. Export a print-ready PDF at actual A7 page size while preserving image
   quality.

The editable Canva design and the exported PDF are both deliverables.

## Verification

Before delivery:

- confirm the Canva design contains exactly 29 pages;
- confirm the visible sequence is `01–08, 10–30` with no duplicate or missing
  supplied table;
- confirm all four language lines are present and unchanged on every page;
- confirm every QR remains square, high-contrast, and unobstructed;
- render the exported PDF and visually inspect the first, middle, and last
  pages at actual proportions;
- independently decode every QR from the exported output and compare it with
  the corresponding source PNG;
- confirm the finished page size is `74 × 105 mm` and the QR is `62 × 62 mm`.

## Deliverables

- one editable Canva design containing all 29 table pages;
- one print-ready PDF containing all 29 A7 pages;
- a concise verification summary covering page count, table mapping, physical
  dimensions, and QR decode results.

## Out of Scope

- regenerating or changing QR payloads;
- creating a table `09` QR;
- changing physical table numbers, manual codes, AliPOS IDs, or application
  behavior;
- redesigning the OLOT SOMSA application or logo;
- adding languages beyond Uzbek, Russian, English, and Simplified Chinese.
