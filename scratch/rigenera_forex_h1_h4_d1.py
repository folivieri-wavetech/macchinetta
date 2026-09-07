import requests
import json
import os
import datetime
from datetime import timezone, timedelta

# Fuso orario Europa/Roma (UTC+2 in estate)
TZ_ITALIA = timezone(timedelta(hours=2))

FOREX_SYMBOLS = {
    "AUD/CAD": "AUDCAD=X",
    "AUD/NZD": "AUDNZD=X",
    "CAD/JPY": "CADJPY=X",
    "EUR/GBP": "EURGBP=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "USD/JPY": "USDJPY=X"
}

def scarica_yahoo(ticker, range_str="1mo", interval_str="1h"):
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
                    "open": round(float(o), 5),
                    "high": round(float(h), 5),
                    "low": round(float(l), 5),
                    "close": round(float(c), 5)
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

def calcola_kj55(candele):
    if len(candele) < 55:
        return None
    sub = candele[-55:]
    highest = max(c['highPrice']['bid'] for c in sub)
    lowest = min(c['lowPrice']['bid'] for c in sub)
    return (highest + lowest) / 2.0

def genera_tutti():
    accounts = ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]
    for acc in accounts:
        os.makedirs(acc, exist_ok=True)
        
    print("==========================================================")
    print(" RECUPERO DATI STORICI VEROSIMILI PER 8 CROSS FOREX")
    print(" TF: H1, H4, D1 (M5 ESCLUSO, GOLD E US500 ESCLUSI)")
    print("==========================================================\n")
    
    for nome, ticker in FOREX_SYMBOLS.items():
        clean = nome.replace("/", "_").replace(" ", "_")
        print(f"--- Elaborazione {nome} ({ticker}) ---")
        
        # 1. Scarica H1 (ultimi 30 giorni orari)
        bars_1h = scarica_yahoo(ticker, range_str="1mo", interval_str="1h")
        if not bars_1h:
            print(f"❌ Impossibile scaricare dati H1 per {ticker}")
            continue
            
        candele_h1 = []
        for b in bars_1h[-100:]:
            snap = b['dt'].strftime("%Y/%m/%d %H:00:00")
            candele_h1.append(crea_candela_ig(snap, b['open'], b['high'], b['low'], b['close']))
            
        # 2. Genera H4 aggregando le ore a blocchi di 4 ore
        candele_h4 = []
        i = 0
        while i < len(bars_1h):
            # Cerca inizio blocco multiplo di 4 ore
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
        
        # 3. Scarica D1 (ultimi 6 mesi giornalieri)
        bars_d1 = scarica_yahoo(ticker, range_str="1y", interval_str="1d")
        candele_d1 = []
        if bars_d1:
            for b in bars_d1[-100:]:
                snap_d = b['dt'].strftime("%Y/%m/%d 00:00:00")
                candele_d1.append(crea_candela_ig(snap_d, b['open'], b['high'], b['low'], b['close']))
                
        # Calcolo KJ di verifica
        kj_h1 = calcola_kj55(candele_h1)
        kj_h4 = calcola_kj55(candele_h4)
        kj_d1 = calcola_kj55(candele_d1)
        
        print(f"  H1 ({len(candele_h1)} candele) -> KJ55: {kj_h1}")
        print(f"  H4 ({len(candele_h4)} candele) -> KJ55: {kj_h4}")
        print(f"  D1 ({len(candele_d1)} candele) -> KJ55: {kj_d1}")
        
        # Salva i file per ciascun account
        for acc in accounts:
            p_h1 = os.path.join(acc, f"candele_{clean}_HOUR.json")
            p_h4 = os.path.join(acc, f"candele_{clean}_HOUR_4.json")
            p_d1 = os.path.join(acc, f"candele_{clean}_DAY.json")
            
            with open(p_h1, "w", encoding="utf-8") as f:
                json.dump(candele_h1, f, indent=2)
            with open(p_h4, "w", encoding="utf-8") as f:
                json.dump(candele_h4, f, indent=2)
            if candele_d1:
                with open(p_d1, "w", encoding="utf-8") as f:
                    json.dump(candele_d1, f, indent=2)

    print("\n[OK] File generati con successo per tutti i 3 conti!")

if __name__ == "__main__":
    genera_tutti()
