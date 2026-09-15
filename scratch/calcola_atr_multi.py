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
    atr_sma = sum(trs[-period:]) / period
    atr_wilder = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_wilder = (atr_wilder * (period - 1) + tr) / period
    return atr_wilder, atr_sma

strum_configs = [
    {
        "nome": "SPOT GOLD",
        "key": "Spot_Gold",
        "is_jpy": False,
        "unita": "punti"
    },
    {
        "nome": "CAD/JPY",
        "key": "CAD_JPY",
        "is_jpy": True,
        "unita": "pip"
    },
    {
        "nome": "GBP/JPY",
        "key": "GBP_JPY",
        "is_jpy": True,
        "unita": "pip"
    }
]

timeframes = [
    ("H1 (1 Ora)", "HOUR"),
    ("H4 (4 Ore)", "HOUR_4"),
    ("D1 (Giornaliero)", "DAY")
]

periods = [13, 21, 34]

for sc in strum_configs:
    print(f"\n=======================================================")
    print(f"       STRUMENTO: {sc['nome']}")
    print(f"=======================================================")
    
    for tf_label, tf_code in timeframes:
        path = f"Logs_e_Cache/candele_{sc['key']}_{tf_code}.json"
        if not os.path.exists(path):
            path = f"candele_{sc['key']}_{tf_code}.json"
        if not os.path.exists(path):
            print(f"File non trovato per {sc['nome']} {tf_code}")
            continue
            
        with open(path, "r", encoding="utf-8") as f:
            candles = json.load(f)
            
        trs = calcola_tr(candles)
        last_c = get_mid(candles[-1].get("closePrice"))
        
        # Moltiplicatore pip se JPY
        mult_pip = 100.0 if sc["is_jpy"] else 1.0
        
        c_str = f"{last_c:.3f}" if sc["is_jpy"] else f"{last_c:.2f}"
        print(f"\nTimeframe {tf_label} - Ultimo Close: {c_str} - Candele: {len(candles)}")
        
        for p in periods:
            w, s = compute_atr(trs, p)
            if w is not None and s is not None:
                w_disp = w * mult_pip
                s_disp = s * mult_pip
                if sc["is_jpy"]:
                    print(f"  ATR ({p}): Wilder = {w_disp:.1f} pip ({w:.3f})  |  SMA = {s_disp:.1f} pip ({s:.3f})")
                else:
                    print(f"  ATR ({p}): Wilder = {w_disp:.2f} punti  |  SMA = {s_disp:.2f} punti")
            else:
                print(f"  ATR ({p}): Dati insufficienti")
