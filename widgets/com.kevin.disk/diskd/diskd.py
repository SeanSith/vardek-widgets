#!/usr/bin/env python3
"""diskd — write disk-volume usage to ../data.js for the Vardek Disk widget.
Uses `df -k`; computes real APFS usage as total-avail (df's "used" only counts the
system snapshot). Run as a StartInterval LaunchAgent (single shot) or `serve`."""
import json, os, subprocess, sys, time
from datetime import datetime, timezone
HERE=os.path.dirname(os.path.abspath(__file__)); WIDGET=os.path.dirname(HERE)
DATA_JS=os.path.join(WIDGET,"data.js"); DATA_JSON=os.path.join(WIDGET,"data.json")
SKIP_PREFIX=("/System/Volumes/","/Library/Developer/","/private/")
def collect():
    out=subprocess.run(["/bin/df","-k"],capture_output=True,text=True,timeout=15).stdout
    vols=[]
    for line in out.splitlines()[1:]:
        p=line.split()
        if len(p)<9 or not p[0].startswith("/dev/disk"): continue
        total=int(p[1])*1024; avail=int(p[3])*1024; mount=" ".join(p[8:])
        if mount!="/" and any(mount.startswith(x) for x in SKIP_PREFIX): continue
        if mount!="/" and total < 2*1024**3: continue  # skip tiny DMG installers
        used=max(0,total-avail); pct=round(used/total*100) if total else 0
        name="Macintosh HD" if mount=="/" else (mount.split("/")[-1] or mount)
        kind="internal" if (mount=="/" ) else ("external" if mount.startswith("/Volumes/") else "other")
        vols.append({"name":name,"mount":mount,"total":total,"used":used,"avail":avail,"pct":pct,"kind":kind})
    # de-dup by (name,total); keep the internal root first
    seen=set(); uniq=[]
    for v in sorted(vols,key=lambda x:(x["kind"]!="internal",x["name"])):
        k=(v["name"],v["total"])
        if k in seen: continue
        seen.add(k); uniq.append(v)
    return {"generatedAt":datetime.now(tz=timezone.utc).isoformat().replace("+00:00","Z"),"volumes":uniq}
def write(d):
    b=json.dumps(d,separators=(",",":"))
    for path,wrap in ((DATA_JS,True),(DATA_JSON,False)):
        open(path+".tmp","w").write(("window.__DISK__="+b+";\n") if wrap else b); os.replace(path+".tmp",path)
if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="serve":
        while True:
            try: write(collect())
            except Exception as e: sys.stderr.write(str(e)+"\n")
            time.sleep(120)
    else:
        d=collect(); write(d); print(json.dumps(d,indent=1))
