import json, requests

token = json.load(open('/data/DANY_DEMO/token_ig.json'))
api_key = ''
with open('/data/DANY_DEMO/.env') as f:
    for line in f:
        if 'IG_API_KEY' in line:
            api_key = line.split('=', 1)[1].strip().strip('"\'')

headers = {
    'X-IG-API-KEY': api_key,
    'CST': token.get('CST'),
    'X-SECURITY-TOKEN': token.get('X-SECURITY-TOKEN'),
    'Version': '2'
}
resp = requests.get('https://demo-api.ig.com/gateway/deal/positions', headers=headers)
data = resp.json()
positions = data.get('positions', [])
print('Total IG positions:', len(positions))
gbp_positions = []
for p in positions:
    pos = p['position']
    m = p['market']
    if 'GBP' in m['instrumentName']:
        gbp_positions.append(p)
    print(f"{m['instrumentName']}: {pos['direction']} size={pos['size']} level={pos['level']} dealId={pos['dealId']} created={pos['createdDate']}")

print(f"\n--- GBP/USD SPECIFIC ({len(gbp_positions)} positions) ---")
for p in sorted(gbp_positions, key=lambda x: x['position']['createdDate']):
    pos = p['position']
    print(f"dealId={pos['dealId']} dir={pos['direction']} size={pos['size']} level={pos['level']} created={pos['createdDate']}")
