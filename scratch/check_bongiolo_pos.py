import requests
import json

with open('BONGIOLO_DEMO/.env') as f:
    env = dict(line.strip().split('=', 1) for line in f if '=' in line and not line.startswith('#'))

headers = {
    'X-IG-API-KEY': env['IG_API_KEY'],
    'Version': '2',
    'Accept': 'application/json; charset=UTF-8',
    'Content-Type': 'application/json; charset=UTF-8'
}
body = {
    'identifier': env['IG_USERNAME'],
    'password': env['IG_PASSWORD']
}

resp = requests.post('https://demo-api.ig.com/gateway/deal/session', json=body, headers=headers)
print('Auth status:', resp.status_code)
if resp.status_code == 200:
    cst = resp.headers.get('CST')
    xst = resp.headers.get('X-SECURITY-TOKEN')
    h_auth = {
        'X-IG-API-KEY': env['IG_API_KEY'],
        'CST': cst,
        'X-SECURITY-TOKEN': xst,
        'Accept': 'application/json'
    }
    r_pos = requests.get('https://demo-api.ig.com/gateway/deal/positions', headers=h_auth)
    print('Positions status:', r_pos.status_code)
    pos_data = r_pos.json().get('positions', [])
    for p in pos_data:
        m = p.get('market', {})
        pos = p.get('position', {})
        name = m.get('instrumentName', '')
        if 'AUD' in name and 'NZD' in name:
            print('=== AUD/NZD POSITION FOUND ===')
            print(json.dumps(p, indent=2))
        else:
            print(name, pos.get('direction'), pos.get('dealSize'), pos.get('openLevel'), pos.get('createdDateUTC'))
else:
    print('Auth error:', resp.text)
