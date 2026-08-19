# Sun Clock Widget

A 24-hour radial sun clock (inspired by [sunclock.net](https://sunclock.net)): the ring is colored by the **real position of the sun** through the day for your location — deep night, astronomical/nautical/civil twilight, the sunrise/sunset bands, golden hour, and full daylight — with a glowing sun (or moon, at night) riding the ring at the current time. The center shows the clock, location, date, and day length; wider sizes add a panel with sunrise, solar noon, sunset, and the next upcoming event.

## Tuned for every size

- **8×2 / 6×2** — large dial + detail panel, centered as a group.
- **4×2 / 3×2 (wide)** — dial + panel.
- **2×2 / squarish** — dial centered with the clock readout inside; sunrise/sunset marked on the ring.
- **rows = 1 / very short cells** — automatically switches to a horizontal day-arc bar with a moving sun and sunrise/sunset ticks.

The dial size, type scale, marker labels, and layout all recompute on resize, so it stays legible from the full panel down to a 2-wide tile.

## How it works

Pure Canvas 2D, self-contained — no data, no network, no daemon. Sun positions come from the **NOAA solar equations** computed in the browser for the configured latitude/longitude and the Mac's current timezone (DST-aware). The ring colour at each minute is the actual sun altitude at that time mapped to a sky palette, so the twilight bands are physically correct. Verified against published tables (San Francisco: sunrise exact, sunset within ~1 min).

## Settings — set your location

| Setting | Default | |
|---|---|---|
| **Latitude** | 37.7749 | Your latitude (°N positive, °S negative). |
| **Longitude** | -122.4194 | Your longitude (°E positive, °W negative). |
| **Location name** | San Francisco | Label shown under the clock. |
| **24-hour clock** | on | Off → 12-hour with AM/PM. |

Defaults to San Francisco. **Change latitude/longitude in Admin → Widgets → Sun Clock to your actual location** — the whole visualization (twilight bands, sunrise/sunset, day length, polar day/night handling) follows from it.

## Notes

- Handles polar cases: at high latitudes it shows "Midnight sun" / "Polar night" when the sun doesn't cross the horizon.
- Files: `manifest.json`, `index.html` only.
