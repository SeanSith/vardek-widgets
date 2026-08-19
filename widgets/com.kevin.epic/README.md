# Earth (EPIC)

NASA's EPIC camera on the DSCOVR satellite photographs the full sunlit disk of
Earth from ~1 million miles away. This widget shows the latest natural-color image.

A daemon (**epicd**) fetches the newest image from api.nasa.gov into `img/`
(downscaled via sips) and writes `data.js`. `epic.json` defaults to `DEMO_KEY`
(rate-limited); set your own free key from https://api.nasa.gov for reliability.

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.epicd.plist
/usr/bin/python3 epicd/epicd.py once
```
Setting: **Show date & location caption**. Logs: `~/Library/Logs/epicd.*.log`.
