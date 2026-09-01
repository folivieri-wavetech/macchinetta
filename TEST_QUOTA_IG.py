import json
import requests
import sys
import os

print("===========================================")
print(" VERIFICA QUOTA STORICA API IG (BONGIOLO)")
print("===========================================\n")

# Parsing manuale del file .env per estrarre le credenziali
api_key = ""
ig_user = ""
ig_pass = ""
try:
    with open("BONGIOLO_DEMO/.env", "r") as f:
        for line in f:
            if line.startswith("IG_API_KEY"):
                api_key = line.strip().split("=")[1].strip()
            elif line.startswith("IG_USERNAME"):
                ig_user = line.strip().split("=")[1].strip()
            elif line.startswith("IG_PASSWORD"):
                ig_pass = line.strip().split("=")[1].strip()
except Exception:
    print("⚠️ Impossibile leggere il file .env per le credenziali.")
    sys.exit()

# Esegui Login Diretto (Standalone)
login_url = "https://demo-api.ig.com/gateway/deal/session"
login_headers = {
    "X-IG-API-KEY": api_key,
    "VERSION": "2",
    "Content-Type": "application/json"
}
login_payload = {
    "identifier": ig_user,
    "password": ig_pass
}

print("Autenticazione in corso...")
r_login = requests.post(login_url, headers=login_headers, json=login_payload)
if r_login.status_code != 200:
    print("❌ ERRORE: Login fallito.", r_login.text)
    input("\nPremi INVIO per uscire...")
    sys.exit()

cst = r_login.headers.get("CST", "")
xst = r_login.headers.get("X-SECURITY-TOKEN", "")

headers = {
    "CST": cst,
    "X-SECURITY-TOKEN": xst,
    "X-IG-API-KEY": api_key,
    "Accept": "application/json",
    "VERSION": "3"
}

if not headers or "X-SECURITY-TOKEN" not in headers:
    print("❌ ERRORE: Token IG non presente. Esegui prima un normale login da Dashboard.")
    input("\nPremi INVIO per uscire...")
    sys.exit()

epic = "CS.D.CFEGOLD.CBE.IP" # Spot Gold
url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution=MINUTE_5&max=300&pageSize=0"

print(f"Richiesta in corso per {epic}...")

try:
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        dati = response.json()
        candele = dati.get("prices", [])
        print("\n✅ TEST SUPERATO!")
        print(f"IG ha restituito con successo {len(candele)} candele storiche.")
        print("La quota dati storici è stata SBLOCCATA. Puoi riattivare la Macchinetta Trend!")
    elif response.status_code == 403 and "historical-data-allowance" in response.text:
        print("\n❌ TEST FALLITO (Quota Esaurita)")
        print("IG blocca ancora lo scarico dei dati storici (Allowance Exceeded).")
        print("Dettagli:", response.text)
    elif response.status_code == 401:
        print("\n❌ TEST FALLITO (Token Scaduto)")
        print("Il token è scaduto. La macchinetta in cloud si riconnetterà da sola.")
        print("Se vuoi testare localmente, apri la dashboard, entra in Bongiolo e chiudi.")
    else:
        print(f"\n⚠️ RISPOSTA IMPREVISTA (Codice {response.status_code})")
        print(response.text)

except Exception as e:
    print(f"\n❌ ERRORE DI CONNESSIONE: {e}")

print("\n===========================================")
input("Premi INVIO per chiudere questa finestra...")
