import os
import sys
import json
import requests
from dotenv import dotenv_values

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ig_request_manager import ig_api_request

# Carica credenziali da FIORDOK_DEMO/.env
env_path = os.path.join("FIORDOK_DEMO", ".env")
if not os.path.exists(env_path):
    env_path = os.path.join("..", "FIORDOK_DEMO", ".env")
cfg = dotenv_values(env_path)

base_url = "https://demo-api.ig.com/gateway/deal"
api_key = cfg.get("IG_API_KEY")
username = cfg.get("IG_USERNAME")
password = cfg.get("IG_PASSWORD")

print(f"Logging in to IG Demo with user {username}...")
login_h = {"X-IG-API-KEY": api_key, "Version": "2", "Content-Type": "application/json"}
login_p = {"identifier": username, "password": password}

r = requests.post(f"{base_url}/session", headers=login_h, json=login_p, timeout=10)
if r.status_code != 200:
    print(f"Login failed: {r.status_code} {r.text}")
    sys.exit(1)

cst = r.headers.get("CST")
xst = r.headers.get("X-SECURITY-TOKEN")
print("Login successful! CST and XST acquired.")

h = {
    "X-IG-API-KEY": api_key,
    "CST": cst,
    "X-SECURITY-TOKEN": xst,
    "Version": "1",
    "Accept": "application/json"
}

def search_ig(term):
    print(f"\n--- Searching IG markets for: '{term}' ---")
    r_search = requests.get(f"{base_url}/markets?searchTerm={term}", headers=h, timeout=10)
    if r_search.status_code != 200:
        print(f"Search failed: {r_search.status_code} {r_search.text}")
        return []
    mkts = r_search.json().get("markets", [])
    print(f"Found {len(mkts)} markets.")
    for m in mkts:
        epic = m.get("epic")
        name = m.get("instrumentName")
        instr_type = m.get("instrumentType")
        bid = m.get("bid")
        offer = m.get("offer")
        high = m.get("high")
        low = m.get("low")
        status = m.get("marketStatus")
        lot_size = m.get("lotSize")
        delay = m.get("delayTime")
        streaming_id = m.get("streamingPricesAvailable")
        print(f"EPIC: {epic} | Name: {name} | Type: {instr_type} | Status: {status} | Bid: {bid} | Offer: {offer} | LotSize: {lot_size}")
    return mkts

# 1. Search Brent
search_ig("brent")

# 2. Search Crude Oil / Petrolio
search_ig("oil")

# 3. Search EUR/JPY Mini
search_ig("EUR/JPY")
search_ig("EURJPY")
