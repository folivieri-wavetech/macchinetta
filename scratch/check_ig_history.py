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
    'Version': '3'
}
# Check transaction history for today
resp = requests.get('https://demo-api.ig.com/gateway/deal/history/transactions?type=ALL&maxSpanSeconds=86400', headers=headers)
print('Transactions status:', resp.status_code)
if resp.status_code == 200:
    txs = resp.json().get('transactions', [])
    print(f'Total transactions last 24h: {len(txs)}')
    for t in txs:
        if 'GBP' in t.get('instrumentName', '') or 'CS.D.GBPUSD' in t.get('epic', ''):
            print(t.get('dateUtc'), t.get('instrumentName'), t.get('transactionType'), t.get('size'), t.get('openLevel'), t.get('closeLevel'), t.get('profitAndLoss'), t.get('reference'))

# Check activity history
resp2 = requests.get('https://demo-api.ig.com/gateway/deal/history/activity?maxSpanSeconds=86400', headers=headers)
print('\nActivity status:', resp2.status_code)
if resp2.status_code == 200:
    acts = resp2.json().get('activities', [])
    print(f'Total activities last 24h: {len(acts)}')
    for a in acts:
        epic = a.get('epic', '')
        if 'GBP' in str(a) or 'GBPUSD' in str(a):
            det = a.get('details', {})
            print(a.get('date'), a.get('activity'), a.get('status'), a.get('description'), det.get('dealId'), det.get('size'), det.get('level'))
