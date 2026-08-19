# Hacker News Widget

The Hacker News front page on your panel: ranked stories with points, comments, domain, age, and author, in two columns. **Tap a story** to open the article; **tap its comments** to open the HN discussion — both open in your Mac's browser.

Sizes: **8×2 / 6×2** (two columns), **4×2 / 3×2** (single column, scrollable), **4×1** (compact). Refreshes every 5 minutes.

## How it works — no daemon

Vardik widgets can reach any HTTPS host listed in the manifest's `permissions.proxy`, through Vardek's proxy. This widget declares `https://hn.algolia.com/**` and fetches the [HN Algolia Search API](https://hn.algolia.com/api) with `xemd.proxy.fetch` — one request returns the whole front page (title, url, points, comments, author, time). Taps use `xemd.openLink(url)`, which the daemon opens in the system browser. Nothing to install or run.

## Settings

| Setting | Default | Description |
|---|---|---|
| **Feed** | `top` | `top` (front page), `new` (newest), `ask` (Ask HN), `show` (Show HN). |
| **Stories to show** | 14 | 1–30. Two columns at 8×2, so 14 fills the panel. |

## Notes

- Stories with a big score (≥ 300) show their points in amber.
- If a fetch fails (offline), the widget keeps showing the last good list and marks the header "offline"; if it has never loaded, it shows the error.
- The widget only works inside the Vardek dashboard (the proxy is relayed by the dashboard runtime) — opening `index.html` on its own will just spin, since there's no runtime to relay the fetch.
- Files: `manifest.json`, `index.html` only.
