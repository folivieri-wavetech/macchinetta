import json

with open('scratch_candles.json') as f:
    candles = json.load(f)

print(f"Total candles: {len(candles)}")
for i, c in enumerate(candles):
    t = c['time']
    o = c['open']
    h = c['high']
    l = c['low']
    cl = c['close']
    color = "VERDE" if cl > o else "ROSSA" if cl < o else "DOJI"
    body = abs(cl - o)
    print(f"[{i:3d}] {t} | Open: {o:7.2f} | High: {h:7.2f} | Low: {l:7.2f} | Close: {cl:7.2f} | {color:5s} | Body: {body:5.2f}")
