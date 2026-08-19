# Cocktail

Rotates through cocktail recipes (photo, ingredients, instructions) from
TheCocktailDB. A daemon (**cocktaild**) fetches a batch of random drinks each
hour, downloads their photos into `img/`, and writes `data.js`.

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.cocktaild.plist
/usr/bin/python3 cocktaild/cocktaild.py once
```
Settings: **Seconds per drink**, **Show** (any / alcoholic / non-alcoholic).
`cocktail.json` sets how many drinks to fetch (default 10). Logs: `~/Library/Logs/cocktaild.*.log`.
