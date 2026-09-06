import requests
import json
from dotenv import dotenv_values

cfg = dotenv_values("FIORDOK_DEMO/.env")
session = requests.Session()
resp = session.post("https://demo-api.ig.com/gateway/deal/session", 
                    json={"identifier": cfg.get("IG_USERNAME"), "password": cfg.get("IG_PASSWORD")}, 
                    headers={"X-IG-API-KEY": cfg.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"})

cst = resp.headers.get("CST")
xst = resp.headers.get("X-SECURITY-TOKEN")
headers = {"X-IG-API-KEY": cfg.get("IG_API_KEY"), "CST": cst, "X-SECURITY-TOKEN": xst, "Version": "3", "Accept": "application/json; charset=UTF-8"}

# Proviamo a scaricare con limit=10 per non eccedere o con resolution diverse
for res in ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]:
    url = f"https://demo-api.ig.com/gateway/deal/prices/CS.D.CFEGOLD.CBE.IP?resolution={res}&max=10"
    r = session.get(url, headers=headers)
    print(f"IG Spot Gold {res}: Status {r.status_code}")
    if r.status_code == 200:
        prices = r.json().get('prices', [])
        print(f"  Ricevute {len(prices)} candele:")
        for p in prices[-3:]:
            print(f"    {p.get('snapshotTime')} -> H: {p.get('highPrice')} | L: {p.get('lowPrice')} | C: {p.get('closePrice')}")
    else:
        print(f"  {r.text[:120]}")
