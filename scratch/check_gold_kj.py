import json
import glob
import os
import pandas as pd
from datetime import datetime

def calcola_kj_55(candele):
    if not candele or len(candele) < 55:
        return None
    sub = candele[-55:]
    highs = []
    lows = []
    for c in sub:
        # High
        h = c.get('highPrice', {})
        if isinstance(h, dict):
            hv = h.get('mid') or h.get('bid') or h.get('ask')
        else:
            hv = h
        # Low
        l = c.get('lowPrice', {})
        if isinstance(l, dict):
            lv = l.get('mid') or l.get('bid') or l.get('ask')
        else:
            lv = l
        if hv is not None and lv is not None:
            highs.append(float(hv))
            lows.append(float(lv))
    if len(highs) < 55:
        return None
    return (max(highs) + min(lows)) / 2.0

def main():
    # Cerca file candele per GOLD
    gold_files = glob.glob('FIORDOK_DEMO/*GOLD*.json') + glob.glob('FIORDOK_DEMO/*gold*.json') + glob.glob('FIORDOK_DEMO/*USCGC*.json')
    print("Files trovati per GOLD in FIORDOK_DEMO:", gold_files)
    
    # Cerchiamo anche in radar_trend o stato
    for f in sorted(gold_files):
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
            kj = calcola_kj_55(data)
            print(f"\nFile: {f}")
            print(f"  Num candele: {len(data)}")
            if data:
                print(f"  Prima candela: {data[0].get('snapshotTime')} (close: {data[0].get('closePrice')})")
                print(f"  Ultima candela: {data[-1].get('snapshotTime')} (close: {data[-1].get('closePrice')})")
                print(f"  Max 55: {max(float(c['highPrice']['mid']) for c in data[-55:])} | Min 55: {min(float(c['lowPrice']['mid']) for c in data[-55:])}")
                print(f"  -> KJ 55 calcolata: {kj}")
        except Exception as e:
            print(f"Errore su {f}: {e}")

if __name__ == '__main__':
    main()
