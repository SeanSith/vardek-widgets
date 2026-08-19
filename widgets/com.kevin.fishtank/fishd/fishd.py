#!/usr/bin/env python3
"""
fishd — the decentralized fish-tank daemon for the Vardek "Fish Tank" widget.

Each running tank is a peer. Fish are unique (id + name + attribute combo) and
migrate between tanks by a **two-phase handoff over a shared directory** — a
local dir for multiple tanks on one Mac, or a Dropbox/iCloud-synced folder for
tanks on different machines (that's the "decentralized, elsewhere" transport: no
server, no ports, just a synced filesystem as the rendezvous).

Safety invariant — a fish can NEVER disappear until the handoff is confirmed:

    source                                   target
    ── lock fish (departing), write OFFER ─▶  create fish as provisional (arriving)
       (fish still resident here)             (fish now present here too)
                                     ◀── ACK  accepted
    ── delete fish, write COMMIT ─────────▶   mark fish resident (arrived)

  * source deletes its copy only AFTER the ACK, so the fish is resident in ≥1
    tank at every instant (a brief in-transit overlap is fine — a lost fish is not).
  * no ACK by the deadline  → source unlocks the fish; it simply stayed.
  * no COMMIT by the deadline → target discards the provisional; it never arrived.
  * txn ids make every step idempotent; a crash re-locks/reaps on restart.

Commands
  serve     the daemon loop (heartbeat presence, drain inbox, attempt migrations,
            write ../data.js for the widget)
  seed N    stock the tank with N fresh fish (only if empty, unless --force)
  status    print this node, its roster, and known peers
  once      run a single tick (for tests)

Config: ../fish.json.  Python 3.9 / system python, no dependencies.
"""

import hashlib
import json
import os
import random
import socket
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET_DIR = os.path.dirname(HERE)
DATA_JS = os.path.join(WIDGET_DIR, "data.js")
DATA_JSON = os.path.join(WIDGET_DIR, "data.json")
CONF = os.path.join(WIDGET_DIR, "fish.json")
STATE = os.path.join(WIDGET_DIR, ".fishstate.json")
LOG = os.path.expanduser("~/Library/Logs/fishtank.log")

# time is passed in / read from the clock only in the daemon (never in workflow land)
def now():
    return time.time()


def default_shared():
    for c in ("~/Cloud/Dropbox/.fishtank", "~/Library/Mobile Documents/com~apple~CloudDocs/.fishtank"):
        p = os.path.expanduser(c)
        parent = os.path.dirname(p)
        if os.path.isdir(parent):
            return p
    return os.path.expanduser("~/Library/Application Support/Vardek/.fishtank-shared")


DEFAULTS = {
    "nodeName": socket.gethostname().split(".")[0] + "-tank",
    "sharedDir": None,               # set on first run to default_shared()
    "capacity": 12,                  # max fish this tank holds
    "seedCount": 6,                  # fish to stock an empty tank with
    "migrateEverySec": 45,           # attempt a handoff this often (when peers exist)
    "migrateChance": 0.6,            # probability of actually sending on each attempt
    "peerTimeoutSec": 25,            # a peer older than this (no heartbeat) is dead
    "handoffDeadlineSec": 40,        # give up an in-flight handoff after this
    "heartbeatSec": 6,
    "pollSec": 3,
}

SPECIES = ["guppy", "betta", "angelfish", "goldfish", "tetra", "clownfish", "koi", "discus", "molly", "gourami"]
PATTERNS = ["solid", "striped", "spotted", "gradient"]
FINS = ["round", "flowing", "spiky", "fan"]
PERSONALITY = ["darter", "glider", "bottom", "hoverer", "schooler"]
ADJ = ["Sir", "Captain", "Lady", "Baron", "Professor", "Little", "Big", "Admiral", "Duke", "Miss",
       "Bubbles", "Sunny", "Shadow", "Gilbert", "Finn", "Coral", "Marlin", "Nemo", "Wanda", "Pearl",
       "Sushi", "Waffles", "Mango", "Pepper", "Blueberry", "Ziggy", "Moxie", "Tango", "Biscuit", "Noodle"]
NOUN = ["Fins", "Gill", "Splash", "Scales", "Bubble", "Tail", "Wave", "Reef", "Current", "Guppy",
        "McSwim", "Flipper", "the Fish", "O'Fish", "Gulliver", "Nibbles", "Sardine", "Anchovy", "Kelp", "Tide"]


def log(msg):
    line = "%s [%s] %s\n" % (datetime.now().strftime("%H:%M:%S"), os.getpid(), msg)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def rid(n=10):
    return hashlib.sha1(("%f-%f-%d" % (now(), random.random(), os.getpid())).encode()).hexdigest()[:n]


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# config / state

def load_conf():
    conf = dict(DEFAULTS)
    try:
        with open(CONF) as f:
            conf.update(json.load(f))
    except (OSError, ValueError):
        pass
    if not conf.get("sharedDir"):
        conf["sharedDir"] = default_shared()
    try:
        with open(CONF, "w") as f:
            json.dump(conf, f, indent=2)
    except OSError:
        pass
    return conf


def atomic_write(path, text):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def load_state():
    try:
        with open(STATE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {}
    st.setdefault("nodeId", rid(12))
    st.setdefault("fish", {})        # id -> fish dict
    st.setdefault("txns", {})        # txnId -> {fishId, target, deadline}
    st.setdefault("seenMsgs", [])    # processed message ids (bounded)
    st.setdefault("events", [])      # recent human events for the widget
    return st


def save_state(st):
    atomic_write(STATE, json.dumps(st))


def event(st, kind, text):
    st["events"].append({"t": iso(now()), "kind": kind, "text": text})
    st["events"] = st["events"][-24:]
    log("%s: %s" % (kind, text))


# ---------------------------------------------------------------------------
# fish

def make_fish(node_id, node_name):
    fid = rid(12)
    name = random.choice(ADJ) + " " + random.choice(NOUN)
    return {
        "id": fid,
        "name": name,
        "species": random.choice(SPECIES),
        "hue": random.randint(0, 359),
        "sat": random.randint(55, 95),
        "size": round(random.uniform(0.72, 1.45), 2),
        "speed": round(random.uniform(0.6, 1.6), 2),
        "pattern": random.choice(PATTERNS),
        "fin": random.choice(FINS),
        "personality": random.choice(PERSONALITY),
        "bornNode": node_name,
        "bornAt": iso(now()),
        "hops": 0,                      # how many tanks it has visited
        "state": "resident",            # resident | departing | provisional
    }


# ---------------------------------------------------------------------------
# shared-dir transport (presence + message inboxes)

def shared_paths(conf):
    root = os.path.expanduser(conf["sharedDir"])
    return {
        "root": root,
        "nodes": os.path.join(root, "nodes"),
        "inbox": os.path.join(root, "inbox"),
    }


def ensure_dirs(conf, st):
    p = shared_paths(conf)
    for d in (p["root"], p["nodes"], os.path.join(p["inbox"], st["nodeId"])):
        os.makedirs(d, exist_ok=True)


def heartbeat(conf, st):
    p = shared_paths(conf)
    residents = [f for f in st["fish"].values() if f["state"] in ("resident", "departing")]
    doc = {"id": st["nodeId"], "name": conf["nodeName"], "pid": os.getpid(),
           "updatedAt": now(), "capacity": conf["capacity"], "count": len(residents)}
    atomic_write(os.path.join(p["nodes"], st["nodeId"] + ".json"), json.dumps(doc))


def read_peers(conf, st):
    p = shared_paths(conf)
    peers = {}
    try:
        files = os.listdir(p["nodes"])
    except OSError:
        return peers
    for fn in files:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(p["nodes"], fn)) as f:
                doc = json.load(f)
        except (OSError, ValueError):
            continue
        if doc.get("id") == st["nodeId"]:
            continue
        if now() - doc.get("updatedAt", 0) > conf["peerTimeoutSec"]:
            continue                     # stale/dead peer
        peers[doc["id"]] = doc
    return peers


def send_msg(conf, target_id, msg):
    p = shared_paths(conf)
    box = os.path.join(p["inbox"], target_id)
    os.makedirs(box, exist_ok=True)
    msg["msgId"] = rid(12)
    msg["sentAt"] = now()
    atomic_write(os.path.join(box, msg["msgId"] + ".json"), json.dumps(msg))


def drain_inbox(conf, st):
    p = shared_paths(conf)
    box = os.path.join(p["inbox"], st["nodeId"])
    try:
        files = sorted(os.listdir(box))
    except OSError:
        return
    seen = set(st["seenMsgs"])
    for fn in files:
        if not fn.endswith(".json"):
            continue
        path = os.path.join(box, fn)
        try:
            with open(path) as f:
                msg = json.load(f)
        except (OSError, ValueError):
            try: os.remove(path)
            except OSError: pass
            continue
        mid = msg.get("msgId", fn)
        if mid not in seen:
            try:
                handle_msg(conf, st, msg)
            except Exception as e:
                log("handle_msg error: %s" % e)
            seen.add(mid)
        try:
            os.remove(path)
        except OSError:
            pass
    st["seenMsgs"] = list(seen)[-400:]


# ---------------------------------------------------------------------------
# handoff protocol

def handle_msg(conf, st, msg):
    kind = msg.get("kind")
    if kind == "OFFER":
        fish = msg.get("fish") or {}
        fid = fish.get("id")
        txn = msg.get("txn")
        src = msg.get("from")
        residents = [f for f in st["fish"].values() if f["state"] != "provisional"]
        full = len(residents) >= conf["capacity"]
        if not fid or full or fid in st["fish"]:
            send_msg(conf, src, {"kind": "ACK", "txn": txn, "accepted": False,
                                 "from": st["nodeId"], "reason": "full" if full else "dup"})
            return
        # accept: hold as provisional (arriving) until COMMIT
        fish["state"] = "provisional"
        fish["arrivedFrom"] = msg.get("fromName")
        fish["provisionalDeadline"] = now() + conf["handoffDeadlineSec"]
        st["fish"][fid] = fish
        send_msg(conf, src, {"kind": "ACK", "txn": txn, "accepted": True, "from": st["nodeId"],
                             "toName": conf["nodeName"]})
        event(st, "incoming", "%s is swimming in from %s" % (fish.get("name"), fish.get("arrivedFrom") or "afar"))

    elif kind == "ACK":
        txn = msg.get("txn")
        t = st["txns"].get(txn)
        if not t:
            return
        fid = t["fishId"]
        f = st["fish"].get(fid)
        if msg.get("accepted"):
            # target holds a provisional copy. We now OWN it as "handedOff": we stop
            # rendering/counting it, but keep it for re-drive and send COMMIT. We do
            # NOT delete until the target confirms DONE — so it's never lost, and
            # since we've stopped rendering it, it's visible in exactly one tank.
            if f:
                f["state"] = "handedOff"; f.pop("departingDeadline", None)
            t["phase"] = "committing"; t["toName"] = msg.get("toName")
            send_msg(conf, t["target"], {"kind": "COMMIT", "txn": txn, "from": st["nodeId"], "fishId": fid})
        else:
            f = st["fish"].get(fid)             # declined — unlock, the fish stays
            if f:
                f["state"] = "resident"; f.pop("departingDeadline", None)
            del st["txns"][txn]

    elif kind == "COMMIT":
        fid = msg.get("fishId")
        txn = msg.get("txn")
        f = st["fish"].get(fid)
        if f and f["state"] == "provisional":
            f["state"] = "resident"
            f["hops"] = f.get("hops", 0) + 1
            f.pop("provisionalDeadline", None)
            f.pop("arrivedFrom", None)
        # DONE is idempotent: acknowledge even a duplicate COMMIT so the source can delete
        send_msg(conf, msg.get("from"), {"kind": "DONE", "txn": txn, "from": st["nodeId"], "fishId": fid})

    elif kind == "DONE":
        txn = msg.get("txn")
        t = st["txns"].get(txn)
        if not t:
            return
        f = st["fish"].pop(t["fishId"], None)   # target durably has it — now safe to delete
        del st["txns"][txn]
        if f:
            event(st, "outgoing", "%s swam off to %s" % (f.get("name"), t.get("toName") or "another tank"))


def start_handoff(conf, st, peers):
    # eligible = resident fish not already in a txn
    locked = {t["fishId"] for t in st["txns"].values()}
    pool = [f for f in st["fish"].values() if f["state"] == "resident" and f["id"] not in locked]
    if not pool or not peers:
        return
    # prefer to not drain below 1; only send if we have >=1 and target has room
    targets = [p for p in peers.values() if p.get("count", 0) < p.get("capacity", 0)]
    if not targets:
        return
    fish = random.choice(pool)
    peer = random.choice(targets)
    txn = rid(12)
    fish["state"] = "departing"
    fish["departingDeadline"] = now() + conf["handoffDeadlineSec"]
    st["txns"][txn] = {"fishId": fish["id"], "target": peer["id"], "deadline": now() + conf["handoffDeadlineSec"]}
    send_msg(conf, peer["id"], {"kind": "OFFER", "txn": txn, "from": st["nodeId"],
                                "fromName": conf["nodeName"], "fish": dict(fish)})
    log("offer %s -> %s (fish %s)" % (st["nodeId"][:6], peer["id"][:6], fish.get("name")))


def reap_timeouts(conf, st):
    t = now()
    for txn in list(st["txns"].keys()):
        tx = st["txns"][txn]
        if tx.get("phase") == "committing":
            # ACK received but no DONE yet — re-drive COMMIT until the target confirms.
            # We still own the fish (handedOff), so nothing is lost meanwhile.
            send_msg(conf, tx["target"], {"kind": "COMMIT", "txn": txn, "from": st["nodeId"], "fishId": tx["fishId"]})
            continue
        if t > tx["deadline"]:
            # offered but never ACKed → unlock the departing fish (it stayed)
            f = st["fish"].get(tx["fishId"])
            if f and f["state"] == "departing":
                f["state"] = "resident"; f.pop("departingDeadline", None)
                event(st, "reclaim", "%s couldn't reach the other tank; it stayed" % f.get("name"))
            del st["txns"][txn]
    # target side: a provisional that never got COMMIT → discard (source still owns it,
    # and will re-drive if it truly handed off; dropping here avoids a duplicate)
    for fid in list(st["fish"].keys()):
        f = st["fish"][fid]
        if f["state"] == "provisional" and t > f.get("provisionalDeadline", t + 1):
            st["fish"].pop(fid, None)


# ---------------------------------------------------------------------------
# output for the widget

def write_data(conf, st, peers):
    # handedOff fish are owned by us for re-drive but already visible in the target tank,
    # so we hide them here — the fish shows in exactly one tank.
    shown = [f for f in st["fish"].values() if f["state"] != "handedOff"]
    residents = [f for f in shown if f["state"] != "provisional"]
    payload = {
        "generatedAt": iso(now()),
        "node": {"id": st["nodeId"], "name": conf["nodeName"], "capacity": conf["capacity"]},
        "fish": [
            {k: f[k] for k in ("id", "name", "species", "hue", "sat", "size", "speed",
                               "pattern", "fin", "personality", "bornNode", "hops", "state")}
            for f in shown
        ],
        "peers": [{"name": p["name"], "count": p.get("count", 0), "capacity": p.get("capacity", 0)}
                  for p in peers.values()],
        "counts": {"resident": len(residents), "total": len(st["fish"]),
                   "departing": sum(1 for f in st["fish"].values() if f["state"] == "departing"),
                   "arriving": sum(1 for f in st["fish"].values() if f["state"] == "provisional")},
        "events": st["events"][-8:],
        "sharedDir": conf["sharedDir"],
    }
    body = json.dumps(payload, separators=(",", ":"))
    atomic_write(DATA_JS, "window.__FISHTANK__=" + body + ";\n")
    atomic_write(DATA_JSON, body)


# ---------------------------------------------------------------------------
# lifecycle

def recover(conf, st):
    """On startup, resolve half-finished handoffs so a fish is never lost or duplicated.
    Rule: the SOURCE owns a fish until it gets DONE. So:
      - departing (offered, no ACK)      → resident   (it never left)
      - handedOff (ACKed, awaiting DONE)  → keep + re-drive COMMIT; not rendered until gone
      - provisional (accepted, no COMMIT) → drop        (source still owns it; avoids a dup)
    """
    keep_txns = {}
    for f in list(st["fish"].values()):
        if f["state"] == "departing":
            f["state"] = "resident"; f.pop("departingDeadline", None)
        elif f["state"] == "provisional":
            st["fish"].pop(f["id"], None)
    # rebuild txns only for fish we still hold as handedOff (re-drive their COMMIT)
    for txn, tx in st.get("txns", {}).items():
        f = st["fish"].get(tx.get("fishId"))
        if f and f["state"] == "handedOff":
            tx["phase"] = "committing"
            tx["deadline"] = now() + conf["handoffDeadlineSec"]
            keep_txns[txn] = tx
    st["txns"] = keep_txns


def seed_if_empty(conf, st, force=False):
    if st["fish"] and not force:
        return
    n = conf["seedCount"]
    for _ in range(n):
        f = make_fish(st["nodeId"], conf["nodeName"])
        st["fish"][f["id"]] = f
    event(st, "seed", "stocked the tank with %d fish" % n)


def tick(conf, st, peers, last):
    t = now()
    if t - last.get("hb", 0) >= conf["heartbeatSec"]:
        heartbeat(conf, st); last["hb"] = t
    drain_inbox(conf, st)
    reap_timeouts(conf, st)
    if t - last.get("mig", 0) >= conf["migrateEverySec"]:
        last["mig"] = t
        if peers and random.random() < conf["migrateChance"]:
            start_handoff(conf, st, peers)
    write_data(conf, st, peers)


def serve():
    conf = load_conf()
    st = load_state()
    ensure_dirs(conf, st)
    recover(conf, st)
    seed_if_empty(conf, st)
    save_state(st)
    log("serve: node=%s id=%s shared=%s cap=%d fish=%d" %
        (conf["nodeName"], st["nodeId"][:6], conf["sharedDir"], conf["capacity"], len(st["fish"])))
    last = {}
    while True:
        try:
            conf = load_conf()
            ensure_dirs(conf, st)
            peers = read_peers(conf, st)
            tick(conf, st, peers, last)
            save_state(st)
        except Exception as e:
            log("loop error: %s" % e)
        time.sleep(max(1, conf.get("pollSec", 3)))


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "serve"
    if cmd == "serve":
        serve()
    elif cmd == "seed":
        conf = load_conf(); st = load_state(); ensure_dirs(conf, st)
        n = int(argv[2]) if len(argv) > 2 else conf["seedCount"]
        conf["seedCount"] = n
        seed_if_empty(conf, st, force=("--force" in argv))
        heartbeat(conf, st); peers = read_peers(conf, st); write_data(conf, st, peers); save_state(st)
        print("seeded; roster now %d" % len(st["fish"]))
    elif cmd == "status":
        conf = load_conf(); st = load_state(); ensure_dirs(conf, st)
        peers = read_peers(conf, st)
        print("node:", conf["nodeName"], st["nodeId"][:8], "| shared:", conf["sharedDir"])
        print("fish (%d):" % len(st["fish"]))
        for f in st["fish"].values():
            print("  %-18s %-10s hue%3d size%.2f %-9s hops%d [%s]" %
                  (f["name"], f["species"], f["hue"], f["size"], f["personality"], f.get("hops", 0), f["state"]))
        print("peers (%d):" % len(peers), ", ".join("%s(%d/%d)" % (p["name"], p.get("count", 0), p.get("capacity", 0)) for p in peers.values()))
    elif cmd == "once":
        conf = load_conf(); st = load_state(); ensure_dirs(conf, st)
        recover(conf, st); seed_if_empty(conf, st)
        peers = read_peers(conf, st); tick(conf, st, peers, {}); save_state(st)
        print("tick done; fish", len(st["fish"]), "peers", len(peers))
    else:
        raise SystemExit("usage: fishd.py [serve|seed N|status|once]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
