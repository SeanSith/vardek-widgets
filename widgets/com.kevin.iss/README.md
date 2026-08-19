# ISS Tracker Widget

Live position of the International Space Station on a day/night world map: the ISS (🛰) with its ground track, the sub‑solar point, your location, and a telemetry panel — latitude/longitude, altitude, speed, distance from you, and whether it's currently sunlit or in Earth's shadow.

Self‑contained (no daemon): fetches the free [wheretheiss.at](https://wheretheiss.at) API through Vardek's proxy every ~5s (declares `https://api.wheretheiss.at/**`). No key. The day/night terminator is computed locally from the sun's position. Ground track is an inclination‑matched approximation.

Settings: **Your latitude / longitude** (for the "you" marker and distance). Files: `manifest.json`, `index.html`.
