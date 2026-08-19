#!/usr/bin/env python3
"""artd — fetches public-domain artworks (with images) from the Art Institute of
Chicago for the Vardek "Art" widget. Downloads images into ../img/ and writes
../data.js. serve|once."""
import json, os, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img"); DATA_JS = os.path.join(WIDGET, "data.js")
CONF = os.path.join(WIDGET, "art.json"); LOG = os.path.expanduser("~/Library/Logs/artd.log")
DEFAULTS = {"count": 8, "maxWidth": 1400}


def log(m):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write("%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m))
    except OSError:
        pass


def conf():
    c = dict(DEFAULTS)
    try: c.update(json.load(open(CONF)))
    except (OSError, ValueError): pass
    try: json.dump(c, open(CONF, "w"), indent=2)
    except OSError: pass
    return c


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-artd", "AIC-User-Agent": "vardek dashboard"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def fetch_list(n):
    # search public-domain works that have an image, highlights first
    q = ("https://api.artic.edu/api/v1/artworks/search?limit=%d"
         "&fields=id,title,artist_display,date_display,image_id,medium_display,place_of_origin"
         "&query[bool][must][][term][is_public_domain]=true"
         "&query[bool][must][][exists][field]=image_id"
         "&sort[has_not_been_viewed_much][order]=asc") % (n * 3)
    d = json.loads(get(q).decode())
    return [a for a in d.get("data", []) if a.get("image_id")]


def collect():
    c = conf(); os.makedirs(IMG, exist_ok=True)
    arts = fetch_list(c["count"])
    out = []
    for a in arts:
        if len(out) >= c["count"]:
            break
        iid = a["image_id"]; fn = "art_" + iid + ".jpg"; dst = os.path.join(IMG, fn)
        if not os.path.exists(dst):
            url = "https://www.artic.edu/iiif/2/%s/full/%d,/0/default.jpg" % (iid, c["maxWidth"])
            try:
                tmp = dst + ".src"; open(tmp, "wb").write(get(url))
                subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", tmp, "--out", dst],
                               capture_output=True, text=True, timeout=50)
                if not os.path.exists(dst): os.replace(tmp, dst)
                else: os.remove(tmp)
            except Exception as e:
                log("img err %s: %s" % (iid, e)); continue
        out.append({"id": a["id"], "title": a.get("title", ""), "artist": (a.get("artist_display") or "").split("\n")[0],
                    "date": a.get("date_display", ""), "medium": a.get("medium_display", ""),
                    "origin": a.get("place_of_origin", ""), "file": "img/" + fn})
        time.sleep(0.2)
    keep = {"art_" + a["image_id"] + ".jpg" for a in arts[:len(out)]}
    for f in os.listdir(IMG):
        if f.startswith("art_") and f not in keep:
            try: os.remove(os.path.join(IMG, f))
            except OSError: pass
    return {"generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"), "count": len(out), "works": out}


def write(d):
    open(DATA_JS + ".tmp", "w").write("window.__ART__=" + json.dumps(d, separators=(",", ":")) + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start")
        while True:
            try: write(collect())
            except Exception as e: log("loop error: %s" % e)
            time.sleep(6 * 3600)
    else:
        d = collect(); write(d); print(json.dumps({"count": d["count"], "sample": [w["title"] for w in d["works"][:5]]}, indent=1))
