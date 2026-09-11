import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from macchinetta_trend.core_engine import CoreEngine, Candle

def test_timeframe_thresholds():
    """Verifica che le soglie per H1, H4, D1 siano rispettivamente 30, 40, 50 pip."""
    e_h1 = CoreEngine({"timeframe": "HOUR"})
    assert e_h1._get_max_kj_tk_threshold_pips() == 30
    
    e_h4 = CoreEngine({"timeframe": "HOUR_4"})
    assert e_h4._get_max_kj_tk_threshold_pips() == 40
    
    e_d1 = CoreEngine({"timeframe": "DAY"})
    assert e_d1._get_max_kj_tk_threshold_pips() == 50
    print("[OK] test_timeframe_thresholds SUPERATO!")

def test_forbice_stretta_long():
    """
    Su H1, soglia = 30 pip.
    Se KJ = 1.1990 e TK = 1.2000 (distanza 10 pip <= 30 pip):
    - Candela chiude sotto TK (c_close = 1.1995 < 1.2000): NON deve scattare la Candela Segnale TK.
    - Prezzo live tocca TK - 15 pip (1.1985): NON deve scattare il paracadute TK.
    - Prezzo live tocca KJ - 15 pip (1.1975): DEVE scattare il paracadute KJ e chiudere Core + Incrementi.
    """
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "HOUR",
        "tk_periods": 21, "kj_periods": 55, "min_body": 5, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    history = [Candle(1.1980, 1.1990, 1.1970, 1.1980) for _ in range(34)] + [Candle(1.2000, 1.2010, 1.1990, 1.2000) for _ in range(21)]
    engine.seed_history(history)
    engine.start(1.2000, "LONG")
    
    # Apri un incremento
    engine.pm.open_increment(1.2000, 1, "LONG")
    assert len(engine.pm.increments) == 1
    
    # Candela chiude sotto TK (1.2000) a 1.1995 (minimo 1.1992)
    c1 = Candle(1.2000, 1.2005, 1.1992, 1.1995)
    events = engine.on_candle_close(c1, 1.1995)
    
    # Forbice TK-KJ e' 10 pip (<= 30 pip) -> niente Candela Segnale TK!
    assert engine.signal_candle_tk_active == False, "Errore: signal_candle_tk_active attivata con forbice <= 30 pip!"
    assert not any(e.get("type") == "signal_candle_tk" for e in events)
    assert len(engine.pm.increments) == 1
    
    # Prezzo live a TK - 15 pip (1.2000 - 0.0015 = 1.1985)
    ev_live = engine.check_live_stops(1.1985)
    assert not any(e.get("type") == "increments_cleared" for e in ev_live), "Errore: paracadute TK scattato con forbice <= 30 pip!"
    assert len(engine.pm.increments) == 1
    
    # Prezzo live a KJ - 15 pip (1.1990 - 0.0015 = 1.1975) -> scatta reversal KJ che chiude sia Core che Incrementi!
    ev_kj = engine.check_live_stops(1.1975)
    assert any(e.get("type") == "reversal" and e.get("reason") == "live_stop_kj" for e in ev_kj), "Errore: stop KJ non scattato!"
    assert len(engine.pm.increments) == 0, "Errore: incrementi non chiusi dallo stop KJ!"
    assert engine.pm.core_position is None
    print("[OK] test_forbice_stretta_long SUPERATO!")

def test_forbice_ampia_long():
    """
    Su H1, soglia = 30 pip.
    Se KJ = 1.1950 e TK = 1.2000 (distanza 50 pip > 30 pip):
    - Candela chiude sotto TK (c_close = 1.1995 < 1.2000): DEVE scattare la Candela Segnale TK!
    - Prezzo live rompe Minimo - 5 pip: DEVE chiudere l'incremento con motivo live_stop_tk_break_min.
    - Il Core rimane aperto sopra KJ!
    """
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "HOUR",
        "tk_periods": 21, "kj_periods": 55, "min_body": 5, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    history = [Candle(1.1900, 1.1910, 1.1890, 1.1900) for _ in range(34)] + [Candle(1.2000, 1.2010, 1.1990, 1.2000) for _ in range(21)]
    engine.seed_history(history)
    engine.start(1.2000, "LONG")
    
    engine.pm.open_increment(1.2000, 1, "LONG")
    assert len(engine.pm.increments) == 1
    
    # Candela chiude sotto TK a 1.1995 con minimo 1.1994 -> stop confermato TK a 1.1994 - 5 pip = 1.1989
    c1 = Candle(1.2000, 1.2005, 1.1994, 1.1995)
    events = engine.on_candle_close(c1, 1.1995)
    
    # Forbice TK-KJ e' 50 pip (> 30 pip) -> Candela Segnale TK DEVE attivarsi!
    assert engine.signal_candle_tk_active == True, "Errore: signal_candle_tk_active NON attivata con forbice > 30 pip!"
    assert any(e.get("type") == "signal_candle_tk" for e in events)
    assert abs(engine.signal_stop_price_tk - 1.1989) < 1e-8
    
    # Prezzo live rompe lo stop confermato (1.1989) che e' prima del paracadute (1.1985)
    ev_live = engine.check_live_stops(1.1989)
    assert any(e.get("type") == "increments_cleared" and e.get("reason") == "live_stop_tk_break_min" for e in ev_live)
    assert len(engine.pm.increments) == 0
    # Core ancora aperto sopra KJ
    assert engine.pm.core_position is not None
    assert engine.current_direction == "LONG"
    print("[OK] test_forbice_ampia_long SUPERATO!")

def test_transizione_dinamica():
    """
    Test di transizione dinamica:
    - Candela 1: forbice 10 pip (<= 30) -> chiusura sotto TK non attiva segnale TK.
    - Candela 2: TK accelera al rialzo e forbice diventa 45 pip (> 30) -> chiusura sotto TK attiva segnale TK!
    """
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "HOUR",
        "tk_periods": 21, "kj_periods": 55, "min_body": 5, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    history = [Candle(1.1980, 1.1990, 1.1970, 1.1980) for _ in range(34)] + [Candle(1.2000, 1.2010, 1.1990, 1.2000) for _ in range(21)]
    engine.seed_history(history)
    engine.start(1.2000, "LONG")
    engine.pm.open_increment(1.2000, 1, "LONG")
    
    # Candela 1: chiude sotto TK (1.2000) a 1.1995, forbice e' 10 pip
    c1 = Candle(1.2000, 1.2005, 1.1990, 1.1995)
    engine.on_candle_close(c1, 1.1995)
    assert engine.signal_candle_tk_active == False
    
    # Creiamo una storia in cui TK e' volata a 1.2050 mentre KJ e' rimasta a 1.1980 (forbice = 70 pip)
    history_exp = [Candle(1.1980, 1.1990, 1.1970, 1.1980) for _ in range(34)] + [Candle(1.2050, 1.2060, 1.2040, 1.2050) for _ in range(21)]
    engine.candles = list(history_exp)
    c2 = Candle(1.2050, 1.2055, 1.2030, 1.2035)
    engine.on_candle_close(c2, 1.2035)
    assert engine.signal_candle_tk_active == True, "Errore: con forbice allargata la protezione TK doveva attivarsi!"
    print("[OK] test_transizione_dinamica SUPERATO!")

if __name__ == "__main__":
    test_timeframe_thresholds()
    test_forbice_stretta_long()
    test_forbice_ampia_long()
    test_transizione_dinamica()
    print("\nTUTTI I TEST UNITARI HANNO AVUTO ESITO POSITIVO!")
