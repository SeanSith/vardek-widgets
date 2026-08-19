# xkcd

Shows the latest xkcd comic with its title and alt (hover) text. Updates when a
new comic is posted (Mon/Wed/Fri).

## How it works

Comics live on imgs.xkcd.com, which sandboxed widgets can't load, so a small
daemon (**xkcdd**) fetches xkcd.com/info.0.json, downloads the comic into this
widget's `img/`, and writes `data.js`. Refetches only when the comic number changes.

## Daemon

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.xkcdd.plist
/usr/bin/python3 xkcdd/xkcdd.py once   # one-shot
launchctl bootout gui/$(id -u)/com.kevin.xkcdd
```

Setting: **Show alt (hover) text** (default on). Logs: `~/Library/Logs/xkcdd.*.log`.
