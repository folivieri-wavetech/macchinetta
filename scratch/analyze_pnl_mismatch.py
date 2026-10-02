from hyper_order_manager import HyperOrderManager
import requests, json

mgr = HyperOrderManager.get_instance('DANY_DEMO')
mgr._ensure_session()
url = f'{mgr.base_url}/history/transactions?type=ALL&maxSpanSeconds=86400&pageSize=200'
r = requests.get(url, headers={
    'X-IG-API-KEY': mgr.api_key,
    'CST': mgr.cst,
    'X-SECURITY-TOKEN': mgr.xst,
    'Version': '2'
})
txs = r.json().get('transactions', [])
today_txs = [t for t in txs if t.get('dateUtc', '').startswith('2026-10-02')]
print(f'Today transactions on IG: {len(today_txs)}')
tot_pnl_ig = 0.0
for t in today_txs:
    pnl_str = t.get('profitAndLoss', '')
    if pnl_str and pnl_str.startswith('E'):
        val = float(pnl_str[1:])
        tot_pnl_ig += val
        print(f"{t.get('dateUtc')} | {t.get('instrumentName')} | size: {t.get('size')} | {val:+.2f} EUR | ref: {t.get('reference')}")
print(f'TOTAL PnL REAL on IG TODAY: {tot_pnl_ig:+.2f} EUR')

# Ora confrontiamo con hyper_trades_history.json
with open('/data/DANY_DEMO/hyper_trades_history.json') as f:
    hist = json.load(f)

tot_pnl_hist = sum(float(t.get('pnl_eur', 0) or 0) for t in hist)
print(f'TOTAL PnL in hyper_trades_history.json: {tot_pnl_hist:+.2f} EUR')
print(f'DIFFERENCE: {tot_pnl_ig - tot_pnl_hist:+.2f} EUR')
