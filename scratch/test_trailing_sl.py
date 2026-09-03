import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test():
    cfg = {"size_i": 3, "size_max": 10, "pip_value": 0.01, "min_body": 5, "auto_restart": True, "tk_periods": 9, "kj_periods": 55}
    engine = CoreEngine(cfg)
    
    # Simula candele per calcolare TK/KJ
    candles = [Candle(160, 160.5, 159.5, 160) for _ in range(60)]
    engine.seed_history(candles)
    
    # Start SHORT a 159.50
    engine.start(159.50, "SHORT")
    assert engine.is_running
    assert engine.pm.core_position is not None
    
    # Apri un incremento
    pos_inc = engine.pm.open_increment(158.50, 1, "SHORT")
    assert len(engine.pm.increments) == 1
    
    # Imposta TK e KJ
    engine.current_tk = 158.777
    engine.current_kj = 159.012
    
    # Candela chiude a 157.56 (distanza da TK = 158.777 - 157.56 = 1.217 = 121.7 pip >= 20 pip)
    # pip_val per JPY e' 0.01 -> 20 * 0.01 = 0.20
    c1 = Candle(157.80, 157.90, 157.50, 157.56)
    events = engine.on_candle_close(c1)
    
    print(f"Trailing SL calcolato: {engine.trailing_sl_incr}")
    expected_sl = 157.56 + 0.20
    assert abs(engine.trailing_sl_incr - expected_sl) < 1e-4, f"Expected {expected_sl}, got {engine.trailing_sl_incr}"
    
    # Candela successiva scende a 157.20 -> Trailing scende a 157.20 + 0.20 = 157.40
    c2 = Candle(157.56, 157.60, 157.10, 157.20)
    events = engine.on_candle_close(c2)
    print(f"Trailing SL aggiornato: {engine.trailing_sl_incr}")
    expected_sl_2 = 157.20 + 0.20
    assert abs(engine.trailing_sl_incr - expected_sl_2) < 1e-4
    
    # Candela successiva rimbalza a 157.35 -> Trailing NON deve salire (resta a 157.40)
    c3 = Candle(157.20, 157.38, 157.15, 157.35)
    events = engine.on_candle_close(c3)
    print(f"Trailing SL dopo rimbalzo (cricchetto): {engine.trailing_sl_incr}")
    assert abs(engine.trailing_sl_incr - expected_sl_2) < 1e-4
    
    # Test check_live_stops: prezzo tocca 157.40
    events_live = engine.check_live_stops(157.40)
    print(f"Events live a 157.40: {events_live}")
    assert any(e.get("type") == "increments_cleared" and e.get("reason") == "live_stop_trailing" for e in events_live)
    assert len(engine.pm.increments) == 0, "Gli incrementi devono essere chiusi!"
    assert engine.pm.core_position is not None, "La Core deve rimanere aperta!"
    assert engine.trailing_sl_incr is None, "Trailing SL deve resettarsi a None!"
    
    print("✅ TEST SUPERATO CON SUCCESSO!")

if __name__ == "__main__":
    test()
