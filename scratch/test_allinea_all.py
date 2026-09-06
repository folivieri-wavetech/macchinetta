import os
import glob
import json
import zoneinfo
from datetime import datetime, timedelta

TZ_ITALIA = zoneinfo.ZoneInfo("Europe/Rome")
TF_MAP = {
    "MINUTE_5": 5,
    "MINUTE_15": 15,
    "HOUR": 60,
    "HOUR_4": 240,
    "DAY": 1440
}

def is_weekend_active(dt=None):
    if dt is None:
        dt = datetime.now(TZ_ITALIA)
    # Venerdì dopo le 23:15
    if dt.weekday() == 4 and (dt.hour > 23 or (dt.hour == 23 and dt.minute >= 15)):
        return True
    # Tutto Sabato
    if dt.weekday() == 5:
        return True
    # Domenica fino alle 23:00
    if dt.weekday() == 6 and dt.hour < 23:
        return True
    return False

def allinea_candele_live(candele_locali, nome, tf, px_live):
    if not candele_locali or not px_live or not isinstance(px_live, (int, float)):
        return candele_locali
    if is_weekend_active():
        return candele_locali
        
    now_t = datetime.now(TZ_ITALIA)
    min_tf = TF_MAP.get(tf, 5)
    offset = 60 if min_tf in (60, 240, 1440) else 0
    min_tot = now_t.hour * 60 + now_t.minute
    boundary_min = ((min_tot - offset) // min_tf) * min_tf + offset
    b_h = (boundary_min // 60) % 24
    b_m = boundary_min % 60
    target_dt = now_t.replace(hour=b_h, minute=b_m, second=0, microsecond=0)
    
    try:
        last_t_str = candele_locali[-1].get("snapshotTime")
        last_dt = datetime.strptime(last_t_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ_ITALIA)
    except Exception:
        return candele_locali

    if last_dt >= target_dt:
        return candele_locali
        
    curr_dt = last_dt + timedelta(minutes=min_tf)
    added = 0
    while curr_dt <= target_dt and added < 100:
        if is_weekend_active(curr_dt):
            curr_dt += timedelta(minutes=min_tf)
            continue
            
        snap_synth = curr_dt.strftime("%Y/%m/%d %H:%M:00")
        last_c = candele_locali[-1]
        try:
            prev_close = (last_c['closePrice']['bid'] + last_c['closePrice']['ask']) / 2
        except Exception:
            prev_close = px_live
            
        synth_candle = {
            "snapshotTime": snap_synth,
            "openPrice": {"bid": prev_close, "ask": prev_close, "lastTraded": None},
            "highPrice": {"bid": max(prev_close, px_live), "ask": max(prev_close, px_live), "lastTraded": None},
            "lowPrice": {"bid": min(prev_close, px_live), "ask": min(prev_close, px_live), "lastTraded": None},
            "closePrice": {"bid": px_live, "ask": px_live, "lastTraded": None}
        }
        candele_locali.append(synth_candle)
        added += 1
        curr_dt += timedelta(minutes=min_tf)
        
    return candele_locali[-100:]

def calcola_kj55(candele):
    if not candele or len(candele) < 55:
        return None
    sub = candele[-55:]
    highs, lows = [], []
    for c in sub:
        h = c.get("highPrice", {})
        hv = h.get("mid") or h.get("bid") or h.get("ask") if isinstance(h, dict) else h
        l = c.get("lowPrice", {})
        lv = l.get("mid") or l.get("bid") or l.get("ask") if isinstance(l, dict) else l
        if hv is not None and lv is not None:
            highs.append(float(hv))
            lows.append(float(lv))
    if len(highs) < 55: return None
    return (max(highs) + min(lows)) / 2.0, max(highs), min(lows)

def main():
    # Test su FIORDOK_DEMO Spot Gold
    for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
        base_dir = f"/data/{acc}" if os.path.exists("/data") else acc
        print(f"\n==================== TEST ALLINEAMENTO SU {acc} ====================")
        for tf in ["MINUTE_5", "HOUR", "HOUR_4", "DAY"]:
            fpath = f"{base_dir}/candele_Spot_Gold_{tf}.json"
            if os.path.exists(fpath):
                with open(fpath) as f:
                    candele = json.load(f)
                
                # Prezzo live simulato o reale (es 4430.5 per Gold)
                px_live = 4430.5
                prima_res = calcola_kj55(candele)
                print(f"\nTimeframe {tf} (PRIMA): {len(candele)} candele, Ultima: {candele[-1]['snapshotTime']}")
                if prima_res:
                    kj, mh, ml = prima_res
                    print(f"  KJ PRIMA: {kj:.2f} (Max={mh:.2f}, Min={ml:.2f})")
                
                allineate = allinea_candele_live(candele, "Spot Gold", tf, px_live)
                dopo_res = calcola_kj55(allineate)
                print(f"Timeframe {tf} (DOPO ALLINEAMENTO): {len(allineate)} candele, Ultima: {allineate[-1]['snapshotTime']}")
                if dopo_res:
                    kj, mh, ml = dopo_res
                    print(f"  KJ DOPO: {kj:.2f} (Max={mh:.2f}, Min={ml:.2f})")

if __name__ == '__main__':
    main()
