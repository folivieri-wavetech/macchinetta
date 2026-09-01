import json, requests, sys
sys.path.append('/data/Sistema')
from auth_manager import IGAuthManager

auth = IGAuthManager('bongiolo')
t = auth.get_valid_token()

r = requests.get('https://api.ig.com/gateway/deal/prices/CS.D.CFEGOLD.CBE.IP?resolution=MINUTE_5&max=100', headers={
    'X-IG-API-KEY': auth.api_key, 
    'CST': t.get('CST'), 
    'X-SECURITY-TOKEN': t.get('X-SECURITY-TOKEN'), 
    'Version': '3'
})
data = r.json()
prices = data.get('prices', [])
print(f"Number of prices: {len(prices)}")
if len(prices) > 0:
    p = prices[0]
    print(f"First price openPrice: {p.get('openPrice')}")
