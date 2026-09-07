import sys
import os
import json
import requests
from dotenv import dotenv_values

conto = "DANY_DEMO"
token_path = f"/data/{conto}/token_ig.json"
if not os.path.exists(token_path):
    token_path = f"C:/Users/Fiordok/Desktop/Macchinetta_IG/{conto}/token_ig.json"

with open(token_path, "r") as f:
    token = json.load(f)
    
# Extract API key from the account's .env file
api_key = ""
try:
    with open(f"C:/Users/Fiordok/Desktop/Macchinetta_IG/{conto}/.env", "r") as f:
        for line in f:
            if line.startswith("IG_API_KEY"):
                api_key = line.strip().split("=")[1].strip()
                break
except Exception:
    pass

api_url = "https://demo-api.ig.com/gateway/deal"

headers = {
    "X-IG-API-KEY": api_key,
    "CST": token.get("CST", token.get("cst")),
    "X-SECURITY-TOKEN": token.get("X-SECURITY-TOKEN", token.get("x_st")),
    "Content-Type": "application/json",
    "Accept": "application/json; charset=UTF-8"
}

url_pos = f"{api_url}/positions"
resp = requests.get(url_pos, headers=headers)

if resp.status_code == 200:
    posizioni = resp.json().get('positions', [])
    found = False
    for p in posizioni:
        market = p.get('market', {})
        pos = p.get('position', {})
        epic = market.get('epic', '')
        if "CADJPY" in epic.replace("/", ""):
            deal_id = pos.get('dealId')
            size = pos.get('size')
            direction = pos.get('direction')
            dir_chiusura = "SELL" if direction == "LONG" else "BUY"
            
            print(f"Trovata posizione CADJPY orfana: {deal_id} ({direction} {size}). Chiusura in corso...")
            
            body = {
                "dealId": deal_id,
                "direction": dir_chiusura,
                "size": str(size),
                "orderType": "MARKET"
            }
            
            headers_chiusura = headers.copy()
            headers_chiusura["_method"] = "DELETE"
            headers_chiusura["VERSION"] = "1"
            
            url_chiudi = f"{api_url}/positions/otc"
            r_c = requests.post(url_chiudi, json=body, headers=headers_chiusura)
            if r_c.status_code == 200:
                print(f"Posizione chiusa con successo!")
            else:
                print(f"Errore chiusura: {r_c.status_code} - {r_c.text}")
            found = True
            
    if not found:
        print("Nessuna posizione CADJPY trovata su IG per DANY_DEMO.")
else:
    print(f"Errore recupero posizioni: {resp.status_code} - {resp.text}")
