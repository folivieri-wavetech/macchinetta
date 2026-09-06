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

# Controlliamo i mercati Gold su IG
print("--- PREZZI LIVE SU IG ---")
for epic in ["CS.D.CFEGOLD.CBE.IP", "CS.D.CFEGOLD.CEB.IP", "MT.D.GC.FWS3.IP"]:
    p_url = f"https://demo-api.ig.com/gateway/deal/markets/{epic}"
    r = session.get(p_url, headers=headers)
    if r.status_code == 200:
        inst = r.json().get('instrument', {})
        snap = r.json().get('snapshot', {})
        print(f"Name: {inst.get('name')} | Epic: {epic} | Currency: {inst.get('currencies',[{}])[0].get('code')} | Bid: {snap.get('bid')} | Offer: {snap.get('offer')}")
    else:
        print(f"Epic {epic}: {r.status_code}")

# Yahoo Finance GC=F
y_url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range=1d&interval=5m"
r_y = requests.get(y_url, headers={"User-Agent": "Mozilla/5.0"})
if r_y.status_code == 200:
    res = r_y.json().get('chart', {}).get('result', [{}])[0]
    quotes = res.get('indicators', {}).get('quote', [{}])[0]
    closes = quotes.get('close', [])
    print(f"\n--- YAHOO FINANCE: GC=F (CME Gold Futures) ---")
    print(f"Ultimo prezzo: {closes[-1] if closes else 'N/D'}")
