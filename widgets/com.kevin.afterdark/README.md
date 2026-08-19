# After Dark Widget

The classic **After Dark** screensavers of the early '90s, recreated in CSS by [Bryan Braun](https://github.com/bryanbraun/after-dark-css) (original After Dark © Berkeley Systems). Three of them, selectable:

- **Flying Toasters** — the icon. Winged toasters and toast drift across the night sky.
- **Warp** — hyperspace starfield zooming toward you.
- **Globe** — the spinning Earth bouncing around the screen.

Setting **Screensaver**: `toasters` (default), `warp`, `globe`, or `cycle` (rotate through all three every **Cycle every N min** minutes, default 3).

## How it works

Pure HTML/CSS (Bryan Braun's animations, adapted). The original sprite art — `toaster-sprite.gif`, `toast1.gif`, `stars1–4.png`, `globe_240.jpg` — lives in this widget's `img/` folder and is served same-origin by the Vardek daemon, which the widget's CSP allows. No script beyond switching which saver is visible; no data, no network.

## Notes

- This is a personal homage running on your own panel. Credit: Bryan Braun's after-dark-css (MIT-spirited, source-available); After Dark is a Berkeley Systems trademark.
- Files: `manifest.json`, `index.html`, `img/` (6 sprites), `README.md`.
