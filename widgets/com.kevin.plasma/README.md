# Plasma Widget

An ambient animated background — a moving lava-lamp / plasma field. Pure Canvas 2D, self-contained (no data, no network, no daemon), so it runs anywhere and is safe in the sandbox.

## Modes (setting: **Style**)

- **lava** (default) — rising/falling blurred metaballs, additively blended: a lava lamp.
- **plasma** — the classic demoscene sine-interference field, smoothly palette-ramped.
- **aurora** — drifting vertical light curtains.

## Palettes (setting: **Palette**)

`tokyo` (indigo/violet, matches the cockpit), `sunset` (pink/orange), `ocean` (teal), `acid` (green/yellow), `mono` (greyscale). **Speed** is 10–300 (100 = default).

Sizes from 2×1 up to 8×2; it fills whatever cell it's in and adapts blob count to width.

## Notes

- Renders at up to 2× device pixels, ~60fps; the plasma mode computes a low-res field and scales it up so it stays cheap even at 2560×720.
- No settings changes need a restart — adjust Style/Palette/Speed in Admin → Widgets → Plasma.
- Files: `manifest.json`, `index.html` only.
