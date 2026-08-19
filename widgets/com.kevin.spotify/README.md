# Now Playing (Spotify / Music) Widget

Current track with a big album cover, artist + title + album, a live progress bar, and transport controls (previous / play-pause / next). The accent color and the ambient glow are pulled from the album art, so the widget takes on the record's palette.

Works with **Spotify** and **Apple Music** — whichever is playing.

Sizes: **8×2 / 6×2** (art + full info + controls), **4×2 / 3×2** (narrower), **4×1 / 3×1** (compact: art, title, play/skip).

## How it works — no daemon needed

Vardek has a built-in `media` data channel (its `MediaProvider` runs JXA against Spotify/Music). This widget just declares `"subscriptions": ["media"]` and:

- **Receives** `{title, artist, album, artworkDataURL, positionSec, durationSec, state, source}` — the artwork arrives as a base64 `data:` URI, so it renders inside the sandboxed iframe with no network.
- **Controls** via `Vardek.sendCommand("media", "previous" | "playPause" | "next")` — the daemon runs the corresponding player action.

Position is interpolated locally between frames so the progress bar moves smoothly; play/pause is optimistic (the icon flips immediately, then the next frame confirms).

Nothing to install or run — it's purely the widget. If neither app is playing it shows a "Nothing playing" state.

## Settings

| Setting | Default | Description |
|---|---|---|
| **Tint accent from album art** | on | Sample the cover for the accent + glow. Off keeps Spotify green. |
| **Show progress bar** | on | Hide the position/duration bar. |

## Notes

- Controls use Vardek's native media channel (not the Macro Pad action system), so this widget coexists with Agent Control fine.
- Artwork for Apple Music is fetched by the daemon and cached; the first track after launch may show the placeholder for a moment.
- Files: `manifest.json`, `index.html` only.
