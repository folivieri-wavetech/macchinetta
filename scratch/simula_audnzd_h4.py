import requests
import json
from datetime import datetime, timezone, timedelta

# 1. Fetch 1h candles from Yahoo Finance
url = 'https://query1.finance.yahoo.com/v8/finance/chart/AUDNZD=X?interval=1h&range=30d'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)
data = r.json()['chart']['result'][0]
timestamps = data['timestamp']
quotes = data['indicators']['quote'][0]

# Convert to Italy time (UTC+2 in summer/CEST)
tz_it = timezone(timedelta(hours=2))

raw_1h = []
for t, o, h, l, c in zip(timestamps, quotes['open'], quotes['high'], quotes['low'], quotes['close']):
    if o is not None and h is not None and l is not None and c is not None:
        dt = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(tz_it)
        raw_1h.append({'dt': dt, 'open': float(o), 'high': float(h), 'low': float(l), 'close': float(c)})

print(f"Total 1h candles fetched: {len(raw_1h)}")

# Aggregate into H4 candles with boundaries: 01:00, 05:00, 09:00, 13:00, 17:00, 21:00
# A candle starting at e.g. 09:00 covers 09:00, 10:00, 11:00, 12:00 and closes at 13:00.
def get_h4_start(dt):
    # offset by 1 hour so boundaries align to 01, 05, 09, 13, 17, 21
    tot_min = dt.hour * 60 + dt.minute
    offset = 60
    b_min = ((tot_min - offset) // 240) * 240 + offset
    base = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(minutes=b_min)

h4_buckets = {}
for c in raw_1h:
    start_dt = get_h4_start(c['dt'])
    if start_dt not in h4_buckets:
        h4_buckets[start_dt] = []
    h4_buckets[start_dt].append(c)

h4_candles = []
for start_dt in sorted(h4_buckets.keys()):
    bucket = h4_buckets[start_dt]
    # To be closed, bucket should be finished or have candles
    o = bucket[0]['open']
    h = max(x['high'] for x in bucket)
    l = min(x['low'] for x in bucket)
    c = bucket[-1]['close']
    h4_candles.append({
        'start': start_dt,
        'open': o,
        'high': h,
        'low': l,
        'close': c,
        'count': len(bucket)
    })

print(f"Total H4 candles built: {len(h4_candles)}")

# Calculate Donchian (TK=9, KJ=26)
def calc_donchian(c_list, period):
    if len(c_list) < period:
        sub = c_list
    else:
        sub = c_list[-period:]
    hi = max(x['high'] for x in sub)
    lo = min(x['low'] for x in sub)
    return (hi + lo) / 2.0

pip_val = 0.0001
tol_pips = 5
max_tk_dist_pips = 20
min_dist_pips = 10
min_body_pips = 1

tolleranza_tk = tol_pips * pip_val
max_dist_tk = max_tk_dist_pips * pip_val
min_dist_incr = min_dist_pips * pip_val
min_body = min_body_pips * pip_val

# Simulate stepping through candles from October 14
print("\n" + "="*80)
print(f"{'H4 Candle Start':<18} | {'Color':<5} | {'Open':<8} | {'Close':<8} | {'TK':<8} | {'KJ':<8} | {'Dist to TK (p)':<14} | {'Increment Condition?'}")
print("="*80)

history = []
for i, c in enumerate(h4_candles):
    history.append(c)
    if len(history) < 26:
        continue
    
    # Check if candle is on or after 2026-10-15 12:00
    c_time = c['start']
    is_after_entry = c_time >= datetime(2026, 10, 15, 9, 0, tzinfo=tz_it)
    
    tk = calc_donchian(history, 9)
    kj = calc_donchian(history, 26)
    
    c_open = c['open']
    c_close = c['close']
    is_green = (c_close - c_open) >= (min_body - 1e-7)
    color = "GREEN" if c_close > c_open else "RED"
    
    # SHORT increment condition check:
    # 1. closed_candle.open < (tk + tolleranza_tk)
    # 2. c_close <= (tk + tolleranza_tk + 1e-7)
    # 3. (tk - c_close) <= (max_dist_tk + 1e-7)   -> c_close >= tk - 20 pip
    # 4. Candela verde di almeno min_body pip: (c_close - c_open) >= min_body
    dist_tk_pips = (tk - c_close) / pip_val
    
    c1 = c_open < (tk + tolleranza_tk)
    c2 = c_close <= (tk + tolleranza_tk + 1e-7)
    c3 = (tk - c_close) <= (max_dist_tk + 1e-7)
    c4 = is_green
    
    reasons = []
    if not c4:
        reasons.append("Non è VERDE (è rossa o doji)")
    if not c1:
        reasons.append(f"Open ({c_open:.5f}) >= TK+5p ({(tk+tolleranza_tk):.5f})")
    if not c2:
        reasons.append(f"Close ({c_close:.5f}) > TK+5p ({(tk+tolleranza_tk):.5f})")
    if not c3:
        reasons.append(f"Prezzo troppo lontano sotto TK ({dist_tk_pips:.1f}p > 20p)")
        
    status = "OK -> INCREMENTO!" if (c1 and c2 and c3 and c4) else "NO: " + ", ".join(reasons)
    
    if is_after_entry:
        print(f"{str(c_time):<18} | {color:<5} | {c_open:<8.5f} | {c_close:<8.5f} | {tk:<8.5f} | {kj:<8.5f} | {dist_tk_pips:<14.1f} | {status}")
