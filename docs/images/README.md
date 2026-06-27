# PartFolder 3D — Brand Assets

Transparent logo and icon assets, masked from the original ChatGPT concepts. One
consistent **flat** icon style is used in both modes (the dark variant is the same
flat mark recolored to a light slate so it keeps contrast on dark surfaces):

- **Dark mode** → flat icon recolored light + light-wordmark lockup (pops on dark surfaces).
- **Light mode** → flat navy icon + navy-wordmark lockup (pops on light surfaces).

Letter counters in the wordmark (a/o/d/e and the "3D" badge) are fully transparent.

## Brand colors

| Token | Hex | Use |
|-------|-----|-----|
| Teal (primary) | `#0FA4AB` | accent, calibration cube, "3D" badge |
| Navy (ink) | `#091D35` | flat icon body, light-mode wordmark, icon tiles |

## Files

| File | What | Where to use |
|------|------|--------------|
| `logo-horizontal-dark.png` | Icon + "PartFolder 3D", white wordmark | Headers/README on **dark** backgrounds |
| `logo-horizontal-light.png` | Icon + "PartFolder 3D", navy wordmark | Headers/README on **light** backgrounds |
| `logo-icon-dark.png` | Flat icon, light recolor (square, padded) | App nav / dark surfaces |
| `logo-icon-light.png` | Flat navy icon (square, padded) | App nav / light surfaces |
| `logo-icon-light-alt.png` | Alternate flat navy icon | Optional variant |
| `favicon.ico` | 16/32/48 tiled (light icon on navy tile) | Browser tab — visible on light **and** dark tabs |
| `favicon-16/32/48.png` | PNG favicons (tiled) | `<link rel="icon">` |
| `favicon-transparent-32.png` | Transparent flat-navy favicon | Light-only contexts |
| `apple-touch-icon.png` | 180×180, light icon on navy rounded tile (opaque) | iOS home screen |
| `icon-192.png`, `icon-512.png` | Transparent PWA icons (flat navy) | `manifest.json` `"purpose": "any"` |
| `icon-512-maskable.png` | Full-bleed navy tile + light icon | `manifest.json` `"purpose": "maskable"` |

## GitHub README (auto dark/light)

```html
<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="docs/images/logo-horizontal-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/images/logo-horizontal-light.png">
  <img alt="PartFolder 3D" src="docs/images/logo-horizontal-light.png" width="420">
</picture>
```

## App `<head>` (when the frontend exists)

```html
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json">
```

`manifest.json` icons:

```json
"icons": [
  { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
  { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" },
  { "src": "/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
]
```

> When the frontend is scaffolded, copy the favicon/app-icon files into `frontend/public/`.
> Originals live in `private_data/images/` (kept out of the published app).
