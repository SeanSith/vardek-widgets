# Photo Frame

A crossfading, Ken-Burns digital photo frame for Vardek. Cycles through the
images in a folder you choose, downscaled for a sharp fit on the Xeneon Edge.

## How it works

Sandboxed Vardek widgets can only load images from their own folder — they
can't reach into `~/Pictures` directly. So a small daemon, **photod**, watches
your source folder, downscales each image to a widget-local `img/` copy (JPEG,
longest side ~1600px, HEIC handled via `sips`), and writes `data.js` with the
frame list. The widget reads `data.js`, then crossfades between two layers with
an optional Ken Burns pan/zoom.

photod is incremental: unchanged photos keep their cached copy, so rescans are
cheap. Removing a photo from the folder prunes its copy on the next scan.

## Point it at your photos

Edit `photoframe.json` in this folder:

```json
{
  "folder": "~/Pictures",   // any folder of images
  "maxImages": 40,          // newest N by modified-time
  "longestSide": 1600,      // downscale target (px)
  "recurse": false,         // include subfolders
  "rescanSec": 300          // how often photod re-scans
}
```

macOS keeps most photos inside `~/Pictures/Photos Library.photoslibrary`, which
is a sealed bundle — point `folder` at a **regular folder of image files**
instead. Easiest path: in Photos.app select an album → File ▸ Export ▸ Export
Photos… into a folder (e.g. `~/Pictures/Frame`), then set `"folder"` to it.

Shipped default is `~/Pictures`; this install is currently pointed at
`~/Downloads` so it shows something out of the box — change it to your real
photo folder.

## Widget settings (Vardek admin)

- **Seconds per photo** (`intervalSec`, default 8)
- **Ken Burns pan/zoom** (`kenBurns`, default on)
- **Show filename/date** (`showCaption`, default off)
- **Shuffle order** (`shuffle`, default on)

## Daemon

Runs via LaunchAgent `~/Library/LaunchAgents/com.kevin.photod.plist`.

```bash
# load / start
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.photod.plist
# one-shot rebuild (writes data.js + img/)
/usr/bin/python3 photod/photod.py once
# stop
launchctl bootout gui/$(id -u)/com.kevin.photod
```

Logs: `~/Library/Logs/photod.{out,err}.log` and `~/Library/Logs/photod.log`.
