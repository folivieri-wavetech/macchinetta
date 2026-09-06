import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test_tp_m5_long():
    cfg = {
        "size_i": 3,
        "size_max": 10,
        "pip_value": 0.01,
        "min_body": 5,
        "timeframe": "MINUTE_5",
        "auto_restart": False,
        "tk_periods": 9,
        "kj_periods": 26
    }
    engine = CoreEngine(cfg)
    candles = [Candle(159.0, 159.40, 158.50, 158.8) for _ in range(50)]
    engine.seed_history(candles)
    engine.start(159.00, "LONG")
    engine.current_tk = 159.10
    engine.current_kj = 158.80
    
    # Apri incremento a 159.20
    engine.pm.open_increment(159.20, 1, "LONG")
    assert len(engine.pm.increments) == 1
    
    # 1. Prezzo sale a 159.35 (+15 pip): Non ha ancora toccato +20 pip
    evs = engine.check_live_stops(159.35)
    assert not any(e.get("type") == "tp_increment" for e in evs)
    assert len(engine.pm.increments) == 1
    print("M5 Test 1 OK: +15 pip non scatta TP.")
    
    # 2. Prezzo sale a 159.40 (+20 pip): SCATTA TP LIVE!
    evs_tp = engine.check_live_stops(159.40)
    assert any(e.get("type") == "tp_increment" for e in evs_tp)
    assert len(engine.pm.increments) == 0 # Incremento chiuso!
    assert engine.pm.core_position is not None # Core ancora aperta!
    assert engine.is_running
    print("M5 Test 2 OK: +20 pip scatta TP live e chiude incremento mantenendo la Core!")

def test_tp_h1_short():
    cfg = {
        "size_i": 3,
        "size_max": 10,
        "pip_value": 0.01,
        "min_body": 5,
        "timeframe": "HOUR",
        "auto_restart": False,
        "tk_periods": 9,
        "kj_periods": 26
    }
    engine = CoreEngine(cfg)
    candles = [Candle(159.0, 159.40, 158.50, 158.8) for _ in range(50)]
    engine.seed_history(candles)
    engine.start(159.00, "SHORT")
    engine.current_tk = 158.90
    engine.current_kj = 159.20
    
    # Apri incremento a 158.80
    engine.pm.open_increment(158.80, 1, "SHORT")
    assert len(engine.pm.increments) == 1
    
    # 1. Prezzo scende a 158.55 (+25 pip gain in short): Non ha ancora toccato +30 pip
    evs = engine.check_live_stops(158.55)
    assert not any(e.get("type") == "tp_increment" for e in evs)
    assert len(engine.pm.increments) == 1
    print("H1 Test 1 OK: +25 pip non scatta TP.")
    
    # 2. Prezzo scende a 158.50 (+30 pip gain in short): SCATTA TP LIVE!
    evs_tp = engine.check_live_stops(158.50)
    assert any(e.get("type") == "tp_increment" for e in evs_tp)
    assert len(engine.pm.increments) == 0
    assert engine.pm.core_position is not None
    assert engine.is_running
    print("H1 Test 2 OK: +30 pip scatta TP live in SHORT e chiude incremento mantenendo la Core!")

if __name__ == "__main__":
    test_tp_m5_long()
    test_tp_h1_short()
    print("TUTTI I TEST TAKE PROFIT INCREMENTI SUPERATI CON SUCCESSO!")
