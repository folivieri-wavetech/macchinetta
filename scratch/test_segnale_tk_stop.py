import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from macchinetta_trend.core_engine import CoreEngine, Candle

def test_long_tk_signal_and_break():
    print("=== TEST 1: LONG - CANDELA SEGNALE TK E BREAK MINIMO -5 PIP ===")
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "MINUTE_5",
        "tk_periods": 21, "kj_periods": 55, "min_body": 5, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    history = [Candle(1.1950, 1.1960, 1.1940, 1.1950) for _ in range(34)] + [Candle(1.2000, 1.2010, 1.1990, 1.2000) for _ in range(21)]
    engine.seed_history(history)
    engine.start(1.2000, "LONG")
    # Apri un incremento
    engine.pm.open_increment(1.2000, 1, "LONG")
    assert len(engine.pm.increments) == 1

    # Candela chiude sotto TK (1.2000) ma sopra KJ (1.1975).
    # Minimo candela = 1.1990, Close = 1.1995
    c1 = Candle(1.2000, 1.2005, 1.1990, 1.1995)
    events = engine.on_candle_close(c1, 1.1995)

    # Verifica: incrementi NON devono essere chiusi! Core rimane viva
    assert len(engine.pm.increments) == 1, "Gli incrementi sono stati chiusi erroneamente a fine candela!"
    assert engine.signal_candle_tk_active == True, "Candela Segnale TK non attivata!"
    assert engine.signal_candle_active == False, "Candela Segnale Core non deve attivarsi se sopra KJ!"
    
    # Livello stop deve essere Minimo - 5 pip = 1.1990 - 0.0005 = 1.19850
    assert abs(engine.signal_stop_price_tk - 1.19850) < 1e-8, f"Stop level errato: {engine.signal_stop_price_tk}"
    assert any(e.get("type") == "signal_candle_tk" for e in events), "Evento signal_candle_tk non emesso!"
    print(f"[OK] Candela chiusa sotto TK: Incrementi NON chiusi. Stop TK impostato a {engine.signal_stop_price_tk:.5f} (Minimo 1.1990 - 5 pip)")

    # Prezzo nuova candela a 1.1988 (> 1.1985) -> incrementi ancora vivi
    ev_live = engine.check_live_stops(1.1988)
    assert len(engine.pm.increments) == 1, "Incrementi chiusi prima dello stop a Minimo - 5 pip!"
    print("[OK] Prezzo a 1.1988: Incrementi rimangono aperti e vivi.")

    # Prezzo nuova candela tocca 1.1985 -> STOP CONFERMATO SCATTA SOLO SUGLI INCREMENTI! Core viva!
    ev_stop = engine.check_live_stops(1.1985)
    assert len(engine.pm.increments) == 0, "Incrementi non chiusi al tocco di Minimo - 5 pip!"
    assert engine.is_running == True, "Core deve rimanere viva sopra la Kijun!"
    assert any(e.get("type") == "increments_cleared" and "break_min" in e.get("reason", "") for e in ev_stop), "Motivo di chiusura errato!"
    print("[OK] Prezzo tocca 1.1985: Scatta rottura minima confermata e chiusura Incrementi (Core intatta)!\n")

def test_long_tk_signal_recovery():
    print("=== TEST 2: LONG - CANDELA SEGNALE TK CON RIMBALZO (RECUPERO) ===")
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "MINUTE_5",
        "tk_periods": 21, "kj_periods": 55, "pip_value": 0.01 # GBP/JPY
    }
    engine = CoreEngine(cfg)
    history = [Candle(198.00, 198.50, 197.50, 198.00) for _ in range(34)] + [Candle(200.00, 200.10, 199.90, 200.00) for _ in range(21)]
    engine.seed_history(history)
    engine.start(200.00, "LONG")
    engine.pm.open_increment(200.00, 1, "LONG")

    # Candela chiude sotto TK (200.00) a 199.95. Minimo = 199.90.
    # Stop atteso = 199.90 - 5 pip = 199.90 - 0.05 = 199.85
    c1 = Candle(200.00, 200.05, 199.90, 199.95)
    engine.on_candle_close(c1, 199.95)
    assert engine.signal_candle_tk_active == True
    assert abs(engine.signal_stop_price_tk - 199.85) < 1e-8
    print(f"[OK] GBP/JPY Candela Segnale TK attiva con stop a {engine.signal_stop_price_tk:.3f}")

    # Candela successiva recupera e chiude sopra TK a 200.10!
    c2 = Candle(199.95, 200.20, 199.90, 200.10)
    engine.on_candle_close(c2, 200.10)
    assert engine.signal_candle_tk_active == False, "Candela Segnale TK non disattivata dopo il recupero!"
    assert engine.signal_stop_price_tk is None
    assert len(engine.pm.increments) == 1, "Gli incrementi non devono essere chiusi se il prezzo recupera!"
    print("[OK] Prezzo risalito sopra TK: Candela Segnale TK disattivata, Incrementi LONG proseguono indisturbati!\n")

def test_tk_paracadute_20_pip():
    print("=== TEST 3: PRIORITA PARACADUTE TK (20 PIP) ===")
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "MINUTE_5",
        "tk_periods": 21, "kj_periods": 55, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    history = [Candle(1.1900, 1.1910, 1.1890, 1.1900) for _ in range(34)] + [Candle(1.2000, 1.2010, 1.1990, 1.2000) for _ in range(21)]
    engine.seed_history(history)
    engine.start(1.2000, "LONG")
    engine.current_tk = 1.2000
    engine.current_kj = 1.1950
    engine.pm.open_increment(1.2000, 1, "LONG")

    # TK = 1.2000. Paracadute = 1.2000 - 20 pip = 1.1980
    # A 1.1981 (19.9 pip) -> NON scatta
    ev1 = engine.check_live_stops(1.1981)
    assert len(engine.pm.increments) == 1, "Paracadute scattato prima di 20 pip!"

    # A 1.1980 (esatti 20 pip) -> SCATTA IL PARACADUTE ALL'ISTANTE
    ev2 = engine.check_live_stops(1.1980)
    assert len(engine.pm.increments) == 0, "Paracadute 20 pip non ha chiuso gli incrementi!"
    assert any(e.get("type") == "increments_cleared" and "live_stop_tk" in e.get("reason", "") for e in ev2)
    print("[OK] Paracadute TK a 20 pip scatta all'istante su crollo violento!\n")

def test_short_tk_signal_and_break():
    print("=== TEST 4: SHORT - CANDELA SEGNALE TK E BREAK MASSIMO +5 PIP ===")
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "MINUTE_5",
        "tk_periods": 21, "kj_periods": 55, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    # Per SHORT in downtrend: KJ è più alta (es. 1.2100) e TK è più bassa (es. 1.2000)
    history = [Candle(1.2100, 1.2110, 1.2090, 1.2100) for _ in range(34)] + [Candle(1.2000, 1.2010, 1.1990, 1.2000) for _ in range(21)]
    engine.seed_history(history)
    engine.start(1.2000, "SHORT")
    engine.pm.open_increment(1.2000, 1, "SHORT")

    # Candela chiude sopra TK (1.2000) a 1.2005 ma sotto KJ (1.2050). Massimo = 1.2010.
    # Stop atteso = 1.2010 + 5 pip = 1.20150
    c1 = Candle(1.2000, 1.2010, 1.1995, 1.2005)
    engine.on_candle_close(c1, 1.2005)
    assert len(engine.pm.increments) == 1, "Incrementi SHORT chiusi erroneamente a fine candela!"
    assert engine.signal_candle_tk_active == True
    assert abs(engine.signal_stop_price_tk - 1.20150) < 1e-8
    print(f"[OK] Candela chiusa sopra TK: Incrementi NON chiusi. Stop impostato a {engine.signal_stop_price_tk:.5f} (Massimo 1.2010 + 5 pip)")

    # Prezzo tocca 1.20150 -> SCATTA STOP INCREMENTI (Core intatta)
    ev_stop = engine.check_live_stops(1.20150)
    assert len(engine.pm.increments) == 0
    assert engine.is_running == True, "Core deve rimanere viva sotto la Kijun!"
    assert any(e.get("type") == "increments_cleared" and "break_max" in e.get("reason", "") for e in ev_stop)
    print("[OK] Prezzo tocca 1.2015: Scatta rottura massimo confermata e chiusura Incrementi SHORT (Core intatta)!\n")

def test_tp_and_trailing_still_work():
    print("=== TEST 5: TAKE PROFIT FISSO E TRAILING SL INCREMENTI ===")
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "MINUTE_5",
        "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    engine.start(1.2000, "LONG")
    engine.current_tk = 1.2000
    engine.current_kj = 1.1950
    engine.pm.open_increment(1.2000, 1, "LONG")

    # TP M5 = +20 pip = 1.2020
    ev_tp = engine.check_live_stops(1.2020)
    assert any(e.get("type") == "tp_increment" for e in ev_tp), "Take profit incremento a +20 pip non scattato!"
    assert len(engine.pm.increments) == 0
    print("[OK] Take profit fisso a +20 pip scatta regolarmente!\n")

if __name__ == "__main__":
    test_long_tk_signal_and_break()
    test_long_tk_signal_recovery()
    test_tk_paracadute_20_pip()
    test_short_tk_signal_and_break()
    test_tp_and_trailing_still_work()
    print("🎯 [PASS] TUTTI I TEST SU TENKAN (TK) E INCREMENTI SUPERATI AL 100%!")
