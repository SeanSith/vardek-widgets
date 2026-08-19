# System Monitor

Live CPU, memory, load average, network throughput, and top processes.

A daemon (**sysmond**) samples the system every 3s via standard macOS tools
(`top`, `memory_pressure`, `sysctl`, `netstat`, `ps`) and writes `data.js`.
Network rates need deltas, so it must run continuously.

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.sysmond.plist
/usr/bin/python3 sysmond/sysmond.py once   # one-shot snapshot
launchctl bootout gui/$(id -u)/com.kevin.sysmond
```
No cloud, no credentials — reads only local system counters. Logs: `~/Library/Logs/sysmond.*.log`.
