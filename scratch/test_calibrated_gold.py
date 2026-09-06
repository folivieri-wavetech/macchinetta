import requests
import datetime
import zoneinfo

TZ_IT = zoneinfo.ZoneInfo("Europe/Rome")

def get_calibrated_gold_candles(tf, px_live_ig):
    interval_map = {
        "MINUTE_5": ("5m", "5d"),
        "MINUTE_15": ("15m", "10d"),
        "HOUR": ("1h", "1mo"),
        "HOUR_4": ("1h", "3mo"),
        "DAY": ("1d", "6mo")
    }
    int_str, rng_str = interval_map.get(tf, ("1h", "1mo"))
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range={rng_str}&interval={int_str}"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code != 200:
        return []
    res = r.json().get('chart', {}).get('result', [{}])[0]
    quotes = res.get('indicators', {}).get('quote', [{}])[0]
    timestamps = res.get('timestamp', [])
    opens = quotes.get('open', [])
    highs = quotes.get('high', [])
    lows = quotes.get('low', [])
    closes = quotes.get('close', [])
    
    raw = []
    for t, o, h, l, c in zip(timestamps, opens, highs, lows, closes):
        if h and l and o and c:
            raw.append((t, o, h, l, c))
    if not raw:
        return []
        
    last_cme = raw[-1][4]
    ratio = px_live_ig / last_cme if last_cme else 1.0
    
    candele = []
    for t, o, h, l, c in raw:
        snap = datetime.datetime.fromtimestamp(t, TZ_IT).strftime("%Y/%m/%d %H:%M:00")
        candele.append({
            "snapshotTime": snap,
            "openPrice": {"bid": round(o * ratio, 1), "ask": round(o * ratio, 1)},
            "highPrice": {"bid": round(h * ratio, 1), "ask": round(h * ratio, 1)},
            "lowPrice": {"bid": round(l * ratio, 1), "ask": round(l * ratio, 1)},
            "closePrice": {"bid": round(c * ratio, 1), "ask": round(c * ratio, 1)}
        })
    return candele

px_live_ig = 4426.5
for tf in ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]:
    c = get_calibrated_gold_candles(tf, px_live_ig)
    if len(c) >= 55:
        sub55 = c[-55:]
        max_h = max(x['highPrice']['bid'] for x in sub55)
        min_l = min(x['lowPrice']['bid'] for x in sub55)
        kj = (max_h + min_l) / 2.0
        diff = px_live_ig - kj
        dir_p = "Possibile LONG" if diff >= 0 else "Possibile SHORT"
        print(f"[{tf:8s}] {len(c)} candele | Da: {sub55[0]['snapshotTime']} a {sub55[-1]['snapshotTime']}")
        print(f"   Max: {max_h:.1f} | Min: {min_l:.1f} | -> KJ55: {kj:.1f} | Distanza: {abs(diff):.1f} pt ({dir_p})")
