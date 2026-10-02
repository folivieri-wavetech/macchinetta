import json, os, datetime

path = "/data/DANY_DEMO/hyper_trades_history.json"
with open(path, "r", encoding="utf-8") as f:
    history = json.load(f)

# Carichiamo i trades dai due file di stato
today_str = datetime.date.today().strftime("%Y-%m-%d")

def reconcile_engine(state_path, epic, default_label):
    if not os.path.exists(state_path):
        return []
    with open(state_path, "r", encoding="utf-8") as f:
        s = json.load(f)
    trades = s.get("trades", [])
    added = []
    for t in trades:
        tc = str(t.get("time_close") or t.get("time") or "")
        if not tc:
            continue
        full_tc = f"{today_str} {tc}" if len(tc) <= 8 and ":" in tc else tc
        pnl = float(t.get("pnl_eur") if t.get("pnl_eur") is not None else (t.get("pnl") or 0.0))
        op = float(t.get("open_price", 0.0) or 0.0)
        cp = float(t.get("close_price", 0.0) or 0.0)
        rsn = str(t.get("reason", ""))
        lbl = default_label
        if "Bancomat" in rsn:
            lbl = f"💰 Bancomat {default_label}"
        elif "Runner" in rsn:
            lbl = f"🏃 Runner {default_label}"
        elif "Speed" in rsn:
            lbl = f"⚡ Speed {default_label}"

        # Verifica se già presente in history per ora vicina e pnl uguale
        already = False
        for h in history:
            h_tc = str(h.get("time_close", ""))
            h_pnl = float(h.get("pnl_eur", 0.0) or 0.0)
            if abs(h_pnl - pnl) < 0.05 and h_tc[:16] == full_tc[:16]:
                already = True
                break
        if not already:
            item = {
                "id": str(int(datetime.datetime.now().timestamp() * 1000) + len(added)),
                "time_open": str(t.get("time_open", full_tc)),
                "time_close": full_tc,
                "tf": "5M",
                "epic": epic,
                "direction": t.get("direction", "LONG"),
                "contracts": t.get("contracts", 5),
                "open_price": op,
                "close_price": cp,
                "pips": round(abs(cp - op), 2),
                "pnl_eur": pnl,
                "deal_id": "--",
                "label": lbl,
                "reason": rsn or "Chiusura riconciliata"
            }
            added.append(item)
    return added

add_gold = reconcile_engine("/data/DANY_DEMO/hyper_gold_m5_state.json", "CS.D.CFEGOLD.CBE.IP", "Spot Gold")
add_us = reconcile_engine("/data/DANY_DEMO/hyper_us500_m5_state.json", "IX.D.SPTRD.IBE.IP", "US500")

print(f"Nuovi da Gold: {len(add_gold)}, Nuovi da US500: {len(add_us)}")
history.extend(add_gold)
history.extend(add_us)
history.sort(key=lambda x: str(x.get("time_close", "")), reverse=True)

with open(path, "w", encoding="utf-8") as f:
    json.dump(history, f, indent=2, ensure_ascii=False)

tot = sum(float(t.get("pnl_eur", 0.0) or 0.0) for t in history)
print(f"Totale storico riconciliato: {len(history)} trade, PnL: {tot:+.2f} EUR")
