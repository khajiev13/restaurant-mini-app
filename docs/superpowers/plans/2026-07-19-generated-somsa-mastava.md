# Generated Somsa and Mastava Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current AliPOS Olot somsa and Mastava photos in all four A2 menu variants with approved photorealistic generated assets.

**Architecture:** Generate two square, project-local PNG assets with the built-in image generator, inspect them visually, and register them in the renderer's existing generated-food lookup. Keep live AliPOS data as the source for names and prices, then rebuild and verify all four A2 PDF and 300 DPI PNG deliverables.

**Tech Stack:** Built-in image generation, Python 3.12, ReportLab, Pillow, pypdf, pytest, Poppler

## Global Constraints

- Preserve the existing A2 portrait layout and four color palettes.
- Preserve every live AliPOS item name and price.
- Keep `1 kg Osh` on its current AliPOS photograph.
- Generated assets must be square PNGs with no text or watermark.
- Somsa must retain the source photo's triangular folded shape and expose meat-and-onion filling in one opened piece.
- Mastava must show tomato-toned broth, rice, beef, carrot, potato, and fresh herbs.
- Choy, kofe, drinks, sauces, and small sides remain typography-only.

---

### Task 1: Generate and validate the two food photographs

**Files:**
- Create: `frontend/src/assets/menu/olot-somsa-generated.png`
- Create: `frontend/src/assets/menu/mastava-generated.png`

**Interfaces:**
- Consumes: the approved visual direction in `docs/superpowers/specs/2026-07-19-alipos-a2-menu-design.md`
- Produces: two square PNG paths consumed by `GENERATED_FOOD_ASSETS`

- [ ] **Step 1: Generate Olot somsa with the built-in image generator**

  Use this prompt:

  ```text
  Use case: photorealistic-natural
  Asset type: square featured food photograph for a printed A2 Uzbek restaurant menu
  Primary request: an appetizing plate of traditional Olot somsa matching the triangular folded pastry shape in the restaurant source reference
  Scene/backdrop: dark polished wooden restaurant table with a subtle Uzbek textile at the edge
  Subject: several golden triangular folded samsa pastries arranged naturally on a blue-and-white Uzbek ceramic plate; one pastry opened cleanly to show juicy diced beef, onion, and seasoning
  Style/medium: premium photorealistic restaurant food photography, natural textures
  Composition/framing: close three-quarter angle, entire plate visible, centered, square crop with safe margin
  Lighting/mood: warm soft side light, appetizing highlights, gentle steam
  Constraints: preserve recognizable triangular Olot somsa form; no sauces dominating the dish; no text, logo, hands, people, or watermark
  ```

- [ ] **Step 2: Generate Mastava with the built-in image generator**

  Use this prompt:

  ```text
  Use case: photorealistic-natural
  Asset type: square featured food photograph for a printed A2 Uzbek restaurant menu
  Primary request: a rich authentic Uzbek mastava soup presented as premium restaurant food photography
  Scene/backdrop: dark polished wooden restaurant table with a subtle Uzbek textile at the edge
  Subject: tomato-toned broth in a blue-and-white Uzbek ceramic bowl, clearly visible rice grains, small tender beef pieces, diced carrot and potato, topped with fresh dill and cilantro; light steam
  Style/medium: premium photorealistic restaurant food photography, natural textures
  Composition/framing: close three-quarter angle, entire bowl visible, centered, square crop with safe margin
  Lighting/mood: warm soft side light, appetizing highlights
  Constraints: recognizable soup rather than lagman; no noodles; no text, logo, hands, people, or watermark
  ```

- [ ] **Step 3: Inspect both generated outputs**

  Open both PNGs at high detail. Accept only if the subject is accurate, the food texture is realistic, the square crop leaves safe margins, and no text or watermark appears.

- [ ] **Step 4: Commit the approved assets**

  ```bash
  git add frontend/src/assets/menu/olot-somsa-generated.png frontend/src/assets/menu/mastava-generated.png
  git commit -m "feat: add generated somsa and mastava photos"
  ```

### Task 2: Register generated Somsa and Mastava assets

**Files:**
- Modify: `scripts/generate_alipos_a2_menu.py`
- Modify: `scripts/test_generate_alipos_a2_menu.py`

**Interfaces:**
- Consumes: `frontend/src/assets/menu/olot-somsa-generated.png` and `frontend/src/assets/menu/mastava-generated.png`
- Produces: `GENERATED_FOOD_ASSETS: dict[str, Path]` entries for `olot somsa` and `mastava`

- [ ] **Step 1: Write the failing lookup test**

  Add assertions that `_generated_food_asset({"name": "Olot somsa"})` and `_generated_food_asset({"name": "Mastava"})` resolve to the two new project assets.

- [ ] **Step 2: Run the focused test and verify it fails**

  ```bash
  PYTHONPATH=/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages:scripts backend/.venv312/bin/python3 -m pytest scripts/test_generate_alipos_a2_menu.py -q
  ```

  Expected: failure because the two names are not yet registered.

- [ ] **Step 3: Add the minimal renderer mapping**

  Add these entries to `GENERATED_FOOD_ASSETS`:

  ```python
  "olot somsa": ROOT / "frontend/src/assets/menu/olot-somsa-generated.png",
  "mastava": ROOT / "frontend/src/assets/menu/mastava-generated.png",
  ```

- [ ] **Step 4: Run tests and lint**

  ```bash
  PYTHONPATH=/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages:scripts backend/.venv312/bin/python3 -m pytest scripts/test_generate_alipos_a2_menu.py -q
  backend/.venv312/bin/ruff check scripts/generate_alipos_a2_menu.py scripts/test_generate_alipos_a2_menu.py
  ```

  Expected: all renderer tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the renderer change**

  ```bash
  git add scripts/generate_alipos_a2_menu.py scripts/test_generate_alipos_a2_menu.py
  git commit -m "feat: use generated somsa and mastava photos"
  ```

### Task 3: Rebuild and verify all deliverables

**Files:**
- Regenerate: `output/pdf/olot-somsa-menu-a2-teal-gold.pdf`
- Regenerate: `output/pdf/olot-somsa-menu-a2-burgundy-cream.pdf`
- Regenerate: `output/pdf/olot-somsa-menu-a2-black-copper.pdf`
- Regenerate: `output/pdf/olot-somsa-menu-a2-ivory-green.pdf`
- Regenerate: matching `.png` previews for all four PDFs

**Interfaces:**
- Consumes: live AliPOS composition and availability, the renderer, and all five featured food images
- Produces: four one-page A2 PDFs and four 4961 x 7016 PNG previews

- [ ] **Step 1: Rebuild the four PDFs from live AliPOS data**

  ```bash
  set -a; source .env; set +a
  PYTHONPATH=/Users/khajievroma/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages:backend:scripts backend/.venv312/bin/python3 scripts/generate_alipos_a2_menu.py
  ```

  Expected: four lines reporting 54 rendered items.

- [ ] **Step 2: Render each PDF to a 300 DPI PNG**

  Use the bundled Poppler `pdftoppm` executable with `-f 1 -singlefile -r 300 -png` for each palette.

- [ ] **Step 3: Inspect all four previews**

  Confirm the new Somsa and Mastava images appear in every palette, all text is readable, and no content is clipped or overlapped.

- [ ] **Step 4: Verify live content and dimensions**

  Compare extracted PDF text with the current AliPOS composition. Require four categories, 54 unique item IDs, `missing_names=0`, `missing_prices=0`, one 1190.55 x 1683.78-point page per PDF, and one 4961 x 7016 PNG per palette.
