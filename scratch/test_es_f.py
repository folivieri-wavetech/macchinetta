import requests
import datetime
import zoneinfo

TZ_IT = zoneinfo.ZoneInfo("Europe/Rome")

def get_yahoo(symb, interval, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symb}?range={rng}&interval={interval}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code != 200:
        return []
    res = r.json().get('chart', {}).get('result', [{}])[0]
    quotes = res.get('indicators', {}).get('quote', [{}])[0]
    timestamps = res.get('timestamp', [])
    highs = quotes.get('high', [])
    lows = quotes.get('low', [])
    candele = []
    for t, h, l in zip(timestamps, highs, lows):
        if h is not None and l is not None:
            snap = datetime.datetime.fromtimestamp(t, TZ_IT).strftime("%Y/%m/%d %H:%M:00")
            candele.append({"time": snap, "h": float(h), "l": float(l)})
    return candele

for symb in ["ES=F", "^GSPC"]:
    c = get_yahoo(symb, "1h", "1mo")
    print(f"\n--- YAHOO: {symb} (Totale candele H1: {len(c)}) ---")
    if len(c) >= 55:
        sub55 = c[-55:]
        max_h = max(x['h'] for x in sub55)
        min_l = min(x['l'] for x in sub55)
        kj = (max_h + min_l) / 2.0
        print(f"Prima delle 55: {sub55[0]['time']}")
        print(f"Ultima delle 55: {sub55[-1]['time']}")
        print(f"Max: {max_h:.2f} | Min: {min_l:.2f}")
        print(f"-> KJ 55 H1 su {symb}: {kj:.2f}")
