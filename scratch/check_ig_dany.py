import json
import os
import requests

def check_ig_positions():
    base_dir = "/data/DANY_DEMO"
    auth_file = os.path.join(base_dir, "token_ig.json")
    if not os.path.exists(auth_file):
        print("Auth file not found:", auth_file)
        return
    with open(auth_file, "r") as f:
        auth = json.load(f)
    
    headers = {
        "CST": auth.get("cst"),
        "X-SECURITY-TOKEN": auth.get("x_security_token"),
        "X-IG-API-KEY": auth.get("api_key"),
        "Version": "2"
    }
    base_url = "https://demo-api.ig.com/gateway/deal"
    r = requests.get(f"{base_url}/positions", headers=headers)
    print("IG Positions status:", r.status_code)
    if r.status_code == 200:
        positions = r.json().get("positions", [])
        print(f"Total open positions on IG for DANY_DEMO: {len(positions)}")
        for p in positions:
            m = p.get("market", {})
            pos = p.get("position", {})
            print(f"- {m.get('instrumentName')} ({m.get('epic')}): {pos.get('direction')} {pos.get('size')} @ {pos.get('level')}")
    else:
        print(r.text)

if __name__ == "__main__":
    check_ig_positions()
