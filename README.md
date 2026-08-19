# Vardek Widgets

A collection of **105 custom widgets** for [Vardek](https://github.com/jorgelaurel/Vardek) — the
Mac-native widget dashboard for the [Corsair XENEON EDGE](https://www.corsair.com/us/en/explorer/diy-builder/accessories/xeneon-edge-widgets-explained/)
(2560×720 touchscreen). Vardek re-implements iCUE's Windows-only widget layer for macOS, and it
runs the same sandboxed HTML/JS widgets.

These range from live data boards (weather, aviation, finance, transit, space) to clocks, games,
system monitors, and a large gallery of generative-art screensavers — all sandbox-friendly and
responsive across every widget size the 8×2 grid supports.

## 🖼️ Showcase

A full visual gallery lives in the `docs/` folder — every widget, shown at multiple sizes, with a
click-to-zoom modal. Enable GitHub Pages on the `docs/` folder to browse it online.

## Install

Vardek loads widgets from `~/Library/Application Support/Vardek/widgets/`. Symlink (or copy) the
widgets you want:

```bash
git clone https://github.com/kevinelliott/vardek-widgets.git
cd vardek-widgets
# symlink every widget into Vardek's widget folder:
for d in widgets/com.kevin.*; do
  ln -sfn "$PWD/$d" "$HOME/Library/Application Support/Vardek/widgets/$(basename "$d")"
done
# then restart Vardek
```

Some widgets ship with a small local **daemon** (a Python `LaunchAgent`) that prepares data or
downloads images into the widget's own folder — because sandboxed widgets can't reach the
filesystem or arbitrary hosts directly. Those widgets include a `README.md` and a `*.plist`.

## Credits

- Built for **Vardek** by Jorge Laurel — <https://github.com/jorgelaurel/Vardek>
- For the **Corsair XENEON EDGE** — <https://www.corsair.com/us/en/explorer/diy-builder/accessories/xeneon-edge-widgets-explained/>
- Widgets & showcase by [@kevinelliott](https://github.com/kevinelliott)

## License

MIT
