import requests
import json
import os
import sys
import datetime
from datetime import timedelta

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(timedelta(hours=2))

INSTRUMENTS = {
    "AUD/NZD": "AUDNZD=X",
    "CAD/JPY": "CADJPY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/JPY": "GBPJPY=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CAD": "USDCAD=X",
    "USD/CHF": "USDCHF=X",
    "USD/JPY": "USDJPY=X",
    "Spot Gold": "GC=F",
    "US 500 Cash": "ES=F"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def fetch_yf_candles(symbol, interval, range_str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range_str}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            print(f"  [!] HTTP {r.status_code} for {symbol} ({interval})")
            return []
        data = r.json()
        res = data['chart']['result'][0]
        timestamps = res['timestamp']
        q = res['indicators']['quote'][0]
        opens = q['open']
        highs = q['high']
        lows = q['low']
        closes = q['close']
        
        candles = []
        for i in range(len(timestamps)):
            if highs[i] is None or lows[i] is None or opens[i] is None or closes[i] is None:
                continue
            # Convert UTC timestamp to Italian Timezone
            dt_utc = datetime.datetime.fromtimestamp(timestamps[i], datetime.timezone.utc)
            dt_it = dt_utc.astimezone(TZ_ITALIA)
            snap = dt_it.strftime("%Y/%m/%d %H:%M:00")
            
            o = float(opens[i])
            h = float(highs[i])
            l = float(lows[i])
            c = float(closes[i])
            
            candles.append({
                "snapshotTime": snap,
                "openPrice": {"bid": o, "ask": o, "lastTraded": None},
                "highPrice": {"bid": h, "ask": h, "lastTraded": None},
                "lowPrice": {"bid": l, "ask": l, "lastTraded": None},
                "closePrice": {"bid": c, "ask": c, "lastTraded": None}
            })
        return candles
    except Exception as e:
        print(f"  [!] Error fetching {symbol} ({interval}): {e}")
        return []

def aggregate_h4(h1_candles):
    """Aggregate H1 candles into H4 candles aligned to standard 4h boundaries."""
    if not h1_candles:
        return []
    h4_list = []
    # Group by 4-hour blocks
    current_block = []
    current_block_id = None
    
    for c in h1_candles:
        snap_str = c["snapshotTime"]
        try:
            dt = datetime.datetime.strptime(snap_str, "%Y/%m/%d %H:%M:00")
            block_h = (dt.hour // 4) * 4
            block_id = dt.replace(hour=block_h, minute=0, second=0)
            
            if current_block_id is None:
                current_block_id = block_id
            
            if block_id != current_block_id:
                # Close previous block
                if current_block:
                    o = current_block[0]["openPrice"]["bid"]
                    h = max(x["highPrice"]["bid"] for x in current_block)
                    l = min(x["lowPrice"]["bid"] for x in current_block)
                    cls = current_block[-1]["closePrice"]["bid"]
                    h4_list.append({
                        "snapshotTime": current_block_id.strftime("%Y/%m/%d %H:%M:00"),
                        "openPrice": {"bid": o, "ask": o, "lastTraded": None},
                        "highPrice": {"bid": h, "ask": h, "lastTraded": None},
                        "lowPrice": {"bid": l, "ask": l, "lastTraded": None},
                        "closePrice": {"bid": cls, "ask": cls, "lastTraded": None}
                    })
                current_block = [c]
                current_block_id = block_id
            else:
                current_block.append(c)
        except Exception:
            pass
            
    if current_block and current_block_id:
        o = current_block[0]["openPrice"]["bid"]
        h = max(x["highPrice"]["bid"] for x in current_block)
        l = min(x["lowPrice"]["bid"] for x in current_block)
        cls = current_block[-1]["closePrice"]["bid"]
        h4_list.append({
            "snapshotTime": current_block_id.strftime("%Y/%m/%d %H:%M:00"),
            "openPrice": {"bid": o, "ask": o, "lastTraded": None},
            "highPrice": {"bid": h, "ask": h, "lastTraded": None},
            "lowPrice": {"bid": l, "ask": l, "lastTraded": None},
            "closePrice": {"bid": cls, "ask": cls, "lastTraded": None}
        })
    return h4_list

def run_seeder():
    print("🚀 Inizio Seeding Candele da Yahoo Finance per tutti i 10 strumenti...")
    
    # Target directories to populate
    target_dirs = []
    for base in ["/data", "."]:
        if os.path.exists(base):
            for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO", "Logs_e_Cache"]:
                p = os.path.join(base, acc)
                if os.path.exists(p) and p not in target_dirs:
                    target_dirs.append(p)
    print(f"Target directories: {target_dirs}")
    
    for nome, sym in INSTRUMENTS.items():
        clean = nome.replace("/", "_").replace(" ", "_")
        print(f"\n--- {nome} ({sym}) ---")
        
        # 1. MINUTE_5
        m5_all = fetch_yf_candles(sym, "5m", "5d")
        if m5_all:
            # We take last 60 closed candles (ignoring candle currently forming if needed, or last 60)
            m5_60 = m5_all[-60:]
            print(f"  M5: {len(m5_60)} candele (da {m5_60[0]['snapshotTime']} a {m5_60[-1]['snapshotTime']})")
            # Calculate Donchian 21 & 55 for quick validation
            h21 = max(c['highPrice']['bid'] for c in m5_60[-21:])
            l21 = min(c['lowPrice']['bid'] for c in m5_60[-21:])
            tk21 = (h21 + l21) / 2
            h55 = max(c['highPrice']['bid'] for c in m5_60[-55:])
            l55 = min(c['lowPrice']['bid'] for c in m5_60[-55:])
            kj55 = (h55 + l55) / 2
            print(f"      Validazione M5 -> TK(21): {tk21:.5f} | KJ(55): {kj55:.5f}")
            save_everywhere(f"candele_{clean}_MINUTE_5.json", m5_60, target_dirs)
        
        # 2. HOUR
        h1_all = fetch_yf_candles(sym, "1h", "1mo")
        if h1_all:
            h1_60 = h1_all[-60:]
            print(f"  H1: {len(h1_60)} candele (da {h1_60[0]['snapshotTime']} a {h1_60[-1]['snapshotTime']})")
            save_everywhere(f"candele_{clean}_HOUR.json", h1_60, target_dirs)
            
            # 3. HOUR_4 (derived from H1)
            h4_all = aggregate_h4(h1_all)
            if h4_all:
                h4_60 = h4_all[-60:]
                print(f"  H4: {len(h4_60)} candele (da {h4_60[0]['snapshotTime']} a {h4_60[-1]['snapshotTime']})")
                save_everywhere(f"candele_{clean}_HOUR_4.json", h4_60, target_dirs)
        
        # 4. DAY
        d1_all = fetch_yf_candles(sym, "1d", "6mo")
        if d1_all:
            d1_60 = d1_all[-60:]
            print(f"  D1: {len(d1_60)} candele (da {d1_60[0]['snapshotTime']} a {d1_60[-1]['snapshotTime']})")
            save_everywhere(f"candele_{clean}_DAY.json", d1_60, target_dirs)

def save_everywhere(filename, data, target_dirs):
    for d in target_dirs:
        out_p = os.path.join(d, filename)
        try:
            tmp_p = f"{out_p}.tmp.{os.getpid()}"
            with open(tmp_p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_p, out_p)
        except Exception as e:
            print(f"    [!] Errore salvataggio {out_p}: {e}")

if __name__ == "__main__":
    run_seeder()
