#!/usr/bin/env python3
"""
apodd — fetches NASA's Astronomy Picture of the Day for the "Astronomy Picture"
Vardek widget. Sandboxed widgets can't load cross-origin images, so this daemon
downloads the day's image into ../img/ (downscaled via sips) and writes ../data.js.
Refetches only when the APOD date changes. Commands: serve | once.

Config ../apod.json {apiKey, maxWidth}. api.nasa.gov DEMO_KEY works but is rate
limited; get a free key at https://api.nasa.gov and set it here.
"""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img")
DATA_JS = os.path.join(WIDGET, "data.js")
CONF = os.path.join(WIDGET, "apod.json")
LOG = os.path.expanduser("~/Library/Logs/apodd.log")
DEFAULTS = {"apiKey": "DEMO_KEY", "maxWidth": 1600}


def log(m):
    line = "%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def conf():
    c = dict(DEFAULTS)
    try:
        c.update(json.load(open(CONF)))
    except (OSError, ValueError):
        pass
    try:
        json.dump(c, open(CONF, "w"), indent=2)
    except OSError:
        pass
    return c


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-apodd"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def download(url, out):
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-apodd"})
    with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
        f.write(r.read())


def write(d):
    b = json.dumps(d, separators=(",", ":"))
    open(DATA_JS + ".tmp", "w").write("window.__APOD__=" + b + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


def collect():
    c = conf(); os.makedirs(IMG, exist_ok=True)
    api = fetch_json("https://api.nasa.gov/planetary/apod?api_key=" + c["apiKey"])
    date = api.get("date", "")
    base = {"date": date, "title": api.get("title", ""), "explanation": api.get("explanation", ""),
            "copyright": (api.get("copyright") or "").strip(), "media_type": api.get("media_type"),
            "sourceUrl": api.get("hdurl") or api.get("url", ""),
            "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")}
    if api.get("media_type") == "image":
        fn = "apod_" + date.replace("-", "") + ".jpg"
        out = os.path.join(IMG, fn)
        if not os.path.exists(out):
            src = api.get("hdurl") or api.get("url")
            tmp = out + ".src"
            download(src, tmp)
            r = subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", "-Z", str(c["maxWidth"]),
                                tmp, "--out", out], capture_output=True, text=True, timeout=60)
            if r.returncode != 0 or not os.path.exists(out):
                os.replace(tmp, out)  # fall back to original bytes
            else:
                try: os.remove(tmp)
                except OSError: pass
            # prune older apod images
            for f in os.listdir(IMG):
                if f.startswith("apod_") and f != fn:
                    try: os.remove(os.path.join(IMG, f))
                    except OSError: pass
        base["file"] = "img/" + fn
    return base


def run_once():
    d = collect(); write(d); return d


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start")
        curdate = None
        while True:
            try:
                d = collect()
                if d.get("date") != curdate:
                    write(d); curdate = d.get("date"); log("updated: %s (%s)" % (d.get("date"), d.get("title")))
            except Exception as e:
                log("loop error: %s" % e)
            time.sleep(1800)
    else:
        d = run_once()
        print(json.dumps({k: (v if k != "explanation" else v[:60] + "…") for k, v in d.items()}, indent=1))
