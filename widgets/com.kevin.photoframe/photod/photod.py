#!/usr/bin/env python3
"""
photod — prepares photos for the Vardek "Photo Frame" widget. Sandboxed widgets
can only load same-origin images from their own dir, so this daemon downscales
photos from a source folder into ../img/ (JPEG, longest side ~1600px, HEIC ok via
sips) and writes ../data.js with the frame list. Incremental: unchanged sources
keep their cached frame. Command: `serve` (rescan loop) or `once`.

Config: ../photoframe.json  {folder, maxImages, longestSide, recurse}.
Python 3.9 / system python, no deps.
"""
import glob, hashlib, json, os, subprocess, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img")
DATA_JS = os.path.join(WIDGET, "data.js")
DATA_JSON = os.path.join(WIDGET, "data.json")
CONF = os.path.join(WIDGET, "photoframe.json")
CACHE = os.path.join(WIDGET, ".photocache.json")
LOG = os.path.expanduser("~/Library/Logs/photod.log")
EXTS = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".webp", ".tif", ".tiff")

DEFAULTS = {"folder": "~/Pictures", "maxImages": 40, "longestSide": 1600, "recurse": False, "rescanSec": 300}


def log(m):
    line = "%s %s\n" % (datetime.now().strftime("%H:%M:%S"), m)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True); open(LOG, "a").write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def load_conf():
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


def find_sources(conf):
    folder = os.path.expanduser(conf["folder"])
    if not os.path.isdir(folder):
        return []
    pats = []
    for e in EXTS:
        pats.append(os.path.join(folder, "*" + e)); pats.append(os.path.join(folder, "*" + e.upper()))
        if conf.get("recurse"):
            pats.append(os.path.join(folder, "**", "*" + e)); pats.append(os.path.join(folder, "**", "*" + e.upper()))
    files = []
    for p in pats:
        files.extend(glob.glob(p, recursive=conf.get("recurse", False)))
    files = list(dict.fromkeys(files))
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files[: conf["maxImages"]]


def frame_name(src):
    return "p_" + hashlib.sha1(src.encode()).hexdigest()[:14] + ".jpg"


def collect(conf):
    os.makedirs(IMG, exist_ok=True)
    try:
        cache = json.load(open(CACHE))
    except (OSError, ValueError):
        cache = {}
    srcs = find_sources(conf)
    frames, keep = [], set()
    for src in srcs:
        try:
            st = os.stat(src)
        except OSError:
            continue
        fn = frame_name(src); out = os.path.join(IMG, fn); keep.add(fn)
        sig = "%d:%d" % (int(st.st_mtime), st.st_size)
        if cache.get(src, {}).get("sig") == sig and os.path.exists(out):
            pass  # already rendered
        else:
            r = subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", "-Z", str(conf["longestSide"]),
                                src, "--out", out], capture_output=True, text=True, timeout=40)
            if r.returncode != 0 or not os.path.exists(out):
                log("sips failed for %s: %s" % (os.path.basename(src), (r.stderr or "").strip()[:120]))
                continue
            cache[src] = {"sig": sig, "frame": fn}
        frames.append({"file": "img/" + fn, "name": os.path.splitext(os.path.basename(src))[0],
                       "date": datetime.fromtimestamp(st.st_mtime).strftime("%b %-d, %Y")})
    # prune frames no longer referenced + stale cache entries
    for f in glob.glob(os.path.join(IMG, "p_*.jpg")):
        if os.path.basename(f) not in keep:
            try: os.remove(f)
            except OSError: pass
    for src in list(cache.keys()):
        if src not in {s for s in srcs}:
            cache.pop(src, None)
    try:
        json.dump(cache, open(CACHE, "w"))
    except OSError:
        pass
    return {"generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "folder": conf["folder"], "count": len(frames), "frames": frames}


def write(d):
    b = json.dumps(d, separators=(",", ":"))
    for path, wrap in ((DATA_JS, True), (DATA_JSON, False)):
        open(path + ".tmp", "w").write(("window.__PHOTOS__=" + b + ";\n") if wrap else b)
        os.replace(path + ".tmp", path)


def run_once():
    conf = load_conf(); d = collect(conf); write(d); return d


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start")
        while True:
            try:
                conf = load_conf(); write(collect(conf))
            except Exception as e:
                log("loop error: %s" % e)
            time.sleep(max(60, load_conf().get("rescanSec", 300)))
    else:
        d = run_once(); print(json.dumps({k: (v if k != "frames" else len(v)) for k, v in d.items()}, indent=1))
