import json
import os
import requests
import datetime
from dotenv import dotenv_values

os.chdir(os.path.dirname(os.path.abspath(__file__)) + "/..")
config = dotenv_values(".env")

yahoo_syms = {
    "AUD/CAD": "AUDCAD=X", "AUD/NZD": "AUDNZD=X", "CAD/JPY": "CADJPY=X",
    "EUR/GBP": "EURGBP=X", "GBP/USD": "GBPUSD=X", "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X", "USD/JPY": "USDJPY=X", "Spot Gold": "GC=F", "US 500 Cash": "ES=F"
}
epics = {
    "AUD/CAD": "CS.D.AUDCAD.MINI.IP", "AUD/NZD": "CS.D.AUDNZD.MINI.IP", "CAD/JPY": "CS.D.CADJPY.MINI.IP",
    "EUR/GBP": "CS.D.EURGBP.MINI.IP", "GBP/USD": "CS.D.GBPUSD.MINI.IP", "USD/CAD": "CS.D.USDCAD.MINI.IP",
    "USD/CHF": "CS.D.USDCHF.MINI.IP", "USD/JPY": "CS.D.USDJPY.MINI.IP", "Spot Gold": "CS.D.CFEGOLD.CBE.IP", "US 500 Cash": "IX.D.SPTRD.IBE.IP"
}
interval_map = {"MINUTE_5": ("5m", "5d"), "HOUR": ("1h", "1mo"), "DAY": ("1d", "6mo")}

auth_payload = {"identifier": config.get("IG_USERNAME"), "password": config.get("IG_PASSWORD")}
headers = {"X-IG-API-KEY": config.get("IG_API_KEY"), "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8", "Version": "2"}

r = requests.post("https://demo-api.ig.com/gateway/deal/session", json=auth_payload, headers=headers)
if r.status_code != 200:
    print("Login IG Fallito")
    exit(1)
cst = r.headers.get("CST")
xst = r.headers.get("X-SECURITY-TOKEN")

h_markets = {"X-IG-API-KEY": config.get("IG_API_KEY"), "CST": cst, "X-SECURITY-TOKEN": xst, "Accept": "application/json", "Version": "1"}

live_prices = {}
for nome, epic in epics.items():
    r_m = requests.get(f"https://demo-api.ig.com/gateway/deal/markets/{epic}", headers=h_markets)
    if r_m.status_code == 200:
        snap = r_m.json().get('snapshot', {})
        bid = snap.get('bid')
        offer = snap.get('offer')
        if bid and offer:
            live_prices[nome] = (bid + offer) / 2.0
        elif bid:
            live_prices[nome] = bid

print(f"Prezzi Live recuperati da IG: {live_prices}")

def aggrega_candele_h4(candele_h1):
    h4 = []
    chunk = []
    for c in candele_h1:
        chunk.append(c)
        if len(chunk) == 4:
            snap = chunk[0]['snapshotTime']
            o = chunk[0]['openPrice']['bid']
            h = max(x['highPrice']['bid'] for x in chunk)
            l = min(x['lowPrice']['bid'] for x in chunk)
            cls = chunk[-1]['closePrice']['bid']
            h4.append({
                "snapshotTime": snap,
                "openPrice": {"bid": o, "ask": o, "lastTraded": None},
                "highPrice": {"bid": h, "ask": h, "lastTraded": None},
                "lowPrice": {"bid": l, "ask": l, "lastTraded": None},
                "closePrice": {"bid": cls, "ask": cls, "lastTraded": None}
            })
            chunk = []
    return h4

if not os.path.exists("generati"):
    os.makedirs("generati")

for nome, symb in yahoo_syms.items():
    px_live = live_prices.get(nome)
    if not px_live: continue
        
    for tf, (int_str, rng_str) in interval_map.items():
        print(f"Scarico {nome} {tf} da Yahoo...")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symb}?range={rng_str}&interval={int_str}"
        yh_headers = {"User-Agent": "Mozilla/5.0"}
        r_y = requests.get(url, headers=yh_headers)
        if r_y.status_code != 200:
            continue
            
        res = r_y.json().get('chart', {}).get('result', [{}])[0]
        quotes = res.get('indicators', {}).get('quote', [{}])[0]
        timestamps = res.get('timestamp', [])
        opens = quotes.get('open', [])
        highs = quotes.get('high', [])
        lows = quotes.get('low', [])
        closes = quotes.get('close', [])
        
        raw = []
        for t, o, h, l, c in zip(timestamps, opens, highs, lows, closes):
            if h is not None and l is not None and o is not None and c is not None:
                raw.append((t, float(o), float(h), float(l), float(c)))
        
        if not raw: continue
        raw = raw[-100:]
            
        last_cme = raw[-1][4]
        ratio = px_live / last_cme if last_cme > 0 else 1.0
        
        candele = []
        for t, o, h, l, c in raw:
            # Timestamp GMT => Italy Time
            dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
            # Aggiungiamo +2h (CEST) per fuso italiano
            dt_it = dt + datetime.timedelta(hours=2)
            snap = dt_it.strftime("%Y/%m/%d %H:%M:00")
            
            dec = 1 if "Gold" in nome else (2 if "US 500" in nome else 5)
            oo = round(o * ratio, dec)
            hh = round(h * ratio, dec)
            ll = round(l * ratio, dec)
            cc = round(c * ratio, dec)
            
            candele.append({
                "snapshotTime": snap,
                "openPrice": {"bid": oo, "ask": oo, "lastTraded": None},
                "highPrice": {"bid": hh, "ask": hh, "lastTraded": None},
                "lowPrice": {"bid": ll, "ask": ll, "lastTraded": None},
                "closePrice": {"bid": cc, "ask": cc, "lastTraded": None}
            })
            
        safe_name = nome.replace('/', '_').replace(' ', '_')
        with open(f"generati/candele_{safe_name}_{tf}.json", "w") as f:
            json.dump(candele, f)
            
        if tf == "HOUR":
            with open(f"generati/candele_{safe_name}_HOUR_4.json", "w") as f:
                json.dump(aggrega_candele_h4(candele), f)

print("Fatto.")
