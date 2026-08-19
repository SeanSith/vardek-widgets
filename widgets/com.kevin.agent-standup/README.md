# AI Standup Widget

A meta-agent that reads the live state of every agent-deck session and asks a model to write a plain-English brief for the panel: **who needs you and why**, who's running clean, who's idle. It turns the raw session list (which the Agent Control widget already shows) into a glance you can act on.

```
STANDUP   2 agents waiting for you            [2 waiting] [2 live] [38 stopped]
│ shell         (claude)   Awaiting input or error from fix-claude-keychain.sh   ›
│ home-network  (claude)   Power cycle complete, waiting for you to verify        ›
                                                        brief 35s ago · haiku-4-5   $0.014/brief
```

Tap an attention card to expand the raw last lines of that session's terminal. The green "✓ nothing needs you" state appears when nothing is waiting.

Sizes: **8×2 / 6×2** full, **4×2 / 3×2** compact (drops the running-idle strip and cost). Lives on dashboard page 4 by default.

---

## How it works

`standup/standup.py serve` (a KeepAlive LaunchAgent) loops every ~8 s:

1. **Input** — reads the Agent Control widget's `data.json` (its loop refreshes that every ~5 s: session ids, status, and the last lines of each tmux pane). If that file is missing/stale it falls back to `agentctl.py collect`.
2. **Change check** — hashes the alive sessions' statuses + pane snippets. **Only if that changed** (and it's been ≥ `minIntervalSec`) does it call the model. Between changes it just rewrites the timestamp — zero tokens.
3. **Model** — `claude -p` in headless mode with `--model claude-haiku-4-5 --output-format json`, run from a neutral cwd with an empty MCP config so it doesn't load your project context/tools. Uses your Claude **subscription** (no API key). The prompt asks for strict JSON: `headline`, `attention[]` (with a ≤90-char reason), `running[]`, `idle[]`.
4. **Output** — writes `../data.js` (`window.__STANDUP__ = …`) plus `data.json`. The sandboxed widget `<script src>`-loads `data.js` every 5 s.

Typical cost is **~$0.01–0.03 per brief** on Haiku, and briefs only regenerate when your fleet's state actually moves, so an idle day is a handful of cents. The footer shows the model and the last brief's cost.

### Start it

```
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.agent-standup.plist
```

Then quit + relaunch Vardek once (the dashboard reads its widget library at boot). Logs: `~/Library/Logs/agent-standup.log`. Stop: `launchctl bootout gui/$(id -u)/com.kevin.agent-standup`.

Manual runs: `standup.py once` (generate + print, respects the cost guard), `standup.py once --force` (always call the model), `standup.py probe` (show the session inputs without calling the model).

---

## Requirements

- **Agent Control widget** running (`com.kevin.agentctl` LaunchAgent) — it's the data source. Standup can fall back to a one-off collect, but the live file is what keeps it cheap and current.
- **`claude` CLI** logged in (`~/.local/bin/claude`, your Claude Code subscription). No API key.

---

## Configuration — `standup.json`

| Key | Default | Meaning |
|---|---|---|
| `model` | `claude-haiku-4-5` | Any model your `claude` login can use (`claude-fable-5` for sharper reasons at higher cost). |
| `pollSeconds` | `8` | How often to check whether state changed. |
| `minIntervalSec` | `90` | Floor between model calls — the main cost guard. Raise to spend less. |
| `maxAgeSec` | `1800` | Force a refresh at least this often even if nothing changed. |
| `cwd` | `/tmp` | Where `claude -p` runs; neutral so no project CLAUDE.md/skills load. |
| `maxSessions` | `26` | Cap on sessions sent to the model. |

Widget settings (Admin → Widgets → AI Standup): **Show running / idle line**, **Show model cost in footer**.

---

## Notes

- This widget is **informational** — it can't send keystrokes (only the `com.vardek.macro-pad` id may trigger Vardek actions, and the Agent Control widget holds that). To act on what the standup surfaces, swipe to the Agent Control page and hit Approve/Esc/etc.
- Reasons are the model's paraphrase of each pane's last lines. It's told not to invent, but it's a summary — tap through to the raw lines (or the Agent Control page) before doing anything irreversible.
- If the model call fails (offline, not logged in), the widget keeps showing the last good brief and puts the error in the footer.
- Files: `manifest.json`, `index.html`, `standup/standup.py`, `standup.json`, generated `data.js`/`data.json`, `.state.json` (hash + last brief), `.empty-mcp.json`.
