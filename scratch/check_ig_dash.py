import sys
sys.path.append('/data')
from Dashboard import get_ig_headers
import requests

h = get_ig_headers("DANY_DEMO")
print("Headers obtained:", bool(h))
if h:
    base_url = "https://demo-api.ig.com/gateway/deal"
    r = requests.get(f"{base_url}/positions", headers=h)
    print("Status:", r.status_code)
    if r.status_code == 200:
        positions = r.json().get("positions", [])
        print(f"Total open positions on IG: {len(positions)}")
        for p in positions:
            m = p.get('market', {})
            pos = p.get('position', {})
            print(f"- {m.get('instrumentName')} ({m.get('epic')}): {pos.get('direction')} {pos.get('size')} @ {pos.get('level')}")
