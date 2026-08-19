# Fish Tank Widget (with decentralized fish handoff)

A living aquarium screensaver. Each fish is **unique** — its own id, generated name, and a combination of attributes (species, hue, size, speed, pattern, fin style, personality). Fish swim, and every so often one is **sent off to a random other tank running elsewhere**, migrating via a decentralized, crash-safe handoff. A fish **never disappears from its tank until the receiving tank has confirmed** it — so a fish is never lost, and never permanently in two tanks at once.

## Two parts

- **`fishd/fishd.py`** — the tank daemon (a KeepAlive LaunchAgent). It owns the fish roster, gossips presence, and runs the handoff. Writes `../data.js`.
- **`index.html`** — the widget. Reads `data.js` and animates the tank: fish swim with per-personality wander, arrivals swim in from an edge, departures dart out, plus plants, bubbles, caustic light, a tank/peer status readout, and a live event feed. Tap a fish to inspect its attributes and travel history.

The widget can't network (sandbox), so the daemon does all migration and the widget just renders — same split as the other agent widgets.

## Decentralized handoff — how a fish moves tanks

"Elsewhere" is a **shared directory** used as the rendezvous — no server, no open ports:

- **Same Mac, several tanks:** they share a local dir.
- **Different machines:** point `sharedDir` at a **Dropbox / iCloud-synced** folder (the default picks `~/Cloud/Dropbox/.fishtank` if Dropbox exists) and tanks on any of your machines find each other and trade fish, wherever they are.

Each tank drops a presence file and reads the others'; handoff messages are files in per-tank inboxes. The protocol is a **two-phase commit with re-drive**:

```
source                                        target
─ lock fish (departing), write OFFER ───────▶ create it as "arriving" (provisional)
                                      ◀─ ACK  accepted (has room, not a dup)
─ stop showing it, write COMMIT ────────────▶ make it resident (arrived)
                                      ◀─ DONE
─ delete our copy ─────────────────────────
```

- The **source owns the fish until DONE**, so at every instant the fish is resident in **≥ 1** tank (a brief in-transit moment where it's visible in exactly one).
- No ACK → the fish just stayed. No COMMIT → the target discards the arrival. A crash mid-handoff is reconciled on restart (departing→stays, un-acked arrival→dropped, acked-but-unfinished→COMMIT is re-driven). Verified under repeated `kill -9`: **0 fish lost, 0 duplicated.**

Migration is autonomous: roughly every `migrateEverySec`, if another tank is online and has room, a random resident fish is offered to it.

## Run it

```
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.fishtank.plist
```

Then quit + relaunch Vardek once. To make fish migrate, run a second tank (another Mac with this widget + daemon, `sharedDir` on the same synced folder — or a second copy on this Mac pointing at a shared local dir). Logs: `~/Library/Logs/fishtank.log`. Stop: `launchctl bootout gui/$(id -u)/com.kevin.fishtank`.

Manual: `fishd.py seed N` (stock the tank), `fishd.py status` (roster + peers), `fishd.py once` (one tick).

## Configuration — `fish.json`

| Key | Default | Meaning |
|---|---|---|
| `nodeName` | `<host>-tank` | This tank's name (shown in every tank it visits). |
| `sharedDir` | Dropbox `.fishtank` if present, else a local dir | The decentralized rendezvous. Point at a synced folder for cross-machine. |
| `capacity` | 12 | Max fish this tank holds (offers are declined when full). |
| `seedCount` | 6 | Fish to stock an empty tank with. |
| `migrateEverySec` / `migrateChance` | 45 / 0.6 | How often / how likely a fish is offered to a peer. |
| `handoffDeadlineSec` | 40 | How long an in-flight handoff may take before it's reclaimed/redriven. |
| `peerTimeoutSec` | 25 | A tank with no heartbeat this long is considered offline. |

Widget settings (Admin → Widgets → Fish Tank): **Show fish names**, **Show tank / peer status**, **Tap a fish to inspect**.

## Notes

- Attributes travel with the fish, so a fish keeps its identity, look, name, and hop count in every tank it visits (tap it to see "tanks visited").
- Same-machine multi-tank is instant; cross-machine via a synced folder is as fast as the sync (seconds) — fine for drifting fish.
- Files: `manifest.json`, `index.html`, `fishd/fishd.py`, `fish.json`, generated `data.js`/`data.json`, `.fishstate.json` (roster + open handoffs).
