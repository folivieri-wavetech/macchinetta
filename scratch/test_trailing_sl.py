import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test_scenario_1():
    cfg = {
        "size_i": 3, 
        "size_max": 10, 
        "pip_value": 0.01, 
        "min_body": 5, 
        "auto_restart": True, 
        "tk_periods": 9, 
        "kj_periods": 55
    }
    engine = CoreEngine(cfg)
    
    # Candele con High 159.0 e Low 158.554 per Donchian TK = 158.777
    candles = [Candle(158.8, 159.0, 158.554, 158.7) for _ in range(60)]
    engine.seed_history(candles)
    
    # Avvio SHORT
    engine.start(159.50, "SHORT")
    assert engine.is_running
    
    # Apri incremento
    engine.pm.open_increment(158.70, 1, "SHORT")
    
    engine.current_tk = 158.777
    engine.current_kj = 159.012
    
    # 1. Candela chiude a 158.48 -> Distanza da TK = 158.777 - 158.48 = 0.297 (29.7 pip < 40 pip)
    # Trailing SL NON deve attivarsi!
    c_sub40 = Candle(158.60, 158.65, 158.45, 158.48)
    engine.on_candle_close(c_sub40)
    assert engine.trailing_sl_incr is None, "A distanza < 40 pip il trailing non deve attivarsi!"
    print("Passo 1 OK: a 30 pip il trailing non e' attivo.")
    
    # 2. Candela chiude a 157.56 -> Distanza = 158.777 - 157.56 = 1.217 (121.7 pip >= 40 pip)
    # Trailing SL si attiva a 157.56 + 20 pip (0.20) = 157.76
    c_ext = Candle(157.80, 157.90, 157.50, 157.56)
    engine.on_candle_close(c_ext)
    assert engine.trailing_sl_incr is not None
    assert abs(engine.trailing_sl_incr - 157.76) < 1e-4
    print("Passo 2 OK: a dist >= 40 pip il trailing e' attivo a Close + 20 pip (157.76).")
    
    # 3. Candela scende a 157.20 -> Trailing scende a 157.20 + 0.20 = 157.40
    c_down = Candle(157.56, 157.60, 157.10, 157.20)
    engine.on_candle_close(c_down)
    assert abs(engine.trailing_sl_incr - 157.40) < 1e-4
    print("Passo 3 OK: trailing scende con nuovi minimi a 157.40.")
    
    # 4. Rimbalzo a 157.35 (distanza da TK resta > 40 pip, ma ritraccia di 15 pip)
    # Il cricchetto tiene lo stop fisso a 157.40
    c_bounce = Candle(157.20, 157.38, 157.15, 157.35)
    engine.on_candle_close(c_bounce)
    assert abs(engine.trailing_sl_incr - 157.40) < 1e-4
    print("Passo 4 OK: cricchetto non si allarga sul rimbalzo.")
    
    # 5. Prezzo tocca 157.40 in live: chiusura incrementi
    evs = engine.check_live_stops(157.40)
    assert any(e.get("type") == "increments_cleared" and e.get("reason") == "live_stop_trailing" for e in evs)
    assert len(engine.pm.increments) == 0
    assert engine.pm.core_position is not None
    assert engine.trailing_sl_incr is None
    print("Passo 5 OK: chiusi tutti gli incrementi su Trailing SL, Core intatta.")

if __name__ == "__main__":
    test_scenario_1()
    print("TUTTI I TEST DELLO SCENARIO 1 SUPERATI!")
