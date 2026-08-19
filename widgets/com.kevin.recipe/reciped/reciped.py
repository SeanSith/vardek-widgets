#!/usr/bin/env python3
"""reciped — fetches random meals from TheMealDB for the Vardek "Recipe" widget.
Downloads meal photos into ../img/ and writes ../data.js. serve|once."""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img"); DATA_JS = os.path.join(WIDGET, "data.js")
CONF = os.path.join(WIDGET, "recipe.json"); LOG = os.path.expanduser("~/Library/Logs/reciped.log")
DEFAULTS = {"count": 8}


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
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-reciped"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def fields(m):
    ings = []
    for i in range(1, 21):
        ing = (m.get("strIngredient%d" % i) or "").strip()
        meas = (m.get("strMeasure%d" % i) or "").strip()
        if ing:
            ings.append((meas + " " + ing).strip())
    return {"id": m["idMeal"], "name": m["strMeal"], "category": m.get("strCategory", ""),
            "area": m.get("strArea", ""), "ingredients": ings,
            "instructions": (m.get("strInstructions") or "").strip(), "thumb": m.get("strMealThumb", "")}


def collect():
    c = conf(); os.makedirs(IMG, exist_ok=True)
    meals, seen, tries = [], set(), 0
    while len(meals) < c["count"] and tries < c["count"] * 3:
        tries += 1
        try:
            data = json.loads(get("https://www.themealdb.com/api/json/v1/1/random.php").decode())
        except Exception as e:
            log("fetch err: %s" % e); continue
        m = fields(data["meals"][0])
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        if m["thumb"]:
            fn = "meal_" + m["id"] + ".jpg"; out = os.path.join(IMG, fn)
            if not os.path.exists(out):
                try:
                    tmp = out + ".src"; open(tmp, "wb").write(get(m["thumb"]))
                    subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", "-Z", "800", tmp, "--out", out],
                                   capture_output=True, text=True, timeout=40)
                    if not os.path.exists(out): os.replace(tmp, out)
                    else: os.remove(tmp)
                except Exception as e:
                    log("img err: %s" % e); continue
            m["file"] = "img/" + fn
        m.pop("thumb", None)
        meals.append(m); time.sleep(0.3)
    keep = {"meal_" + m["id"] + ".jpg" for m in meals}
    for f in os.listdir(IMG):
        if f.startswith("meal_") and f not in keep:
            try: os.remove(os.path.join(IMG, f))
            except OSError: pass
    return {"generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"), "count": len(meals), "meals": meals}


def write(d):
    open(DATA_JS + ".tmp", "w").write("window.__RECIPES__=" + json.dumps(d, separators=(",", ":")) + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start")
        while True:
            try: write(collect())
            except Exception as e: log("loop error: %s" % e)
            time.sleep(3600)
    else:
        d = collect(); write(d); print(json.dumps({"count": d["count"], "sample": [m["name"] for m in d["meals"][:5]]}, indent=1))
