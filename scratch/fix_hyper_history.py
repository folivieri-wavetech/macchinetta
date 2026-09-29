import json
import os

paths = [
    "/data/DANY_DEMO/hyper_trades_history.json",
    "/data/FIORDOK_DEMO/hyper_trades_history.json"
]

for p in paths:
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            changed = 0
            for t in data:
                if isinstance(t, dict):
                    op = float(t.get("open_price", 0.0) or 0.0)
                    lbl = str(t.get("label", ""))
                    rsn = str(t.get("reason", ""))
                    ep = str(t.get("epic", ""))
                    is_us = ("SPTRD" in ep.upper() or "US500" in lbl.upper() or "US500" in rsn.upper() or op > 4000.0)
                    if is_us and ep != "IX.D.SPTRD.IBE.IP":
                        t["epic"] = "IX.D.SPTRD.IBE.IP"
                        if "US500" not in lbl.upper():
                            t["label"] = f"{lbl} US500".strip()
                        changed += 1
            if changed > 0:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"Aggiornati {changed} trade in {p}")
            else:
                print(f"Nessun trade da aggiornare in {p}")
        except Exception as e:
            print(f"Errore su {p}: {e}")
