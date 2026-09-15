import json
import os

def get_mid(d):
    if not d:
        return 0.0
    if isinstance(d, dict):
        if d.get("mid") is not None:
            return float(d["mid"])
        b = d.get("bid")
        a = d.get("ask")
        if b is not None and a is not None:
            return (float(b) + float(a)) / 2.0
        if b is not None:
            return float(b)
        if a is not None:
            return float(a)
    return float(d)

def calcola_tr(prices):
    trs = []
    for i in range(1, len(prices)):
        h = get_mid(prices[i].get("highPrice"))
        l = get_mid(prices[i].get("lowPrice"))
        prev_c = get_mid(prices[i-1].get("closePrice"))
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return trs

def compute_atr(trs, period):
    if len(trs) < period:
        return None, None
    # SMA (media semplice degli ultimi 'period' TR)
    atr_sma = sum(trs[-period:]) / period
    
    # Wilder Smoothing (standard Wilder ATR)
    atr_wilder = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_wilder = (atr_wilder * (period - 1) + tr) / period
        
    return atr_wilder, atr_sma

files = [
    ("H1 (1 Ora)", "Logs_e_Cache/candele_Spot_Gold_HOUR.json"),
    ("H4 (4 Ore)", "Logs_e_Cache/candele_Spot_Gold_HOUR_4.json"),
    ("D1 (Giornaliero)", "Logs_e_Cache/candele_Spot_Gold_DAY.json")
]

print("=== CALCOLO ATR SPOT GOLD DA FILE LOCALI ===")
for label, path in files:
    if not os.path.exists(path):
        print(f"{label}: File non trovato {path}")
        continue
    with open(path, "r", encoding="utf-8") as f:
        candles = json.load(f)
    
    trs = calcola_tr(candles)
    w13, s13 = compute_atr(trs, 13)
    w21, s21 = compute_atr(trs, 21)
    
    last_c = get_mid(candles[-1].get("closePrice"))
    t_start = candles[0].get("snapshotTime")
    t_end = candles[-1].get("snapshotTime")
    
    print(f"\nTimeframe: {label}")
    print(f"  Candele totali nel file: {len(candles)} (dal {t_start} al {t_end})")
    print(f"  Ultimo Close: {last_c:.2f}")
    print(f"  ATR(13): Wilder = {w13:.2f} punti  |  SMA = {s13:.2f} punti")
    print(f"  ATR(21): Wilder = {w21:.2f} punti  |  SMA = {s21:.2f} punti")
