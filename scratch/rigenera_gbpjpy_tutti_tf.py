import requests
import json
import os
import datetime
from datetime import timezone, timedelta

TZ_ITALIA = timezone(timedelta(hours=2))

def scarica_yahoo(ticker, range_str="5d", interval_str="5m"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval={interval_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        return []
    try:
        data = r.json()
        res = data['chart']['result'][0]
        timestamps = res['timestamp']
        indicators = res['indicators']['quote'][0]
        opens = indicators.get('open', [])
        highs = indicators.get('high', [])
        lows = indicators.get('low', [])
        closes = indicators.get('close', [])
        
        bars = []
        for i in range(len(timestamps)):
            t = timestamps[i]
            o = opens[i] if i < len(opens) else None
            h = highs[i] if i < len(highs) else None
            l = lows[i] if i < len(lows) else None
            c = closes[i] if i < len(closes) else None
            if None not in (t, o, h, l, c) and o > 0 and h > 0 and l > 0 and c > 0:
                dt = datetime.datetime.fromtimestamp(t, tz=timezone.utc).astimezone(TZ_ITALIA)
                bars.append({
                    "dt": dt,
                    "open": round(float(o), 3),
                    "high": round(float(h), 3),
                    "low": round(float(l), 3),
                    "close": round(float(c), 3)
                })
        return bars
    except Exception as e:
        print(f"Errore parsing {ticker}: {e}")
        return []

def crea_candela_ig(snap_str, o, h, l, c):
    return {
        "snapshotTime": snap_str,
        "openPrice": {"bid": o, "ask": o, "lastTraded": None},
        "highPrice": {"bid": h, "ask": h, "lastTraded": None},
        "lowPrice": {"bid": l, "ask": l, "lastTraded": None},
        "closePrice": {"bid": c, "ask": c, "lastTraded": None}
    }

def calcola_donchian(candele, periods=55):
    if len(candele) < periods:
        return None
    sub = candele[-periods:]
    highest = max(c['highPrice']['bid'] for c in sub)
    lowest = min(c['lowPrice']['bid'] for c in sub)
    return (highest + lowest) / 2.0

def main():
    print("==========================================================")
    print(" DOWNLOAD CANDLE REALISTICHE GBP/JPY (M5, H1, H4, D1)")
    print("==========================================================")
    
    ticker = "GBPJPY=X"
    
    # 1. M5 (5m)
    print("Scarico dati M5 da Yahoo Finance...")
    bars_m5 = scarica_yahoo(ticker, range_str="5d", interval_str="5m")
    candele_m5 = []
    for b in bars_m5[-100:]:
        snap = b['dt'].strftime("%Y/%m/%d %H:%M:00")
        candele_m5.append(crea_candela_ig(snap, b['open'], b['high'], b['low'], b['close']))
    print(f"Candele M5 pronte: {len(candele_m5)}")
    
    # 2. H1 (1h)
    print("Scarico dati H1 da Yahoo Finance...")
    bars_1h = scarica_yahoo(ticker, range_str="2mo", interval_str="1h")
    candele_h1 = []
    for b in bars_1h[-100:]:
        snap = b['dt'].strftime("%Y/%m/%d %H:00:00")
        candele_h1.append(crea_candela_ig(snap, b['open'], b['high'], b['low'], b['close']))
    print(f"Candele H1 pronte: {len(candele_h1)}")
    
    # 3. H4 (4h aggregate da 1h)
    print("Aggrego H4 da H1...")
    candele_h4 = []
    i = 0
    while i < len(bars_1h):
        b_init = bars_1h[i]
        block = [b_init]
        b_hour_boundary = (b_init['dt'].hour // 4) * 4
        j = i + 1
        while j < len(bars_1h) and (bars_1h[j]['dt'].hour // 4) * 4 == b_hour_boundary and (bars_1h[j]['dt'] - b_init['dt']).total_seconds() < 14400:
            block.append(bars_1h[j])
            j += 1
        i = j
        if block:
            snap_h4 = block[0]['dt'].replace(minute=0, second=0).strftime("%Y/%m/%d %H:00:00")
            o_h4 = block[0]['open']
            h_h4 = max(x['high'] for x in block)
            l_h4 = min(x['low'] for x in block)
            c_h4 = block[-1]['close']
            candele_h4.append(crea_candela_ig(snap_h4, o_h4, h_h4, l_h4, c_h4))
    candele_h4 = candele_h4[-100:]
    print(f"Candele H4 pronte: {len(candele_h4)}")
    
    # 4. D1 (Daily)
    print("Scarico dati D1 da Yahoo Finance...")
    bars_d1 = scarica_yahoo(ticker, range_str="1y", interval_str="1d")
    candele_d1 = []
    for b in bars_d1[-100:]:
        snap = b['dt'].strftime("%Y/%m/%d 00:00:00")
        candele_d1.append(crea_candela_ig(snap, b['open'], b['high'], b['low'], b['close']))
    print(f"Candele D1 pronte: {len(candele_d1)}")
    
    # Calcolo valori KJ55 e TK21
    kj_m5 = calcola_donchian(candele_m5, 55)
    tk_m5 = calcola_donchian(candele_m5, 21)
    
    kj_h1 = calcola_donchian(candele_h1, 55)
    tk_h1 = calcola_donchian(candele_h1, 21)
    
    kj_h4 = calcola_donchian(candele_h4, 55)
    tk_h4 = calcola_donchian(candele_h4, 21)
    
    kj_d1 = calcola_donchian(candele_d1, 55)
    tk_d1 = calcola_donchian(candele_d1, 21)
    
    print("\n--- VALORI CALCOLATI PER GBP/JPY ---")
    print(f"M5 -> KJ55: {kj_m5:.3f} | TK21: {tk_m5:.3f}")
    print(f"H1 -> KJ55: {kj_h1:.3f} | TK21: {tk_h1:.3f}")
    print(f"H4 -> KJ55: {kj_h4:.3f} | TK21: {tk_h4:.3f}")
    print(f"D1 -> KJ55: {kj_d1:.3f} | TK21: {tk_d1:.3f}")
    
    accounts = ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]
    for acc in accounts:
        os.makedirs(acc, exist_ok=True)
        # Salva file candele
        with open(os.path.join(acc, "candele_GBP_JPY_MINUTE_5.json"), "w") as f:
            json.dump(candele_m5, f, indent=2)
        with open(os.path.join(acc, "candele_GBP_JPY_HOUR.json"), "w") as f:
            json.dump(candele_h1, f, indent=2)
        with open(os.path.join(acc, "candele_GBP_JPY_HOUR_4.json"), "w") as f:
            json.dump(candele_h4, f, indent=2)
        with open(os.path.join(acc, "candele_GBP_JPY_DAY.json"), "w") as f:
            json.dump(candele_d1, f, indent=2)
            
        # Rimuovi file candele vecchi di EUR_GBP se presenti
        for old_tf in ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]:
            old_p = os.path.join(acc, f"candele_EUR_GBP_{old_tf}.json")
            if os.path.exists(old_p):
                try:
                    os.remove(old_p)
                except Exception:
                    pass
                    
        # Aggiorna memoria_parametri.json
        mem_file = os.path.join(acc, "memoria_parametri.json")
        mem_data = {}
        if os.path.exists(mem_file):
            try:
                with open(mem_file, "r") as f:
                    mem_data = json.load(f)
            except Exception:
                pass
                
        # Rimuovi EUR/GBP
        if "EUR/GBP" in mem_data:
            del mem_data["EUR/GBP"]
            
        # Inserisci GBP/JPY
        mem_data["GBP/JPY"] = {
            "attivo": False,
            "direzione": "SHORT",
            "tp": 80,
            "opp": 20,
            "dts": 15,
            "size": 3,
            "stato": "FLAT",
            "storico_wip": [],
            "errore_avvio": False,
            "errore_ripristino": False,
            "comando_manuale": False,
            "msg_manuale": "",
            "prezzo_base": 0.0,
            "sospeso_rollover": False,
            "rollover_snapshot": {},
            "tentativi_ripristino": 0,
            "pausa_mercato": false if False else False,
            "stats": {
                "Micro": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Flip": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Ticket1": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Ticket2": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "OverGain": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "OverLoss": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Ultima": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Fase3": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                "Assicurazione": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0}
            },
            "ticket2_active": False,
            "kill_switch": False,
            "sospeso_weekend": False,
            "tipo_strategia": "TREND",
            "allarme_distanza": False,
            "timeframe": "MINUTE_5",
            "size_max": 5,
            "scala": 1,
            "min_body": 5,
            "auto_restart": False,
            "storico_wip_trend": [],
            "posizioni_core": [],
            "posizioni_incr": [],
            "trailing_sl_core": None,
            "trailing_sl_incr": None,
            "needs_manual_start": False,
            "current_tk": tk_m5,
            "current_kj": kj_m5,
            "last_candle_time": candele_m5[-1]['snapshotTime'] if candele_m5 else ""
        }
        
        with open(mem_file, "w") as f:
            json.dump(mem_data, f, indent=4)
        print(f"[OK] Account {acc}: Candele e memoria GBP/JPY aggiornate con successo.")

if __name__ == "__main__":
    main()
