import sys, os
sys.path.insert(0, os.path.abspath("."))
from macchinetta_trend.core_engine import CoreEngine, Candle

def test_distanza_incrementi():
    # TEST 1: MINUTE_5 (almeno 10 pip)
    cfg_m5 = {
        "size_i": 2,
        "size_max": 10,
        "scala": 1,
        "timeframe": "MINUTE_5",
        "tk_periods": 21,
        "kj_periods": 55,
        "min_body": 5,
        "pip_value": 0.01,
        "max_kj_distance": 50.0,
        "max_entry_delay": 5,
        "auto_restart": False
    }
    engine_m5 = CoreEngine(cfg_m5)
    
    # 55 candele di base per Ichimoku SHORT (High=159.20, Low=159.00 -> TK=159.10, KJ=159.10)
    history = [Candle(159.10, 159.20, 159.00, 159.10) for _ in range(55)]
    engine_m5.seed_history(history)
    
    # Avvio SHORT
    engine_m5.start(159.10, "SHORT")
    assert engine_m5.is_running
    
    # 1° Incremento a 159.00 (candela verde di ritracciamento su SHORT: open=158.90, high=159.10, close=159.00)
    # distanza_percorsa = 159.10 - 158.90 = 0.20 >= min_body (0.05)
    c1 = Candle(158.90, 159.10, 158.90, 159.00)
    evs1 = engine_m5.on_candle_close(c1, 159.00)
    assert len(engine_m5.pm.increments) == 1
    assert engine_m5.pm.increments[0].entry_price == 159.00
    print("M5 - 1° Incremento aperto a 159.00: OK")
    
    # Tentativo 2° Incremento a 159.05 (distanza 5 pip < 10 pip rispetto a 159.00)
    c2 = Candle(158.95, 159.10, 158.95, 159.05)
    evs2 = engine_m5.on_candle_close(c2, 159.05)
    assert len(engine_m5.pm.increments) == 1, "Non doveva aprire perché distanza = 5 pip (< 10 pip)"
    print("M5 - 2° Incremento a 159.05 (5 pip) correttamente RIFIUTATO: OK")
    
    # Tentativo 2° Incremento a 158.88 (distanza 12 pip >= 10 pip rispetto a 159.00)
    # Aggiorniamo la history per spostare la TK verso il basso a 158.95
    history_lower = [Candle(158.95, 159.05, 158.85, 158.95) for _ in range(55)]
    engine_m5.seed_history(history_lower)
    c3 = Candle(158.80, 158.95, 158.80, 158.88)
    evs3 = engine_m5.on_candle_close(c3, 158.88)
    assert len(engine_m5.pm.increments) == 2, "Doveva aprire perché distanza = 12 pip (>= 10 pip)"
    print("M5 - 2° Incremento a 158.88 (12 pip) correttamente APERTO: OK")
    
    # TEST 2: HOUR (almeno 20 pip)
    cfg_h1 = {
        "size_i": 2,
        "size_max": 10,
        "scala": 1,
        "timeframe": "HOUR",
        "tk_periods": 21,
        "kj_periods": 55,
        "min_body": 5,
        "pip_value": 0.01,
        "max_kj_distance": 50.0,
        "max_entry_delay": 5,
        "auto_restart": False
    }
    engine_h1 = CoreEngine(cfg_h1)
    engine_h1.seed_history(history)
    engine_h1.start(159.10, "SHORT")
    
    # 1° Incremento a 159.00
    engine_h1.on_candle_close(c1, 159.00)
    assert len(engine_h1.pm.increments) == 1
    print("H1 - 1° Incremento aperto a 159.00: OK")
    
    # Tentativo 2° Incremento a 158.85 (distanza 15 pip < 20 pip rispetto a 159.00)
    engine_h1.seed_history(history_lower)
    c4 = Candle(158.75, 158.95, 158.75, 158.85)
    engine_h1.on_candle_close(c4, 158.85)
    assert len(engine_h1.pm.increments) == 1, "In H1 non doveva aprire con 15 pip (< 20 pip)"
    print("H1 - 2° Incremento a 158.85 (15 pip) correttamente RIFIUTATO: OK")
    
    # Tentativo 2° Incremento a 158.75 (distanza 25 pip >= 20 pip rispetto a 159.00)
    history_lowest = [Candle(158.80, 158.90, 158.70, 158.80) for _ in range(55)]
    engine_h1.seed_history(history_lowest)
    c5 = Candle(158.65, 158.80, 158.65, 158.75)
    engine_h1.on_candle_close(c5, 158.75)
    assert len(engine_h1.pm.increments) == 2, "In H1 doveva aprire con 25 pip (>= 20 pip)"
    print("H1 - 2° Incremento a 158.75 (25 pip) correttamente APERTO: OK")
    
    print("TUTTI I TEST DI DISTANZA INCREMENTI SUPERATI AL 100%!")

if __name__ == "__main__":
    test_distanza_incrementi()
