import sys
import os
sys.path.insert(0, os.path.abspath("."))

from macchinetta_trend.core_engine import CoreEngine, Candle

def create_candle(o, h, l, c):
    return Candle(o, h, l, c)

def test_all():
    print("=== TEST 1: Caso A (Spiombo live a KJ - 20 pip) ===")
    cfg_h1 = {
        "size_i": 3,
        "timeframe": "HOUR",
        "tk_periods": 21,
        "kj_periods": 55,
        "pip_value": 0.01, # JPY
        "max_kj_distance": 30.0,
        "auto_restart": True
    }
    engine = CoreEngine(cfg_h1)
    
    # 55 candele stabili attorno a 160.00 in modo che KJ sia 160.00
    candles = [create_candle(159.0, 161.0, 159.0, 160.0) for _ in range(60)]
    engine.seed_history(candles)
    # Calcola indicatori
    engine.on_candle_close(candles[-1])
    assert abs(engine.current_kj - 160.0) < 1e-4, f"KJ attesa 160.0, trovata {engine.current_kj}"
    
    # Avviamo la Core LONG a 160.15
    engine.start(160.15, direction="LONG")
    # Aggiungiamo anche un incremento per verificare che venga chiuso anch'esso
    engine.pm.open_increment(160.30, size=1, direction="LONG")
    assert engine.pm.core_position is not None
    assert len(engine.pm.increments) == 1
    
    # KJ = 160.00, pip_val = 0.01 -> Paracadute a KJ - 20 pip = 160.00 - 0.20 = 159.80
    # Prezzo scende a 159.85 (non tocca 159.80): la Core resta assolutamente aperta!
    ev1 = engine.check_live_stops(159.85)
    assert engine.pm.core_position is not None, "A 159.85 la Core deve rimanere aperta!"
    assert engine.current_direction == "LONG"
    print("OK: Prezzo a 159.85: la Core rimane aperta (non tocca KJ - 20 pip).")
    
    # Prezzo tocca 159.80 (o spiomba a 159.20):
    ev2 = engine.check_live_stops(159.20)
    assert any(e.get("type") == "reversal" and e.get("new_direction") == "FLAT" for e in ev2), f"Manca evento reversal a FLAT: {ev2}"
    assert engine.current_direction == "FLAT"
    assert engine.pm.core_position is None, "La Core doveva essere chiusa"
    assert len(engine.pm.increments) == 0, "Tutti gli incrementi dovevano essere chiusi"
    print(f"OK: Spiombo a 159.20 chiude Core e Incrementi e porta la macchina a FLAT. Eventi: {len(ev2)}")

    print("\n=== TEST 2: Caso B (Discesa a 159.85 e chiusura candela sopra KJ a 160.15) ===")
    engine = CoreEngine(cfg_h1)
    engine.seed_history(candles)
    engine.on_candle_close(candles[-1])
    engine.start(160.15, direction="LONG")
    engine.pm.open_increment(160.30, size=1, direction="LONG")
    
    # Live drops to 159.85
    ev_live = engine.check_live_stops(159.85)
    assert engine.pm.core_position is not None, "La Core deve rimanere aperta a 159.85"
    # Candela chiude alle 15:00 a 160.15 (sopra KJ 160.00)
    c_close_ok = create_candle(160.10, 160.30, 159.85, 160.15)
    ev_candle = engine.on_candle_close(c_close_ok)
    assert engine.current_direction == "LONG", "Doveva rimanere LONG"
    assert engine.pm.core_position is not None, "La Core deve rimanere aperta"
    print("OK: Caso B superato: la candela chiude sopra KJ, si rimane LONG come se nulla fosse successo.")

    print("\n=== TEST 3: Caso C (Discesa a 159.85 e chiusura candela sotto KJ a 159.90 -> Reversal SHORT) ===")
    engine = CoreEngine(cfg_h1)
    engine.seed_history(candles)
    engine.on_candle_close(candles[-1])
    engine.start(160.15, direction="LONG")
    engine.pm.open_increment(160.30, size=1, direction="LONG")
    
    # Live drops to 159.85 (non tocca 159.80)
    engine.check_live_stops(159.85)
    # Candela chiude alle 15:00 a 159.90 (sotto KJ 160.00) con candela rossa
    c_close_rev = create_candle(160.10, 160.15, 159.85, 159.90)
    ev_candle = engine.on_candle_close(c_close_rev)
    
    reversal_ev = next((e for e in ev_candle if e.get("type") == "reversal"), None)
    auto_start_ev = next((e for e in ev_candle if e.get("type") == "auto_start"), None)
    assert reversal_ev is not None, "Doveva esserci un evento di reversal"
    assert auto_start_ev is not None, "Con auto_restart=True doveva esserci un auto_start SHORT"
    assert auto_start_ev.get("direction") == "SHORT"
    assert engine.current_direction == "SHORT"
    print("OK: Caso C superato: chiusura sotto KJ con candela rossa chiude Core ed esegue Reverse a SHORT.")

    print("\n=== TEST 4: Trailing Stop Core (Solo M5 vs H1) ===")
    cfg_m5 = {"size_i": 3, "timeframe": "MINUTE_5", "tk_periods": 21, "kj_periods": 55, "pip_value": 0.01, "max_kj_distance": 30.0}
    eng_m5 = CoreEngine(cfg_m5)
    eng_m5.seed_history(candles)
    eng_m5.on_candle_close(candles[-1])
    eng_m5.start(160.15, "LONG")
    
    # Su M5: Prezzo sale di 25 pip sopra KJ (a 160.25)
    c_m5_gain = create_candle(160.15, 160.30, 160.15, 160.25)
    eng_m5.on_candle_close(c_m5_gain)
    assert eng_m5.trailing_sl_core is not None, "Su M5 il Trailing SL Core DOVEVA attivarsi!"
    print(f"OK: Su M5 Trailing SL Core attivo a {eng_m5.trailing_sl_core:.2f}")

    # Su H1: Prezzo sale di 100 pip sopra KJ (a 161.00)
    eng_h1 = CoreEngine(cfg_h1)
    eng_h1.seed_history(candles)
    eng_h1.on_candle_close(candles[-1])
    eng_h1.start(160.15, "LONG")
    c_h1_gain = create_candle(160.15, 161.10, 160.15, 161.00)
    eng_h1.on_candle_close(c_h1_gain)
    assert eng_h1.trailing_sl_core is None, "Su H1 il Trailing SL Core NON DEVE MAI attivarsi!"
    print("OK: Su H1 Trailing SL Core è rimasto None (disattivato).")

    print("\n=== TEST 5: max_kj_distance (30 pip) ===")
    eng_dist = CoreEngine(cfg_h1) # max_kj_distance = 30 pip = 0.30
    eng_dist.seed_history(candles)
    eng_dist.is_running = True
    eng_dist.current_direction = "FLAT"
    eng_dist.on_candle_close(candles[-1]) # KJ = 160.00
    assert eng_dist.current_direction == "FLAT"
    
    # Rottura KJ con candela verde che chiude a 160.40 (distanza 40 pip > 30 pip)
    c_break_far = create_candle(159.95, 160.45, 159.90, 160.40)
    ev_far = eng_dist.on_candle_close(c_break_far)
    assert not any(e.get("type") == "auto_start" for e in ev_far), "Non doveva entrare perchè distanza > 30 pip"
    print("OK: A 40 pip dalla KJ non entra perchè oltre il limite di 30 pip.")
    
    # Ora candela verde che ritraccia a 160.25 (distanza 25 pip <= 30 pip)
    c_retrace = create_candle(160.15, 160.30, 160.15, 160.25)
    ev_retrace = eng_dist.on_candle_close(c_retrace)
    assert any(e.get("type") == "auto_start" for e in ev_retrace), "Doveva entrare dopo il ritracciamento entro 30 pip"
    print("OK: Rientrato entro 30 pip, la Core entra a mercato con successo.")

    print("\n>>> TUTTI I 5 TEST SONO STATI SUPERATI AL 100%! <<<")

if __name__ == "__main__":
    test_all()
