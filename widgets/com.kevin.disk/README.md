# Disk Widget
Storage usage per volume — a bar and used/free/total for your Mac's drive and any external drives, color‑coded (blue < 70%, amber ≥ 70%, red ≥ 90%). Shows the real APFS figure (`total − available`, not `df`'s snapshot "used").

Daemon `diskd/diskd.py` runs `df` and writes `data.js` every 5 min (a StartInterval LaunchAgent — single‑shot, not a persistent loop). No credentials.
**Start:** `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.diskd.plist`, then relaunch Vardek. Setting: **Show external drives**.
