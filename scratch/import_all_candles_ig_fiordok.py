import os
import sys
import time
import json
import requests
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding='utf-8')


CONFIG_STRUMENTI = {
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP"},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP"},
    "EUR/JPY": {"epic": "CS.D.EURJPY.MINI.IP"},
    "GBP/JPY": {"epic": "CS.D.GBPJPY.MINI.IP"},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP"},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP"},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP"},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP"},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP"},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP"},
    "Oil - US Crude": {"epic": "CC.D.CL.UBE.IP"}
}

TIMEFRAMES = ["HOUR", "HOUR_4", "DAY"]

def get_clean_name(nome):
    return nome.replace("/", "_").replace(" ", "_")

def main():
    env_file = "FIORDOK_DEMO/.env"
    if not os.path.exists(env_file):
        print(f"❌ File {env_file} non trovato!")
        sys.exit(1)
        
    cfg = dotenv_values(env_file)
    api_key = cfg.get("IG_API_KEY")
    username = cfg.get("IG_USERNAME")
    password = cfg.get("IG_PASSWORD")
    
    print(f"🔑 Autenticazione IG per {username} (SOLO CONTO FIORDOK)...")
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
    
    print("✅ Autenticato con successo su IG!")
    print(f"📊 Avvio importazione per {len(CONFIG_STRUMENTI)} strumenti × 3 timeframe (H1, H4, D1)...")
    
    total_calls = 0
    total_candles = 0
    target_dirs = [".", "Logs_e_Cache", "FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]
    for d in target_dirs:
        os.makedirs(d, exist_ok=True)
        
    for nome, info in CONFIG_STRUMENTI.items():
        epic = info["epic"]
        clean = get_clean_name(nome)
        print(f"\n📈 Strumento: {nome} (EPIC: {epic})")
        
        for tf in TIMEFRAMES:
            url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution={tf}&max=60&pageSize=0"
            resp = sess.get(url, headers=req_headers, timeout=10)
            total_calls += 1
            
            if resp.status_code == 200:
                data = resp.json()
                prices = data.get("prices", [])
                total_candles += len(prices)
                fname = f"candele_{clean}_{tf}.json"
                
                # Salva in tutte le directory target
                for d in target_dirs:
                    dest_file = os.path.join(d, fname)
                    with open(dest_file, "w", encoding="utf-8") as f:
                        json.dump(prices, f, indent=2)
                        
                print(f"  ✅ [{tf:6}] {len(prices)} candele salvate in '{fname}'")
            else:
                print(f"  ❌ [{tf:6}] Errore {resp.status_code}: {resp.text}")
                
            time.sleep(0.5)  # Rispetto prudenziale del rate limit
            
    print("\n" + "="*60)
    print(f"🏁 COMPLETATO CON SUCCESSO!")
    print(f"📞 Totale chiamate API effettuate: {total_calls} (su 10.000 settimanali disponibili)")
    print(f"🕯️ Totale candele importate: {total_candles}")
    print(f"📦 Dati distribuiti su: {', '.join(target_dirs)}")
    print("="*60)

if __name__ == "__main__":
    main()
