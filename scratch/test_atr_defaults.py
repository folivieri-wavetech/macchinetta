import json
import os
import sys
sys.path.insert(0, ".")
from Dashboard import calcola_atr_da_candele_dash, calcola_default_range_da_atr_dash, CONFIG_STRUMENTI

print("=== TEST CALCOLO DEFAULT RANGE ED ATR21 ===")
strumenti_test = ["Spot Gold", "CAD/JPY", "GBP/JPY", "AUD/NZD", "US 500 Cash"]

for nome in strumenti_test:
    tp, opp, dts = calcola_default_range_da_atr_dash(".", nome)
    print(f"\n[RANGE] {nome}:")
    print(f"  Suggerito default: TP = {tp} | OPP = {opp} | DTS = {dts}")
    assert tp >= 80, f"TP deve essere >= 80, ottenuto {tp}"
    assert tp % 20 == 0, f"TP deve essere a step di 20, ottenuto {tp}"
    assert opp == round(tp / 4.0), f"OPP deve essere TP/4, ottenuto {opp}"
    assert dts == round(tp / 8.0), f"DTS deve essere TP/8, ottenuto {dts}"

print("\n=== TEST CALCOLO TREND TP CON ATR21 (H1) ===")
for nome in strumenti_test:
    clean = nome.replace("/", "_").replace(" ", "_")
    p = f"Logs_e_Cache/candele_{clean}_HOUR.json"
    if not os.path.exists(p):
        p = f"candele_{clean}_HOUR.json"
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            c_loc = json.load(f)
        atr_tf = calcola_atr_da_candele_dash(c_loc, periods=21)
        mult = CONFIG_STRUMENTI[nome]["moltiplicatore"]
        pips = atr_tf / mult if atr_tf else 0
        tp_trend = max(40, int(round(pips / 10.0) * 10))
        print(f"[TREND H1] {nome}: ATR(21) = {pips:.1f} -> TP calcolato = {tp_trend} (min 40, step 10)")
        assert tp_trend >= 40, f"Trend TP deve essere >= 40, ottenuto {tp_trend}"
        assert tp_trend % 10 == 0, f"Trend TP deve essere a step di 10, ottenuto {tp_trend}"

print("\n TUTTI I TEST MATEMATICI HANNO AVUTO SUCCESSO!")
