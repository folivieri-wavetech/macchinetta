import json
import requests

api_key = "81e0165a8c24f625859a327db81b380a1ecbc985"
username = "dmatera79"
password = "Cancro@79"
base_url = "https://demo-api.ig.com/gateway/deal"

headers_login = {
    "X-IG-API-KEY": api_key,
    "Content-Type": "application/json",
    "Accept": "application/json; charset=UTF-8",
    "VERSION": "2"
}

body = {
    "identifier": username,
    "password": password
}

resp_login = requests.post(f"{base_url}/session", headers=headers_login, json=body)
if resp_login.status_code == 200:
    cst = resp_login.headers.get("CST")
    xst = resp_login.headers.get("X-SECURITY-TOKEN")
    
    headers_req = {
        "X-IG-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": xst,
        "Content-Type": "application/json",
        "Accept": "application/json; charset=UTF-8",
        "VERSION": "2"
    }
    
    resp = requests.get(f"{base_url}/positions", headers=headers_req)
    if resp.status_code == 200:
        positions = resp.json().get("positions", [])
        for p in positions:
            market = p["market"]
            pos = p["position"]
            if "GBP" in market["epic"] and "USD" in market["epic"]:
                print(f"Deal ID: {pos['dealId']} | Size: {pos.get('size', pos.get('dealSize'))} | Dir: {pos['direction']} | Created: {pos['createdDateUTC']} | Epic: {market['epic']}")
    else:
        print("Error getting positions:", resp.status_code, resp.text)
else:
    print("Login error:", resp_login.status_code, resp_login.text)
