from hyper_order_manager import HyperOrderManager
import requests, json, datetime

mgr = HyperOrderManager.get_instance('DANY_DEMO')
mgr._ensure_session()
url = f'{mgr.base_url}/history/transactions?type=ALL&maxSpanSeconds=86400&pageSize=100'
r = requests.get(url, headers=mgr._get_headers(version='2'))
txs = [t for t in r.json().get('transactions', []) if t.get('dateUtc', '').startswith('2026-10-02') and t.get('transactionType') == 'DEAL']

# Filtriamo solo le operazioni dalle 07:00 UTC (09:00 italiane) in poi (inizio sessione odierna 5M)
session_txs = [t for t in txs if t.get('dateUtc') >= '2026-10-02T07:00:00']
print(f"Operazioni totali della sessione 5M su IG: {len(session_txs)}")

clean_history = []
for t in session_txs:
    inst = t.get('instrumentName', '')
    is_gold = 'Gold' in inst
    epic = "CS.D.CFEGOLD.CBE.IP" if is_gold else "IX.D.SPTRD.IBE.IP"
    name_str = "Spot Gold" if is_gold else "US500"
    
    pnl_str = t.get('profitAndLoss', 'E0')
    pnl = float(pnl_str[1:]) if pnl_str.startswith('E') else float(pnl_str or 0.0)
    
    op_px = float(t.get('openLevel', 0.0) or 0.0)
    cl_px = float(t.get('closeLevel', 0.0) or 0.0)
    
    size_str = str(t.get('size', '5'))
    direction = "LONG" if size_str.startswith('+') else "SHORT"
    contracts = abs(float(size_str))
    
    # Orario italiano (UTC + 2)
    dt_utc = datetime.datetime.fromisoformat(t.get('dateUtc'))
    dt_it = dt_utc + datetime.timedelta(hours=2)
    time_close_str = dt_it.strftime("%Y-%m-%d %H:%M:%S")
    
    dt_op_utc = datetime.datetime.fromisoformat(t.get('openDateUtc')) if t.get('openDateUtc') else dt_utc
    dt_op_it = dt_op_utc + datetime.timedelta(hours=2)
    time_open_str = dt_op_it.strftime("%H:%M:%S")
    
    ref = t.get('reference', '')
    
    # Determiniamo etichetta intelligente
    if pnl < 0:
        lbl = f"🏃 Runner {name_str}" if contracts == 5 else f"💰 Bancomat {name_str}"
        rsn = f"Stop Loss ({cl_px:.2f})"
    elif pnl > 30.0:
        lbl = f"🏃 Runner {name_str}"
        rsn = f"Trailing Stop Runner ({cl_px:.2f})"
    elif 10.0 <= pnl <= 25.0:
        lbl = f"💰 Bancomat {name_str}"
        rsn = f"TP1 Bancomat Incassato"
    else:
        lbl = f"⚡ Speed 1 {name_str}"
        rsn = f"Hit TP Rapido"
        
    pips = round(abs(cl_px - op_px), 2)
    
    clean_history.append({
        "id": str(int(dt_it.timestamp() * 1000)),
        "time_open": time_open_str,
        "time_close": time_close_str,
        "tf": "5M",
        "epic": epic,
        "direction": direction,
        "contracts": int(contracts),
        "open_price": op_px,
        "close_price": cl_px,
        "pips": pips if pnl >= 0 else -pips,
        "pnl_eur": round(pnl, 2),
        "deal_id": ref,
        "label": lbl,
        "reason": rsn
    })

clean_history.sort(key=lambda x: x["time_close"], reverse=True)
pnl_tot = sum(t["pnl_eur"] for t in clean_history)
print(f"Costruito storico certificato IG: {len(clean_history)} operazioni, P&L Netto: {pnl_tot:+.2f} EUR")

path = "/data/DANY_DEMO/hyper_trades_history.json"
with open(path, "w", encoding="utf-8") as f:
    json.dump(clean_history, f, indent=2, ensure_ascii=False)
print("Salvato in /data/DANY_DEMO/hyper_trades_history.json!")
