# Battery Widget
A battery wall: this Mac's charge (battery‑shape gauge, charging state, time remaining) plus **health %, cycle count, temperature**, and any connected **Bluetooth devices** (AirPods, Magic Trackpad/Mouse/Keyboard) with their levels.

Daemon (`batteryd/batteryd.py serve`, a KeepAlive LaunchAgent) runs `pmset` + `ioreg` + `system_profiler SPBluetoothDataType` every 20s and writes `data.js`. No credentials.

**Start it:** `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.batteryd.plist`, then relaunch Vardek. Logs: `~/Library/Logs/batteryd.log`. Manual: `batteryd.py once`.
