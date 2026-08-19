# Recipe

Rotates through meal recipes (photo, ingredients, instructions) from TheMealDB.
A daemon (**reciped**) fetches a batch of random meals each hour and downloads
their photos into `img/`.

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.kevin.reciped.plist
/usr/bin/python3 reciped/reciped.py once
```
Setting: **Seconds per recipe**. `recipe.json` sets batch size (default 8). Logs: `~/Library/Logs/reciped.*.log`.
