# Crypto Widget

Live prices for the coins you pick, with 24‑hour change (green up / red down) and a 7‑day sparkline. Self‑contained (no daemon): fetches [CoinGecko](https://www.coingecko.com/en/api)'s free API through Vardek's proxy (declares `https://api.coingecko.com/**`), refreshing every ~1 min. No key.

Settings: **Coin ids** (CoinGecko ids, comma‑separated, e.g. `bitcoin,ethereum,solana`), **Currency** (`usd`, `eur`, `gbp`, …). Files: `manifest.json`, `index.html`.
