import os
import requests
import json
from dotenv import dotenv_values

env_path = "/data/FIORDOK_DEMO/.env" if os.path.exists("/data/FIORDOK_DEMO/.env") else "FIORDOK_DEMO/.env"
cfg = dotenv_values(env_path)

api_key = cfg.get("IG_API_KEY")
username = cfg.get("IG_USERNAME")
password = cfg.get("IG_PASSWORD")
acc_num = cfg.get("IG_ACC_NUM")

session = requests.Session()
auth_url = "https://demo-api.ig.com/gateway/deal/session"
auth_payload = {
    "identifier": username,
    "password": password
}
auth_headers = {
    "X-IG-API-KEY": api_key,
    "Version": "2",
    "Content-Type": "application/json",
    "Accept": "application/json; charset=UTF-8"
}

resp = session.post(auth_url, json=auth_payload, headers=auth_headers)
if resp.status_code != 200:
    print("Auth failed:", resp.status_code, resp.text)
    exit(1)

cst = resp.headers.get("CST")
xst = resp.headers.get("X-SECURITY-TOKEN")

headers = {
    "X-IG-API-KEY": api_key,
    "CST": cst,
    "X-SECURITY-TOKEN": xst,
    "Version": "1",
    "Accept": "application/json; charset=UTF-8"
}

# Ricerca mercati Gold
m_url = "https://demo-api.ig.com/gateway/deal/markets?searchTerm=Gold"
r = session.get(m_url, headers=headers)
if r.status_code == 200:
    for m in r.json().get('markets', []):
        print(f"{m.get('instrumentName')} | Epic: {m.get('epic')} | Type: {m.get('instrumentType')} | Bid: {m.get('bid')} | Offer: {m.get('offer')}")
else:
    print("Market search error:", r.status_code, r.text)

# Verifichiamo direttamente l'epic Spot Gold configurato CS.D.CFEGOLD.CBE.IP
for epic in ["CS.D.CFEGOLD.CBE.IP", "CS.D.CFDGOLD.CFD.IP", "CS.D.USCGC.TODAY.IP", "IX.D.SPTRD.IBE.IP"]:
    p_url = f"https://demo-api.ig.com/gateway/deal/markets/{epic}"
    p_resp = session.get(p_url, headers={"X-IG-API-KEY": api_key, "CST": cst, "X-SECURITY-TOKEN": xst, "Version": "3"})
    if p_resp.status_code == 200:
        inst = p_resp.json().get('instrument', {})
        snap = p_resp.json().get('snapshot', {})
        print(f"\n--- EPIC: {epic} ---")
        print(f"Name: {inst.get('name')} | Currency: {inst.get('currencies', [{}])[0].get('code')} | Type: {inst.get('type')}")
        print(f"Bid: {snap.get('bid')} | Offer: {snap.get('offer')} | NetChange: {snap.get('netChange')}")
    else:
        print(f"\nEPIC {epic} error: {p_resp.status_code}")
