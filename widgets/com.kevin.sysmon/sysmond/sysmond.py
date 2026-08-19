#!/usr/bin/env python3
"""
sysmond — system resource collector for the Vardek "System Monitor" widget.
Reads CPU / memory / load / network / top processes via standard macOS tools and
writes ../data.js. Network rates need deltas, so `serve` keeps state between reads.
Commands: serve | once.
"""
import json, os, re, subprocess, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); WIDGET = os.path.dirname(HERE)
DATA_JS = os.path.join(WIDGET, "data.js"); LOG = os.path.expanduser("~/Library/Logs/sysmond.log")


def log(m):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write("%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m))
    except OSError:
        pass


def sh(cmd, timeout=8):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def cpu_pct():
    # top -l 2 gives a real (non-startup) sample in the 2nd block
    out = sh(["/usr/bin/top", "-l", "2", "-n", "0", "-s", "1"], timeout=10)
    blocks = re.findall(r"CPU usage: ([\d.]+)% user, ([\d.]+)% sys, ([\d.]+)% idle", out)
    if not blocks:
        return None
    u, s, i = blocks[-1]
    return {"user": float(u), "sys": float(s), "idle": float(i), "used": round(100 - float(i), 1)}


def mem():
    total = int(sh(["/usr/sbin/sysctl", "-n", "hw.memsize"]).strip() or 0)
    free_pct = None
    out = sh(["/usr/bin/memory_pressure"], timeout=6)
    m = re.search(r"free percentage:\s*(\d+)%", out)
    if m:
        free_pct = int(m.group(1))
    used_pct = (100 - free_pct) if free_pct is not None else None
    return {"totalGB": round(total / 1e9, 1), "usedPct": used_pct,
            "usedGB": round(total / 1e9 * used_pct / 100, 1) if used_pct is not None else None}


def loadavg():
    out = sh(["/usr/sbin/sysctl", "-n", "vm.loadavg"]).strip()
    m = re.findall(r"[\d.]+", out)
    return [float(x) for x in m[:3]] if len(m) >= 3 else None


def net_bytes():
    # sum non-loopback interface in/out bytes from netstat -ib
    out = sh(["/usr/sbin/netstat", "-ib"])
    rx = tx = 0; seen = set()
    for line in out.splitlines()[1:]:
        f = line.split()
        if len(f) < 11 or f[0] == "lo0" or f[0] in seen:
            continue
        # Only rows with a Link# address carry the real byte counters
        if not f[2].startswith("<Link"):
            continue
        try:
            rx += int(f[6]); tx += int(f[9]); seen.add(f[0])
        except (ValueError, IndexError):
            continue
    return rx, tx


def uptime():
    out = sh(["/usr/sbin/sysctl", "-n", "kern.boottime"])
    m = re.search(r"sec = (\d+)", out)
    if not m:
        return None
    return int(time.time()) - int(m.group(1))


def top_procs(n=4):
    out = sh(["/bin/ps", "-arcwwwxo", "pid=,comm=,%cpu="])
    procs = []
    for line in out.splitlines():
        f = line.split(None, 2)
        if len(f) < 3:
            continue
        try:
            procs.append({"name": f[1][:22], "cpu": float(f[2])})
        except ValueError:
            continue
    return procs[:n]


def collect(prev):
    now = time.time()
    rx, tx = net_bytes()
    net = {"rxKBs": None, "txKBs": None}
    if prev and prev.get("net_raw"):
        dt = now - prev["ts"]
        if dt > 0:
            net = {"rxKBs": max(0, round((rx - prev["net_raw"][0]) / dt / 1024, 1)),
                   "txKBs": max(0, round((tx - prev["net_raw"][1]) / dt / 1024, 1))}
    d = {"cpu": cpu_pct(), "mem": mem(), "load": loadavg(), "net": net,
         "cores": int(sh(["/usr/sbin/sysctl", "-n", "hw.ncpu"]).strip() or 0),
         "uptime": uptime(), "top": top_procs(),
         "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")}
    return d, {"ts": now, "net_raw": (rx, tx)}


def write(d):
    open(DATA_JS + ".tmp", "w").write("window.__SYS__=" + json.dumps(d, separators=(",", ":")) + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start"); prev = None
        while True:
            try:
                d, prev = collect(prev); write(d)
            except Exception as e:
                log("loop error: %s" % e)
            time.sleep(3)
    else:
        # one-shot: sample twice for a network rate
        _, prev = collect(None); time.sleep(1); d, _ = collect(prev); write(d)
        print(json.dumps(d, indent=1))
