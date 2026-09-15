import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test_user_scenario_long():
    """
    Scenario dell'utente:
    - Incrementi aperti a 5015, 5030, 5055.
    - TK a 5040, KJ a 4980.
    - Durante i tick live, il prezzo tocca 5090: NESSUN TP scatta in live tick.
    - A chiusura candela a 5090 (TK 5040 + 50 pip = 5090):
      Tutti e 3 gli incrementi vengono chiusi con evento 'tp_increment' e PnL corretto!
    - La Core position resta aperta.
    """
    cfg = {
        "size_i": 1,
        "size_max": 10,
        "pip_value": 1.0,  # Es. Indici/Punti o pip=1
        "min_body": 1,
        "timeframe": "HOUR",
        "auto_restart": False,
        "tk_periods": 9,
        "kj_periods": 26
    }
    engine = CoreEngine(cfg)
    # Popola storico per avere TK e KJ stabili
    candles = [Candle(5000, 5060, 4980, 5020) for _ in range(50)]
    engine.seed_history(candles)
    engine.start(5000, "LONG")
    
    # Apri i 3 incrementi
    engine.pm.open_increment(5015, 1, "LONG")
    engine.pm.open_increment(5030, 1, "LONG")
    engine.pm.open_increment(5055, 1, "LONG")
    assert len(engine.pm.increments) == 3, "Devono esserci 3 incrementi"
    
    # 1. Verifica che durante i tick live a 5090 non scatti nulla
    engine.current_tk = 5040
    engine.current_kj = 4980
    evs_live = engine.check_live_stops(5090)
    assert not any(e.get("type") == "tp_increment" for e in evs_live), "Non deve scattare TP su tick live!"
    assert len(engine.pm.increments) == 3, "Gli incrementi devono restare aperti durante i tick live"
    print("[OK] Test 1 OK: Su tick live a 5090 nessun TP scatta prematuramente.")
    
    # 2. Chiusura candela a 5080 (< TK 5040 + 50 = 5090): nessun TP a fine candela
    c_sub = Candle(5060, 5085, 5050, 5080)
    evs_c1 = engine.on_candle_close(c_sub)
    assert not any(e.get("type") == "tp_increment" for e in evs_c1), "A 5080 non deve scattare TP"
    assert len(engine.pm.increments) == 3
    print("[OK] Test 2 OK: Candela chiusa a 5080 (< TK+50), incrementi rimangono aperti.")
    
    # 3. Chiusura candela a 5090: c_close >= TK + 50 -> Chiusura in blocco di tutti e 3!
    # Creiamo candela tale che il nuovo TK calcolato sia 5040
    # Impostiamo artificialmente Donchian per il test
    engine._calculate_donchian = lambda p: 5040 if p == 9 else 4980
    c_tp = Candle(5070, 5095, 5065, 5090)
    evs_c2 = engine.on_candle_close(c_tp)
    
    tp_events = [e for e in evs_c2 if e.get("type") == "tp_increment"]
    assert len(tp_events) == 3, f"Attesi 3 eventi tp_increment, ricevuti: {len(tp_events)}"
    assert len(engine.pm.increments) == 0, "Tutti gli incrementi devono essere stati chiusi!"
    assert engine.pm.core_position is not None, "La Core deve rimanere aperta!"
    
    # Verifica pips registrati per ciascun incremento
    pips_gained = [e["tp_pips"] for e in tp_events]
    assert 75 in pips_gained, f"Manca incremento da +75p: {pips_gained}"
    assert 60 in pips_gained, f"Manca incremento da +60p: {pips_gained}"
    assert 35 in pips_gained, f"Manca incremento da +35p: {pips_gained}"
    print(f"[OK] Test 3 OK: Chiusi tutti e 3 gli incrementi a 5090 con pips: {pips_gained} e Core intatta.")

def test_scenario_short():
    """
    Scenario SHORT:
    - Prezzo e TK scendono. TK = 5040.
    - 2 incrementi aperti: a 5035 e 5020.
    - A chiusura candela a 4990 (TK 5040 - 50 pip = 4990):
      Tutti gli incrementi in profitto vengono chiusi!
    """
    cfg = {
        "size_i": 1,
        "size_max": 10,
        "pip_value": 1.0,
        "min_body": 1,
        "timeframe": "HOUR_4",
        "auto_restart": False,
        "tk_periods": 9,
        "kj_periods": 26
    }
    engine = CoreEngine(cfg)
    candles = [Candle(5100, 5120, 5000, 5050) for _ in range(50)]
    engine.seed_history(candles)
    engine.start(5080, "SHORT")
    
    engine.pm.open_increment(5035, 1, "SHORT")
    engine.pm.open_increment(5020, 1, "SHORT")
    assert len(engine.pm.increments) == 2
    
    engine._calculate_donchian = lambda p: 5040 if p == 9 else 5100
    
    # Candela chiude a 4990 (<= TK 5040 - 50 = 4990)
    c_short_tp = Candle(5010, 5015, 4985, 4990)
    evs = engine.on_candle_close(c_short_tp)
    
    tp_events = [e for e in evs if e.get("type") == "tp_increment"]
    assert len(tp_events) == 2, f"Attesi 2 eventi tp_increment SHORT, ricevuti: {len(tp_events)}"
    assert len(engine.pm.increments) == 0
    assert engine.pm.core_position is not None
    
    pips_gained = [e["tp_pips"] for e in tp_events]
    assert 45 in pips_gained, f"Manca incremento da +45p: {pips_gained}"
    assert 30 in pips_gained, f"Manca incremento da +30p: {pips_gained}"
    print(f"[OK] Test SHORT OK: Chiusi 2 incrementi con pips: {pips_gained}.")

if __name__ == "__main__":
    test_user_scenario_long()
    test_scenario_short()
    print("\n=== TUTTI I TEST TP SU TENKAN (TK +- 50 pip) SUPERATI CON SUCCESSO! ===")
