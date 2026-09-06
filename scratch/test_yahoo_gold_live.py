import requests
import datetime
import json
import zoneinfo

TZ_IT = zoneinfo.ZoneInfo("Europe/Rome")

def get_yahoo_candles(symb, interval, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symb}?range={rng}&interval={interval}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code != 200:
        print(f"Errore Yahoo {r.status_code}")
        return []
    res = r.json().get('chart', {}).get('result', [{}])[0]
    quotes = res.get('indicators', {}).get('quote', [{}])[0]
    timestamps = res.get('timestamp', [])
    opens = quotes.get('open', [])
    highs = quotes.get('high', [])
    lows = quotes.get('low', [])
    closes = quotes.get('close', [])
    
    candele = []
    for t, o, h, l, c in zip(timestamps, opens, highs, lows, closes):
        if h is not None and l is not None and o is not None and c is not None:
            snap = datetime.datetime.fromtimestamp(t, TZ_IT).strftime("%Y/%m/%d %H:%M:00")
            candele.append({
                "snapshotTime": snap,
                "openPrice": {"bid": float(o), "ask": float(o)},
                "highPrice": {"bid": float(h), "ask": float(h)},
                "lowPrice": {"bid": float(l), "ask": float(l)},
                "closePrice": {"bid": float(c), "ask": float(c)}
            })
    return candele

for tf, (iv, rng) in [("M5", ("5m", "5d")), ("H1", ("1h", "1mo")), ("D1", ("1d", "6mo"))]:
    candles = get_yahoo_candles("GC=F", iv, rng)
    print(f"\n================ YAHOO GC=F ({tf}) Totale candele: {len(candles)} ================")
    if candles:
        print(f"Prima: {candles[0]['snapshotTime']} | Ultima: {candles[-1]['snapshotTime']}")
        sub55 = candles[-55:]
        max_h = max(c['highPrice']['bid'] for c in sub55)
        min_l = min(c['lowPrice']['bid'] for c in sub55)
        kj = (max_h + min_l) / 2.0
        print(f"Ultime 55 barre -> Da: {sub55[0]['snapshotTime']} a {sub55[-1]['snapshotTime']}")
        print(f"Max High: {max_h:.2f} | Min Low: {min_l:.2f} | Close: {sub55[-1]['closePrice']['bid']:.2f}")
        print(f"➡️ KJ (55) calcolata su barre REALI AGGIORNATE: {kj:.2f}")
