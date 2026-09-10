import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
from dotenv import dotenv_values
from ig_request_manager import ig_api_request, rate_limiter

accounts = ["BONGIOLO_DEMO", "DANY_DEMO", "FIORDOK_DEMO"]

for acc in accounts:
    env_path = os.path.join(acc, ".env")
    if not os.path.exists(env_path):
        print(f"[{acc}] File .env non trovato.")
        continue
        
    cfg = dotenv_values(env_path)
    api_key = cfg.get("IG_API_KEY")
    username = cfg.get("IG_USERNAME")
    password = cfg.get("IG_PASSWORD")
    
    base_url = "https://demo-api.ig.com/gateway/deal"
    h = {
        "X-IG-API-KEY": api_key,
        "Version": "2",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    p = {
        "identifier": username,
        "password": password
    }
    
    print(f"\n--- TEST LOGIN PER {acc} ({username}) ---")
    r = ig_api_request("POST", f"{base_url}/session", headers=h, payload=p)
    if r is not None and r.status_code == 200:
        cst = r.headers.get("CST")
        x_sec = r.headers.get("X-SECURITY-TOKEN")
        print(f"✅ [{acc}] Login 200 OK! CST={cst[:10]}... SecToken={x_sec[:10]}...")
        
        # Test positions
        h_auth = {
            "X-IG-API-KEY": api_key,
            "CST": cst,
            "X-SECURITY-TOKEN": x_sec,
            "Version": "2"
        }
        r_pos = ig_api_request("GET", f"{base_url}/positions", headers=h_auth)
        if r_pos is not None and r_pos.status_code == 200:
            positions = r_pos.json().get("positions", [])
            print(f"✅ [{acc}] Positions 200 OK! Totale posizioni aperte: {len(positions)}")
            for p_item in positions:
                m = p_item.get("market", {})
                pos = p_item.get("position", {})
                print(f"   -> {m.get('instrumentName')} ({m.get('epic')}): {pos.get('direction')} {pos.get('dealSize')} dealId={pos.get('dealId')}")
        else:
            print(f"❌ [{acc}] Errore get positions: {r_pos.status_code if r_pos else 'None'} {r_pos.text if r_pos else ''}")
    else:
        print(f"❌ [{acc}] Login fallito: {r.status_code if r is not None else 'None'} {r.text if r is not None else ''}")
