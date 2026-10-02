import json, os

path = "DANY_DEMO/hyper_trades_history.json"
with open(path, "r", encoding="utf-8") as f:
    trades = json.load(f)

# Verifica se già presenti per deal_id
existing_deals = {t.get("deal_id") for t in trades}
to_add = []

if "DIAAAAYLBKDSUBM" not in existing_deals:
    to_add.append({
        "id": "1790948434000",
        "time_open": "15:40:00",
        "time_close": "2026-10-02 15:40:34",
        "tf": "5M",
        "epic": "CS.D.CFEGOLD.CBE.IP",
        "direction": "LONG",
        "contracts": 5,
        "open_price": 4199.70,
        "close_price": 4192.24,
        "pips": -7.46,
        "pnl_eur": -37.30,
        "deal_id": "DIAAAAYLBKDSUBM",
        "label": "💰 Bancomat Spot Gold",
        "reason": "Stop Loss Strutturale (4192.24)"
    })

if "DIAAAAYLBK7KYBD" not in existing_deals:
    to_add.append({
        "id": "1790948434001",
        "time_open": "15:40:02",
        "time_close": "2026-10-02 15:40:34",
        "tf": "5M",
        "epic": "CS.D.CFEGOLD.CBE.IP",
        "direction": "LONG",
        "contracts": 5,
        "open_price": 4198.85,
        "close_price": 4192.24,
        "pips": -6.61,
        "pnl_eur": -33.05,
        "deal_id": "DIAAAAYLBK7KYBD",
        "label": "🏃 Runner Spot Gold",
        "reason": "Stop Loss Strutturale (4192.24)"
    })

if to_add:
    # Inseriamo in ordine cronologico decrescente per time_close
    trades.extend(to_add)
    trades.sort(key=lambda x: str(x.get("time_close", "")), reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(trades, f, indent=2, ensure_ascii=False)
    print(f"Aggiunti {len(to_add)} trade mancanti delle 15:40 con successo!")
else:
    print("Trade delle 15:40 già presenti.")

tot = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in trades)
print(f"Nuovo totale trade: {len(trades)}, PnL totale: {tot:.2f} EUR")
