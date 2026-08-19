#!/usr/bin/env python3
"""
xkcdd — fetches the latest xkcd comic for the Vardek "xkcd" widget. Sandboxed
widgets can't load imgs.xkcd.com, so this downloads the comic into ../img/ and
writes ../data.js. Refetches only when the comic number changes. serve | once.
"""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img"); DATA_JS = os.path.join(WIDGET, "data.js")
LOG = os.path.expanduser("~/Library/Logs/xkcdd.log")


def log(m):
    line = "%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-xkcdd"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def download(url, out):
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-xkcdd"})
    with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
        f.write(r.read())


def write(d):
    open(DATA_JS + ".tmp", "w").write("window.__XKCD__=" + json.dumps(d, separators=(",", ":")) + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


def collect():
    os.makedirs(IMG, exist_ok=True)
    c = fetch_json("https://xkcd.com/info.0.json")
    num = c["num"]
    ext = os.path.splitext(c["img"])[1] or ".png"
    fn = "xkcd_%d%s" % (num, ext); out = os.path.join(IMG, fn)
    if not os.path.exists(out):
        download(c["img"], out)
        # downscale only if very large
        subprocess.run(["/usr/bin/sips", "-Z", "1600", out], capture_output=True, text=True, timeout=40)
        for f in os.listdir(IMG):
            if f.startswith("xkcd_") and f != fn:
                try: os.remove(os.path.join(IMG, f))
                except OSError: pass
    return {"num": num, "title": c.get("safe_title") or c.get("title", ""), "alt": c.get("alt", ""),
            "file": "img/" + fn, "date": "%s-%02d-%02d" % (c.get("year"), int(c.get("month", 1)), int(c.get("day", 1))),
            "link": "https://xkcd.com/%d/" % num,
            "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start"); cur = None
        while True:
            try:
                d = collect()
                if d["num"] != cur:
                    write(d); cur = d["num"]; log("updated: #%d %s" % (d["num"], d["title"]))
            except Exception as e:
                log("loop error: %s" % e)
            time.sleep(3600)
    else:
        d = collect(); write(d)
        print(json.dumps({k: (v if k != "alt" else v[:50] + "…") for k, v in d.items()}, indent=1))
