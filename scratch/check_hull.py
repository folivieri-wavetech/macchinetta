import json

with open("hull_trend.json", "r", encoding="utf-8") as f:
    d = json.load(f)

for k, v in d.items():
    print(f"{k:15}: HMA={v.get('hma377'):12.5f} | Slope={v.get('slope'):12} | Pos={v.get('pos_vs_hull'):6} | Close={v.get('last_close')}")
