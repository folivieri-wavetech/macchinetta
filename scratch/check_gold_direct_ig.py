import os
import requests
import json
from dotenv import dotenv_values

env_path = "BONGIOLO_DEMO/.env"
cfg = dotenv_values(env_path)

session = requests.Session()
resp = session.post("https://demo-api.ig.com/gateway/deal/session", 
                    json={"identifier": cfg.get("IG_USERNAME"), "password": cfg.get("IG_PASSWORD")}, 
                    headers={"X-IG-API-KEY": cfg.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"})
cst = resp.headers.get("CST")
xst = resp.headers.get("X-SECURITY-TOKEN")
headers = {"X-IG-API-KEY": cfg.get("IG_API_KEY"), "CST": cst, "X-SECURITY-TOKEN": xst, "Version": "3", "Accept": "application/json; charset=UTF-8"}

epic = "CS.D.CFEGOLD.CBE.IP"

def calcola_kj_55(candele):
    if not candele or len(candele) < 55:
        return None
    sub = candele[-55:]
    highs, lows = [], []
    for c in sub:
        h = c.get("highPrice", {})
        hv = h.get("mid") or h.get("bid") or h.get("ask") if isinstance(h, dict) else h
        l = c.get("lowPrice", {})
        lv = l.get("mid") or l.get("bid") or l.get("ask") if isinstance(l, dict) else l
        if hv is not None and lv is not None:
            highs.append(float(hv))
            lows.append(float(lv))
    if len(highs) < 55: return None
    return (max(highs) + min(lows)) / 2.0, max(highs), min(lows)

resolutions = [
    ("M5", "MINUTE_5"),
    ("H1", "HOUR"),
    ("H4", "HOUR_4"),
    ("D1", "DAY")
]

print("=== VERIFICA DIRETTA CANDLE STORICHE DA IG PER SPOT GOLD (CS.D.CFEGOLD.CBE.IP) [BONGIOLO_DEMO] ===")
for label, res in resolutions:
    url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution={res}&max=100"
    r = session.get(url, headers=headers)
    if r.status_code == 200:
        prices = r.json().get('prices', [])
        kj_res = calcola_kj_55(prices)
        if kj_res:
            kj, max_h, min_l = kj_res
            print(f"\nTimeframe: {label} ({res}) - Candele ricevute: {len(prices)}")
            print(f"  Range date: da {prices[0].get('snapshotTime')} a {prices[-1].get('snapshotTime')}")
            print(f"  Ultimo Close: {prices[-1].get('closePrice')}")
            print(f"  Ultime 55 barre -> MAX: {max_h:.2f} | MIN: {min_l:.2f}")
            print(f"  -> KJ (55) = ({max_h:.2f} + {min_l:.2f}) / 2 = {kj:.2f} (arrotondato a 1 dec: {round(kj, 1)})")
        else:
            print(f"\nTimeframe {label}: Meno di 55 candele ({len(prices)})")
    else:
        print(f"\nTimeframe {label}: Errore API {r.status_code} - {r.text}")
