# Astronomy Picture (NASA APOD)

Shows NASA's Astronomy Picture of the Day full-bleed, with title, date, and
explanation. Updates daily.

## How it works

Sandboxed widgets can't load cross-origin images, so a small daemon (**apodd**)
fetches the APOD JSON, downloads the day's image into this
widget's own `img/` folder (downscaled via `sips`), and writes `data.js`. The
widget shows it same-origin. On "video" APOD days it shows the title/explanation
and points you to apod.nasa.gov.

## Data source

Uses NASA's APOD Basic JSON feed (`science.nasa.gov/wp-json/wp/v2/apod-basic`),
which needs no API key; the old `api.nasa.gov/planetary/apod` endpoint is being
retired (it already returns a NASA logo placeholder). The feed is newest-first, so
if today's entry is unusable the daemon shows the most recent good one, and if the
feed is unreachable it re-serves the last good record (`last_good.json`).
`apod.json` takes `maxWidth` (image downscale, default 1600); any old `apiKey` is ignored.

## Daemon

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.apodd.plist
/usr/bin/python3 apodd/apodd.py once   # one-shot fetch
launchctl bootout gui/$(id -u)/com.kevin.apodd
```

Settings: **Show title & explanation** (default on), **Ken Burns pan/zoom** (default on).
Logs: `~/Library/Logs/apodd.{out,err}.log`.
