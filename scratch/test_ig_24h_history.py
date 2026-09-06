import os
import requests
import json
from dotenv import dotenv_values

for acc in ["BONGIOLO_DEMO", "DANY_DEMO", "FIORDOK_DEMO"]:
    env_path = f"{acc}/.env" if os.path.exists(f"{acc}/.env") else f"/data/{acc}/.env"
    cfg = dotenv_values(env_path)
    session = requests.Session()
    resp = session.post("https://demo-api.ig.com/gateway/deal/session", 
                        json={"identifier": cfg.get("IG_USERNAME"), "password": cfg.get("IG_PASSWORD")}, 
                        headers={"X-IG-API-KEY": cfg.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"})
    cst = resp.headers.get("CST")
    xst = resp.headers.get("X-SECURITY-TOKEN")
    headers = {"X-IG-API-KEY": cfg.get("IG_API_KEY"), "CST": cst, "X-SECURITY-TOKEN": xst, "Version": "3", "Accept": "application/json; charset=UTF-8"}
    
    print(f"\n================ TEST IG HISTORICAL DATA SU {acc} ================")
    # Test scaricamento US 500 Cash
    epic = "IX.D.SPTRD.IBE.IP"
    url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution=HOUR&max=70"
    r = session.get(url, headers=headers)
    if r.status_code == 200:
        prices = r.json().get('prices', [])
        print(f"OK! Ricevute {len(prices)} candele H1 per US 500 Cash.")
        if len(prices) >= 55:
            sub55 = prices[-55:]
            highs = [float(c['highPrice']['bid']) for c in sub55 if c.get('highPrice',{}).get('bid')]
            lows = [float(c['lowPrice']['bid']) for c in sub55 if c.get('lowPrice',{}).get('bid')]
            max_h = max(highs)
            min_l = min(lows)
            kj = (max_h + min_l) / 2.0
            print(f"Prima delle 55: {sub55[0]['snapshotTime']}")
            print(f"Ultima delle 55: {sub55[-1]['snapshotTime']}")
            print(f"Max: {max_h:.2f} | Min: {min_l:.2f}")
            print(f"-> KJ H1 US 500 calcolata su dati 24h IG: {kj:.2f}")
            break
    else:
        print(f"Errore {r.status_code}: {r.text[:100]}")
