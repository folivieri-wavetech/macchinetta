import json
import os
import sys

def restore_dany_state(base_dir):
    state_file = os.path.join(base_dir, "hyper_gold_m5_state.json")
    hist_file = os.path.join(base_dir, "hyper_trades_history.json")

    # 1. Ripristina hyper_gold_m5_state.json
    if os.path.exists(state_file):
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["position"] = {
            "direction": "LONG",
            "open_price": 4289.99,
            "contracts": 5,
            "deal_id": "DIAAAAYJRJDHEBW",
            "open_time": "21:25:02"
        }
        data["increments"] = [
            {
                "id": 1,
                "direction": "LONG",
                "open_price": 4293.45,
                "contracts": 5,
                "tp_price": 4298.45,
                "deal_id": "DIAAAAYJRKUS3AU",
                "open_time": "21:45:01",
                "mode": "BANCOMAT"
            }
        ]

        trades = data.get("trades", [])
        # Rimuovi eventuali vecchi record parziali delle stesse posizioni se presenti
        trades = [t for t in trades if "DIAAAAYJRJDHEBW" not in str(t.get("reason", "")) and "DIAAAAYJRKUS3AU" not in str(t.get("reason", ""))]
        # Inserisci le due aperture in testa
        trades.insert(0, {
            "time": "21:45:01",
            "action": "➕ OPEN REAL IG INC LONG (+5c, Tot: 10c)",
            "open_price": 4293.45,
            "close_price": None,
            "contracts": 5,
            "pnl": 0.0,
            "balance": round(data.get("balance", 9801.51), 2),
            "reason": "Incremento M5 IG @ 4293.45 € (TP: 4298.45, Deal ID: DIAAAAYJRKUS3AU)"
        })
        trades.insert(1, {
            "time": "21:25:02",
            "action": "🚀 OPEN REAL IG LONG (5c Core M5)",
            "open_price": 4289.99,
            "close_price": None,
            "contracts": 5,
            "pnl": 0.0,
            "balance": round(data.get("balance", 9801.51), 2),
            "reason": "Ingresso IG Reale LONG @ 4289.99 € (Deal ID Core: DIAAAAYJRJDHEBW)"
        })
        data["trades"] = trades

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"✅ Ripristinato {state_file}")

    # 2. Ripristina hyper_trades_history.json
    if os.path.exists(hist_file):
        with open(hist_file, "r", encoding="utf-8") as f:
            hist = json.load(f)

        if isinstance(hist, list):
            # Rimuovi i due finti trade rifiutati a mezzanotte
            hist_pulito = [
                t for t in hist
                if t.get("deal_id") not in ("DIAAAAYJRKUS3AU", "DIAAAAYJRJDHEBW")
            ]
            with open(hist_file, "w", encoding="utf-8") as f:
                json.dump(hist_pulito, f, indent=2)
            print(f"✅ Ripristinato {hist_file} (rimossi {len(hist) - len(hist_pulito)} trade non conclusi)")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "/data/DANY_DEMO"
    restore_dany_state(target)
