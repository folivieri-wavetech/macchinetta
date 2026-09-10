import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from macchinetta_trend.core_engine import CoreEngine, Candle

def test_distance_check_long():
    print("--- Test Increment Distance Check LONG (Opzione B) ---")
    config = {
        "pip_value": 0.0001,
        "scala": 1,
        "size_max": 10,
        "incr_tp_pips": 100,
        "core_tp_pips": 100,
        "entry_mode": "AGGIUNGI_SUBITO"
    }
    engine = CoreEngine(config=config)
    engine.is_running = True
    engine.current_direction = "LONG"
    engine.current_tk = 1.2000
    engine.current_kj = 1.1900
    # Blocchiamo il ricalcolo donchian per il test unitario
    engine._calculate_donchian = lambda p: engine.current_tk if p == config.get("tk_periods") else engine.current_kj
    engine.pm.open_core(1.2000, 1, "LONG")

    # Candela 1: Rossa che apre sopra TK, chiude sopra TK, chiude a 1.2010.
    # Distanza da TK: 1.2010 - 1.2000 = 10 pip <= 20 pip.
    c1 = Candle(1.2020, 1.2025, 1.2005, 1.2010)
    evs = engine.on_candle_close(c1, next_open_price=1.2010)
    assert any(e["type"] == "increment_opened" for e in evs), "Increment 1 should be opened at 1.2010"
    assert len(engine.pm.increments) == 1
    assert engine.pm.increments[0].entry_price == 1.2010
    print("Incremento 1 aperto con successo a 1.2010")

    # Candela 2: Rossa che chiude a 1.2005 (distanza 5 pip da 1.2010 < 10 pip).
    c2 = Candle(1.2015, 1.2015, 1.2002, 1.2005)
    evs2 = engine.on_candle_close(c2, next_open_price=1.2005)
    assert not any(e["type"] == "increment_opened" for e in evs2), "Increment should be REJECTED (dist 5 pip < 10 pip)"
    assert len(engine.pm.increments) == 1
    print("Incremento a 1.2005 correttamente RIFIUTATO (troppo vicino, 5 pip < 10 pip)")

    # Candela 3: Rossa che chiude di nuovo a 1.2010.
    # Distanza dall'incremento 1 (1.2010) è 0 pip < 10 pip.
    # Con Opzione B DEVE ESSERE RIFIUTATO perché c'è già un incremento a 1.2010!
    c3 = Candle(1.2015, 1.2015, 1.2008, 1.2010)
    evs3 = engine.on_candle_close(c3, next_open_price=1.2010)
    assert not any(e["type"] == "increment_opened" for e in evs3), "Increment should be REJECTED (overlap with 1.2010)"
    assert len(engine.pm.increments) == 1
    print("Incremento a 1.2010 correttamente RIFIUTATO (sovrapposizione con incremento 1)")

    # Candela 4: Rossa che chiude a 1.2020 (Open 1.2025, Close 1.2020).
    # Distanza da TK = 1.2020 - 1.2000 = 20 pip <= 20 pip.
    # Distanza da Incr 1 (1.2010) = 1.2020 - 1.2010 = 10 pip >= 10 pip. DEVE ESSERE ACCETTATO!
    c4 = Candle(1.2025, 1.2026, 1.2018, 1.2020)
    evs4 = engine.on_candle_close(c4, next_open_price=1.2020)
    assert any(e["type"] == "increment_opened" for e in evs4), "Increment should be OPENED at 1.2020 (dist 10 pip >= 10 pip)"
    assert len(engine.pm.increments) == 2
    print("Incremento 2 aperto con successo a 1.2020 (distanza 10 pip esatti)")

    # Candela 5: Ora abbiamo incrementi a 1.2010 e 1.2020.
    # Candidato a 1.2015: Distanza da 1.2010 è 5 pip (< 10 pip), distanza da 1.2020 è 5 pip (< 10 pip).
    # Con Opzione B DEVE ESSERE RIFIUTATO perché è vicino a ENTRAMBI gli incrementi!
    c5 = Candle(1.2018, 1.2019, 1.2012, 1.2015)
    evs5 = engine.on_candle_close(c5, next_open_price=1.2015)
    assert not any(e["type"] == "increment_opened" for e in evs5), "Increment should be REJECTED (5 pip from both)"
    assert len(engine.pm.increments) == 2
    print("Incremento a 1.2015 correttamente RIFIUTATO (a metà tra 1.2010 e 1.2020, dist 5 pip)")


def test_paracadute_15_pips():
    print("\n--- Test Paracadute 15 Pip (TK e KJ) ---")
    pip_val = 0.0001
    
    # LONG: TK = 1.2000, KJ = 1.1900
    config = {"pip_value": pip_val, "scala": 1, "size_max": 5}
    engine = CoreEngine(config=config)
    engine.is_running = True
    engine.current_direction = "LONG"
    engine.current_tk = 1.2000
    engine.current_kj = 1.1900
    engine.pm.open_core(1.2050, 1, "LONG")
    engine.pm.open_increment(1.2020, 1, "LONG")

    # Prezzo a TK - 14 pip = 1.2000 - 0.0014 = 1.1986 -> NON deve scattare stop TK
    evs = engine.check_live_stops(1.1986)
    assert len(engine.pm.increments) == 1, "Increments should not close at TK - 14 pip"

    # Prezzo a TK - 15 pip = 1.2000 - 0.0015 = 1.1985 -> DEVE scattare stop TK
    evs = engine.check_live_stops(1.1985)
    assert any(e.get("type") == "increments_cleared" for e in evs), "Increments should close at TK - 15 pip"
    assert len(engine.pm.increments) == 0
    assert engine.pm.core_position is not None, "Core should remain open"
    print("Paracadute TK LONG test superato (scatta a TK - 15 pip)")

    # Prezzo a KJ - 14 pip = 1.1900 - 0.0014 = 1.1886 -> NON deve scattare stop KJ
    evs = engine.check_live_stops(1.1886)
    assert engine.current_direction == "LONG"

    # Prezzo a KJ - 15 pip = 1.1900 - 0.0015 = 1.1885 -> DEVE scattare stop KJ
    evs = engine.check_live_stops(1.1885)
    assert any(e.get("type") == "reversal" and e.get("reason") == "live_stop_kj" for e in evs)
    assert engine.current_direction == "FLAT"
    print("Paracadute KJ LONG test superato (scatta a KJ - 15 pip)")

    # SHORT: TK = 1.2000, KJ = 1.2100
    engine_s = CoreEngine(config=config)
    engine_s.is_running = True
    engine_s.current_direction = "SHORT"
    engine_s.current_tk = 1.2000
    engine_s.current_kj = 1.2100
    engine_s.pm.open_core(1.1950, 1, "SHORT")
    engine_s.pm.open_increment(1.1980, 1, "SHORT")

    # Prezzo a TK + 14 pip = 1.2014 -> NON deve scattare
    evs = engine_s.check_live_stops(1.2014)
    assert len(engine_s.pm.increments) == 1

    # Prezzo a TK + 15 pip = 1.2015 -> DEVE scattare
    evs = engine_s.check_live_stops(1.2015)
    assert any(e.get("type") == "increments_cleared" for e in evs)
    assert len(engine_s.pm.increments) == 0
    print("Paracadute TK SHORT test superato (scatta a TK + 15 pip)")

    # Prezzo a KJ + 14 pip = 1.2114 -> NON deve scattare
    evs = engine_s.check_live_stops(1.2114)
    assert engine_s.current_direction == "SHORT"

    # Prezzo a KJ + 15 pip = 1.2115 -> DEVE scattare
    evs = engine_s.check_live_stops(1.2115)
    assert any(e.get("type") == "reversal" and e.get("reason") == "live_stop_kj" for e in evs)
    assert engine_s.current_direction == "FLAT"
    print("Paracadute KJ SHORT test superato (scatta a KJ + 15 pip)")

if __name__ == "__main__":
    test_distance_check_long()
    test_paracadute_15_pips()
    print("\nTUTTI I TEST SUPERATI CON SUCCESSO!")
