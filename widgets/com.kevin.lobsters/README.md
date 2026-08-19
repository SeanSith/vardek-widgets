# Lobsters Widget

The [lobste.rs](https://lobste.rs) front page on your panel: stories with score, tags, comments, domain, age, and submitter, in two columns. **Tap a story** to open the article (or the discussion, for text posts); **tap its comments** to open the Lobsters thread. Both open in your Mac's browser.

Lobsters' signature **tags** are shown as chips — topic tags in crimson, meta tags (ask/show/meta/…) in grey.

Sizes: **8×2 / 6×2** (two columns), **4×2 / 3×2** (single column, scrollable), **4×1** (compact). Refreshes every 5 minutes.

## How it works — no daemon

Declares `https://lobste.rs/**` in `permissions.proxy` and fetches the public JSON API (`hottest.json` / `newest.json`) with `xemd.proxy.fetch` through Vardek's proxy — one request per refresh. Taps use `xemd.openLink`. Nothing to install or run. (Same pattern as the Hacker News widget.)

## Settings

| Setting | Default | Description |
|---|---|---|
| **Feed** | `hottest` | `hottest` or `newest`. |
| **Stories to show** | 14 | 1–25. |

## Notes

- Works only inside the Vardek dashboard (the proxy is relayed by the runtime); opening `index.html` alone just spins.
- Offline: keeps the last good list and marks the header "offline".
- Files: `manifest.json`, `index.html` only.
