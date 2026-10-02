from hyper_order_manager import HyperOrderManager
import requests

mgr = HyperOrderManager.get_instance('DANY_DEMO')
mgr._ensure_session()

def find_closed_transaction(epic, open_price, contracts):
    url = f'{mgr.base_url}/history/transactions?type=ALL&maxSpanSeconds=86400&pageSize=50'
    r = requests.get(url, headers=mgr._get_headers(version="2"), timeout=10)
    if r.status_code != 200:
        return None
    txs = r.json().get('transactions', [])
    for t in txs:
        if t.get('transactionType') != 'DEAL':
            continue
        inst = t.get('instrumentName', '').upper()
        if ('GOLD' in epic.upper() and 'GOLD' in inst) or ('SPTRD' in epic.upper() and 'US 500' in inst):
            t_op = float(t.get('openLevel', 0.0) or 0.0)
            if abs(t_op - open_price) < 0.5:
                pnl_str = t.get('profitAndLoss', '')
                pnl = float(pnl_str[1:]) if pnl_str.startswith('E') else float(pnl_str or 0.0)
                cl_lvl = float(t.get('closeLevel', 0.0) or 0.0)
                return {
                    'close_level': cl_lvl,
                    'profit': pnl,
                    'reference': t.get('reference')
                }
    return None

res = find_closed_transaction('CS.D.CFEGOLD.CBE.IP', 4178.56, 5)
print('Found:', res)
