import requests, datetime
from zoneinfo import ZoneInfo
TZ_ITALIA = ZoneInfo('Europe/Rome')
url = 'https://query1.finance.yahoo.com/v8/finance/chart/USDCAD=X?range=1d&interval=5m'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers, timeout=5)
res = r.json()['chart']['result'][0]
timestamps = res['timestamp']
q = res['indicators']['quote'][0]

candles = []
for t, o, h, l, c in zip(timestamps, q['open'], q['high'], q['low'], q['close']):
    if None not in (o, h, l, c):
        candles.append({'t': datetime.datetime.fromtimestamp(t, TZ_ITALIA).strftime('%H:%M'), 'o': o, 'h': h, 'l': l, 'c': c})

print(f"Total candles today: {len(candles)}")
pip_val = 0.0001
for i in range(21, len(candles)):
    sub = candles[i-21:i]
    hh = max(x['h'] for x in sub)
    ll = min(x['l'] for x in sub)
    tk = (hh + ll) / 2
    c_curr = candles[i]
    diff = (c_curr['c'] - c_curr['o']) / pip_val
    dist_tk = (tk - c_curr['c']) / pip_val
    is_cand_green = diff >= 3.0
    cond_tk = c_curr['o'] < tk and c_curr['c'] <= tk and dist_tk <= 20.0
    if i >= len(candles) - 20:
        match = is_cand_green and cond_tk
        flag = "🔥 INCREMENT!" if match else "   "
        print(f"{flag} {c_curr['t']} | O:{c_curr['o']:.5f} C:{c_curr['c']:.5f} | TK:{tk:.5f} | diff:{diff:+.1f} pip | dist_tk:{dist_tk:+.1f} pip | Green>=3:{is_cand_green} | TK_valid:{cond_tk}")
