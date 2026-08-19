#!/usr/bin/env python3
"""
agentctl — status loop + action runner for the Vardek "Agent Control" widget.

The widget itself is a sandboxed iframe: it can't run anything, so it goes
through Vardek's own action system (owner-authored `config.actions`, which the
Macro Pad widget id is allowed to trigger). This script:

  serve      long-running loop (LaunchAgent, KeepAlive). Every few seconds it
             collects desktop-app state, agent-deck sessions (+ what a waiting
             agent is asking, from its tmux pane), and live CLI agent processes,
             writes ../data.js for the widget, and keeps a generated set of
             `agentctl.*` actions in Vardek's config so every button on the
             panel maps to a fixed, allow-listed command.
  run V T    execute one verb on one target (this is what the actions call):
             app.focus | app.quit | ad.start | ad.stop | ad.restart |
             ad.enter | ad.esc | ad.open | tui | refresh
  setup      detect installed AI apps, extract their icons, write agents.json,
             resolve tool paths. Safe to re-run; keeps user edits.

Config: ../agents.json (apps list, process matchers, terminal app, tool paths).
Python 3.9 / system python, no dependencies.
"""

import glob
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET_DIR = os.path.dirname(HERE)
DATA_JS = os.path.join(WIDGET_DIR, "data.js")
DATA_JSON = os.path.join(WIDGET_DIR, "data.json")
CONF = os.path.join(WIDGET_DIR, "agents.json")
ICON_DIR = os.path.join(WIDGET_DIR, "icons")
POKE = os.path.join(WIDGET_DIR, ".poke")
EDGE_GEOM = os.path.join(HERE, "edge-geom")
TOUCH_DRIVER_LABEL = "com.ajvwhite.MacXeneonEdgeTouchDriver"
TOUCH_DRIVER_LOG = os.path.expanduser("~/Library/Logs/MacXeneonEdgeTouchDriver/driver.log")
LOG = os.path.expanduser("~/Library/Logs/agentctl.log")
DAEMON = "http://127.0.0.1:8137"
RELAY = {"X-Vardek-Relay": "1", "Content-Type": "application/json"}

POLL_SEC = 5.0
POKE_CHECK_SEC = 0.5
ACTION_PREFIX = "agentctl."
MAX_SESSIONS = 40

KNOWN_APPS = [
    # key, display, candidate bundle paths, emoji fallback
    ("claude", "Claude", ["/Applications/Claude.app"], "✳"),
    ("chatgpt", "ChatGPT", ["/Applications/ChatGPT.app"], "◎"),
    ("codex", "Codex", ["/Applications/Codex.app"], "❯"),
    ("cursor", "Cursor", ["/Applications/Cursor.app"], "▮"),
    ("antigravity", "Antigravity", ["/Applications/Antigravity.app"], "◭"),
    ("grokbot", "Grok Bot", ["/Applications/Grok Bot.app"], "𝕏"),
    ("grok", "Grok", ["/Applications/Grok.app"], "𝕏"),
    ("lmstudio", "LM Studio", ["/Applications/LM Studio.app"], "▣"),
    ("ollama", "Ollama", ["/Applications/Ollama.app"], "◉"),
    ("windsurf", "Windsurf", ["/Applications/Windsurf.app"], "≈"),
    ("zed", "Zed", ["/Applications/Zed.app"], "Z"),
    ("perplexity", "Perplexity", ["/Applications/Perplexity.app"], "?"),
    ("warp", "Warp", ["/Applications/Warp.app"], "▤"),
]

# CLI agents to surface as live processes: key -> (display, regex on argv)
KNOWN_PROCS = {
    "claude": ("Claude Code", r"(^|/)claude( |$)"),
    "codex": ("Codex CLI", r"(^|/)codex( |$)"),
    "grok": ("Grok CLI", r"(^|/)grok( |$)"),
    "muse": ("Muse Code", r"(^|/)muse-bin[^ ]* |(^|/)muse( |$)"),
    "opencode": ("OpenCode", r"(^|/)opencode( |$)"),
    "amp": ("Amp", r"(^|/)amp( |$)"),
    "gemini": ("Gemini CLI", r"(^|/)gemini( |$)"),
    "aider": ("Aider", r"(^|/)aider( |$)"),
    "crush": ("Crush", r"(^|/)crush( |$)"),
}
PROC_IGNORE = re.compile(r"app-server|--daemon|mcp|language-server|helper|codexbar", re.I)


def log(msg):
    line = "%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def sh(args, timeout=20, check=False):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if check and r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[:300])
        return r
    except subprocess.TimeoutExpired:
        raise RuntimeError("timeout: %s" % " ".join(args[:3]))


def which(name, extra=()):
    for p in extra:
        if p and os.path.exists(p):
            return p
    found = shutil.which(name)
    if found:
        return found
    for d in ("/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin"), "/usr/bin", "/bin"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# config

def load_conf():
    try:
        with open(CONF) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_conf(conf):
    tmp = CONF + ".tmp"
    with open(tmp, "w") as f:
        json.dump(conf, f, indent=2)
    os.replace(tmp, CONF)


def app_info(path):
    try:
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            pl = plistlib.load(f)
    except Exception:
        return {}
    return {
        "bundleId": pl.get("CFBundleIdentifier"),
        "name": pl.get("CFBundleDisplayName") or pl.get("CFBundleName"),
        "iconFile": pl.get("CFBundleIconFile") or pl.get("CFBundleIconName"),
        "exe": pl.get("CFBundleExecutable"),
    }


def extract_icon(path, key, icon_file):
    """icns -> 128px png in ICON_DIR. Returns relative url or None."""
    if not icon_file:
        return None
    os.makedirs(ICON_DIR, exist_ok=True)
    cands = [os.path.join(path, "Contents", "Resources", icon_file)]
    if not icon_file.endswith(".icns"):
        cands.append(cands[0] + ".icns")
    src = next((c for c in cands if os.path.exists(c)), None)
    if not src:
        return None
    out = os.path.join(ICON_DIR, key + ".png")
    r = sh(["/usr/bin/sips", "-s", "format", "png", "-Z", "128", src, "--out", out], timeout=30)
    if r.returncode == 0 and os.path.exists(out):
        return "icons/%s.png" % key
    return None


def setup(quiet=False):
    conf = load_conf() or {}
    apps = {a["key"]: a for a in conf.get("apps", [])}
    for key, name, paths, emoji in KNOWN_APPS:
        path = next((p for p in paths if os.path.isdir(p)), None)
        if key in apps and not apps[key].get("auto", True):
            continue  # user-managed entry
        if not path:
            apps.pop(key, None) if apps.get(key, {}).get("auto", True) else None
            continue
        info = app_info(path)
        entry = apps.get(key, {})
        entry.update({
            "key": key, "name": entry.get("name") or info.get("name") or name, "path": path,
            "bundleId": info.get("bundleId"), "exe": info.get("exe"), "emoji": entry.get("emoji") or emoji,
            "auto": True, "enabled": entry.get("enabled", True),
        })
        icon = extract_icon(path, key, info.get("iconFile"))
        if icon:
            entry["icon"] = icon
        apps[key] = entry
    order = [k for k, _, _, _ in KNOWN_APPS] + [k for k in apps if k not in [x[0] for x in KNOWN_APPS]]
    conf["apps"] = [apps[k] for k in order if k in apps]
    conf.setdefault("terminal", "Terminal")   # Terminal | iTerm
    conf.setdefault("processes", {k: v[0] for k, v in KNOWN_PROCS.items()})
    conf["bin"] = {
        "agent-deck": which("agent-deck", [conf.get("bin", {}).get("agent-deck")]),
        "tmux": which("tmux", [conf.get("bin", {}).get("tmux")]),
        "open": "/usr/bin/open", "osascript": "/usr/bin/osascript",
    }
    conf.setdefault("pollSeconds", POLL_SEC)
    conf.setdefault("touchWatchdog", True)
    conf["python"] = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else (sys.executable or "python3")
    save_conf(conf)
    if not quiet:
        log("setup: %d apps, agent-deck=%s tmux=%s" % (len(conf["apps"]), conf["bin"]["agent-deck"], conf["bin"]["tmux"]))
    return conf


# ---------------------------------------------------------------------------
# status collection

def running_apps(conf):
    """Return {key: {pid, frontmost}} for configured apps, via ps + lsappinfo."""
    r = sh(["/bin/ps", "-axo", "pid=,comm="], timeout=25)
    procs = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid, _, comm = line.partition(" ")
        procs.append((pid.strip(), comm.strip()))
    front = None
    try:
        fr = sh(["/usr/bin/lsappinfo", "front"], timeout=5)
        asn = fr.stdout.strip()
        if asn:
            info = sh(["/usr/bin/lsappinfo", "info", "-only", "bundleid", asn], timeout=5).stdout
            m = re.search(r'"?CFBundleIdentifier"?\s*=\s*"([^"]+)"', info)
            if m:
                front = m.group(1)
    except Exception:
        pass
    out = {}
    for a in conf.get("apps", []):
        exe_prefix = os.path.join(a["path"], "Contents", "MacOS") + "/"
        pid = next((p for p, c in procs if c.startswith(exe_prefix)), None)
        out[a["key"]] = {"running": pid is not None, "pid": int(pid) if pid else None,
                         "frontmost": bool(front and a.get("bundleId") == front)}
    return out


DECOR = re.compile(r"^[\s─━═┄┅╌╍╴╶┈┉│┃┆┇╎╏║╭╮╯╰╱╲╳▁▂▃▄▅▆▇█▀▔▕▏▎▍▌▋▊▉ ┏┓┗┛┣┫┳┻╋╔╗╚╝╠╣╦╩╬•·]*$")
NOISE = re.compile(r"bypass permissions|shift\+tab to cycle|for agents|\? for shortcuts|esc to interrupt|"
                   r"tokens \d|context left|^\s*[╭╰]|auto-accept|plan mode|^\s*⏵|^\s*[❯>›]\s*$|"
                   r"\|\s*(opus|fable|sonnet|haiku|gpt|codex|gemini|grok)\b", re.I)


def pane_snippet(tmux, session, lines=18):
    """Last couple of meaningful lines from a tmux pane (what the agent shows)."""
    if not tmux or not session:
        return None
    r = sh([tmux, "capture-pane", "-p", "-J", "-t", session, "-S", "-%d" % lines], timeout=5)
    if r.returncode != 0:
        return None
    keep = []
    for raw in r.stdout.splitlines():
        s = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", raw).rstrip()
        if not s.strip() or DECOR.match(s) or NOISE.search(s):
            continue
        if not re.search(r"[A-Za-z0-9]", s):
            continue  # pure decoration (rules, spinners, borders)
        s = re.sub(r"\s{3,}", "  ", s.strip())
        keep.append(s[:140])
    if not keep:
        return None
    return keep[-2:]


def agentdeck_sessions(conf):
    ad = conf.get("bin", {}).get("agent-deck")
    tmux = conf.get("bin", {}).get("tmux")
    if not ad:
        return None, "agent-deck not found"
    try:
        r = sh([ad, "list", "--json"], timeout=25)
    except RuntimeError as e:
        return None, str(e)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()[:200] or "agent-deck list failed"
    txt = r.stdout
    start = txt.find("[")
    if start < 0:
        return [], None
    try:
        arr = json.loads(txt[start:])
    except ValueError:
        return None, "bad json from agent-deck"
    live = set()
    if tmux:
        t = sh([tmux, "ls", "-F", "#{session_name}"], timeout=5)
        if t.returncode == 0:
            live = set(t.stdout.split())
    out = []
    for s in arr:
        if s.get("archived"):
            continue
        tsess = s.get("tmux_session")
        status = s.get("status") or "unknown"
        alive = tsess in live
        entry = {
            "id": s.get("id"), "title": s.get("title") or "(untitled)", "group": s.get("group") or "",
            "path": s.get("path") or "", "tool": s.get("tool") or "", "status": status,
            "alive": alive, "tmux": tsess, "createdAt": s.get("created_at"),
        }
        if alive and status in ("waiting", "running"):
            entry["snippet"] = pane_snippet(tmux, tsess)
        out.append(entry)
    rank = {"waiting": 0, "running": 1, "idle": 2, "error": 3}
    out.sort(key=lambda e: (rank.get(e["status"], 4), not e["alive"], e["title"].lower()))
    return out[:MAX_SESSIONS], None


_cwd_cache = {}


def proc_cwd(pid):
    hit = _cwd_cache.get(pid)
    if hit and time.time() - hit[0] < 120:
        return hit[1]
    cwd = None
    try:
        r = sh(["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], timeout=5)
        for line in r.stdout.splitlines():
            if line.startswith("n"):
                cwd = line[1:]
    except Exception:
        pass
    _cwd_cache[pid] = (time.time(), cwd)
    return cwd


def cli_processes(conf):
    r = sh(["/bin/ps", "-axo", "pid=,etime=,tty=,args="], timeout=25)
    out = []
    matchers = [(k, re.compile(rx)) for k, (_, rx) in KNOWN_PROCS.items() if k in conf.get("processes", {})]
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 4:
            continue
        pid, etime, tty, args = parts
        first = args.split(" ", 1)[0]
        if PROC_IGNORE.search(args):
            continue
        for key, rx in matchers:
            if rx.search(first) or rx.search(args[:80]):
                out.append({"key": key, "name": conf["processes"].get(key, key), "pid": int(pid),
                            "elapsed": etime, "tty": None if tty == "??" else tty,
                            "cwd": proc_cwd(pid)})
                break
    out.sort(key=lambda p: (p["key"], p["pid"]))
    return out[:24]


def collect(conf):
    apps = running_apps(conf)
    sessions, ad_err = agentdeck_sessions(conf)
    procs = cli_processes(conf)
    counts = {"waiting": 0, "running": 0, "idle": 0, "error": 0}
    for s in sessions or []:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    return {
        "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "apps": [dict(a, **apps.get(a["key"], {})) for a in conf.get("apps", []) if a.get("enabled", True)],
        "sessions": sessions or [],
        "sessionCounts": counts,
        "agentDeckError": ad_err,
        "processes": procs,
        "terminal": conf.get("terminal"),
        "actionsPrefix": ACTION_PREFIX,
    }


# ---------------------------------------------------------------------------
# Vardek config actions

def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(DAEMON + path, data=data, method=method, headers=RELAY)
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def desired_actions(conf, status):
    py = conf.get("python") or "/usr/bin/python3"
    script = os.path.join(HERE, "agentctl.py")

    def cmd(verb, target=""):
        return '"%s" "%s" run %s %s' % (py, script, verb, json.dumps(target)) if target else '"%s" "%s" run %s' % (py, script, verb)

    acts = []
    for a in status["apps"]:
        acts.append({"id": ACTION_PREFIX + "app.focus." + a["key"], "label": "Open " + a["name"],
                     "icon": a.get("emoji") or "▶", "type": "shell", "command": cmd("app.focus", a["key"])})
        acts.append({"id": ACTION_PREFIX + "app.quit." + a["key"], "label": "Quit " + a["name"],
                     "icon": "×", "type": "shell", "command": cmd("app.quit", a["key"])})
    verbs = [("start", "▶", "Start"), ("stop", "■", "Stop"), ("restart", "↻", "Restart"),
             ("enter", "⏎", "Approve"), ("esc", "⎋", "Esc"), ("open", "⌨", "Open")]
    for s in status["sessions"]:
        for v, icon, lab in verbs:
            acts.append({"id": ACTION_PREFIX + "ad." + v + "." + s["id"],
                         "label": "%s · %s" % (lab, s["title"]), "icon": icon,
                         "type": "shell", "command": cmd("ad." + v, s["id"])})
    acts.append({"id": ACTION_PREFIX + "tui", "label": "Agent Deck TUI", "icon": "▦", "type": "shell", "command": cmd("tui")})
    acts.append({"id": ACTION_PREFIX + "refresh", "label": "Refresh agents", "icon": "↻", "type": "shell", "command": cmd("refresh")})
    acts.append({"id": ACTION_PREFIX + "selftest", "label": "agentctl self-test", "icon": "✓", "type": "shell", "command": cmd("selftest")})
    return acts


def sync_actions(conf, status, force=False):
    """Merge generated actions into Vardek's config.actions (keeps user's own)."""
    try:
        _, cfg = http("GET", "/api/config")
    except Exception as e:
        log("config GET failed: %s" % e)
        return False
    current = cfg.get("actions") or []
    mine_now = [a for a in current if str(a.get("id", "")).startswith(ACTION_PREFIX)]
    theirs = [a for a in current if not str(a.get("id", "")).startswith(ACTION_PREFIX)]
    want = desired_actions(conf, status)
    if not force and json.dumps(mine_now, sort_keys=True) == json.dumps(want, sort_keys=True):
        return False
    cfg["actions"] = theirs + want
    try:
        st, _ = http("PUT", "/api/config", cfg)
        log("actions synced (%d generated, %d user) -> %s" % (len(want), len(theirs), st))
        return True
    except Exception as e:
        log("config PUT failed: %s" % e)
        return False


def write_data(status):
    payload = json.dumps(status, separators=(",", ":"))
    for path, wrap in ((DATA_JS, True), (DATA_JSON, False)):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(("window.__AGENTCTL__=" + payload + ";\n") if wrap else payload)
        os.replace(tmp, path)


# ---------------------------------------------------------------------------
# touch-driver watchdog: the MacXeneonEdgeTouchDriver resolves the Edge's screen
# position only when the HID (re)matches, and caches it. After a sleep/replug it
# can latch onto a transient (0,0) before macOS restores the real arrangement,
# and then every tap clicks the *main* display instead of the panel. We compare
# the driver's last-resolved origin to the panel's live CoreGraphics origin and
# kick the driver's LaunchAgent when they disagree.

_wd_last_kick = 0.0


def edge_cg_origin():
    if not os.path.exists(EDGE_GEOM):
        return None
    try:
        r = sh([EDGE_GEOM], timeout=5)
    except RuntimeError:
        return None
    out = r.stdout.strip()
    if not out or out == "NONE":
        return None
    parts = out.split()
    if len(parts) < 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError:
        return None


def driver_resolved_origin():
    """Last 'Resolved ... x=..., y=...' the driver logged."""
    try:
        with open(TOUCH_DRIVER_LOG, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    origin = None
    for m in re.finditer(r"Resolved Xeneon Edge display[^\n]*x=(-?\d+)\.?\d*,\s*y=(-?\d+)\.?\d*", tail):
        origin = (int(m.group(1)), int(m.group(2)))
    return origin


def touch_watchdog(conf):
    global _wd_last_kick
    if not conf.get("touchWatchdog", True):
        return
    if time.time() - _wd_last_kick < 30:
        return
    cg = edge_cg_origin()
    if cg is None:
        return  # panel not currently a 2560x720 display; nothing to enforce
    drv = driver_resolved_origin()
    if drv is not None and drv == cg:
        return  # driver is aimed at the right place
    # driver stale (or never resolved to the live origin): kick it
    _wd_last_kick = time.time()
    r = sh(["/bin/launchctl", "kickstart", "-k", "gui/%d/%s" % (os.getuid(), TOUCH_DRIVER_LABEL)], timeout=15)
    log("touch-watchdog: driver origin %s != panel %s -> restarted driver (rc=%d)" % (drv, cg, r.returncode))


def serve():
    conf = setup(quiet=True)
    log("serve: start (poll %ss)" % conf.get("pollSeconds", POLL_SEC))
    last_json = None
    last_write = 0
    last_poke = 0
    next_poll = 0
    last_good_sessions = []
    last_good_counts = {"waiting": 0, "running": 0, "idle": 0, "error": 0}
    while True:
        now = time.time()
        try:
            poke = os.path.getmtime(POKE)
        except OSError:
            poke = 0
        if poke > last_poke:
            last_poke = poke
            next_poll = 0
        if now >= next_poll:
            try:
                fresh = load_conf() or conf
                if fresh is not conf:
                    conf = fresh
                try:
                    touch_watchdog(conf)
                except Exception as e:
                    log("touch-watchdog error: %s" % e)
                status = collect(conf)
                if status.get("agentDeckError"):
                    # transient agent-deck failure (load, timeout): keep showing the
                    # last good session list and leave the action catalog alone
                    status["sessions"] = last_good_sessions
                    status["sessionCounts"] = last_good_counts
                else:
                    last_good_sessions = status["sessions"]
                    last_good_counts = status["sessionCounts"]
                sig = json.dumps({k: v for k, v in status.items() if k not in ("generatedAt", "agentDeckError")}, sort_keys=True)
                if sig != last_json or now - last_write > 30:
                    write_data(status)
                    last_write = now
                    if sig != last_json and not status.get("agentDeckError"):
                        sync_actions(conf, status)
                    last_json = sig
            except Exception as e:
                log("loop error: %s" % e)
            next_poll = time.time() + float(conf.get("pollSeconds", POLL_SEC))
        time.sleep(POKE_CHECK_SEC)


# ---------------------------------------------------------------------------
# verbs (called by Vardek actions)

def poke():
    with open(POKE, "w") as f:
        f.write(str(time.time()))


def find_app(conf, key):
    for a in conf.get("apps", []):
        if a["key"] == key:
            return a
    raise SystemExit("unknown app: %s" % key)


def find_session(conf, sid):
    ad = conf["bin"]["agent-deck"]
    r = sh([ad, "list", "--json"], timeout=25, check=True)
    txt = r.stdout
    arr = json.loads(txt[txt.find("["):])
    for s in arr:
        if s.get("id") == sid or (s.get("id") or "").startswith(sid):
            return s
    raise SystemExit("unknown session: %s" % sid)


def terminal_run(conf, command):
    term = (conf.get("terminal") or "Terminal").lower()
    osa = conf["bin"]["osascript"]
    esc = command.replace("\\", "\\\\").replace('"', '\\"')
    if term.startswith("iterm"):
        script = ('tell application "iTerm"\n activate\n create window with default profile command "%s"\nend tell' % esc)
    else:
        script = ('tell application "Terminal"\n activate\n do script "%s"\nend tell' % esc)
    sh([osa, "-e", script], timeout=15, check=True)


SLOW_VERBS = ("ad.start", "ad.stop", "ad.restart", "ad.open", "tui")
DRY = os.environ.get("AGENTCTL_DRY") == "1"


def session_from_data(sid):
    """Resolve a session from the loop's last snapshot — no agent-deck round trip."""
    try:
        with open(DATA_JSON) as f:
            d = json.load(f)
        for s in d.get("sessions", []):
            if s.get("id") == sid:
                return {"id": s["id"], "tmux_session": s.get("tmux"), "title": s.get("title")}
    except (OSError, ValueError):
        pass
    return None


def detach(verb, target):
    """Run a slow verb in a detached child so the daemon's action call returns at once."""
    py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
    with open(LOG, "a") as lf:
        subprocess.Popen([py, os.path.join(HERE, "agentctl.py"), "bg", verb, target],
                         stdout=lf, stderr=lf, stdin=subprocess.DEVNULL, start_new_session=True)


def run(verb, target, inline=False):
    conf = load_conf() or setup(quiet=True)
    b = conf["bin"]
    if verb == "refresh":
        poke()
        return
    if verb == "selftest":
        log("selftest: start (sleeping 6s)")
        time.sleep(6)
        log("selftest: end — daemon did not kill a 6s action")
        return
    if verb in SLOW_VERBS and not inline:
        detach(verb, target)
        return
    if verb == "tui":
        terminal_run(conf, "%s" % b["agent-deck"])
        return
    if verb in ("app.focus", "app.quit"):
        a = find_app(conf, target)
        if verb == "app.focus":
            sh([b["open"], "-a", a["path"]], timeout=15, check=True)
        else:
            ident = a.get("bundleId")
            script = 'tell application id "%s" to quit' % ident if ident else 'quit app "%s"' % a["name"]
            sh([b["osascript"], "-e", script], timeout=15, check=True)
        poke()
        return
    if verb.startswith("ad."):
        op = verb[3:]
        s = session_from_data(target) if op in ("enter", "esc", "ctrlc") else None
        if s is None:
            s = find_session(conf, target)
        sid = s["id"]
        if op in ("start", "stop", "restart"):
            sh([b["agent-deck"], "session", op, sid], timeout=120, check=True)
        elif op in ("enter", "esc", "ctrlc"):
            tsess = s.get("tmux_session")
            if not tsess:
                raise SystemExit("session has no tmux session")
            key = {"enter": "Enter", "esc": "Escape", "ctrlc": "C-c"}[op]
            if DRY:
                log("dry-run: %s send-keys -t %s %s" % (b["tmux"], tsess, key))
            else:
                sh([b["tmux"], "send-keys", "-t", tsess, key], timeout=5, check=True)
        elif op == "open":
            terminal_run(conf, '%s --select %s' % (b["agent-deck"], sid))
        else:
            raise SystemExit("unknown verb: %s" % verb)
        poke()
        return
    raise SystemExit("unknown verb: %s" % verb)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd == "serve":
        serve()
    elif cmd == "setup":
        setup()
    elif cmd == "touch":
        conf = load_conf() or setup(quiet=True)
        print("panel:", edge_cg_origin(), "driver:", driver_resolved_origin())
        touch_watchdog(dict(conf, touchWatchdog=True))
    elif cmd == "collect":
        conf = load_conf() or setup(quiet=True)
        print(json.dumps(collect(conf), indent=1))
    elif cmd == "sync":
        conf = load_conf() or setup(quiet=True)
        st = collect(conf)
        write_data(st)
        print("changed" if sync_actions(conf, st, force=True) else "unchanged")
    elif cmd in ("run", "bg"):
        if len(argv) < 3:
            raise SystemExit("run <verb> [target]")
        verb, target = argv[2], (argv[3] if len(argv) > 3 else "")
        try:
            run(verb, target, inline=(cmd == "bg"))
        except (RuntimeError, SystemExit) as e:
            log("%s %s %s failed: %s" % (cmd, verb, target, e))
            raise
        log("%s %s %s %s" % (cmd, verb, target, "queued" if (cmd == "run" and verb in SLOW_VERBS) else "ok"))
    else:
        raise SystemExit("unknown command: %s" % cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
