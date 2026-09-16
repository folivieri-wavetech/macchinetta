import os
import sys
import time
import json
import requests
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding='utf-8')

CONFIG_STRUMENTI_FOREX = {
    "AUD/NZD": "CS.D.AUDNZD.MINI.IP",
    "CAD/JPY": "CS.D.CADJPY.MINI.IP",
    "EUR/JPY": "CS.D.EURJPY.MINI.IP",
    "GBP/JPY": "CS.D.GBPJPY.MINI.IP",
    "GBP/USD": "CS.D.GBPUSD.MINI.IP",
    "USD/CAD": "CS.D.USDCAD.MINI.IP",
    "USD/CHF": "CS.D.USDCHF.MINI.IP",
    "USD/JPY": "CS.D.USDJPY.MINI.IP",
    "US 500 Cash": "IX.D.SPTRD.IBE.IP"
}

def get_clean_name(nome):
    return nome.replace("/", "_").replace(" ", "_")

def main():
    base_env = "FIORDOK_DEMO/.env" if os.path.exists("FIORDOK_DEMO/.env") else (".env" if os.path.exists(".env") else "/data/FIORDOK_DEMO/.env")
    cfg = dotenv_values(base_env)
    api_key = cfg.get("IG_API_KEY")
    username = cfg.get("IG_USERNAME")
    password = cfg.get("IG_PASSWORD")
    
    print(f"🔑 Autenticazione IG per {username}...")
    sess = requests.Session()
    auth_resp = sess.post(
        "https://demo-api.ig.com/gateway/deal/session",
        json={"identifier": username, "password": password},
        headers={
            "X-IG-API-KEY": api_key,
            "Version": "2",
            "Content-Type": "application/json",
            "Accept": "application/json; charset=UTF-8"
        },
        timeout=10
    )
    
    if auth_resp.status_code != 200:
        print(f"❌ Login fallito: {auth_resp.status_code} - {auth_resp.text}")
        sys.exit(1)
        
    cst = auth_resp.headers.get("CST")
    xst = auth_resp.headers.get("X-SECURITY-TOKEN")
    req_headers = {
        "X-IG-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": xst,
        "Version": "3",
        "Accept": "application/json; charset=UTF-8"
    }
    
    print("✅ Connesso a IG! Inizio scarico candele H1 fresche...")
    
    target_dirs = ["/data", "/data/Logs_e_Cache", "/data/FIORDOK_DEMO", "/data/DANY_DEMO", "/data/BONGIOLO_DEMO", ".", "Logs_e_Cache", "FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]
    existing_dirs = [d for d in set(target_dirs) if os.path.exists(d) and os.path.isdir(d)]
    
    for nome, epic in CONFIG_STRUMENTI_FOREX.items():
        clean = get_clean_name(nome)
        url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution=HOUR&max=60&pageSize=0"
        resp = sess.get(url, headers=req_headers, timeout=10)
        if resp.status_code == 200:
            prices = resp.json().get("prices", [])
            fname = f"candele_{clean}_HOUR.json"
            for d in existing_dirs:
                dest_file = os.path.join(d, fname)
                with open(dest_file, "w", encoding="utf-8") as f:
                    json.dump(prices, f, indent=2)
            print(f"  ✅ {nome:12} ({epic}): {len(prices)} candele H1 salvate (ultima: {prices[-1].get('snapshotTime') if prices else '-'})")
        else:
            print(f"  ❌ {nome:12}: Errore {resp.status_code}: {resp.text}")
        time.sleep(0.3)
        
    print("\n🏁 Scarico completato con successo!")

if __name__ == "__main__":
    main()
