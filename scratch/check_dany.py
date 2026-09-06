import json
import os

with open('/data/DANY_DEMO/memoria_parametri.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
    for k, v in d.items():
        if isinstance(v, dict):
            attivo = v.get('attivo')
            stato = v.get('stato')
            direzione = v.get('direzione')
            strat = v.get('tipo_strategia')
            tf = v.get('timeframe')
            n_core = len(v.get('posizioni_core', []))
            print(f"STRUM: {k:<15} | attivo: {str(attivo):<5} | stato: {str(stato):<10} | dir: {str(direzione):<6} | strat: {str(strat):<6} | tf: {str(tf):<8} | n_core: {n_core}")
