import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test_tk20_kj40():
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
    
    # 60 candele per la Donchian (High 159.47, Low 158.554 -> KJ = 159.012, TK = 158.777 sulle ultime 9)
    candles = [Candle(159.0, 159.47, 158.554, 158.8) for _ in range(51)] + [Candle(158.7, 159.0, 158.554, 158.7) for _ in range(9)]
    engine.seed_history(candles)
    
    # Avvio SHORT a 159.50
    engine.start(159.50, "SHORT")
    assert engine.is_running
    
    # Apri 1 incremento
    engine.pm.open_increment(158.70, 1, "SHORT")
    
    # Forziamo TK = 158.777, KJ = 159.012 per il test
    engine.current_tk = 158.777
    engine.current_kj = 159.012
    
    # 1. Candela chiude a 158.65:
    # Distanza TK: 158.777 - 158.65 = 12.7 pip (< 20 pip) -> Trailing Incr NON attivo
    # Distanza KJ: 159.012 - 158.65 = 36.2 pip (< 40 pip) -> Trailing Core NON attivo
    c1 = Candle(158.70, 158.75, 158.60, 158.65)
    engine.on_candle_close(c1)
    assert engine.trailing_sl_incr is None
    assert engine.trailing_sl_core is None
    print("Passo 1 OK: Distanze < 20 TK e < 40 KJ -> Nessun trailing attivo.")
    
    # 2. Candela chiude a 158.50:
    # Distanza TK: 158.777 - 158.50 = 27.7 pip (>= 20 pip) -> Trailing Incr si attiva a 158.50 + 0.20 = 158.70
    # Distanza KJ: 159.012 - 158.50 = 51.2 pip (>= 40 pip) -> Trailing Core si attiva a 158.50 + 0.40 = 158.90
    c2 = Candle(158.65, 158.68, 158.48, 158.50)
    engine.on_candle_close(c2)
    assert engine.trailing_sl_incr is not None
    assert abs(engine.trailing_sl_incr - 158.70) < 1e-4
    assert engine.trailing_sl_core is not None
    assert abs(engine.trailing_sl_core - 158.90) < 1e-4
    print("Passo 2 OK: TK 20/20 attivo a 158.70 e KJ 40/40 attivo a 158.90.")
    
    # 3. Candela scende forte a 157.20:
    # Trailing Incr scende a 157.20 + 0.20 = 157.40
    # Trailing Core scende a 157.20 + 0.40 = 157.60
    c3 = Candle(158.50, 158.50, 157.15, 157.20)
    engine.on_candle_close(c3)
    assert abs(engine.trailing_sl_incr - 157.40) < 1e-4
    assert abs(engine.trailing_sl_core - 157.60) < 1e-4
    print("Passo 3 OK: Cricchetto scende a 157.40 (Incr) e 157.60 (Core).")
    
    # 4. Rimbalzo a 157.35:
    # Entrambi gli stop devono rimanere invariati (cricchetto)
    c4 = Candle(157.20, 157.38, 157.18, 157.35)
    engine.on_candle_close(c4)
    assert abs(engine.trailing_sl_incr - 157.40) < 1e-4
    assert abs(engine.trailing_sl_core - 157.60) < 1e-4
    print("Passo 4 OK: Nessun arretramento sul rimbalzo.")
    
    # 5. Prezzo tocca 157.40 in live:
    # Chiude SOLO gli incrementi! La Core deve rimanere aperta con il suo stop a 157.60!
    evs_inc = engine.check_live_stops(157.40)
    assert any(e.get("type") == "increments_cleared" for e in evs_inc)
    assert len(engine.pm.increments) == 0
    assert engine.pm.core_position is not None
    assert engine.trailing_sl_incr is None
    assert engine.trailing_sl_core is not None
    print("Passo 5 OK: Incrementi chiusi su Trailing SL (157.40), Core ancora viva!")
    
    # 6. Prezzo continua a rimbalzare e tocca 157.60 in live:
    # Chiude anche la Core e passa in FLAT!
    evs_core = engine.check_live_stops(157.60)
    assert any(e.get("type") == "reversal" for e in evs_core)
    assert engine.pm.core_position is None
    assert engine.current_direction == "FLAT"
    assert engine.trailing_sl_core is None
    print("Passo 6 OK: Core chiusa su Trailing SL Core (157.60), sistema passa in FLAT!")

if __name__ == "__main__":
    test_tk20_kj40()
    print("TEST TK 20/20 E KJ 40/40 SUPERATI AL 100%!")
