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
with open('/data/DANY_DEMO/hyper_trades_history.json') as f:
    hist = json.load(f)

print('--- CONFRONTO COMPLETO ---')
diff_tot = 0.0
for h in hist:
    d_id = h.get('deal_id', '')
    match = None
    for t in txs:
        ref = t.get('reference', '')
        if ref and ref in d_id:
            match = t
            break
    
    hist_pnl = float(h.get('pnl_eur', 0) or 0)
    ig_pnl_str = match.get('profitAndLoss', '') if match else ''
    ig_pnl = float(ig_pnl_str[1:]) if ig_pnl_str.startswith('E') else None
    diff = (ig_pnl - hist_pnl) if ig_pnl is not None else 0.0
    if abs(diff) > 0.05:
        diff_tot += diff
        print(f"DIFF! {h.get('time_close')} | {h.get('label')} | Hist: {hist_pnl:+.2f} | IG: {ig_pnl:+.2f} | Diff: {diff:+.2f} | Deal: {d_id}")
    else:
        # print(f"OK: {h.get('label')} {hist_pnl:+.2f}")
        pass

print(f"TOTALE DISCREPANZA TROVATA: {diff_tot:+.2f} EUR")
