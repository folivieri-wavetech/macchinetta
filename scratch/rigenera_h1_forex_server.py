import urllib.request
import json
import os
import datetime
from datetime import timezone, timedelta
import subprocess

TZ_ITALIA = timezone(timedelta(hours=2))

FOREX_SYMBOLS = {
    "AUD/NZD": "AUDNZD=X",
    "CAD/JPY": "CADJPY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/JPY": "GBPJPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "USD/JPY": "USDJPY=X"
}

ACCOUNTS = ["BONGIOLO_DEMO", "DANY_DEMO", "FIORDOK_DEMO", "Logs_e_Cache"]

def scarica_h1(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1h"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        res = data["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        valid = []
        for i in range(len(ts)):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None not in (o, h, l, c) and o > 0 and h > 0 and l > 0 and c > 0:
                dt = datetime.datetime.fromtimestamp(ts[i], tz=timezone.utc).astimezone(TZ_ITALIA)
                valid.append({
                    "snapshotTime": dt.strftime("%Y/%m/%d %H:00:00"),
                    "openPrice": {"bid": round(float(o), 5), "ask": round(float(o), 5), "lastTraded": None},
                    "highPrice": {"bid": round(float(h), 5), "ask": round(float(h), 5), "lastTraded": None},
                    "lowPrice": {"bid": round(float(l), 5), "ask": round(float(l), 5), "lastTraded": None},
                    "closePrice": {"bid": round(float(c), 5), "ask": round(float(c), 5), "lastTraded": None}
                })
        return valid[-60:]

def main():
    print("=== RIGENERAZIONE CANDELE H1 FOREX (60 PERIODI) ===")
    for nome, ticker in FOREX_SYMBOLS.items():
        clean = nome.replace("/", "_").replace(" ", "_")
        print(f"Scaricamento H1 per {nome} ({ticker})...")
        candele = scarica_h1(ticker)
        if len(candele) < 55:
            print(f"⚠️ Attenzione: scaricate solo {len(candele)} candele per {nome}")
        else:
            highs = [c["highPrice"]["bid"] for c in candele[-55:]]
            lows = [c["lowPrice"]["bid"] for c in candele[-55:]]
            kj55 = (max(highs) + min(lows)) / 2
            print(f"  OK {len(candele)} candele | Ultima: {candele[-1]['snapshotTime']} | H1 KJ55: {kj55:.5f}")
        
        fname = f"candele_{clean}_HOUR.json"
        for acc in ACCOUNTS:
            os.makedirs(acc, exist_ok=True)
            p = os.path.join(acc, fname)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(candele, f, indent=2)

    print("\nFile H1 locali salvati con successo per tutti i conti.")

if __name__ == "__main__":
    main()
