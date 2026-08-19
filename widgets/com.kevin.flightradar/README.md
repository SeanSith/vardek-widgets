# Flight Radar Widget

A radar scope of aircraft near your location, live from crowd‑sourced ADS‑B. Airborne aircraft are heading‑arrows colored by altitude (red < 5k ft · amber < 15k · green < 30k · cyan above); ground traffic is dim dots. Range rings, compass, and a sweep. The panel lists the closest airborne with type, distance, and flight level.

Self‑contained widget (no daemon): declares `https://api.adsb.lol/**` and fetches the free [adsb.lol](https://adsb.lol) API through Vardek's proxy every ~10s. No key.

## Settings
| Setting | Default | |
|---|---|---|
| Latitude / Longitude | 37.7749 / -122.4194 | Radar center. Set to your location. |
| Range (nm) | 60 | Radar radius in nautical miles. |
| Show aircraft labels | on | Callsign + flight level on the nearest airborne. |

Notes: works only inside the Vardek dashboard (proxy relay). Files: `manifest.json`, `index.html`.
