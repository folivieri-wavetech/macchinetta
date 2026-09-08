import json
import requests
import time

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
        "VERSION": "1",
        "_method": "DELETE"
    }
    
    deals_to_close = [
        ("DIAAAAYETLNV6AZ", 4.0, "SELL"), # 2:15
        ("DIAAAAYEWG5RXA7", 1.0, "SELL"), # 08:00
        ("DIAAAAYEWJ4M7BT", 1.0, "SELL"), # 08:20
        ("DIAAAAYEWKT6YAB", 1.0, "SELL"), # 08:25
        ("DIAAAAYEWK8QVBK", 1.0, "SELL"), # 08:30
        ("DIAAAAYEWLVQFB3", 1.0, "SELL"), # 08:40
        ("DIAAAAYEWNUXAAB", 1.0, "SELL")  # 09:05
    ]
    
    for deal_id, size, direction in deals_to_close:
        payload = {
            "dealId": deal_id,
            "direction": "BUY" if direction == "SELL" else "SELL",
            "size": str(size),
            "orderType": "MARKET"
        }
        
        print(f"Closing Deal {deal_id} ...")
        resp = requests.post(f"{base_url}/positions/otc", headers=headers_req, json=payload)
        print(resp.status_code, resp.text)
        time.sleep(1)
else:
    print("Login error:", resp_login.status_code, resp_login.text)
