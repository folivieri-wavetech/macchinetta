import json

with open('/data/DANY_DEMO/hyper_trades_history.json') as f:
    trades = json.load(f)

selected = []
for t in trades:
    tc = t.get('time_close', '')
    if '2026-10-02 17:59:00' <= tc <= '2026-10-06 09:10:05':
        selected.append(t)

selected.sort(key=lambda x: x.get('time_close', ''))

print(f"Trovate {len(selected)} operazioni nel periodo:")
tot_pnl = 0
vinti = 0
persi = 0

for i, t in enumerate(selected, 1):
    pnl = t.get('pnl_eur', 0) or 0
    tot_pnl += pnl
    if pnl > 0:
        vinti += 1
    elif pnl < 0:
        persi += 1
    
    label = t.get('label', '')
    epic = t.get('epic', '')
    instr = "US500" if "SPTRD" in epic else ("GOLD" if "GOLD" in epic else epic)
    direction = t.get('direction', '')
    open_p = t.get('open_price')
    close_p = t.get('close_price')
    pips = t.get('pips')
    reason = t.get('reason')
    t_open = t.get('time_open')
    t_close = t.get('time_close')
    deal_id = t.get('deal_id')
    contracts = t.get('contracts')
    
    print(f"{i:2d}. {t_close} | {instr:5s} | {direction:5s} | {label:22s} | Qta: {contracts} | {open_p} -> {close_p} | {pips:+.2f} pt | {pnl:+.2f} EUR | {reason}")

print(f"\nTotale Operazioni: {len(selected)} (Vinte: {vinti}, Perse: {persi})")
print(f"PnL Cumulato Periodo: {tot_pnl:+.2f} EUR")
