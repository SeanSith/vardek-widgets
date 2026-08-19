#!/usr/bin/env python3
"""
batteryd — writes battery levels (Mac + Bluetooth devices) to ../data.js for the
Vardek "Battery" widget. Sandboxed widgets can't run shell, so this loop does:
  pmset -g batt            → charge %, charging state, time remaining
  ioreg -rn AppleSmartBattery → cycle count, health (max/design), temperature
  system_profiler SPBluetoothDataType -json → connected BT device battery levels
Runs on system python 3.9, no deps. Command: `serve` (loop) or `once`.
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET = os.path.dirname(HERE)
DATA_JS = os.path.join(WIDGET, "data.js")
DATA_JSON = os.path.join(WIDGET, "data.json")
LOG = os.path.expanduser("~/Library/Logs/batteryd.log")


def log(m):
    line = "%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        open(LOG, "a").write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def sh(args, timeout=8):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def mac_battery():
    out = sh(["/usr/bin/pmset", "-g", "batt"])
    m = re.search(r"(\d+)%; *(\w[\w ]*?);", out)
    pct = int(m.group(1)) if m else None
    state = (m.group(2).strip() if m else "").lower()
    tm = re.search(r"(\d+:\d\d) remaining", out)
    remaining = tm.group(1) if tm else None
    ac = "AC Power" in out or "charging" in state or "charged" in state
    ig = sh(["/usr/sbin/ioreg", "-rn", "AppleSmartBattery"])

    def iv(key):
        mm = re.search(r'"%s"\s*=\s*(-?\d+)' % key, ig)
        return int(mm.group(1)) if mm else None
    design, rawmax = iv("DesignCapacity"), iv("AppleRawMaxCapacity")
    cyc, temp = iv("CycleCount"), iv("Temperature")
    health = round(rawmax / design * 100) if (design and rawmax) else None
    if pct is None:
        cur, mx = iv("CurrentCapacity"), iv("MaxCapacity")
        if cur is not None and mx:
            pct = round(cur / mx * 100)
    if pct is None:
        return None
    return {"kind": "mac", "name": "This Mac", "pct": pct,
            "charging": ("charging" in state), "acPower": ac, "full": ("charged" in state),
            "remaining": remaining, "health": health, "cycles": cyc,
            "tempC": round(temp / 100, 1) if temp else None}


BT_ICON = {"headphones": "🎧", "keyboard": "⌨️", "mouse": "🖱", "trackpad": "🖲", "gamepad": "🎮"}


def bt_batteries():
    out = sh(["/usr/sbin/system_profiler", "SPBluetoothDataType", "-json"], timeout=12)
    devs = []
    try:
        data = json.loads(out)
    except ValueError:
        return devs
    blocks = data.get("SPBluetoothDataType", [])
    for blk in blocks:
        conn = blk.get("device_connected") or []
        for entry in conn:
            for name, info in entry.items():
                if not isinstance(info, dict):
                    continue
                lvl = None
                for k in ("device_batteryLevelMain", "device_batteryLevel",
                          "device_batteryLevelLeft", "device_batteryLevelRight",
                          "device_batteryLevelCase"):
                    if info.get(k):
                        try:
                            lvl = int(str(info[k]).replace("%", "").strip())
                            break
                        except ValueError:
                            pass
                if lvl is None:
                    continue
                minor = str(info.get("device_minorType", "") or info.get("device_majorType", "")).lower()
                icon = "🔵"
                for key, ic in BT_ICON.items():
                    if key in minor or key in name.lower():
                        icon = ic
                devs.append({"kind": "bt", "name": name, "pct": lvl, "icon": icon})
    return devs


def collect():
    out = []
    mac = mac_battery()
    if mac:
        out.append(mac)
    try:
        out.extend(bt_batteries())
    except Exception as e:
        log("bt error: %s" % e)
    return {"generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "devices": out}


def write(payload):
    body = json.dumps(payload, separators=(",", ":"))
    for path, wrap in ((DATA_JS, True), (DATA_JSON, False)):
        tmp = path + ".tmp"
        open(tmp, "w").write(("window.__BATTERY__=" + body + ";\n") if wrap else body)
        os.replace(tmp, path)


def serve():
    log("serve: start")
    last_bt = 0
    while True:
        try:
            write(collect())
        except Exception as e:
            log("loop error: %s" % e)
        time.sleep(20)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "once":
        d = collect(); write(d); print(json.dumps(d, indent=1))
    else:
        serve()
