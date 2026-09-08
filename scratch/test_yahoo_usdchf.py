import requests

url = "https://query1.finance.yahoo.com/v8/finance/chart/USDCHF=X?interval=5m&range=1d"
headers = {"User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers)
data = r.json()
result = data['chart']['result'][0]
timestamps = result['timestamp']
indicators = result['indicators']['quote'][0]
opens = indicators['open']
highs = indicators['high']
lows = indicators['low']
closes = indicators['close']

import datetime
candles = []
for i in range(len(timestamps)):
    t = datetime.datetime.fromtimestamp(timestamps[i], datetime.timezone.utc)
    if highs[i] is not None and lows[i] is not None:
        candles.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "open": opens[i], "high": highs[i], "low": lows[i], "close": closes[i]
        })

print(f"Total candles from Yahoo: {len(candles)}")
print(f"Latest candle: {candles[-1]}")
recent21 = candles[-21:]
h21 = max(c['high'] for c in recent21)
l21 = min(c['low'] for c in recent21)
tk21 = (h21 + l21) / 2
print(f"Yahoo 21 period: MinLow={l21:.5f}, MaxHigh={h21:.5f} -> TK={tk21:.5f}")
