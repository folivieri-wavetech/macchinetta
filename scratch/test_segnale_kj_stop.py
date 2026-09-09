import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if len(sys.argv) < 2:
    sys.argv.append("FIORDOK_DEMO")

from macchinetta_trend.core_engine import CoreEngine, Candle
from Motore_Trend import CONFIG_STRUMENTI, pips_to_price, format_price_ig


def test_pip_calculations():
    print("=== TEST 1: CALCOLO DEI PIP PER STRUMENTO ===")
    
    # Forex standard (EUR/USD)
    pips_eur = pips_to_price("EUR/USD", 5)
    assert abs(pips_eur - 0.00050) < 1e-7, f"Errore EUR/USD 5 pip: {pips_eur}"
    assert format_price_ig("EUR/USD", 1.234567) == 1.23457
    print(f"[OK] EUR/USD: 5 pip = {pips_eur:.5f} (formattato a 5 decimali)")
    
    # Forex JPY (GBP/JPY)
    pips_gj = pips_to_price("GBP/JPY", 5)
    assert abs(pips_gj - 0.050) < 1e-5, f"Errore GBP/JPY 5 pip: {pips_gj}"
    assert format_price_ig("GBP/JPY", 207.8694) == 207.869
    print(f"[OK] GBP/JPY: 5 pip = {pips_gj:.3f} (formattato a 3 decimali)")
    
    # Indici / Metalli (Spot Gold)
    pips_gold = pips_to_price("Spot Gold", 5)
    assert abs(pips_gold - 5.0) < 1e-5, f"Errore Gold 5 pip: {pips_gold}"
    assert format_price_ig("Spot Gold", 4415.901) == 4415.90
    print(f"[OK] Spot Gold: 5 pip/punti = {pips_gold:.2f} (formattato a 2 decimali)")
    print("Tutti i calcoli dei PIP sono matematicamente esatti!\n")

def test_long_signal_candle_break():
    print("=== TEST 2: LONG - CANDELA SEGNALE E BREAK MINIMO ===")
    cfg = {
        "size_i": 2,
        "timeframe": "HOUR",
        "tk_periods": 21,
        "kj_periods": 55,
        "pip_value": 0.0001 # EUR/USD
    }
    engine = CoreEngine(cfg)
    
    dummy_history = [Candle(1.2000, 1.2020, 1.1980, 1.2000) for _ in range(60)]
    engine.seed_history(dummy_history)
    engine.start(1.2000, "LONG")
    
    assert engine.is_running and engine.current_direction == "LONG"
    
    # Nuova candela chiude a 1.1995 (sotto KJ = 1.2000 per mezzo pip), con Minimo a 1.1990
    candela_sotto_kj = Candle(1.2005, 1.2010, 1.1990, 1.1995)
    events = engine.on_candle_close(candela_sotto_kj)
    
    # NON deve chiudere la Core all'Open!
    assert not any(e.get("type") in ("core_closed", "reversal") for e in events), "ERRORE: Core chiusa prematuramente all'Open!"
    assert engine.signal_candle_active == True, "ERRORE: Candela Segnale non attivata!"
    
    # Stop atteso: Minimo (1.1990) - 5 pip (0.0005) = 1.1985
    expected_stop = 1.1985
    assert abs(engine.signal_stop_price - expected_stop) < 1e-7, f"Stop atteso {expected_stop}, trovato {engine.signal_stop_price}"
    print(f"[OK] Candela chiusa sotto KJ: Core NON chiusa. Stop impostato a {engine.signal_stop_price:.5f} (Minimo 1.1990 - 5 pip)")
    
    # Durante la nuova candela: prezzo oscilla a 1.1992 (sopra lo stop)
    ev_live1 = engine.check_live_stops(1.1992)
    assert not ev_live1, "ERRORE: Stop scattato prima del livello!"
    print("[OK] Prezzo a 1.1992: Core rimane aperta e viva.")
    
    # Prezzo tocca 1.1985 (rottura confermata)
    ev_live2 = engine.check_live_stops(1.1985)
    assert any(e.get("type") == "reversal" and e.get("reason") == "live_stop_kj_break_min" for e in ev_live2), "ERRORE: Stop rottura minimo non scattato!"
    assert engine.current_direction == "FLAT", "ERRORE: Motore non andato a FLAT!"
    print("[OK] Prezzo tocca 1.1985: Scatta rottura minima confermata e chiusura Core a FLAT!\n")

def test_long_signal_candle_recovery():
    print("=== TEST 3: LONG - CANDELA SEGNALE CON RIMBALZO (RECUPERO) ===")
    cfg = {
        "size_i": 2,
        "timeframe": "HOUR",
        "tk_periods": 21,
        "kj_periods": 55,
        "pip_value": 0.01 # GBP/JPY
    }
    engine = CoreEngine(cfg)
    dummy_history = [Candle(200.00, 200.20, 199.80, 200.00) for _ in range(60)]
    engine.seed_history(dummy_history)
    engine.start(200.00, "LONG")
    
    # Candela chiude a 199.98 (sotto KJ = 200.00), Minimo a 199.90
    candela_sotto = Candle(200.05, 200.10, 199.90, 199.98)
    events1 = engine.on_candle_close(candela_sotto)
    assert engine.signal_candle_active == True
    # Stop su GBP/JPY: 199.90 - (5 * 0.01) = 199.85
    assert abs(engine.signal_stop_price - 199.85) < 1e-5
    print(f"[OK] GBP/JPY Candela Segnale attiva con stop a {engine.signal_stop_price:.3f}")
    
    # Durante la barra il prezzo non tocca 199.85 e anzi risale chiudendo a 200.15 (sopra KJ)
    candela_rimbalzo = Candle(199.99, 200.20, 199.92, 200.15)
    events2 = engine.on_candle_close(candela_rimbalzo)
    assert engine.signal_candle_active == False, "ERRORE: Candela segnale non disattivata dopo rimbalzo!"
    assert engine.current_direction == "LONG", "ERRORE: Core chiusa ingiustamente!"
    print("[OK] Prezzo risalito sopra KJ: Candela Segnale disattivata, Core LONG prosegue indisturbata!\n")

def test_paracadute_priority():
    print("=== TEST 4: PRIORITA PARACADUTE KJ (20 PIP) ===")
    cfg = {
        "size_i": 2,
        "timeframe": "HOUR",
        "tk_periods": 21,
        "kj_periods": 55,
        "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    dummy_history = [Candle(1.2000, 1.2020, 1.1980, 1.2000) for _ in range(60)]
    engine.seed_history(dummy_history)
    engine.start(1.2000, "LONG")
    engine.current_kj = 1.2000
    engine.current_tk = 1.2000
    
    # Crollo improvviso di oltre 20 pip durante la barra (KJ = 1.2000 -> paracadute a 1.1980)
    evs = engine.check_live_stops(1.1979)
    assert any(e.get("type") == "reversal" and e.get("reason") == "live_stop_kj" for e in evs)
    print("[OK] Paracadute 20 pip scatta all'istante a mercato su spike violento!\n")

def test_short_signal_candle_break():
    print("=== TEST 5: SHORT - CANDELA SEGNALE E BREAK MASSIMO ===")
    cfg = {
        "size_i": 2,
        "timeframe": "HOUR",
        "tk_periods": 21,
        "kj_periods": 55,
        "pip_value": 0.0001 # EUR/USD
    }
    engine = CoreEngine(cfg)
    dummy_history = [Candle(1.2000, 1.2020, 1.1980, 1.2000) for _ in range(60)]
    engine.seed_history(dummy_history)
    engine.start(1.2000, "SHORT")
    
    # Candela chiude a 1.2005 (sopra KJ = 1.2000), con Massimo a 1.2010
    candela_sopra_kj = Candle(1.1995, 1.2010, 1.1990, 1.2005)
    events = engine.on_candle_close(candela_sopra_kj)
    
    assert not any(e.get("type") in ("core_closed", "reversal") for e in events)
    assert engine.signal_candle_active == True
    # Stop atteso: Massimo (1.2010) + 5 pip (0.0005) = 1.2015
    assert abs(engine.signal_stop_price - 1.2015) < 1e-7
    print(f"[OK] Candela chiusa sopra KJ: Core NON chiusa. Stop impostato a {engine.signal_stop_price:.5f} (Massimo 1.2010 + 5 pip)")
    
    # Prezzo tocca 1.2015 (rottura confermata)
    ev_live = engine.check_live_stops(1.2015)
    assert any(e.get("type") == "reversal" and e.get("reason") == "live_stop_kj_break_max" for e in ev_live)
    assert engine.current_direction == "FLAT"
    print("[OK] Prezzo tocca 1.2015: Scatta rottura massimo confermata e chiusura Core a FLAT!\n")

if __name__ == "__main__":
    test_pip_calculations()
    test_long_signal_candle_break()
    test_long_signal_candle_recovery()
    test_paracadute_priority()
    test_short_signal_candle_break()
    print("[PASS] TUTTI I TEST SONO PASSATI CON SUCCESSO AL 100%!")


