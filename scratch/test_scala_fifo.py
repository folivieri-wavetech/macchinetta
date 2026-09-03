import sys, os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle

def test_scala_fifo():
    cfg = {
        "size_i": 4, 
        "size_max": 10, 
        "scala": 2,
        "pip_value": 0.01, 
        "min_body": 5, 
        "auto_restart": True, 
        "tk_periods": 9, 
        "kj_periods": 55
    }
    engine = CoreEngine(cfg)
    
    # 60 candele per la Donchian (High 159.0, Low 158.0 -> TK = 158.5, KJ = 158.5)
    candles = [Candle(158.5, 159.0, 158.0, 158.5) for _ in range(60)]
    engine.seed_history(candles)
    
    # Avvio SHORT a 159.0 (Core = 4)
    engine.start(159.0, "SHORT")
    assert engine.pm.core_position.size == 4
    assert engine.pm.total_active_size() == 4
    print("Core aperta: size 4. Totale attivo = 4.")
    
    # Forziamo TK = 158.5, KJ = 159.0
    engine.current_tk = 158.5
    engine.current_kj = 159.0
    
    # Simula ritracciamento SHORT valido: candela verde che sale di 6 pip, apre sotto TK e chiude sotto TK entro 20 pip
    # 1° Incremento
    c1 = Candle(158.30, 158.40, 158.28, 158.38) # open 158.30, high 158.40 -> dist = 10 pip >= min_body (5 pip)
    evs1 = engine.on_candle_close(c1)
    assert len(engine.pm.increments) == 1
    assert engine.pm.increments[0].size == 2
    assert engine.pm.total_active_size() == 6
    print("1° Incremento aperto: size 2. Totale attivo = 6.")
    
    # 2° Incremento
    c2 = Candle(158.30, 158.40, 158.28, 158.38)
    evs2 = engine.on_candle_close(c2)
    assert len(engine.pm.increments) == 2
    assert engine.pm.increments[1].size == 2
    assert engine.pm.total_active_size() == 8
    print("2° Incremento aperto: size 2. Totale attivo = 8.")
    
    # 3° Incremento -> Raggiunge il max (4 + 6 = 10)
    c3 = Candle(158.30, 158.40, 158.28, 158.38)
    evs3 = engine.on_candle_close(c3)
    assert len(engine.pm.increments) == 3
    assert engine.pm.increments[2].size == 2
    assert engine.pm.total_active_size() == 10
    print("3° Incremento aperto: size 2. Totale attivo = 10 (Size Max raggiunta!).")
    
    # 4° Incremento -> Con totale = 10 e scala = 2, deve chiudere in FIFO il 1° incremento e aprire il 4°
    c4 = Candle(158.30, 158.40, 158.28, 158.38)
    evs4 = engine.on_candle_close(c4)
    assert any(e.get("type") == "fifo_close" for e in evs4)
    assert any(e.get("type") == "increment_opened" for e in evs4)
    assert engine.pm.total_active_size() == 10
    assert len(engine.pm.increments) == 3
    print("4° Incremento: riciclo FIFO eseguito con successo, totale sempre = 10!")

if __name__ == "__main__":
    test_scala_fifo()
    print("TEST SCALA E RICICLO FIFO SUPERATO AL 100%!")
