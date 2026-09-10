import requests
from dotenv import dotenv_values

accounts = ['FIORDOK_DEMO', 'DANY_DEMO', 'BONGIOLO_DEMO']
for acc in accounts:
    cfg = dotenv_values(f'{acc}/.env')
    sess = requests.Session()
    resp = sess.post('https://demo-api.ig.com/gateway/deal/session',
                     json={'identifier': cfg.get('IG_USERNAME'), 'password': cfg.get('IG_PASSWORD')},
                     headers={'X-IG-API-KEY': cfg.get('IG_API_KEY'), 'Version': '2', 'Content-Type': 'application/json', 'Accept': 'application/json; charset=UTF-8'})
    cst = resp.headers.get('CST')
    xst = resp.headers.get('X-SECURITY-TOKEN')
    headers = {'X-IG-API-KEY': cfg.get('IG_API_KEY'), 'CST': cst, 'X-SECURITY-TOKEN': xst, 'Version': '3', 'Accept': 'application/json; charset=UTF-8'}
    
    r = sess.get('https://demo-api.ig.com/gateway/deal/prices/CS.D.GBPJPY.MINI.IP?resolution=HOUR&max=2', headers=headers)
    print(f"=== {acc} ===")
    print(f"Status Code: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Candles count: {len(data.get('prices', []))}")
        print(f"Allowance info: {data.get('allowance')}")
    else:
        print(f"Error body: {r.text}")
