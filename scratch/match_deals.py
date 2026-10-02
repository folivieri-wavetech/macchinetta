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
txs = [t for t in r.json().get('transactions', []) if t.get('dateUtc', '').startswith('2026-10-02') and t.get('transactionType') == 'DEAL']

with open('/data/DANY_DEMO/hyper_trades_history.json') as f:
    hist = json.load(f)

print(f"Total IG closed deals today: {len(txs)}")
print(f"Total History deals: {len(hist)}")

# Check each trade in history
for h in hist:
    op_px = round(float(h.get('open_price', 0)), 2)
    h_pnl = round(float(h.get('pnl_eur', 0)), 2)
    t_op = h.get('time_open', '')
    t_cl = h.get('time_close', '')
    is_gold = 'GOLD' in str(h.get('epic', '')).upper() or 'GOLD' in str(h.get('label', '')).upper()
    
    # Trova in txs
    found = []
    for t in txs:
        t_is_gold = 'Gold' in t.get('instrumentName', '')
        if is_gold == t_is_gold:
            t_op_px = round(float(t.get('openLevel', 0)), 2)
            if abs(t_op_px - op_px) < 0.5:
                found.append(t)
    
    # Stampa anomalie
    if '14:42' in t_cl or abs(h_pnl) > 50:
        print(f"HIST: {t_cl} | {h.get('label')} | Open: {op_px} | Close: {h.get('close_price')} | PnL: {h_pnl} EUR")
        for f_t in found:
            print(f"   -> IG: {f_t.get('dateUtc')} | Open: {f_t.get('openLevel')} | Close: {f_t.get('closeLevel')} | PnL: {f_t.get('profitAndLoss')}")
