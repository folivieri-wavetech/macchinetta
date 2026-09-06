import requests
import json
import datetime
import zoneinfo

TZ_IT = zoneinfo.ZoneInfo("Europe/Rome")

# Test diverse fonti pubbliche per Spot Gold
symbols_to_test = [
    ("GC=F", "Yahoo CME Gold Futures"),
    ("XAUUSD=X", "Yahoo Spot Gold USD"),
    ("GLD", "SPDR Gold Shares"),
    ("IAU", "iShares Gold Trust"),
    ("SGOL", "Aberdeen Standard Gold"),
]

for symb, desc in symbols_to_test:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symb}?range=5d&interval=1h"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    print(f"\n--- {desc} ({symb}) --- Status: {r.status_code}")
    if r.status_code == 200:
        res = r.json().get('chart', {}).get('result', [{}])[0]
        quotes = res.get('indicators', {}).get('quote', [{}])[0]
        timestamps = res.get('timestamp', [])
        highs = quotes.get('high', [])
        lows = quotes.get('low', [])
        closes = quotes.get('close', [])
        valid = [(t, h, l, c) for t, h, l, c in zip(timestamps, highs, lows, closes) if h and l and c]
        if valid:
            print(f"  Totale candele H1: {len(valid)}")
            print(f"  Prima: {datetime.datetime.fromtimestamp(valid[0][0], TZ_IT)} | Ultima: {datetime.datetime.fromtimestamp(valid[-1][0], TZ_IT)}")
            print(f"  Ultimo close: {valid[-1][3]}")
            sub = valid[-55:] if len(valid) >= 55 else valid
            max_h = max(x[1] for x in sub)
            min_l = min(x[2] for x in sub)
            print(f"  Ultime {len(sub)} barre -> Max: {max_h:.2f} | Min: {min_l:.2f} | Mediana: {(max_h+min_l)/2:.2f}")
