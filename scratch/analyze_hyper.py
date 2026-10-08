import json
import subprocess
import sys

# Imposta stdout in utf-8
sys.stdout.reconfigure(encoding='utf-8')

res = subprocess.run([
    "kubectl", "--kubeconfig", "local.yaml", "exec", 
    "macchinetta-dashboard-dfddd56c5-wdn59", "-n", "macchinetta", 
    "--", "cat", "/data/DANY_DEMO/hyper_trades_history.json"
], capture_output=True, text=True, encoding='utf-8')

if res.returncode != 0:
    print("Errore kubectl:", res.stderr)
    exit(1)

trades = json.loads(res.stdout)
print(f"Totale trade registrati in history: {len(trades)}")
tot_pnl = sum(t.get('pnl_eur', 0) for t in trades)
wins = [t for t in trades if t.get('pnl_eur', 0) > 0]
losses = [t for t in trades if t.get('pnl_eur', 0) < 0]
win_rate = (len(wins) / len(trades) * 100) if trades else 0
print(f"PnL Totale: {tot_pnl:.2f} EUR, Wins: {len(wins)}, Losses: {len(losses)}, WinRate: {win_rate:.1f}%\n")

gold_trades = [t for t in trades if 'GOLD' in t.get('epic', '')]
us500_trades = [t for t in trades if 'SPTRD' in t.get('epic', '') or 'US500' in t.get('epic', '')]

def print_stats(name, group):
    pnl = sum(t.get('pnl_eur', 0) for t in group)
    w = [t for t in group if t.get('pnl_eur', 0) > 0]
    wr = len(w) / len(group) * 100 if group else 0
    print(f"--- {name} ---")
    print(f"Trade: {len(group)}, PnL: {pnl:.2f} EUR, WinRate: {wr:.1f}% ({len(w)}/{len(group)})")
    
    # Raggruppa per sessioni / segnali
    longs = [t for t in group if t.get('direction') == 'LONG']
    shorts = [t for t in group if t.get('direction') == 'SHORT']
    print(f"LONG: {len(longs)} trades, PnL: {sum(t.get('pnl_eur', 0) for t in longs):.2f} EUR")
    print(f"SHORT: {len(shorts)} trades, PnL: {sum(t.get('pnl_eur', 0) for t in shorts):.2f} EUR")
    
    # Cause di uscita
    reasons = {}
    for t in group:
        r = t.get('reason', 'Unknown')
        reasons[r] = reasons.get(r, 0) + 1
    print("Motivi di uscita:")
    for r, c in reasons.items():
        print(f"  - {r}: {c}")
    print()

print_stats("SPOT GOLD (5M)", gold_trades)
print_stats("US 500 (5M)", us500_trades)

print("--- DETTAGLIO CRONOLOGICO TUTTI I TRADE ---")
# I trade sono in ordine inverso o diretto? Controlliamo gli orari
for i, t in enumerate(trades):
    open_p = t.get('open_price', 0)
    close_p = t.get('close_price', 0)
    pips = t.get('pips', 0)
    pnl = t.get('pnl_eur', 0)
    print(f"{i+1}. [{t.get('time_open')} -> {t.get('time_close')}] {t.get('epic')[-12:]} | {t.get('direction')} | {t.get('label')} | PnL: {pnl:.2f} EUR | Pips: {pips:.2f} | Open: {open_p} -> Close: {close_p} | Motivo: {t.get('reason')}")
