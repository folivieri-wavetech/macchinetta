import os
import sys
import time
import json
import requests
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding='utf-8')

missing = [
    ('USD/JPY', 'CS.D.USDJPY.MINI.IP', ['DAY']),
    ('Spot Gold', 'CS.D.CFEGOLD.CBE.IP', ['HOUR', 'HOUR_4', 'DAY']),
    ('US 500 Cash', 'IX.D.SPTRD.IBE.IP', ['HOUR', 'HOUR_4', 'DAY']),
    ('Oil - US Crude', 'CC.D.CL.UBE.IP', ['HOUR', 'HOUR_4', 'DAY'])
]

def get_clean_name(nome):
    return nome.replace("/", "_").replace(" ", "_")

def main():
    cfg = dotenv_values('DANY_DEMO/.env')
    sess = requests.Session()
    resp = sess.post('https://demo-api.ig.com/gateway/deal/session',
                     json={'identifier': cfg.get('IG_USERNAME'), 'password': cfg.get('IG_PASSWORD')},
                     headers={'X-IG-API-KEY': cfg.get('IG_API_KEY'), 'Version': '2', 'Content-Type': 'application/json', 'Accept': 'application/json; charset=UTF-8'},
                     timeout=10)
    if resp.status_code != 200:
        print(f"Errore login DANY: {resp.status_code}")
        sys.exit(1)
        
    cst = resp.headers.get('CST')
    xst = resp.headers.get('X-SECURITY-TOKEN')
    headers = {'X-IG-API-KEY': cfg.get('IG_API_KEY'), 'CST': cst, 'X-SECURITY-TOKEN': xst, 'Version': '3', 'Accept': 'application/json; charset=UTF-8'}
    
    target_dirs = [".", "Logs_e_Cache", "FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]
    for d in target_dirs:
        os.makedirs(d, exist_ok=True)
        
    for nome, epic, tfs in missing:
        clean = get_clean_name(nome)
        print(f"Scaricamento per {nome} ({epic})...")
        for tf in tfs:
            url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution={tf}&max=60&pageSize=0"
            r = sess.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                prices = r.json().get("prices", [])
                fname = f"candele_{clean}_{tf}.json"
                for d in target_dirs:
                    with open(os.path.join(d, fname), "w", encoding="utf-8") as f:
                        json.dump(prices, f, indent=2)
                print(f"  ✅ [{tf:6}] {len(prices)} candele salvate in '{fname}'")
            else:
                print(f"  ❌ [{tf:6}] Errore {r.status_code}: {r.text}")
            time.sleep(0.5)

    print("Completato scarico e distribuzione completi!")

if __name__ == "__main__":
    main()
