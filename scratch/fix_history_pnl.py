import json, shutil, os

path = "DANY_DEMO/hyper_trades_history.json"
backup_path = "DANY_DEMO/hyper_trades_history_backup_20261002.json"

shutil.copyfile(path, backup_path)
print(f"Backup salvato in {backup_path}")

with open(path, "r", encoding="utf-8") as f:
    trades = json.load(f)

old_tot = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades)
print(f"PnL Totale prima della correzione: {old_tot:.2f} EUR")

fixed_count = 0
for t in trades:
    # 1. Bancomat Spot Gold delle 14:05 (chiuso su IG alle 14:29:54 a 4186.91 per -41.75 EUR)
    if t.get("deal_id") == "DIAAAAYLA9G6AB2" or t.get("id") == "1790944950528":
        print(f"Correggo Bancomat | PnL vecchio: {t.get('pnl_eur')} -> nuovo: -41.75 EUR")
        t["close_price"] = 4186.91
        t["pips"] = round(4178.56 - 4186.91, 2)
        t["pnl_eur"] = -41.75
        t["time_close"] = "2026-10-02 14:29:54"
        fixed_count += 1

    # 2. Runner Spot Gold delle 14:05 (chiuso su IG alle 14:29:54 a 4186.91 per -41.10 EUR)
    elif t.get("deal_id") == "DIAAAAYLA92QGA3" or t.get("id") == "1790944949191":
        print(f"Correggo Runner | PnL vecchio: {t.get('pnl_eur')} -> nuovo: -41.10 EUR")
        t["close_price"] = 4186.91
        t["pips"] = round(4178.56 - 4186.91, 2)
        t["pnl_eur"] = -41.10
        t["time_close"] = "2026-10-02 14:29:54"
        fixed_count += 1

new_tot = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades)
print(f"Trade corretti: {fixed_count}")
print(f"PnL Totale dopo la correzione: {new_tot:.2f} EUR")

with open(path, "w", encoding="utf-8") as f:
    json.dump(trades, f, indent=2, ensure_ascii=False)

print("File locale DANY_DEMO/hyper_trades_history.json aggiornato con successo.")
