import os
import requests
import json
from dotenv import dotenv_values

env_path = "BONGIOLO_DEMO/.env"
cfg = dotenv_values(env_path)

session = requests.Session()
resp = session.post("https://demo-api.ig.com/gateway/deal/session", 
                    json={"identifier": cfg.get("IG_USERNAME"), "password": cfg.get("IG_PASSWORD")}, 
                    headers={"X-IG-API-KEY": cfg.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8"})
cst = resp.headers.get("CST")
xst = resp.headers.get("X-SECURITY-TOKEN")
headers = {"X-IG-API-KEY": cfg.get("IG_API_KEY"), "CST": cst, "X-SECURITY-TOKEN": xst, "Version": "3", "Accept": "application/json; charset=UTF-8"}

epic = "CS.D.CFEGOLD.CBE.IP"

def get_val(d):
    if isinstance(d, dict):
        return d.get("mid") or d.get("bid") or d.get("ask")
    return d

def compute_atr(prices, period):
    if len(prices) < period + 1:
        return None, None
    
    trs = []
    for i in range(1, len(prices)):
        h = float(get_val(prices[i].get("highPrice")))
        l = float(get_val(prices[i].get("lowPrice")))
        prev_c = float(get_val(prices[i-1].get("closePrice")))
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
        
    # SMA ATR (ultime 'period' candele)
    atr_sma = sum(trs[-period:]) / period
    
    # Wilder's Smoothing ATR
    atr_wilder = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_wilder = (atr_wilder * (period - 1) + tr) / period
        
    return atr_wilder, atr_sma

resolutions = [
    ("M5", "MINUTE_5"),
    ("M15", "MINUTE_15"),
    ("H1", "HOUR"),
    ("H4", "HOUR_4"),
    ("D1", "DAY")
]

print("=== CALCOLO ATR SPOT GOLD (IG DEMO) ===")
for label, res in resolutions:
    url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution={res}&max=150"
    r = session.get(url, headers=headers)
    if r.status_code == 200:
        prices = r.json().get('prices', [])
        ult_c = float(get_val(prices[-1].get("closePrice")))
        w13, s13 = compute_atr(prices, 13)
        w21, s21 = compute_atr(prices, 21)
        print(f"\n--- TIMEFRAME {label} (Ultimo Close: {ult_c:.2f}) ---")
        print(f"Candele disponibili: {len(prices)}")
        print(f"ATR(13): Wilder={w13:.2f} punti | SMA={s13:.2f} punti")
        print(f"ATR(21): Wilder={w21:.2f} punti | SMA={s21:.2f} punti")
    else:
        print(f"Timeframe {label}: Errore {r.status_code} - {r.text}")
