#!/usr/bin/env python3
"""
cocktaild — fetches random cocktails from TheCocktailDB for the Vardek "Cocktail"
widget. Sandboxed widgets can't load thecocktaildb.com images, so this downloads
drink thumbnails into ../img/ and writes ../data.js with the recipe list. serve|once.
"""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__)); WIDGET = os.path.dirname(HERE)
IMG = os.path.join(WIDGET, "img"); DATA_JS = os.path.join(WIDGET, "data.js")
CONF = os.path.join(WIDGET, "cocktail.json"); LOG = os.path.expanduser("~/Library/Logs/cocktaild.log")
DEFAULTS = {"count": 10}


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
    req = urllib.request.Request(url, headers={"User-Agent": "vardek-cocktaild"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def drink_fields(c):
    ings = []
    for i in range(1, 16):
        ing = (c.get("strIngredient%d" % i) or "").strip()
        meas = (c.get("strMeasure%d" % i) or "").strip()
        if ing:
            ings.append((meas + " " + ing).strip())
    return {"id": c["idDrink"], "name": c["strDrink"], "category": c.get("strCategory", ""),
            "glass": c.get("strGlass", ""), "alcoholic": c.get("strAlcoholic", ""),
            "ingredients": ings, "instructions": (c.get("strInstructions") or "").strip(),
            "thumb": c.get("strDrinkThumb", "")}


def collect():
    c = conf(); os.makedirs(IMG, exist_ok=True)
    drinks, seen = [], set()
    tries = 0
    while len(drinks) < c["count"] and tries < c["count"] * 3:
        tries += 1
        try:
            data = json.loads(get("https://www.thecocktaildb.com/api/json/v1/1/random.php").decode())
        except Exception as e:
            log("fetch err: %s" % e); continue
        d = drink_fields(data["drinks"][0])
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        if d["thumb"]:
            fn = "ck_" + d["id"] + ".jpg"; out = os.path.join(IMG, fn)
            if not os.path.exists(out):
                try:
                    tmp = out + ".src"; open(tmp, "wb").write(get(d["thumb"]))
                    subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", "-Z", "700", tmp, "--out", out],
                                   capture_output=True, text=True, timeout=40)
                    if not os.path.exists(out):
                        os.replace(tmp, out)
                    else:
                        os.remove(tmp)
                except Exception as e:
                    log("img err: %s" % e); continue
            d["file"] = "img/" + fn
        d.pop("thumb", None)
        drinks.append(d)
        time.sleep(0.3)
    keep = {"ck_" + d["id"] + ".jpg" for d in drinks}
    for f in os.listdir(IMG):
        if f.startswith("ck_") and f not in keep:
            try: os.remove(os.path.join(IMG, f))
            except OSError: pass
    return {"generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "count": len(drinks), "drinks": drinks}


def write(d):
    open(DATA_JS + ".tmp", "w").write("window.__COCKTAILS__=" + json.dumps(d, separators=(",", ":")) + ";\n")
    os.replace(DATA_JS + ".tmp", DATA_JS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        log("serve: start")
        while True:
            try: write(collect())
            except Exception as e: log("loop error: %s" % e)
            time.sleep(3600)
    else:
        d = collect(); write(d)
        print(json.dumps({"count": d["count"], "sample": [x["name"] for x in d["drinks"][:5]]}, indent=1))
