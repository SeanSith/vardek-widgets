# Art

Rotates through public-domain artworks from the Art Institute of Chicago. A daemon
(**artd**) fetches a batch, downloads the images into `img/`, and writes `data.js`.

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.artd.plist
/usr/bin/python3 artd/artd.py once
```
Settings: **Seconds per work**, **Show caption**. `art.json` sets batch size. Logs: `~/Library/Logs/artd.*.log`.
