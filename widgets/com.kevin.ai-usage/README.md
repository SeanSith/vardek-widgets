# AI Usage Widget

Four instrument panels — **Claude Code**, **Codex CLI**, **Grok CLI**, **Muse Code** — each showing live subscription quota windows, today's token burn (with an API-list-price cost estimate), a 14-day activity chart, and last-active time. Styled to the Vardek cockpit design (Tokyo Night surfaces, SF Mono values, indigo/violet at rest, amber ≥ 75 %, red ≥ 90 %).

---

## Panels

| Section | Content |
|---|---|
| **Header** | Provider name, CLI + plan (Pro / SuperGrok / Contributor …), most recently used model |
| **Quotas** | Up to three rate-limit windows (5-hour, weekly, model-specific weekly …) with used %, bar and reset countdown. Providers without a quota show *no quota window · usage-based* |
| **Today** | Total tokens today, output / input split with cache-hit %, call count, estimated cost |
| **14 days** | Daily token bars (today highlighted), this week's tokens and cost |
| **Footer** | Last activity, sessions today |

Sizes: **8×2** (four panels side by side) and **4×2** (2×2 compact grid — chart shrinks, footer hidden).

---

## How it gets data

Vardek widgets are sandboxed iframes with no file access, and the proxy blocks localhost. So a small collector script writes a JSONP file (`data.js`) next to `index.html`; the widget `<script src="data.js">`-loads it on every refresh (every 60 s, throttled to once per 5 s).

`collector/collect.py` (system `/usr/bin/python3`, no dependencies) reads:

| Provider | Source | What's counted |
|---|---|---|
| Claude | `~/.claude/projects/**/*.jsonl` | `message.usage` per assistant record, de-duplicated by `(message.id, requestId)` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` | `token_count` events (deltas of `total_token_usage`), model from `turn_context` |
| Grok | `~/.grok/sessions/*/*/updates.jsonl` | `turn_completed` usage; cost is Grok's own `costUsdTicks` (1e-10 USD) — *billed*, not estimated |
| Muse | `~/.local/share/muse/sessions/**/session.jsonl` | `model_completed` usage + subagent `runtime_observed` snapshots |
| Quotas | `codexbar usage --provider claude\|codex\|grok --json` | Live rate-limit windows and plan (needs the [CodexBar](https://github.com/steipete/CodexBar) CLI at `/opt/homebrew/bin/codexbar`) |

Cost estimates use the LiteLLM price table (cached daily in `~/Library/Caches/com.kevin.ai-usage/pricing.json`); models missing from it show tokens only. Per-file aggregates are cached by size + mtime, so a run typically re-reads only the active session files (~1–2 s of parsing + ~10 s of CodexBar).

Only the last 30 days of files are scanned. Day buckets use the Mac's local timezone.

---

## Collector schedule

`~/Library/LaunchAgents/com.kevin.ai-usage-collector.plist` runs the collector every **180 s** and at login.

```
# run once by hand
/usr/bin/python3 "~/Library/Application Support/Vardek/widgets/com.kevin.ai-usage/collector/collect.py"

# reload / remove the agent
launchctl bootout   gui/$(id -u)/com.kevin.ai-usage-collector
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.ai-usage-collector.plist

# logs
tail -f ~/Library/Logs/ai-usage-collector.log
```

If the collector stops, the widget dims its values and shows a **stale** badge after `staleMinutes` (default 20). If `data.js` has never been written, it shows a "Waiting for the usage collector" card with the command to run.

---

## Settings

| Setting | Type | Default | Description |
|---|---|---|---|
| **Show estimated cost** | Boolean | on | Hide the `$` figures if you'd rather see tokens only |
| **Show 14-day chart** | Boolean | on | Hide the bar chart |
| **Mark data stale after (min)** | Number | 20 | Age at which values dim and the stale badge appears |

---

## Notes

- Quota windows are what CodexBar reports: Claude (5-hour, weekly, model-specific weekly), Codex (weekly + Spark weekly), Grok (SuperGrok window). Muse reports no quota. If CodexBar isn't installed or fails, Codex falls back to the `rate_limits` block in its own newest session log.
- Cost for subscription usage is an *equivalent API price* — useful for relative burn, not a bill. Grok's number is the real invoice amount.
- Files: `manifest.json`, `index.html`, `collector/collect.py`, generated `data.js` / `data.json` (rewritten atomically every run).
