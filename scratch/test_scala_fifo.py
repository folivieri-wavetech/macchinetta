import sys, os
sys.path.insert(0, os.path.abspath("."))
from macchinetta_trend.core_engine import CoreEngine, Candle

def test_scala_fifo():
    cfg = {
        "size_i": 4,
        "size_max": 10,
        "scala": 2, # Ogni incremento è di 2 lotti
        "timeframe": "MINUTE_5",
        "tk_periods": 21,
        "kj_periods": 55,
        "min_body": 5,
        "pip_value": 0.01,
        "max_kj_distance": 50.0,
        "max_entry_delay": 5,
        "auto_restart": False
    }
    engine = CoreEngine(cfg)
    
    # 55 candele iniziali
    history = [Candle(159.0, 159.10, 158.90, 159.0) for _ in range(55)]
    engine.seed_history(history)
    
    # Start SHORT
    engine.start(159.0, "SHORT")
    assert engine.pm.core_position.size == 4
    print("Core aperta: size 4. Totale attivo = 4.")
    
    # 1° Incremento a 158.90
    c1 = Candle(158.85, 158.95, 158.85, 158.90)
    engine.on_candle_close(c1, 158.90)
    assert len(engine.pm.increments) == 1
    assert engine.pm.increments[0].size == 2
    assert engine.pm.total_active_size() == 6
    print("1° Incremento aperto: size 2. Totale attivo = 6.")
    
    # 2° Incremento a 158.78 (distanza 12 pip >= 10 pip rispetto a 158.90, gain 1° inc = 12 pip < 20 pip TP)
    engine.seed_history([Candle(158.85, 158.95, 158.75, 158.85) for _ in range(55)])
    c2 = Candle(158.75, 158.85, 158.75, 158.78)
    engine.on_candle_close(c2, 158.78)
    assert len(engine.pm.increments) == 2
    assert engine.pm.increments[1].size == 2
    assert engine.pm.total_active_size() == 8
    print("2° Incremento aperto: size 2. Totale attivo = 8.")
    
    # Test FIFO simulando aggiunta manuale del 3° incremento a 158.68 per raggiungere size_max (10)
    engine.pm.open_increment(158.68, 2, "SHORT")
    assert engine.pm.total_active_size() == 10
    assert len(engine.pm.increments) == 3
    print("3° Incremento: size_max raggiunta a 10.")
    
    # Ora con capienza piena (10), l'ingresso del 4° incremento a 158.55 deve chiudere in FIFO il 1° incremento
    engine.seed_history([Candle(158.65, 158.75, 158.55, 158.65) for _ in range(55)])
    c4 = Candle(158.55, 158.65, 158.55, 158.55)
    evs4 = engine.on_candle_close(c4, 158.55)
    assert any(e.get("type") in ("fifo_close", "tp_increment") for e in evs4)
    assert engine.pm.total_active_size() <= 10
    print("4° Incremento: capienza gestita con successo (FIFO / TP)!")

if __name__ == "__main__":
    test_scala_fifo()
