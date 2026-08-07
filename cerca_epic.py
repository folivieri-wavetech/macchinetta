import requests
import json
from dotenv import dotenv_values

config = dotenv_values(".env")
h = {"X-IG-API-KEY": config.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json"}
p = {"identifier": config.get("IG_USERNAME"), "password": config.get("IG_PASSWORD")}

# Login
r = requests.post("https://demo-api.ig.com/gateway/deal/session", headers=h, json=p)
if r.status_code == 200:
    cst = r.headers.get('CST')
    sec = r.headers.get('X-SECURITY-TOKEN')
    h_search = {
        "X-IG-API-KEY": config.get("IG_API_KEY"),
        "CST": cst,
        "X-SECURITY-TOKEN": sec,
        "Version": "1"
    }
    # Cerca ETH nel database IG
    r_s = requests.get("https://demo-api.ig.com/gateway/deal/markets?searchTerm=ETH", headers=h_search)
    if r_s.status_code == 200:
        print("\n🔍 RISULTATI RICERCA IG PER 'ETH':\n")
        for m in r_s.json().get('markets', []):
            print(f"📌 Nome: {m.get('instrumentName')} | EPIC: {m.get('epic')}")
    else:
        print("Errore ricerca:", r_s.text)
else:
    print("Errore Login IG:", r.text)