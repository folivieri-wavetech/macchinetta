import sys
import os
import datetime

sys.argv = ["Motore_Trend.py", "FIORDOK_DEMO"]

from Motore_Trend import TZ_ITALIA, is_session_break_active, allinea_candele_live, LIVE_OHLC_TRACKER, aggiorna_candele_live_globale
from Dashboard import is_session_break_active_dash, allinea_candele_live_dash

def run_tests():
    print("=== TEST 1: is_session_break_active logic ===")
    # Lunedi 23:30 (weekday 0)
    dt_mon_23 = datetime.datetime(2026, 9, 7, 23, 30, tzinfo=TZ_ITALIA)
    assert is_session_break_active("Spot Gold", dt_mon_23) == True, "Lunedi 23:30 deve essere session break per Gold"
    assert is_session_break_active("Oil - US Crude", dt_mon_23) == True, "Lunedi 23:30 deve essere session break per Oil"
    assert is_session_break_active("EUR/USD", dt_mon_23) == False, "Forex non deve avere session break alle 23"
    assert is_session_break_active("US 500 Cash", dt_mon_23) == False, "US 500 non ha pausa alle 23"

    # Giovedi 23:45 (weekday 3)
    dt_thu_23 = datetime.datetime(2026, 9, 10, 23, 45, tzinfo=TZ_ITALIA)
    assert is_session_break_active("Spot Gold", dt_thu_23) == True, "Giovedi 23:45 deve essere session break"
    
    # Venerdi 23:15 (weekday 4 - gestito dal weekend!)
    dt_fri_23 = datetime.datetime(2026, 9, 11, 23, 15, tzinfo=TZ_ITALIA)
    assert is_session_break_active("Spot Gold", dt_fri_23) == False, "Venerdi 23 e gestito da is_weekend_active, non session break"

    # Martedi 00:05 (weekday 1 - mercato riaperto)
    dt_tue_00 = datetime.datetime(2026, 9, 8, 0, 5, tzinfo=TZ_ITALIA)
    assert is_session_break_active("Spot Gold", dt_tue_00) == False, "Martedi 00:05 mercato aperto"

    # Martedi 22:55 (weekday 1 - prima della pausa)
    dt_tue_22 = datetime.datetime(2026, 9, 8, 22, 55, tzinfo=TZ_ITALIA)
    assert is_session_break_active("Spot Gold", dt_tue_22) == False, "Martedi 22:55 mercato aperto"

    print("TEST 1 superato!")

    print("=== TEST 2: Dashboard is_session_break_active_dash ===")
    assert is_session_break_active_dash("Spot Gold", dt_mon_23) == True
    assert is_session_break_active_dash("EUR/USD", dt_mon_23) == False
    print("TEST 2 superato!")

    print("=== TEST 3: allinea_candele_live durante session break ===")
    # Campione con ultima candela alle 22:00 di lunedì 7 settembre
    candele_sample = [
        {"snapshotTime": "2026/09/07 22:00:00", "openPrice": {"bid": 2500}, "highPrice": {"bid": 2505}, "lowPrice": {"bid": 2495}, "closePrice": {"bid": 2502}}
    ]
    # Se invocato durante le 23:30 di lunedì (simuliamo con dt_mon_23 patchando now_it)
    import Motore_Trend
    orig_now = Motore_Trend.now_it
    Motore_Trend.now_it = lambda: dt_mon_23
    try:
        res = allinea_candele_live(candele_sample, "Spot Gold", "HOUR", 2504.0)
        assert len(res) == 1, f"Non deve aggiungere candela ombra durante pausa 23:00! Ricevuto {len(res)}"
        assert res[0]["snapshotTime"] == "2026/09/07 22:00:00"
        print("allinea_candele_live non aggiunge candela sintetica a 23:00!")
    finally:
        Motore_Trend.now_it = orig_now

    # Simula riapertura a 00:05 di martedì 8 settembre: deve proiettare la candela di 00:00, NON di 23:00!
    Motore_Trend.now_it = lambda: dt_tue_00
    try:
        res_00 = allinea_candele_live(candele_sample, "Spot Gold", "HOUR", 2510.0)
        assert len(res_00) == 2, f"A 00:05 deve proiettare la candela corrente delle 00:00! Len: {len(res_00)}"
        assert res_00[-1]["snapshotTime"] == "2026/09/08 00:00:00", f"La candela sintetica deve essere 00:00:00 ma e {res_00[-1]['snapshotTime']}"
        print(f"allinea_candele_live a 00:05 proietta correttamente: {res_00[-1]['snapshotTime']}")
    finally:
        Motore_Trend.now_it = orig_now

    print("=== TUTTI I TEST SUPERATI CON SUCCESSO! ===")

if __name__ == "__main__":
    run_tests()
