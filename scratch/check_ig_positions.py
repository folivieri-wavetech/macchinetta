import sys
sys.path.insert(0, '/data')
from Sistema.auth_manager import get_ig_session
session = get_ig_session('DANY_DEMO')
resp = session.get(f'{session.base_url}/positions')
data = resp.json()
positions = data.get('positions', [])
print(f'IG Positions Count: {len(positions)}')
gbp_pos = [p for p in positions if 'GBP' in p['market']['instrumentName']]
print(f'GBP/USD Positions on IG: {len(gbp_pos)}')
for p in gbp_pos:
    pos = p['position']
    print(f"dealId: {pos['dealId']} dir: {pos['direction']} size: {pos['size']} level: {pos['level']} created: {pos['createdDate']}")
