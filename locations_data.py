import json

with open("locations.json", "r", encoding="utf-8") as f:
    LOCATIONS = json.load(f)

SORTED_KEYS = sorted(LOCATIONS.keys(), key=len, reverse=True)
