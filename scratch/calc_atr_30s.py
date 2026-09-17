import json

path = "hyper_gold_state.json"
with open(path, "r", encoding="utf-8") as f:
    d = json.load(f)

candles = d.get("candles", [])
print(f"Candele totali memorizzate per 30S: {len(candles)}")

if len(candles) < 22:
    print("Meno di 22 candele memorizzate.")
    exit()

# Calcolo True Range (TR)
# TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
tr_list = []
for i in range(1, len(candles)):
    c = candles[i]
    prev_c = candles[i - 1]
    h = c["high"]
    l = c["low"]
    pc = prev_c["close"]
    tr = max(h - l, abs(h - pc), abs(l - pc))
    tr_list.append((c.get("time", ""), tr, h - l))

# Calcolo ATR(21)
# Metodo 1: Semplice SMA su ultime 21 barre
recent_21 = tr_list[-21:]
atr_sma_21 = sum(x[1] for x in recent_21) / 21.0

# Metodo 2: Esponenziale / Wilder RMA standard (su tutto lo storico)
atr_rma = sum(x[1] for x in tr_list[:21]) / 21.0
atr_history = [(tr_list[20][0], atr_rma)]
for i in range(21, len(tr_list)):
    atr_rma = (atr_rma * 20.0 + tr_list[i][1]) / 21.0
    atr_history.append((tr_list[i][0], atr_rma))

# Statistiche aggiuntive
last_time, last_atr_rma = atr_history[-1]
avg_high_low_21 = sum(x[2] for x in recent_21) / 21.0
min_tr_21 = min(x[1] for x in recent_21)
max_tr_21 = max(x[1] for x in recent_21)

print("\n--- RISULTATI ATR(21) GOLD 30 SECONDI ---")
print(f"Ultimo orario candela: {last_time}")
print(f"ATR(21) Wilder/Standard attuale: {last_atr_rma:.2f} pip (punti)")
print(f"ATR(21) Media Semplice (ultime 21 candele = 10.5 min): {atr_sma_21:.2f} pip")
print(f"Escursione Media High-Low (ultime 21 candele): {avg_high_low_21:.2f} pip")
print(f"Range Minimo TR nelle ultime 21 candele: {min_tr_21:.2f} pip")
print(f"Range Massimo TR nelle ultime 21 candele: {max_tr_21:.2f} pip")

# Statistiche storiche su tutte le 500 candele (ultime ~4 ore e mezza di trading)
all_trs = [x[1] for x in tr_list]
print(f"\nMedia TR sull'intero storico ({len(tr_list)} barre, ~4h): {sum(all_trs)/len(all_trs):.2f} pip")
print(f"ATR(21) minimo registrato oggi: {min(x[1] for x in atr_history):.2f} pip")
print(f"ATR(21) massimo registrato oggi: {max(x[1] for x in atr_history):.2f} pip")
