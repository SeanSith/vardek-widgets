# Astronomy Picture (NASA APOD)

Shows NASA's Astronomy Picture of the Day full-bleed, with title, date, and
explanation. Updates daily.

## How it works

Sandboxed widgets can't load cross-origin images, so a small daemon (**apodd**)
fetches the APOD JSON from api.nasa.gov, downloads the day's image into this
widget's own `img/` folder (downscaled via `sips`), and writes `data.js`. The
widget shows it same-origin. On "video" APOD days it shows the title/explanation
and points you to apod.nasa.gov.

## API key

`apod.json` defaults to NASA's shared `DEMO_KEY`, which is rate-limited. Since the
daemon only fetches once a day that's usually fine, but for reliability grab a
free key at https://api.nasa.gov and set it:

```json
{ "apiKey": "YOUR_KEY", "maxWidth": 1600 }
```

## Daemon

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.apodd.plist
/usr/bin/python3 apodd/apodd.py once   # one-shot fetch
launchctl bootout gui/$(id -u)/com.kevin.apodd
```

Settings: **Show title & explanation** (default on), **Ken Burns pan/zoom** (default on).
Logs: `~/Library/Logs/apodd.{out,err}.log`.
