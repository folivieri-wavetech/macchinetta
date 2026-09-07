import json
import requests
from dotenv import dotenv_values
config = dotenv_values(".env")

auth_payload = {
    "identifier": config.get("IG_USERNAME"),
    "password": config.get("IG_PASSWORD")
}
headers = {
    "X-IG-API-KEY": config.get("IG_API_KEY"),
    "Content-Type": "application/json",
    "Accept": "application/json; charset=UTF-8",
    "Version": "2"
}

r = requests.post("https://demo-api.ig.com/gateway/deal/session", json=auth_payload, headers=headers)
if r.status_code == 200:
    cst = r.headers.get("CST")
    xst = r.headers.get("X-SECURITY-TOKEN")
    
    h2 = headers.copy()
    h2["CST"] = cst
    h2["X-SECURITY-TOKEN"] = xst
    h2["Version"] = "1"
    
    r_gold = requests.get("https://demo-api.ig.com/gateway/deal/markets?searchTerm=Spot%20Gold", headers=h2)
    if r_gold.status_code == 200:
        print("Gold:", json.dumps(r_gold.json().get('markets', [])[:5], indent=2))
        
    r_us = requests.get("https://demo-api.ig.com/gateway/deal/markets?searchTerm=US%20500", headers=h2)
    if r_us.status_code == 200:
        print("US500:", json.dumps(r_us.json().get('markets', [])[:5], indent=2))
else:
    print("Login Failed", r.status_code, r.text)
