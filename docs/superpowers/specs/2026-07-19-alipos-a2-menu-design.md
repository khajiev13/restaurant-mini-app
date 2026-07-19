# AliPOS A2 Restaurant Menu Design

## Goal

Create four print-ready A2 portrait menu color variants for OLOT SOMSA using the
current AliPOS menu composition. Every variant must keep identical content and
layout while the source item names and prices remain accurate.

## Source of truth

- Menu composition: live AliPOS `GET /api/Integration/v1/menu/{restaurantId}/composition`
- Availability: live AliPOS `GET /api/Integration/v1/menu/{restaurantId}/availability`
- Brand artwork: `frontend/src/assets/logo.png`
- Existing category artwork: `frontend/src/assets/categories/`
- Product photography: the approved generated photographs for Qovirma lagmon,
  Lag'mon, Olot somsa, and Mastava, plus the current AliPOS image for `1 kg Osh`

The live read on 2026-07-19 returned four categories and 54 items. The
availability response contained no item or modifier restrictions. Item IDs and
credentials are not printed or embedded in the deliverable.

## Format

- Finished size: A2 portrait, 420 x 594 mm
- Print rendering: 300 DPI
- Deliverables: four print PDFs and four full-resolution PNG previews
- Safe margin: at least 15 mm
- No bleed-dependent content; the design remains complete if printed without
  full-bleed trimming

## Visual direction

Use the established OLOT SOMSA identity from the logo: deep teal as the base,
warm orange for accents, and gold for headings and price emphasis. The design
should feel like a professionally printed Uzbek restaurant menu, not a mobile
screen or app mockup.

The logo anchors the header. The user approved a consistent generated-photo
style for `Qovirma lagmon`, `Lag'mon`, `Olot somsa`, and `Mastava`: traditional
Uzbek ceramic servingware on a dark wooden table, warm natural restaurant
lighting, realistic food texture, and a close three-quarter food-photography
composition. The `1 kg Osh` card retains its current AliPOS photograph. Choy,
kofe, suvlar, souslar, and small side items remain typography-only rows.

The generated OLOT somsa image must preserve the triangular folded pastry shape
shown by the restaurant's source photo, with appetizing golden blistering and
one opened piece showing the meat-and-onion filling. The generated Mastava image
must be a recognizable Uzbek tomato-toned rice soup with small beef pieces,
carrot, potato, and fresh herbs. Both assets are square, contain no text or
watermark, and leave enough margin for the existing rounded menu crop.

Produce these four palettes:

1. Deep teal with orange and gold
2. Burgundy with cream and warm bronze
3. Black with copper and warm ivory
4. Light ivory with traditional green and burnt orange

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

Images are supporting cards for four named main dishes: three with approved
generated photos and one with a verified AliPOS photo. The Somsa section uses a
fourth generated photo for `Olot somsa`. Images are not repeated for small
items. This keeps all 54 entries legible at normal A2 viewing distance and
avoids implying that a generic image belongs to a specific dish.

## Accuracy and fallback rules

- Preserve every live AliPOS price.
- Do not infer ingredients or serving sizes from item names.
- Do not mark items unavailable because the live availability arrays were empty.
- If the remote `1 kg Osh` product image cannot be downloaded, omit it and
  retain the typography-only layout. Generated project assets are local and
  must not fall back to the older AliPOS Somsa or Mastava photos.
- If a displayed source name is ambiguous or misspelled, only capitalization
  and punctuation may be cleaned up; no semantic correction is allowed.

## Verification

- Compare the rendered menu against the live snapshot: four sections, 54 unique
  entries, and matching prices.
- Render the PDF to an image and inspect it for clipping, overlap, low-contrast
  text, stretched photography, and unreadably small type.
- Verify the PDF page size is A2 portrait and the preview is full resolution.
- Deliver both files without modifying AliPOS or production application data.
