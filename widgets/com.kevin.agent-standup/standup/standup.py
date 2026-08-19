#!/usr/bin/env python3
"""
standup — the AI Standup generator for the Vardek "Agent Standup" widget.

A small meta-agent: it reads the live state of every agent-deck session (from
the Agent Control widget's data.json, which its loop refreshes every ~5s), and
asks the local `claude` CLI (headless, Haiku — uses your Claude subscription, no
API key) to write a plain-English brief: who needs you and why, who's running
clean, who's idle. The digest is written to ../data.js for the sandboxed widget
to <script src>-load.

Cost control: the model is called only when the session state actually changed
(hash of statuses + pane snippets), and no more often than `minIntervalSec`.
Between changes the widget just re-reads the last digest — zero tokens.

Commands
  serve    KeepAlive loop: poll state, regenerate when it changes, write data.js
  once     one generation pass (prints the digest)
  probe    print the current session inputs without calling the model

Config: ../standup.json  (model, cadence, cwd, source path). Python 3.9, no deps.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
WIDGET_DIR = os.path.dirname(HERE)
DATA_JS = os.path.join(WIDGET_DIR, "data.js")
DATA_JSON = os.path.join(WIDGET_DIR, "data.json")
CONF = os.path.join(WIDGET_DIR, "standup.json")
STATE = os.path.join(WIDGET_DIR, ".state.json")
LOG = os.path.expanduser("~/Library/Logs/agent-standup.log")

# Agent Control writes this every ~5s; it's our raw input.
AGENTCTL_DATA = os.path.expanduser(
    "~/Library/Application Support/Vardek/widgets/com.kevin.agent-control/data.json")
AGENTCTL_PY = os.path.expanduser(
    "~/Library/Application Support/Vardek/widgets/com.kevin.agent-control/agentctl/agentctl.py")

DEFAULTS = {
    "model": "claude-haiku-4-5",
    "pollSeconds": 8,          # how often to check whether state changed
    "minIntervalSec": 90,      # floor between model calls (cost guard)
    "maxAgeSec": 1800,         # force a refresh at least this often
    "cwd": "/tmp",             # neutral cwd → no project CLAUDE.md / skills loaded
    "maxSessions": 26,         # cap sessions sent to the model
    "timeoutSec": 90,
}

SYS = (
    "You summarize a developer's fleet of terminal coding-agent sessions for a "
    "glanceable status panel. Return ONLY minified JSON, no prose, no code fences, "
    "matching exactly:\n"
    '{"headline":string,"attention":[{"id":string,"title":string,"tool":string,"reason":string}],'
    '"running":[string],"idle":[string]}\n'
    "Rules:\n"
    "- attention: sessions waiting on the human or showing an error/failure. "
    "reason <= 90 chars, plain English, say concretely what it wants or what broke. "
    "Read the snippet lines; a line starting with the prompt char is usually the human's own "
    "last message, so infer what the agent is now asking for. Do NOT invent facts.\n"
    "- running: titles of sessions actively working (status running).\n"
    "- idle: titles of alive sessions that are quiet.\n"
    "- headline: <= 60 chars, lead with what needs the human, e.g. '2 agents need you'.\n"
    "- Order attention most-urgent first. Keep every string terse. Use the exact id/title/tool given."
)


def log(msg):
    line = "%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(line)
    except OSError:
        pass
    sys.stderr.write(line)


def load_conf():
    conf = dict(DEFAULTS)
    try:
        with open(CONF) as f:
            conf.update(json.load(f))
    except (OSError, ValueError):
        pass
    # keep the file present/complete for the user to edit
    try:
        if not os.path.exists(CONF):
            with open(CONF, "w") as f:
                json.dump(conf, f, indent=2)
    except OSError:
        pass
    return conf


def which_claude():
    for p in (os.path.expanduser("~/.local/bin/claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"):
        if os.path.exists(p):
            return p
    return "claude"


# ---------------------------------------------------------------------------
# inputs

def read_sessions(conf):
    """Live session list from Agent Control's data.json (fresh) or a fallback collect."""
    data = None
    try:
        age = time.time() - os.path.getmtime(AGENTCTL_DATA)
        if age < 30:
            with open(AGENTCTL_DATA) as f:
                data = json.load(f)
    except (OSError, ValueError):
        data = None
    if data is None and os.path.exists(AGENTCTL_PY):
        try:
            r = subprocess.run(["/usr/bin/python3", AGENTCTL_PY, "collect"],
                               capture_output=True, text=True, timeout=40)
            data = json.loads(r.stdout)
        except Exception as e:
            log("fallback collect failed: %s" % e)
    if data is None:
        return [], {"waiting": 0, "running": 0, "idle": 0, "error": 0, "stopped": 0}, None
    sessions = data.get("sessions", [])
    counts = dict(data.get("sessionCounts", {}))
    counts["stopped"] = sum(1 for s in sessions if not s.get("alive"))
    return sessions, counts, data.get("generatedAt")


def compact_for_model(sessions, cap):
    """Only alive sessions matter for a standup; trim to what the model needs."""
    alive = [s for s in sessions if s.get("alive")]
    # waiting first, then running, then idle — so the cap keeps the important ones
    rank = {"waiting": 0, "running": 1, "idle": 2}
    alive.sort(key=lambda s: rank.get(s.get("status"), 3))
    out = []
    for s in alive[:cap]:
        snip = s.get("snippet") or []
        out.append({
            "id": (s.get("id") or "")[:12],
            "title": s.get("title") or "session",
            "tool": s.get("tool") or "",
            "status": s.get("status") or "",
            "snippet": [str(x)[:140] for x in snip[-2:]],
        })
    return out


def state_hash(compact):
    h = hashlib.sha1()
    for s in compact:
        h.update((s["id"] + "|" + s["status"] + "|" + "¦".join(s["snippet"])).encode("utf-8", "replace"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# model call

def strip_fence(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    # grab the outermost JSON object if the model added stray words
    a, b = t.find("{"), t.rfind("}")
    return t[a:b + 1] if a >= 0 and b > a else t


def call_model(conf, compact):
    claude = which_claude()
    prompt = SYS + "\n\nSessions:\n" + json.dumps(compact, separators=(",", ":"))
    mcp = os.path.join(HERE, ".empty-mcp.json")
    try:
        if not os.path.exists(mcp):
            with open(mcp, "w") as f:
                json.dump({"mcpServers": {}}, f)
    except OSError:
        mcp = None
    args = [claude, "-p", prompt, "--model", conf["model"], "--output-format", "json"]
    if mcp:
        args += ["--strict-mcp-config", "--mcp-config", mcp]
    env = dict(os.environ)
    env["PATH"] = os.path.expanduser("~/.local/bin") + ":/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "/usr/bin:/bin")
    r = subprocess.run(args, capture_output=True, text=True, timeout=conf["timeoutSec"],
                       cwd=conf.get("cwd") if os.path.isdir(conf.get("cwd", "")) else None, env=env)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:300] or "claude exited %d" % r.returncode)
    env_obj = json.loads(r.stdout)
    if env_obj.get("is_error"):
        raise RuntimeError(str(env_obj.get("result", ""))[:200])
    body = strip_fence(env_obj.get("result", ""))
    digest = json.loads(body)
    return digest, env_obj.get("total_cost_usd"), env_obj.get("duration_ms")


def sanitize(digest, valid_ids):
    def s(x):
        return str(x) if x is not None else ""
    att = []
    for a in (digest.get("attention") or [])[:12]:
        if not isinstance(a, dict):
            continue
        att.append({"id": s(a.get("id"))[:12], "title": s(a.get("title"))[:60],
                    "tool": s(a.get("tool"))[:12], "reason": s(a.get("reason"))[:140]})
    running = [s(x)[:60] for x in (digest.get("running") or [])][:20]
    idle = []
    for x in (digest.get("idle") or [])[:20]:
        idle.append(s(x.get("title"))[:60] if isinstance(x, dict) else s(x)[:60])
    return {"headline": s(digest.get("headline"))[:80], "attention": att, "running": running, "idle": idle}


# ---------------------------------------------------------------------------
# write + loop

def write_data(payload):
    body = json.dumps(payload, separators=(",", ":"))
    for path, wrap in ((DATA_JS, True), (DATA_JSON, False)):
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(("window.__STANDUP__=" + body + ";\n") if wrap else body)
        os.replace(tmp, path)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    try:
        with open(STATE + ".tmp", "w") as f:
            json.dump(st, f)
        os.replace(STATE + ".tmp", STATE)
    except OSError:
        pass


def generate(conf, st, force=False):
    sessions, counts, src_ts = read_sessions(conf)
    compact = compact_for_model(sessions, conf["maxSessions"])
    h = state_hash(compact)
    now = time.time()
    last_digest = st.get("digest")
    changed = h != st.get("hash")
    stale = (now - st.get("lastLLMAt", 0)) > conf["maxAgeSec"]
    throttled = (now - st.get("lastLLMAt", 0)) < conf["minIntervalSec"]

    degraded = None
    cost = st.get("lastCost")
    if last_digest is None or force or ((changed or stale) and not throttled):
        if not compact:
            digest = {"headline": "No live agent sessions", "attention": [], "running": [], "idle": []}
        else:
            try:
                raw, cost, dur = call_model(conf, compact)
                digest = sanitize(raw, {s["id"] for s in compact})
                # attach the real last pane lines to each attention item (tap-to-expand
                # in the widget), matched by id or title against the model's input
                by_id = {s["id"]: s for s in compact}
                by_title = {s["title"]: s for s in compact}
                for a in digest["attention"]:
                    src = by_id.get(a["id"]) or by_title.get(a["title"])
                    if src and src.get("snippet"):
                        a["detail"] = "\n".join(src["snippet"])
                st["lastLLMAt"] = now
                log("digest ok: %d attention, cost $%.4f, %sms" %
                    (len(digest["attention"]), cost or 0, dur))
            except Exception as e:
                log("model call failed: %s" % e)
                digest = last_digest or {"headline": "Standup unavailable", "attention": [], "running": [], "idle": []}
                degraded = str(e)[:160]
        st["hash"] = h
        st["digest"] = digest
        st["lastCost"] = cost
    else:
        digest = last_digest

    payload = dict(digest)
    payload.update({
        "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "counts": {"waiting": counts.get("waiting", 0), "running": counts.get("running", 0),
                   "idle": counts.get("idle", 0), "stopped": counts.get("stopped", 0),
                   "alive": sum(1 for s in sessions if s.get("alive"))},
        "model": conf["model"],
        "lastModelAt": datetime.fromtimestamp(st.get("lastLLMAt", 0), tz=timezone.utc).isoformat().replace("+00:00", "Z") if st.get("lastLLMAt") else None,
        "lastCost": cost,
        "degraded": degraded,
        "sourceAt": src_ts,
    })
    write_data(payload)
    save_state(st)
    return payload


def serve():
    conf = load_conf()
    log("serve: start (poll %ss, min-interval %ss, model %s)" % (conf["pollSeconds"], conf["minIntervalSec"], conf["model"]))
    st = load_state()
    # always refresh the header timestamp each poll; only call the model when needed
    while True:
        try:
            conf = load_conf()
            generate(conf, st)
        except Exception as e:
            log("loop error: %s" % e)
        time.sleep(max(3, conf.get("pollSeconds", 8)))


def main(argv):
    if len(argv) > 1 and argv[1] == "serve":
        serve()
    elif len(argv) > 1 and argv[1] == "probe":
        conf = load_conf()
        sessions, counts, ts = read_sessions(conf)
        print(json.dumps({"counts": counts, "sourceAt": ts,
                          "compact": compact_for_model(sessions, conf["maxSessions"])}, indent=1))
    else:  # once
        conf = load_conf()
        st = load_state()
        print(json.dumps(generate(conf, st, force=("--force" in argv)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
