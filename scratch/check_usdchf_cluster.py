import json
import os

with open('/data/FIORDOK_DEMO/radar_trend.json') as f:
    rad = json.load(f)
print('RADAR USD/CHF:')
print(json.dumps(rad.get('radar_trend', {}).get('USD/CHF', {}), indent=2))

for fn in ['/data/FIORDOK_DEMO/candele_USD_CHF_HOUR.json', '/data/Logs_e_Cache/candele_USD_CHF_HOUR.json', '/data/candele_USD_CHF_HOUR.json']:
    if os.path.exists(fn):
        try:
            with open(fn) as f:
                c = json.load(f)
                st = c[-1].get('snapshotTime') if c else None
                # compute kj55
                recent = c[-55:]
                hi = max(float(x.get('highPrice',{}).get('bid',0)) for x in recent)
                lo = min(float(x.get('lowPrice',{}).get('bid',0)) for x in recent)
                print(f'{fn}: len={len(c)}, last={st}, high={hi}, low={lo}, KJ={(hi+lo)/2}')
        except Exception as e:
            print(f'{fn}: {e}')
    else:
        print(f'{fn}: NOT FOUND')
