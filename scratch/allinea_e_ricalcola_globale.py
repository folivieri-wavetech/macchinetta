import os
import sys
import glob
import json
import zoneinfo
import datetime

sys.path.insert(0, '/data')
sys.path.insert(0, '/app')
sys.argv = ['Motore_Trend.py', 'FIORDOK_DEMO']

import Motore_Trend

CONFIG_STRUMENTI = Motore_Trend.CONFIG_STRUMENTI
tfs = ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]

for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
    base_dir = f"/data/{acc}" if os.path.exists("/data") else acc
    print(f"\n=======================================================")
    print(f"🔄 ALLINEAMENTO E CALCOLO REALE PER {acc}")
    print(f"=======================================================")
    
    # Prendi prezzi live
    stato_file = os.path.join(base_dir, "stato_sistema.json")
    prezzi_live = {}
    if os.path.exists(stato_file):
        try:
            with open(stato_file, "r") as f:
                prezzi_live = json.load(f).get("prezzi_live", {})
        except Exception:
            pass
            
    print(f"Prezzi live rilevati: {len(prezzi_live)} strumenti")
    
    os.chdir(base_dir)
    for nome, cfg in CONFIG_STRUMENTI.items():
        px = prezzi_live.get(nome)
        if not px:
            continue
        print(f"\n📊 Strumento: {nome:<12} | Live: {px}")
        for tf in tfs:
            candele = Motore_Trend.carica_candele_locali(nome, tf, px_live=px)
            kj = Motore_Trend.calcola_kj55_da_candele(candele, periods=55)
            last_t = candele[-1].get("snapshotTime") if candele else "N/A"
            kj_str = f"{kj:.{cfg['decimali']}f}" if kj is not None else "N/D"
            pos_rel = "SOPRA KJ (LONG)" if (kj and px >= kj) else ("SOTTO KJ (SHORT)" if kj else "-")
            print(f"   [{tf:8s}] Candele: {len(candele):3d} | Ultimo: {last_t} | KJ55: {kj_str:<10} | {pos_rel}")
            
    # Ricalcola Radar Trend
    mem_file = os.path.join(base_dir, "memoria_parametri.json")
    memoria = {}
    if os.path.exists(mem_file):
        try:
            with open(mem_file, "r") as f:
                memoria = json.load(f)
        except Exception:
            pass
            
    Motore_Trend.aggiorna_radar_trend(prezzi_live, memoria)
    print(f"\n✅ Radar Trend ricalcolato e sincronizzato su disco per {acc}")

print("\n🚀 ALLINEAMENTO E VERIFICA GLOBALE COMPLETATI CON SUCCESSO.")
