import sys
sys.path.append('/data')
from Dashboard import get_ig_headers
import requests
import json

h = get_ig_headers("DANY_DEMO")
if h:
    base_url = "https://demo-api.ig.com/gateway/deal"
    r = requests.get(f"{base_url}/positions", headers=h)
    if r.status_code == 200:
        positions = r.json().get("positions", [])
        print(f"Total open positions on IG: {len(positions)}")
        for p in positions:
            m = p.get('market', {})
            pos = p.get('position', {})
            print(f"- {m.get('instrumentName')}: dir={pos.get('direction')}, size={pos.get('size')}, level={pos.get('level')}, dealId={pos.get('dealId')}, createdDate={pos.get('createdDate')}")
