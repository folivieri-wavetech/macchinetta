import requests, json, datetime

YAHOO_SYMBOLS = {
    "AUD/NZD": "AUDNZD=X",
    "CAD/JPY": "CADJPY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/JPY": "GBPJPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "USD/JPY": "USDJPY=X",
    "Spot Gold": "GC=F",
    "US 500 Cash": "ES=F"
}

TF_CONFIG = {
    "MINUTE_5": ("5m", "5d"),
    "HOUR": ("1h", "1mo"),
    "DAY": ("1d", "6mo")
}

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

for nome, sym in YAHOO_SYMBOLS.items():
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=5m&range=2d"
    try:
        r = requests.get(url, headers=headers, timeout=5)
        d = r.json()
        res = d['chart']['result'][0]
        ts = res['timestamp']
        q = res['indicators']['quote'][0]
        h = [x for x in q['high'] if x is not None]
        print(f"OK {nome:<12} ({sym}): {len(h)} M5 candles, latest ts={datetime.datetime.fromtimestamp(ts[-1])}")
    except Exception as e:
        print(f"ERR {nome}: {e}")
