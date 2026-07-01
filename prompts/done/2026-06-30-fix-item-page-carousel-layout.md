---
name: 2026-06-30-fix-item-page-carousel-layout
status: done
created: 2026-06-30
model: sonnet
completed: 2026-06-29
result: >
  Rewrote ImageCarousel in ItemPage.tsx: fixed-height (300px) main image,
  6-thumbnail controlled strip with ‹/› scroll arrows and page-number jump nav,
  auto-scroll of strip to keep active thumb visible, image counter overlay.
  Hero grid changed to auto-fit minmax(320px,1fr) for responsive stacking.
  Extracted buildCarouselPagerItems to carousel-utils.ts (7 unit tests added).
  tsc clean, vitest 221/221, vite build succeeded. Feature parity confirmed.
---

# Task: Fix the item page layout + image carousel (16+ thumbnails break the layout)

On the item page, the image area renders **all** images' thumbnails (16+), so the image block
takes the whole center and the details column gets squished. Rework the carousel + hero layout so
it's controlled and balanced.

## Desired behavior (owner)
- Show **one large default/active image** (sensible max-height, `object-fit: contain`, doesn't
  dominate the page).
- Below it, a **compact thumbnail strip showing ~5–6 thumbnails** with **left/right scroll arrows
  (‹ ›)** and a **jump nav like "1 2 3 4 … more"** (or dot/pager) to go directly to an image —
  NOT all 16 thumbnails rendered at once.
- The **details column stays readable** and is not shoved/squished by the image block.

## Where
- `frontend/src/pages/ItemPage.tsx` — the `ImageCarousel` component + the hero grid
  (`gridTemplateColumns: '1fr 1fr'` image|details). Keep the page's other sections intact.

## Requirements
- **Feature parity** — keep ALL existing carousel/image features: set-as-default, delete image
  (per-image), upload image, the **"Rendered"** badge on `source==='render'`, and any
  lightbox/zoom behavior. Active-image selection must sync with the thumbnail nav.
- Thumbnail strip: fixed height, horizontal; only ~5–6 visible; ‹ › scroll the strip; a pager to
  jump to any image (numbered + "more"/overflow, or pages of thumbnails). Active thumb highlighted.
- Layout: cap the main image height so the hero stays balanced; details column readable. Make it
  **responsive** — on narrow widths the image + details stack (image above details), and the strip
  stays usable.
- Aurora-styled (existing `--aurora-*` tokens + the page's button styles). NO new deps. Don't touch
  `frontend/src/pages/examples/`.

## Verify
- `cd frontend && npx tsc --noEmit` clean; `npx vitest run` passes; **and `npx vite build` MUST
  succeed**. Do NOT commit `dist/`. (If any carousel logic is cleanly unit-testable — e.g. the
  paging math — add a small test; don't force it for pure layout.)

## When done
1. Frontmatter; `git mv` to `prompts/done/`.
2. `docs/decisions.md`: the carousel/paging approach + layout caps.
3. **Do NOT commit/push/branch, NEVER `git add -A`.** Report back: file list; one-line `fix:`/
   `style:` commit message; tsc / vitest / **vite build** results; feature-parity confirmation
   (set-default, delete, upload, rendered badge, active sync); anything unverified (note visual
   needs a browser).
