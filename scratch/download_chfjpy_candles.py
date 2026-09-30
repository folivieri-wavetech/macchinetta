"""
Script one-shot per scaricare le candele storiche di CHF/JPY Mini (CS.D.CHFJPY.MINI.IP)
da IG usando le credenziali FIORDOK_DEMO.
3 chiamate: DAY (60), HOUR_4 (60), HOUR (60) con pausa 5s tra ciascuna.
"""
import os, sys, json, time, requests
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from dotenv import dotenv_values

# Cerca il file .env di FIORDOK_DEMO
env_paths = [
    "FIORDOK_DEMO/.env",
    "../FIORDOK_DEMO/.env",
    "/data/FIORDOK_DEMO/.env",
    ".env"
]
env_path = None
for p in env_paths:
    if os.path.exists(p):
        env_path = p
        break

if not env_path:
    print("❌ File .env di FIORDOK_DEMO non trovato!")
    sys.exit(1)

print(f"✅ Trovato .env: {env_path}")
cfg = dotenv_values(env_path)
api_key = cfg.get("IG_API_KEY")
username = cfg.get("IG_USERNAME")
password = cfg.get("IG_PASSWORD")

if not api_key or not username or not password:
    print("❌ Credenziali IG incomplete!")
    sys.exit(1)

# Autenticazione
print("🔑 Autenticazione su IG (FIORDOK_DEMO)...")
auth_headers = {
    "X-IG-API-KEY": api_key,
    "Version": "2",
    "Content-Type": "application/json",
    "Accept": "application/json; charset=UTF-8"
}
auth_resp = requests.post(
    "https://demo-api.ig.com/gateway/deal/session",
    headers=auth_headers,
    json={"identifier": username, "password": password},
    timeout=15
)

if auth_resp.status_code != 200:
    print(f"❌ Autenticazione fallita: {auth_resp.status_code} - {auth_resp.text[:200]}")
    sys.exit(1)

cst = auth_resp.headers.get("CST")
xst = auth_resp.headers.get("X-SECURITY-TOKEN")
print(f"✅ Autenticato con successo (CST: {cst[:8]}...)")

req_headers = {
    "X-IG-API-KEY": api_key,
    "CST": cst,
    "X-SECURITY-TOKEN": xst,
    "Version": "3",
    "Accept": "application/json; charset=UTF-8"
}

# Configurazione download
EPIC = "CS.D.CHFJPY.MINI.IP"
CLEAN_NAME = "CHF_JPY"
TIMEFRAMES = ["DAY", "HOUR_4", "HOUR"]
MAX_CANDLES = 60

# Directory di distribuzione (come fa sync_settimanale.py)
target_dirs = [".", "Logs_e_Cache", "/data", "/data/Logs_e_Cache"]
for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    target_dirs.extend([acc, f"../{acc}", f"/data/{acc}"])
valid_dirs = [d for d in set(target_dirs) if os.path.exists(d) and os.path.isdir(d)]
print(f"📁 Directory di distribuzione trovate: {len(valid_dirs)}")

# Download con pausa prudenziale
print(f"\n{'='*50}")
print(f"📥 Download candele CHF/JPY Mini ({EPIC})")
print(f"{'='*50}\n")

for i, tf in enumerate(TIMEFRAMES, 1):
    print(f"[{i}/3] Richiesta {tf} ({MAX_CANDLES} candele)...")
    url = f"https://demo-api.ig.com/gateway/deal/prices/{EPIC}?resolution={tf}&max={MAX_CANDLES}&pageSize=0"
    
    r = requests.get(url, headers=req_headers, timeout=15)
    
    if r.status_code == 200:
        prices = r.json().get("prices", [])
        if prices:
            fname = f"candele_{CLEAN_NAME}_{tf}.json"
            salvati = 0
            for d in valid_dirs:
                dest = os.path.join(d, fname)
                try:
                    tmp = f"{dest}.tmp.{os.getpid()}"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(prices, f, indent=2)
                    os.replace(tmp, dest)
                    salvati += 1
                except Exception:
                    pass
            print(f"  ✅ {tf}: {len(prices)} candele scaricate e salvate in {salvati} directory")
            # Mostra prima e ultima candela
            print(f"     📊 Da: {prices[0].get('snapshotTime', '?')} -> A: {prices[-1].get('snapshotTime', '?')}")
        else:
            print(f"  ⚠️ {tf}: Risposta OK ma nessuna candela ricevuta!")
    elif r.status_code == 403:
        print(f"  🛑 {tf}: ERRORE 403 - Quota esaurita! STOP IMMEDIATO.")
        sys.exit(1)
    else:
        print(f"  ❌ {tf}: Errore {r.status_code} - {r.text[:200]}")
    
    # Pausa prudenziale tra le chiamate (5 secondi)
    if i < len(TIMEFRAMES):
        print(f"  ⏳ Pausa 5 secondi prima della prossima chiamata...")
        time.sleep(5.0)

print(f"\n{'='*50}")
print(f"✅ Download CHF/JPY completato con successo!")
print(f"{'='*50}")
