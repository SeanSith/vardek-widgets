#!/usr/bin/env python3
"""
apodd — fetches NASA's Astronomy Picture of the Day for the "Astronomy Picture"
Vardek widget. Sandboxed widgets can't load cross-origin images, so this daemon
downloads the day's image into ../img/ (downscaled via sips) and writes ../data.js.
Refetches only when the APOD date changes. Commands: serve | once.

Uses NASA's APOD Basic JSON feed (no API key needed). Config ../apod.json {maxWidth}.
"""
import hashlib, html, json, os, re, subprocess, sys, time, urllib.request
from urllib.parse import quote, urlsplit, urlunsplit
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img")
DATA_JS = os.path.join(WIDGET, "data.js")
CONF = os.path.join(WIDGET, "apod.json")
LAST_GOOD = os.path.join(WIDGET, "last_good.json")
LOG = os.path.expanduser("~/Library/Logs/apodd.log")
MIN_BYTES = 20000
LIST_URL = "https://science.nasa.gov/wp-json/wp/v2/apod-basic"
DEFAULTS = {"maxWidth": 1600}


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


def ascii_url(url):
    """Percent-encode non-ASCII (e.g. "č") in a URL; urllib can't send it as-is."""
    # Safe sets keep "%" and URL delimiters, so existing escapes survive (idempotent).
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe="/%:@!$&'()*+,;=~"),
                       quote(p.query, safe="=&%/?:@!$'()*+,;~"), p.fragment))


def download(url, out):
    req = urllib.request.Request(ascii_url(url), headers={"User-Agent": "vardek-apodd"})
    with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
        f.write(r.read())


def write(d):
    b = json.dumps(d, separators=(",", ":"))
    open(DATA_JS + ".tmp", "w").write("window.__APOD__=" + b + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


def clean(html_text):
    t = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", " ", html_text or "")))
    return re.sub(r"\s+", " ", t).strip()


def explanation(raw):
    t = clean(raw)
    t = re.sub(r"^Explanation:\s*", "", t)
    return re.split(r"\s*Tomorrow's picture:", t)[0].strip()


def build(item, c):
    """Turn one apod-basic entry into widget data, downloading its image."""
    date = item.get("date", "")
    base = {"date": date, "title": clean(item.get("title")), "explanation": explanation(item.get("explanation")),
            "credit": clean(item.get("credit") or item.get("copyright")), "media_type": item.get("media_type"),
            "sourceUrl": item.get("hdurl") or item.get("url", ""),
            "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")}
    if item.get("media_type") == "image":
        src = item.get("hdurl")
        if not src or re.search(r"(^|[^a-z])logo([^a-z]|$)", src.lower()):
            raise ValueError("no usable image for %s: %s" % (date, src))
        # name by source too, so a corrected image for the same date isn't mistaken for the cached one
        fn = "apod_%s_%s.jpg" % (date.replace("-", ""), hashlib.md5(src.encode()).hexdigest()[:8])
        out = os.path.join(IMG, fn)
        if not os.path.exists(out):
            tmp = out + ".src"
            download(src, tmp)
            if os.path.getsize(tmp) < MIN_BYTES:
                os.remove(tmp)
                raise ValueError("image too small for %s: %s" % (date, src))
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
    remember(base)
    return base


def remember(d):
    try:
        json.dump(d, open(LAST_GOOD + ".tmp", "w")); os.replace(LAST_GOOD + ".tmp", LAST_GOOD)
    except OSError:
        pass


def last_good():
    try:
        d = json.load(open(LAST_GOOD))
    except (OSError, ValueError):
        return None
    if d.get("file") and not os.path.exists(os.path.join(WIDGET, d["file"])):
        return None
    return d


def collect():
    """Newest usable APOD (the list is newest-first, so a bad entry today falls
    back to yesterday's); if none work, the last good record we saved."""
    c = conf(); os.makedirs(IMG, exist_ok=True)
    try:
        for item in fetch_json(LIST_URL + "?per_page=5"):
            try:
                return build(item, c)
            except Exception as e:
                log("skipping %s: %s" % (item.get("date"), e))
    except Exception as e:
        log("APOD list failed: %s" % e)
    d = last_good()
    if not d:
        raise RuntimeError("no APOD available and no last good record saved")
    log("serving last good: %s" % d.get("date"))
    return d


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
