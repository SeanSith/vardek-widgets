#!/usr/bin/env python3
"""
AI CLI usage collector for the Vardek "AI Usage" widget.

Reads local session logs written by four coding CLIs and (optionally) the
CodexBar CLI for live subscription quota windows, then writes a small JSONP
file (data.js) next to the widget's index.html. The widget iframe is fully
sandboxed and can't read files or hit localhost, so this file is the bridge:
the widget just <script src="data.js"> loads it on every refresh.

Sources
  Claude Code  ~/.claude/projects/**/*.jsonl        message.usage per assistant record
  Codex CLI    ~/.codex/sessions/YYYY/MM/DD/*.jsonl token_count events (total deltas)
  Grok CLI     ~/.grok/sessions/*/*/updates.jsonl   turn_completed usage (+ costUsdTicks)
  Muse Code    ~/.local/share/muse/sessions/**/session.jsonl  model_completed usage
  Quotas       `codexbar usage --provider <p> --json` for claude / codex / grok

Runs fine on the system /usr/bin/python3 (3.9). No third-party deps.
Incremental: per-file aggregates are cached by (size, mtime) so a run only
re-parses files that changed since last time.
"""

import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
WIDGET_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(WIDGET_DIR, "data.js")
DATA_JSON = os.path.join(WIDGET_DIR, "data.json")
CACHE_DIR = os.path.join(HOME, "Library", "Caches", "com.kevin.ai-usage")
CACHE_FILE = os.path.join(CACHE_DIR, "cache.json")
PRICING_FILE = os.path.join(CACHE_DIR, "pricing.json")
LOG_FILE = os.path.join(HOME, "Library", "Logs", "ai-usage-collector.log")

LOOKBACK_DAYS = 30          # only parse files touched within this window
DAYS_IN_OUTPUT = 14         # sparkline length
PRICING_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PRICING_TTL = 24 * 3600
CODEXBAR_TIMEOUT = 75
CACHE_VERSION = 4

CLAUDE_DIR = os.path.join(HOME, ".claude", "projects")
CODEX_DIR = os.path.join(os.environ.get("CODEX_HOME", os.path.join(HOME, ".codex")), "sessions")
GROK_DIR = os.path.join(os.environ.get("GROK_HOME", os.path.join(HOME, ".grok")), "sessions")
MUSE_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local", "share")), "muse", "sessions")

CODEXBAR_CANDIDATES = [
    "/opt/homebrew/bin/codexbar",
    "/usr/local/bin/codexbar",
    "/Applications/CodexBar.app/Contents/MacOS/codexbar",
]

METRIC_KEYS = ("input", "output", "cacheRead", "cacheWrite", "reasoning", "calls", "cost")


def log(msg):
    line = "%s %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line)
    except OSError:
        pass
    sys.stderr.write(line)


# ---------------------------------------------------------------------------
# helpers

def local_day(ts):
    """epoch seconds -> 'YYYY-MM-DD' in the machine's local zone."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def parse_iso(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def empty_metrics():
    return {k: 0 for k in METRIC_KEYS}


def add_metrics(dst, src):
    for k in METRIC_KEYS:
        dst[k] = dst.get(k, 0) + src.get(k, 0)


def new_file_agg():
    return {"days": {}, "models": {}, "lastTs": 0, "sessions": {}}


def bump(agg, ts, model, m):
    """Add one usage sample (dict with METRIC_KEYS) to a per-file aggregate."""
    if not any(m.get(k) for k in ("input", "output", "cacheRead", "cacheWrite")):
        return  # empty sample (e.g. subagent snapshot with no calls) — nothing to record
    day = local_day(ts)
    d = agg["days"].setdefault(day, empty_metrics())
    add_metrics(d, m)
    mm = agg["models"].setdefault(model or "unknown", empty_metrics())
    add_metrics(mm, m)
    if ts >= agg["lastTs"]:
        agg["lastTs"] = ts
        agg["lastModel"] = model or None
    # per-day session presence (file == session for every CLI here)
    agg["sessions"][day] = True


def file_stat_key(path):
    st = os.stat(path)
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


# ---------------------------------------------------------------------------
# pricing (LiteLLM table, cached for a day). Cost is an API-list-price
# estimate — the CLIs here mostly run on subscriptions, but it's still the
# most legible "how much did I burn" number.

class Pricing:
    def __init__(self):
        self.table = {}
        self.loaded = False
        self.load()

    def load(self):
        try:
            if os.path.exists(PRICING_FILE) and time.time() - os.path.getmtime(PRICING_FILE) < PRICING_TTL:
                with open(PRICING_FILE) as f:
                    self.table = json.load(f)
                self.loaded = True
                return
        except (OSError, ValueError):
            pass
        try:
            req = urllib.request.Request(PRICING_URL, headers={"User-Agent": "ai-usage-collector/1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = json.load(r)
            # keep only what we need; the full file is ~2MB
            slim = {}
            for k, v in raw.items():
                if not isinstance(v, dict) or "input_cost_per_token" not in v:
                    continue
                slim[k] = {
                    "in": v.get("input_cost_per_token") or 0,
                    "out": v.get("output_cost_per_token") or 0,
                    "cr": v.get("cache_read_input_token_cost") or 0,
                    "cw": v.get("cache_creation_input_token_cost") or 0,
                }
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(PRICING_FILE, "w") as f:
                json.dump(slim, f)
            self.table = slim
            self.loaded = True
            log("pricing table refreshed (%d models)" % len(slim))
        except Exception as e:  # network down: fall back to whatever cache exists
            log("pricing fetch failed: %s" % e)
            try:
                with open(PRICING_FILE) as f:
                    self.table = json.load(f)
                self.loaded = True
            except (OSError, ValueError):
                self.loaded = False

    def lookup(self, model, provider):
        if not model or not self.table:
            return None
        prefixes = {
            "claude": ["", "anthropic/"],
            "codex": ["", "openai/", "azure/", "azure/us/"],
            "grok": ["xai/", ""],
            "muse": ["meta/", ""],
        }.get(provider, [""])
        for p in prefixes:
            hit = self.table.get(p + model)
            if hit:
                return hit
        # last resort: any key whose tail matches
        tail = "/" + model
        for k, v in self.table.items():
            if k.endswith(tail):
                return v
        return None

    def cost(self, model, provider, inp, out, cr, cw):
        """inp = uncached input tokens. Returns None if the model is unknown."""
        p = self.lookup(model, provider)
        if not p:
            return None
        return inp * p["in"] + out * p["out"] + cr * p["cr"] + cw * p["cw"]


# ---------------------------------------------------------------------------
# per-provider file parsers. Each returns a per-file aggregate dict.

def parse_claude(path, pricing):
    agg = new_file_agg()
    seen = {}  # (message.id, requestId) -> (ts, model, usage) with max output
    with open(path, "rb") as f:
        for line in f:
            if b'"usage"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            m = r.get("message")
            if not isinstance(m, dict):
                continue
            u = m.get("usage")
            if not isinstance(u, dict):
                continue
            model = m.get("model") or ""
            if model in ("<synthetic>", ""):
                continue
            ts = parse_iso(r.get("timestamp"))
            if ts is None:
                continue
            key = (m.get("id"), r.get("requestId")) if m.get("id") else (id(r), None)
            out = u.get("output_tokens") or 0
            prev = seen.get(key)
            if prev is None or out > prev[2].get("output_tokens", 0):
                seen[key] = (ts, model, u)
    for ts, model, u in seen.values():
        inp = u.get("input_tokens") or 0
        out = u.get("output_tokens") or 0
        cr = u.get("cache_read_input_tokens") or 0
        cw = u.get("cache_creation_input_tokens") or 0
        cost = pricing.cost(model, "claude", inp, out, cr, cw)
        bump(agg, ts, model, {
            "input": inp, "output": out, "cacheRead": cr, "cacheWrite": cw,
            "reasoning": ((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0),
            "calls": 1, "cost": cost or 0,
        })
        if cost is None:
            agg.setdefault("unpriced", {})[model] = True
    return agg


def parse_codex(path, pricing, want_rate_limits=False):
    agg = new_file_agg()
    model = None
    prev_total = None
    rate_limits = None
    with open(path, "rb") as f:
        for line in f:
            if b'"turn_context"' in line:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("type") == "turn_context":
                    model = (r.get("payload") or {}).get("model") or model
                continue
            if b'"token_count"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            p = r.get("payload") or {}
            if p.get("type") != "token_count":
                continue
            if want_rate_limits and p.get("rate_limits"):
                rate_limits = {"ts": parse_iso(r.get("timestamp")), "rate_limits": p["rate_limits"]}
            info = p.get("info")
            if not isinstance(info, dict):
                continue
            total = info.get("total_token_usage") or {}
            last = info.get("last_token_usage") or {}
            ts = parse_iso(r.get("timestamp"))
            if ts is None:
                continue
            fields = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                      "output_tokens", "reasoning_output_tokens")
            if prev_total is None:
                delta = {k: total.get(k) or 0 for k in fields}
            else:
                delta = {k: (total.get(k) or 0) - (prev_total.get(k) or 0) for k in fields}
                if any(v < 0 for v in delta.values()):
                    # counter reset (compaction / resumed session): trust the last-turn figure
                    delta = {k: last.get(k) or 0 for k in fields}
            prev_total = total
            if not any(delta.values()):
                continue  # duplicate emission (e.g. rate-limit-only update)
            # Codex "input_tokens" INCLUDES cached tokens; split them out.
            cached = delta["cached_input_tokens"]
            uncached = max(0, delta["input_tokens"] - cached)
            out = delta["output_tokens"]
            cw = delta["cache_write_input_tokens"]
            cost = pricing.cost(model, "codex", uncached, out, cached, cw)
            bump(agg, ts, model, {
                "input": uncached, "output": out, "cacheRead": cached, "cacheWrite": cw,
                "reasoning": delta["reasoning_output_tokens"], "calls": 1, "cost": cost or 0,
            })
            if cost is None:
                agg.setdefault("unpriced", {})[model or "unknown"] = True
    if want_rate_limits:
        agg["rateLimits"] = rate_limits
    return agg


def parse_grok(path, pricing):
    agg = new_file_agg()
    with open(path, "rb") as f:
        for line in f:
            if b'"turn_completed"' not in line or b'"usage"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            upd = ((r.get("params") or {}).get("update")) or {}
            if upd.get("sessionUpdate") != "turn_completed":
                continue
            u = upd.get("usage")
            if not isinstance(u, dict):
                continue
            ts = r.get("timestamp")
            if isinstance(ts, (int, float)):
                ts = float(ts) / (1000.0 if ts > 1e11 else 1.0)
            else:
                meta = r.get("_meta") or {}
                ts = (meta.get("agentTimestampMs") or 0) / 1000.0
            if not ts:
                continue
            per_model = u.get("modelUsage") or {}
            if not per_model:
                per_model = {"grok": u}
            for model, mu in per_model.items():
                inp_total = mu.get("inputTokens") or 0
                cr = mu.get("cachedReadTokens") or 0
                cw = mu.get("cacheCreationTokens") or 0
                out = mu.get("outputTokens") or 0
                ticks = mu.get("costUsdTicks")
                cost = (ticks / 1e10) if isinstance(ticks, (int, float)) else None
                if cost is None:
                    cost = pricing.cost(model, "grok", max(0, inp_total - cr), out, cr, cw)
                bump(agg, ts, model, {
                    "input": max(0, inp_total - cr), "output": out, "cacheRead": cr, "cacheWrite": cw,
                    "reasoning": mu.get("reasoningTokens") or 0,
                    "calls": mu.get("modelCalls") or 1, "cost": cost or 0,
                })
    return agg


def parse_muse(path, pricing):
    agg = new_file_agg()
    session_model = None
    subagents = {}  # subagent_id -> (ts, usage) latest cumulative snapshot
    with open(path, "rb") as f:
        for line in f:
            if b'"model_id"' in line and b'runtime.session.metadata' in line and session_model is None:
                try:
                    r = json.loads(line)
                    session_model = (((r.get("payload") or {}).get("record")) or {}).get("model_id")
                except ValueError:
                    pass
                continue
            is_call = b'"model_completed"' in line
            is_sub = b'"runtime_observed"' in line
            if not (is_call or is_sub):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ts = (r.get("recorded_at") or 0) / 1e6
            if not ts:
                continue
            payload = r.get("payload") or {}
            if is_call:
                ev = payload.get("event") or {}
                if ev.get("kind") != "model_completed":
                    continue
                u = ev.get("usage") or {}
                model = ev.get("model") or session_model
                _muse_bump(agg, ts, model, u, pricing)
            else:
                rec = payload.get("record") or {}
                if rec.get("kind") != "runtime_observed":
                    continue
                sid = rec.get("subagent_id")
                u = rec.get("usage") or {}
                if sid and isinstance(u, dict):
                    prev = subagents.get(sid)
                    if prev is None or (u.get("input_tokens") or 0) >= (prev[1].get("input_tokens") or 0):
                        subagents[sid] = (ts, u)
    for ts, u in subagents.values():
        _muse_bump(agg, ts, session_model, u, pricing, calls=0)
    return agg


def _muse_bump(agg, ts, model, u, pricing, calls=1):
    inp_total = u.get("input_tokens") or 0
    cr = u.get("cache_read_tokens") or u.get("cached_tokens") or 0
    cw = u.get("cache_write_tokens") or 0
    out = u.get("output_tokens") or 0
    inp = max(0, inp_total - cr)
    cost = pricing.cost(model, "muse", inp, out, cr, cw)
    bump(agg, ts, model, {
        "input": inp, "output": out, "cacheRead": cr, "cacheWrite": cw,
        "reasoning": u.get("reasoning_tokens") or 0, "calls": calls, "cost": cost or 0,
    })
    if cost is None:
        agg.setdefault("unpriced", {})[model or "unknown"] = True


# ---------------------------------------------------------------------------
# file discovery

def recent(paths, cutoff):
    out = []
    for p in paths:
        try:
            if os.path.getmtime(p) >= cutoff:
                out.append(p)
        except OSError:
            pass
    return out


def day_dirs_since(root, cutoff_date):
    """Yield YYYY/MM/DD dirs at or after cutoff_date (a date)."""
    for y in sorted(glob.glob(os.path.join(root, "[0-9][0-9][0-9][0-9]"))):
        for m in sorted(glob.glob(os.path.join(y, "[0-9][0-9]"))):
            for d in sorted(glob.glob(os.path.join(m, "[0-9][0-9]"))):
                try:
                    dt = datetime.strptime("/".join(d.split(os.sep)[-3:]), "%Y/%m/%d").date()
                except ValueError:
                    continue
                if dt >= cutoff_date:
                    yield d


def discover(cutoff_ts):
    cutoff_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).date()
    files = {"claude": [], "codex": [], "grok": [], "muse": []}
    if os.path.isdir(CLAUDE_DIR):
        files["claude"] = recent(glob.glob(os.path.join(CLAUDE_DIR, "**", "*.jsonl"), recursive=True), cutoff_ts)
    if os.path.isdir(CODEX_DIR):
        for d in day_dirs_since(CODEX_DIR, cutoff_date):
            files["codex"].extend(glob.glob(os.path.join(d, "*.jsonl")))
    if os.path.isdir(GROK_DIR):
        files["grok"] = recent(glob.glob(os.path.join(GROK_DIR, "*", "*", "updates.jsonl")), cutoff_ts)
    if os.path.isdir(MUSE_DIR):
        for d in day_dirs_since(MUSE_DIR, cutoff_date):
            files["muse"].extend(glob.glob(os.path.join(d, "*", "session.jsonl")))
    return files


# ---------------------------------------------------------------------------
# codexbar quotas

def find_codexbar():
    for c in CODEXBAR_CANDIDATES:
        if os.path.exists(c):
            return c
    for d in os.environ.get("PATH", "").split(":"):
        c = os.path.join(d, "codexbar")
        if os.path.exists(c):
            return c
    return None


def codexbar_usage(binary, provider):
    try:
        out = subprocess.run(
            [binary, "usage", "--provider", provider, "--json", "--no-color"],
            capture_output=True, text=True, timeout=CODEXBAR_TIMEOUT,
        )
        txt = out.stdout.strip()
        # codexbar may print notice lines before the JSON; find the array start
        start = txt.find("[")
        if start < 0:
            return None, "no json (%s)" % (out.stderr.strip()[:200] or "empty output")
        arr = json.loads(txt[start:])
        for e in arr:
            if e.get("provider") == provider:
                if e.get("error"):
                    return None, e["error"].get("message", "provider error")
                return e, None
        return None, "provider missing from output"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)


def window_label(minutes, fallback):
    if not minutes:
        return "Quota" if fallback in ("primary", "secondary", "tertiary") else fallback
    if minutes == 300:
        return "5-hour"
    if minutes == 10080:
        return "Weekly"
    if minutes == 1440:
        return "Daily"
    if minutes % 1440 == 0:
        return "%d-day" % (minutes // 1440)
    if minutes % 60 == 0:
        return "%d-hour" % (minutes // 60)
    return "%d-min" % minutes


def windows_from_codexbar(entry):
    """Normalise codexbar's usage block into a list of quota windows."""
    u = entry.get("usage") or {}
    wins = []

    def push(w, wid, title):
        if not isinstance(w, dict) or w.get("usedPercent") is None:
            return
        wins.append({
            "id": wid,
            "label": title or window_label(w.get("windowMinutes"), wid),
            "usedPercent": w.get("usedPercent"),
            "resetsAt": w.get("resetsAt"),
            "windowMinutes": w.get("windowMinutes"),
        })

    push(u.get("primary"), "primary", None)
    push(u.get("secondary"), "secondary", None)
    push(u.get("tertiary"), "tertiary", None)
    for x in u.get("extraRateWindows") or []:
        push(x.get("window"), x.get("id") or "extra", x.get("title"))
    # de-dup accidental duplicates (same label+reset)
    seen = set()
    uniq = []
    for w in wins:
        k = (w["label"], w.get("resetsAt"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(w)
    ident = u.get("identity") or {}
    plan = u.get("loginMethod") or ident.get("loginMethod") or entry.get("planType")
    return uniq, plan, u.get("accountEmail") or ident.get("accountEmail")


def windows_from_codex_log(rl):
    """Fallback: Codex's own rate_limits block from the newest session log."""
    if not rl:
        return [], None
    wins = []
    for key in ("primary", "secondary"):
        w = rl.get(key)
        if isinstance(w, dict) and w.get("used_percent") is not None:
            resets = w.get("resets_at")
            wins.append({
                "id": key,
                "label": window_label(w.get("window_minutes"), key),
                "usedPercent": w.get("used_percent"),
                "resetsAt": datetime.fromtimestamp(resets, tz=timezone.utc).isoformat().replace("+00:00", "Z") if resets else None,
                "windowMinutes": w.get("window_minutes"),
            })
    return wins, rl.get("plan_type")


# ---------------------------------------------------------------------------
# main

def summarise(provider, file_aggs, days_out=DAYS_IN_OUTPUT):
    days = defaultdict(empty_metrics)
    models7 = defaultdict(empty_metrics)
    unpriced = set()
    last_ts = 0
    last_model = None
    sessions_by_day = defaultdict(int)
    today = local_day(time.time())
    week_floor = local_day(time.time() - 6 * 86400)
    for agg in file_aggs:
        for day, m in agg.get("days", {}).items():
            add_metrics(days[day], m)
        for day in agg.get("sessions", {}):
            sessions_by_day[day] += 1
        if agg.get("lastTs", 0) >= last_ts:
            last_ts = agg.get("lastTs", 0)
            last_model = agg.get("lastModel") or last_model
        for mdl in agg.get("unpriced", {}):
            unpriced.add(mdl)
    # models over the last 7 days can't be derived from day buckets (they're
    # keyed by day only), so approximate with per-file model totals for files
    # whose last activity is within 7 days.
    cutoff7 = time.time() - 7 * 86400
    for agg in file_aggs:
        if agg.get("lastTs", 0) >= cutoff7:
            for mdl, m in agg.get("models", {}).items():
                add_metrics(models7[mdl], m)

    series = []
    for i in range(days_out - 1, -1, -1):
        d = local_day(time.time() - i * 86400)
        m = days.get(d, empty_metrics())
        series.append({
            "date": d,
            "tokens": m["input"] + m["output"] + m["cacheRead"] + m["cacheWrite"],
            "output": m["output"],
            "cost": round(m["cost"], 4),
            "calls": m["calls"],
        })

    def total(pred):
        t = empty_metrics()
        for d, m in days.items():
            if pred(d):
                add_metrics(t, m)
        t["tokens"] = t["input"] + t["output"] + t["cacheRead"] + t["cacheWrite"]
        t["cost"] = round(t["cost"], 4)
        return t

    top_models = sorted(
        [kv for kv in models7.items() if (kv[1]["input"] + kv[1]["output"] + kv[1]["cacheRead"] + kv[1]["cacheWrite"]) > 0],
        key=lambda kv: -(kv[1]["input"] + kv[1]["output"] + kv[1]["cacheRead"] + kv[1]["cacheWrite"]))
    return {
        "today": total(lambda d: d == today),
        "week": total(lambda d: d >= week_floor),
        "month": total(lambda d: True),
        "days": series,
        "models": [{"model": k, "tokens": v["input"] + v["output"] + v["cacheRead"] + v["cacheWrite"],
                    "output": v["output"], "cost": round(v["cost"], 4)} for k, v in top_models[:4]],
        "unpriced": sorted(unpriced),
        "currentModel": last_model,
        "lastActive": datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z") if last_ts else None,
        "sessionsToday": sessions_by_day.get(today, 0),
    }


def main():
    t0 = time.time()
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE) as f:
            cache = json.load(f)
        if cache.get("version") != CACHE_VERSION:
            cache = {}
    except (OSError, ValueError):
        cache = {}
    cache.setdefault("version", CACHE_VERSION)
    cache.setdefault("files", {})
    fcache = cache["files"]

    pricing = Pricing()

    # kick off codexbar in the background while we parse logs
    codexbar = find_codexbar()
    quota_futures = {}
    pool = ThreadPoolExecutor(max_workers=3)
    if codexbar:
        for prov in ("claude", "codex", "grok"):
            quota_futures[prov] = pool.submit(codexbar_usage, codexbar, prov)

    cutoff_ts = time.time() - LOOKBACK_DAYS * 86400
    files = discover(cutoff_ts)
    parsers = {"claude": parse_claude, "codex": parse_codex, "grok": parse_grok, "muse": parse_muse}
    aggs = {p: [] for p in parsers}
    parsed = 0
    newest_codex = None
    if files["codex"]:
        newest_codex = max(files["codex"], key=lambda p: os.path.getmtime(p))
    live_paths = set()
    for prov, paths in files.items():
        for path in paths:
            live_paths.add(path)
            try:
                sk = file_stat_key(path)
            except OSError:
                continue
            ck = prov + ":" + path
            entry = fcache.get(ck)
            need = (entry is None or entry.get("size") != sk["size"] or entry.get("mtime") != sk["mtime"]
                    or (prov == "codex" and path == newest_codex))
            if need:
                try:
                    if prov == "codex":
                        agg = parse_codex(path, pricing, want_rate_limits=(path == newest_codex))
                    else:
                        agg = parsers[prov](path, pricing)
                except OSError as e:
                    log("skip %s: %s" % (path, e))
                    continue
                parsed += 1
                entry = {"size": sk["size"], "mtime": sk["mtime"], "agg": agg}
                fcache[ck] = entry
            aggs[prov].append(entry["agg"])
    # drop cache entries for files that aged out / vanished
    for ck in list(fcache.keys()):
        if ck.split(":", 1)[1] not in live_paths:
            del fcache[ck]

    providers = {}
    meta = {
        "claude": {"name": "Claude", "cli": "Claude Code"},
        "codex": {"name": "Codex", "cli": "Codex CLI"},
        "grok": {"name": "Grok", "cli": "Grok CLI"},
        "muse": {"name": "Muse", "cli": "Muse Code"},
    }
    for prov in ("claude", "codex", "grok", "muse"):
        s = summarise(prov, aggs[prov])
        s.update(meta[prov])
        s["installed"] = bool(files[prov]) or os.path.isdir({
            "claude": CLAUDE_DIR, "codex": CODEX_DIR, "grok": GROK_DIR, "muse": MUSE_DIR}[prov])
        s["windows"] = []
        s["plan"] = None
        s["quotaSource"] = None
        s["quotaError"] = None
        providers[prov] = s

    # quotas
    for prov, fut in quota_futures.items():
        try:
            entry, err = fut.result(timeout=CODEXBAR_TIMEOUT + 5)
        except Exception as e:
            entry, err = None, str(e)
        if entry:
            wins, plan, email = windows_from_codexbar(entry)
            providers[prov]["windows"] = wins
            providers[prov]["plan"] = plan
            providers[prov]["account"] = email
            providers[prov]["quotaSource"] = "codexbar"
            providers[prov]["quotaUpdatedAt"] = (entry.get("usage") or {}).get("updatedAt")
        else:
            providers[prov]["quotaError"] = err
    pool.shutdown(wait=False)
    if not codexbar:
        for prov in ("claude", "codex", "grok"):
            providers[prov]["quotaError"] = "codexbar not installed"
    # Codex fallback from its own logs
    if not providers["codex"]["windows"] and newest_codex:
        rl = (fcache.get("codex:" + newest_codex) or {}).get("agg", {}).get("rateLimits")
        if rl:
            wins, plan = windows_from_codex_log(rl.get("rate_limits"))
            if wins:
                providers["codex"]["windows"] = wins
                providers["codex"]["plan"] = plan
                providers["codex"]["quotaSource"] = "codex-log"
                providers["codex"]["quotaUpdatedAt"] = (
                    datetime.fromtimestamp(rl["ts"], tz=timezone.utc).isoformat().replace("+00:00", "Z") if rl.get("ts") else None)
    # Muse: subscription-less today; plan from the model name if it hints at one
    mm = providers["muse"]["models"]
    if mm and "contributor" in mm[0]["model"]:
        providers["muse"]["plan"] = "Contributor"

    out = {
        "generatedAt": datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "collectorVersion": CACHE_VERSION,
        "durationMs": int((time.time() - t0) * 1000),
        "pricingLoaded": pricing.loaded,
        "providers": providers,
    }
    payload = json.dumps(out, separators=(",", ":"))
    tmp = DATA_JS + ".tmp"
    with open(tmp, "w") as f:
        f.write("window.__AI_USAGE__=" + payload + ";\n")
    os.replace(tmp, DATA_JS)
    tmp = DATA_JSON + ".tmp"
    with open(tmp, "w") as f:
        f.write(payload)
    os.replace(tmp, DATA_JSON)
    with open(CACHE_FILE + ".tmp", "w") as f:
        json.dump(cache, f)
    os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
    log("ok: parsed %d files, %d cached, %.1fs" % (parsed, len(fcache) - parsed, time.time() - t0))


if __name__ == "__main__":
    main()
