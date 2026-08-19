#!/usr/bin/env python3
"""
epicd — downloads NASA EPIC's latest full-disk Earth image (DSCOVR satellite,
~1M miles out) for the Vardek "Earth (EPIC)" widget. Sandboxed widgets can't load
api.nasa.gov, so this fetches the newest natural-color image into ../img/
(downscaled via sips) and writes ../data.js. Refetches when a newer image appears.
serve | once. Config ../epic.json {apiKey, maxWidth}.
"""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img"); DATA_JS = os.path.join(WIDGET, "data.js")
CONF = os.path.join(WIDGET, "epic.json"); LOG = os.path.expanduser("~/Library/Logs/epicd.log")
DEFAULTS = {"apiKey": "DEMO_KEY", "maxWidth": 1400}


def log(m):
    line = "%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def conf():
    c = dict(DEFAULTS)
    try: c.update(json.load(open(CONF)))
    except (OSError, ValueError): pass
    try: json.dump(c, open(CONF, "w"), indent=2)
    except OSError: pass
    return c


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-epicd"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def write(d):
    open(DATA_JS + ".tmp", "w").write("window.__EPIC__=" + json.dumps(d, separators=(",", ":")) + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


def collect():
    c = conf(); os.makedirs(IMG, exist_ok=True)
    arr = json.loads(get("https://api.nasa.gov/EPIC/api/natural?api_key=" + c["apiKey"]).decode())
    if not arr:
        raise RuntimeError("no EPIC images")
    m = arr[-1]
    ident = m["identifier"]; datepath = m["date"].split(" ")[0].replace("-", "/")
    fn = "epic_" + ident + ".jpg"; out = os.path.join(IMG, fn)
    if not os.path.exists(out):
        url = "https://api.nasa.gov/EPIC/archive/natural/%s/png/%s.png?api_key=%s" % (datepath, m["image"], c["apiKey"])
        tmp = out + ".png"; open(tmp, "wb").write(get(url))
        r = subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", "-Z", str(c["maxWidth"]), tmp, "--out", out],
                           capture_output=True, text=True, timeout=60)
        try: os.remove(tmp)
        except OSError: pass
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError("sips failed: " + (r.stderr or "")[:120])
        for f in os.listdir(IMG):
            if f.startswith("epic_") and f != fn:
                try: os.remove(os.path.join(IMG, f))
                except OSError: pass
    cc = m.get("centroid_coordinates", {}) or {}
    return {"identifier": ident, "date": m["date"], "caption": m.get("caption", ""),
            "lat": cc.get("lat"), "lon": cc.get("lon"), "file": "img/" + fn,
            "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start"); cur = None
        while True:
            try:
                d = collect()
                if d["identifier"] != cur:
                    write(d); cur = d["identifier"]; log("updated: %s" % d["date"])
            except Exception as e:
                log("loop error: %s" % e)
            time.sleep(1800)
    else:
        d = collect(); write(d)
        print(json.dumps({k: v for k, v in d.items() if k != "caption"}, indent=1))
