import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test_h1_30pips():
    cfg = {
        "size_i": 3, 
        "size_max": 10, 
        "pip_value": 0.01, 
        "min_body": 5, 
        "auto_restart": True, 
        "tk_periods": 9, 
        "kj_periods": 55,
        "timeframe": "HOUR"
    }
    engine = CoreEngine(cfg)
    candles = [Candle(159.0, 159.47, 158.554, 158.8) for _ in range(51)] + [Candle(158.7, 159.0, 158.554, 158.7) for _ in range(9)]
    engine.seed_history(candles)
    engine.start(159.50, "SHORT")
    engine.pm.open_increment(158.70, 1, "SHORT")
    engine.current_tk = 158.777
    engine.current_kj = 159.012
    
    # 1. Candela chiude a 158.75:
    # Distanza KJ: 159.012 - 158.75 = 26.2 pip (< 30 pip) -> Trailing Core NON attivo
    c1 = Candle(158.70, 158.80, 158.70, 158.75)
    engine.on_candle_close(c1)
    assert engine.trailing_sl_core is None
    
    # 2. Candela chiude a 158.70:
    # Distanza KJ: 159.012 - 158.70 = 31.2 pip (>= 30 pip) -> Trailing Core si attiva a 158.70 + 0.30 = 159.00
    c2 = Candle(158.75, 158.78, 158.68, 158.70)
    engine.on_candle_close(c2)
    assert engine.trailing_sl_core is not None
    assert abs(engine.trailing_sl_core - 159.00) < 1e-4
    print("H1 (HOUR) Test OK: Trailing SL Core scatta a 30 pip (159.00)")

def test_m5_20pips():
    cfg = {
        "size_i": 3, 
        "size_max": 10, 
        "pip_value": 0.01, 
        "min_body": 5, 
        "auto_restart": True, 
        "tk_periods": 9, 
        "kj_periods": 55,
        "timeframe": "MINUTE_5"
    }
    engine = CoreEngine(cfg)
    candles = [Candle(159.0, 159.47, 158.554, 158.8) for _ in range(51)] + [Candle(158.7, 159.0, 158.554, 158.7) for _ in range(9)]
    engine.seed_history(candles)
    engine.start(159.50, "SHORT")
    engine.current_tk = 158.777
    engine.current_kj = 159.012
    
    # Candela chiude a 158.80:
    # Distanza KJ: 159.012 - 158.80 = 21.2 pip (>= 20 pip) -> Trailing Core si attiva a 158.80 + 0.20 = 159.00
    c1 = Candle(158.85, 158.85, 158.78, 158.80)
    engine.on_candle_close(c1)
    assert engine.trailing_sl_core is not None
    assert abs(engine.trailing_sl_core - 159.00) < 1e-4
    print("M5 (MINUTE_5) Test OK: Trailing SL Core scatta a 20 pip (159.00)")

def test_h4_40pips():
    cfg = {
        "size_i": 3, 
        "size_max": 10, 
        "pip_value": 0.01, 
        "min_body": 5, 
        "auto_restart": True, 
        "tk_periods": 9, 
        "kj_periods": 55,
        "timeframe": "HOUR_4"
    }
    engine = CoreEngine(cfg)
    candles = [Candle(159.0, 159.47, 158.554, 158.8) for _ in range(51)] + [Candle(158.7, 159.0, 158.554, 158.7) for _ in range(9)]
    engine.seed_history(candles)
    engine.start(159.50, "SHORT")
    engine.current_tk = 158.777
    engine.current_kj = 159.012
    
    # 1. Candela chiude a 158.70:
    # Distanza KJ: 159.012 - 158.70 = 31.2 pip (< 40 pip) -> Trailing Core NON attivo
    c1 = Candle(158.75, 158.78, 158.68, 158.70)
    engine.on_candle_close(c1)
    assert engine.trailing_sl_core is None
    
    # 2. Candela chiude a 158.60:
    # Distanza KJ: 159.012 - 158.60 = 41.2 pip (>= 40 pip) -> Trailing Core si attiva a 158.60 + 0.40 = 159.00
    c2 = Candle(158.70, 158.70, 158.58, 158.60)
    engine.on_candle_close(c2)
    assert engine.trailing_sl_core is not None
    assert abs(engine.trailing_sl_core - 159.00) < 1e-4
    print("H4 (HOUR_4) Test OK: Trailing SL Core scatta a 40 pip (159.00)")

if __name__ == "__main__":
    test_h1_30pips()
    test_m5_20pips()
    test_h4_40pips()
    print("TUTTI I TEST MULTI-TIMEFRAME SUPERATI AL 100%!")
