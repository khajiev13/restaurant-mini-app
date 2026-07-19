# AliPOS A2 Restaurant Menu Design

## Goal

Create one print-ready A2 portrait menu for OLOT SOMSA using the current AliPOS
menu composition. The result must look like a real restaurant menu while keeping
the source item names and prices accurate.

## Source of truth

- Menu composition: live AliPOS `GET /api/Integration/v1/menu/{restaurantId}/composition`
- Availability: live AliPOS `GET /api/Integration/v1/menu/{restaurantId}/availability`
- Brand artwork: `frontend/src/assets/logo.png`
- Existing category artwork: `frontend/src/assets/categories/`
- Product photography: current image URLs returned by AliPOS

The live read on 2026-07-19 returned four categories and 54 items. The
availability response contained no item or modifier restrictions. Item IDs and
credentials are not printed or embedded in the deliverable.

## Format

- Finished size: A2 portrait, 420 x 594 mm
- Print rendering: 300 DPI
- Deliverables: print PDF and full-resolution PNG preview
- Safe margin: at least 15 mm
- No bleed-dependent content; the design remains complete if printed without
  full-bleed trimming

## Visual direction

Use the established OLOT SOMSA identity from the logo: deep teal as the base,
warm orange for accents, and gold for headings and price emphasis. The design
should feel like a professionally printed Uzbek restaurant menu, not a mobile
screen or app mockup.

The logo anchors the header. A restrained set of real AliPOS product photos may
appear in the header or category bands. Do not synthesize or substitute fake
food photos. Where no product photograph exists, rely on typography, dividers,
and the existing category artwork.

## Content hierarchy

1. OLOT SOMSA logo and `MENYU` title
2. Four clearly separated menu sections:
   - Ovqatlar
   - Somsa
   - Choy va kofe
   - Ichimliklar
3. Item name on the left and price on the right, with dot leaders or a clear
   alignment system
4. Prices formatted in Uzbek so'm, using grouped thousands

All 54 AliPOS items must appear exactly once. The presentation may normalize
capitalization and obvious punctuation for readability, but it must not rename
items, invent descriptions, change category membership, or alter prices.

## Layout

Use a tall A2 poster with a compact branded header and a four-column content
grid. The large Ovqatlar section receives two columns because it contains most
items. Somsa, Choy va kofe, and Ichimliklar use the remaining columns and lower
continuations as needed. Section headings, spacing, and thin ornamental rules
must make the reading order unambiguous.

Images are supporting accents, not repeated cards for every item. This keeps all
54 entries legible at normal A2 viewing distance and avoids implying that a
generic image belongs to a specific dish.

## Accuracy and fallback rules

- Preserve every live AliPOS price.
- Do not infer ingredients or serving sizes from item names.
- Do not mark items unavailable because the live availability arrays were empty.
- If a remote product image cannot be downloaded, omit it and retain the
  typography-only layout.
- If a displayed source name is ambiguous or misspelled, only capitalization
  and punctuation may be cleaned up; no semantic correction is allowed.

## Verification

- Compare the rendered menu against the live snapshot: four sections, 54 unique
  entries, and matching prices.
- Render the PDF to an image and inspect it for clipping, overlap, low-contrast
  text, stretched photography, and unreadably small type.
- Verify the PDF page size is A2 portrait and the preview is full resolution.
- Deliver both files without modifying AliPOS or production application data.
