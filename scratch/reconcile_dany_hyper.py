import json
import os

HISTORY_FILE = "/data/DANY_DEMO/hyper_trades_history.json"
GOLD_STATE_FILE = "/data/DANY_DEMO/hyper_gold_m5_state.json"
US500_STATE_FILE = "/data/DANY_DEMO/hyper_us500_m5_state.json"

# Carica storia attuale
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)
else:
    history = []

# Tutti i trade chiusi odierni con dati certi
confirmed_trades = [
    # US500 Orfano appena chiuso
    {
        "id": "1790665457000",
        "time_open": "2026-09-29 07:50:03",
        "time_close": "2026-09-29 09:04:17",
        "tf": "10M",
        "epic": "IX.D.SPTRD.IBE.IP",
        "direction": "SHORT",
        "contracts": 4,
        "open_price": 7665.37,
        "close_price": 7681.15,
        "pips": -15.78,
        "pnl_eur": -63.12,
        "deal_id": "DIAAAAYJ4T4PRAZ",
        "label": "Inc BANCOMAT US500 10M",
        "reason": "Paracadute KJ US500 (Chiusura FLAT)"
    },
    # Gold TS hit delle 08:17 (06:17 UTC)
    {
        "id": "1790659029000",
        "time_open": "2026-09-29 07:40:01",
        "time_close": "2026-09-29 08:17:09",
        "tf": "10M",
        "epic": "CS.D.CFEGOLD.CBE.IP",
        "direction": "LONG",
        "contracts": 5,
        "open_price": 4135.86,
        "close_price": 4143.48,
        "pips": 7.62,
        "pnl_eur": 38.10,
        "deal_id": "DIAAAAYJ4CE2AB3",
        "label": "Core Spot Gold 10M",
        "reason": "TS Spot Gold 10M @ 4143.83"
    },
    # US500 Core Paracadute delle 06:34 (08:34 Roma)
    {
        "id": "1790656450000",
        "time_open": "2026-09-29 06:30:10",
        "time_close": "2026-09-29 08:34:10",
        "tf": "10M",
        "epic": "IX.D.SPTRD.IBE.IP",
        "direction": "SHORT",
        "contracts": 4,
        "open_price": 7665.17,
        "close_price": 7684.18,
        "pips": -19.01,
        "pnl_eur": -76.04,
        "deal_id": "DIAAAAYJ2DBH7A4",
        "label": "Core US500 10M",
        "reason": "Paracadute KJ US500: Mid 7683.80 >= (KJ 7673.78 + 10p = 7683.78) ➔ FLAT"
    },
    # US500 Runner TS delle 07:39
    {
        "id": "1790653171000",
        "time_open": "2026-09-29 07:20:02",
        "time_close": "2026-09-29 07:39:31",
        "tf": "10M",
        "epic": "IX.D.SPTRD.IBE.IP",
        "direction": "SHORT",
        "contracts": 4,
        "open_price": 7666.61,
        "close_price": 7661.92,
        "pips": 4.69,
        "pnl_eur": 18.76,
        "deal_id": "DIAAAAYJ2LEFNBN",
        "label": "Inc RUNNER US500 10M",
        "reason": "TS Runner Inc (+5.19p)"
    },
    # Gold Core Paracadute delle 07:34 (05:34 UTC)
    {
        "id": "1790652841000",
        "time_open": "2026-09-29 03:50:02",
        "time_close": "2026-09-29 07:34:01",
        "tf": "10M",
        "epic": "CS.D.CFEGOLD.CBE.IP",
        "direction": "LONG",
        "contracts": 5,
        "open_price": 4135.13,
        "close_price": 4121.55,
        "pips": -13.58,
        "pnl_eur": -67.90,
        "deal_id": "DIAAAAYJZZXC9B3",
        "label": "Core Spot Gold 10M",
        "reason": "Paracadute KJ: Mid live 4122.00 <= (KJ 4128.02 - 6p = 4122.02) ➔ FLAT"
    },
    # Gold Bancomat TP delle 05:31
    {
        "id": "1790652672021",
        "time_open": "2026-09-29 04:30:02",
        "time_close": "2026-09-29 05:31:12",
        "tf": "10M",
        "epic": "CS.D.CFEGOLD.CBE.IP",
        "direction": "LONG",
        "contracts": 5,
        "open_price": 4135.99,
        "close_price": 4139.84,
        "pips": 3.85,
        "pnl_eur": 19.25,
        "deal_id": "DIAAAAYJZ4CWDB3",
        "label": "Inc BANCOMAT Spot Gold 10M",
        "reason": "TP Bancomat (+5.0p)"
    },
    # US500 Runner Sicurezza delle 07:18
    {
        "id": "1790651906000",
        "time_open": "2026-09-29 07:10:03",
        "time_close": "2026-09-29 07:18:26",
        "tf": "10M",
        "epic": "IX.D.SPTRD.IBE.IP",
        "direction": "SHORT",
        "contracts": 4,
        "open_price": 7665.87,
        "close_price": 7668.43,
        "pips": -2.56,
        "pnl_eur": -10.24,
        "deal_id": "DIAAAAYJ2FTVMBV",
        "label": "Inc RUNNER US500 10M",
        "reason": "Incasso Sicurezza Runner (dist KJ 10.0p <= 10p, PnL: -2.1p)"
    },
    # US500 Runner Sicurezza delle 07:00
    {
        "id": "1790650840000",
        "time_open": "2026-09-29 07:00:02",
        "time_close": "2026-09-29 07:00:40",
        "tf": "10M",
        "epic": "IX.D.SPTRD.IBE.IP",
        "direction": "SHORT",
        "contracts": 4,
        "open_price": 7665.50,
        "close_price": 7668.67,
        "pips": -3.17,
        "pnl_eur": -12.68,
        "deal_id": "DIAAAAYJ2FABQBK",
        "label": "Inc RUNNER US500 10M",
        "reason": "Incasso Sicurezza Runner (dist KJ 9.9p <= 10p, PnL: -2.7p)"
    }
]

# Mantieni i trade precedenti (della notte) già presenti
existing_deals = {t.get("deal_id") for t in confirmed_trades}
filtered_history = [t for t in history if t.get("deal_id") not in existing_deals]

# Combina: confermati in cima (ordinati decrescenti per id / time_close)
new_history = confirmed_trades + filtered_history

# Salva history
with open(HISTORY_FILE, "w", encoding="utf-8") as f:
    json.dump(new_history, f, indent=2)
print(f"✅ History salvata con successo ({len(new_history)} operazioni)!")

# Sincronizza lo stato di Gold (P&L e trades)
if os.path.exists(GOLD_STATE_FILE):
    with open(GOLD_STATE_FILE, "r", encoding="utf-8") as f:
        g_state = json.load(f)
    g_trades = g_state.get("trades", [])
    
    # Aggiungi a g_trades le chiusure Core che mancavano
    has_c1 = any(t.get("reason") and "4121.55" in t.get("reason", "") or "DIAAAAYJZZXC9B3" in t.get("reason", "") for t in g_trades)
    if not has_c1:
        g_trades.insert(0, {
            "time": "07:34:01",
            "action": "CLOSE CORE 10M LONG (-67.90 €)",
            "open_price": 4135.13,
            "close_price": 4121.55,
            "contracts": 5,
            "pnl": -67.90,
            "balance": 9471.26,
            "reason": "Paracadute KJ: Mid live 4122.00 <= (KJ 4128.02 - 6p = 4122.02) ➔ FLAT"
        })
    has_c2 = any(t.get("reason") and "4143.48" in t.get("reason", "") or "DIAAAAYJ4CE2AB3" in t.get("reason", "") for t in g_trades)
    if not has_c2:
        g_trades.insert(0, {
            "time": "08:17:09",
            "action": "CLOSE CORE 10M LONG (+38.10 €)",
            "open_price": 4135.86,
            "close_price": 4143.48,
            "contracts": 5,
            "pnl": 38.10,
            "balance": 9509.36,
            "reason": "TS Spot Gold 10M @ 4143.83"
        })
    g_state["trades"] = g_trades
    with open(GOLD_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(g_state, f, indent=2)
    print("✅ hyper_gold_m5_state.json aggiornato!")

# Sincronizza lo stato di US500
if os.path.exists(US500_STATE_FILE):
    with open(US500_STATE_FILE, "r", encoding="utf-8") as f:
        u_state = json.load(f)
    u_trades = u_state.get("trades", [])
    has_u_flat = any("DIAAAAYJ2DBH7A4" in str(t.get("reason", "")) for t in u_trades if "CLOSE" in t.get("action", ""))
    if not has_u_flat:
        u_trades.insert(0, {
            "time": "08:34:10",
            "action": "🏁 CLOSE REAL IG US500 SHORT (-76.04 €)",
            "open_price": 7665.17,
            "close_price": 7684.18,
            "contracts": 4,
            "pnl": -76.04,
            "balance": 9771.10,
            "reason": "Paracadute KJ US500: Mid 7683.80 >= (KJ 7673.78 + 10p = 7683.78) ➔ FLAT"
        })
    u_state["trades"] = u_trades
    with open(US500_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(u_state, f, indent=2)
    print("✅ hyper_us500_m5_state.json aggiornato!")
