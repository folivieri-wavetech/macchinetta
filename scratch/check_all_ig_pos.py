import json
import os
import requests

for acc in ['FIORDOK_DEMO', 'DANY_DEMO', 'BONGIOLO_DEMO']:
    tok_f = f'/data/{acc}/token_ig.json'
    env_f = f'/data/{acc}/.env'
    if not os.path.exists(tok_f):
        print(acc, 'No token file')
        continue
    try:
        with open(tok_f) as f:
            tok = json.load(f)
    except Exception as e:
        print(acc, 'Token read error:', e)
        continue
    api_key = ''
    if os.path.exists(env_f):
        with open(env_f) as f:
            for line in f:
                if line.startswith('IG_API_KEY='):
                    api_key = line.split('=', 1)[1].strip().strip('"').strip("'")
    h = {
        'X-IG-API-KEY': api_key,
        'CST': tok.get('CST'),
        'X-SECURITY-TOKEN': tok.get('X-SECURITY-TOKEN'),
        'Accept': 'application/json'
    }
    r = requests.get('https://demo-api.ig.com/gateway/deal/positions', headers=h)
    print('=== ACCOUNT:', acc, 'STATUS:', r.status_code)
    if r.status_code == 200:
        pos = r.json().get('positions', [])
        print('POSIZIONI APERTE:', len(pos))
        for p in pos:
            m = p.get('market', {})
            pos_info = p.get('position', {})
            print(f"  {m.get('instrumentName')} ({m.get('epic')}) | {pos_info.get('direction')} | dealSize: {pos_info.get('dealSize')} | dealId: {pos_info.get('dealId')} | openLevel: {pos_info.get('openLevel')}")
