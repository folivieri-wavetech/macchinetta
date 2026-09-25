import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from macchinetta_trend.core_engine import CoreEngine, Candle

def test_h1_kj_zone_resets_ts_short():
    """
    Test su H1 SHORT:
    - Se dist_kj_tk > 100 pip e prezzo lontano (> 45 pip), TS scatta.
    - Se poi il prezzo ritraccia vicino a Kijun (distanza <= 45 pip), TS Core si disattiva!
    """
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "HOUR",
        "tk_periods": 21, "kj_periods": 55, "min_body": 5, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    
    # Per avere KJ = 1.3350 e TK = 1.3200:
    # 34 candele con Max 1.3400 e Min 1.3300 (Donchian 55 periodo: Max 1.3400, Min 1.3100 -> KJ = 1.3250)
    # Creiamo 34 candele alte (1.3400/1.3300) e 21 candele basse (1.3250/1.3150)
    candles = [Candle(1.3450, 1.3500, 1.3400, 1.3450) for _ in range(34)] + [Candle(1.3200, 1.3210, 1.3190, 1.3200) for _ in range(21)]
    engine.seed_history(candles)
    engine.start(1.3400, "SHORT")
    
    # Donchian 55: High 1.3500, Low 1.3190 -> KJ = (1.3500 + 1.3190)/2 = 1.3345
    # Donchian 21: High 1.3210, Low 1.3190 -> TK = (1.3210 + 1.3190)/2 = 1.3200
    # Forbice: 1.3345 - 1.3200 = 145 pip (> 100 pip)
    # Candela 1: close = 1.3200 -> dist_kj = 1.3345 - 1.3200 = 145 pip (> 45 pip)
    
    c1 = Candle(1.3210, 1.3210, 1.3190, 1.3200)
    events1 = engine.on_candle_close(c1)
    
    assert engine.trailing_sl_core is not None, "TS Core doveva attivarsi con forbice 150p e prezzo a 140p da KJ"
    print(f"TS Core attivato a: {engine.trailing_sl_core}")
    
    # Candela 2: Prezzo ritraccia a 1.3315 -> dist_kj = 1.3350 - 1.3315 = 35 pip (<= 45 pip!)
    c2 = Candle(1.3250, 1.3320, 1.3250, 1.3315)
    events2 = engine.on_candle_close(c2)
    
    assert engine.trailing_sl_core is None, "TS Core doveva essere rimosso in zona respiro Kijun (distanza <= 45p)!"
    assert any(e.get("type") == "trailing_core_cleared" for e in events2), "Evento trailing_core_cleared non generato!"
    print("OK: TS Core disattivato correttamente a chiusura candela in zona Kijun <= 45p!")
    
    # Test tick live: se TS viene impostato a 1.3250, ma prezzo live sale a 1.3310 (distanza 40p <= 45p)
    engine.trailing_sl_core = 1.3250
    ev_live = engine.check_live_stops(1.3310)
    assert engine.trailing_sl_core is None, "TS Core doveva essere rimosso su tick live con distanza <= 45p!"
    print("OK: TS Core rimosso su tick live in zona Kijun <= 45p!")

def test_h1_gbpusd_scenario():
    """
    Scenario reale GBPUSD evidenziato dall'utente:
    KJ = 1.32751, TK = 1.32289 (forbice = 46.2 pip, inferiore a 100 pip!)
    Prezzo = 1.32350 (distanza da KJ = 40.1 pip <= 45 pip)
    -> Il TS Core NON deve attivarsi a TK + 10 pip!
    """
    cfg = {
        "size_i": 1, "size_max": 5, "scala": 1, "timeframe": "HOUR",
        "tk_periods": 21, "kj_periods": 55, "min_body": 5, "pip_value": 0.0001
    }
    engine = CoreEngine(cfg)
    candles = [Candle(1.3250, 1.3260, 1.3240, 1.3250) for _ in range(55)]
    engine.seed_history(candles)
    engine.start(1.3250, "SHORT")
    
    engine.current_kj = 1.32751
    engine.current_tk = 1.32289
    
    c_live = Candle(1.3230, 1.3240, 1.3225, 1.3235) # dist da KJ = 40.1 pip
    events = engine.on_candle_close(c_live)
    
    assert engine.trailing_sl_core is None, "TS Core NON deve attivarsi su GBPUSD con forbice 46.2p e dist KJ 40.1p!"
    print("OK: Scenario GBPUSD verificato, nessun falso TS Core!")

if __name__ == "__main__":
    test_h1_kj_zone_resets_ts_short()
    test_h1_gbpusd_scenario()
    print("\nTUTTI I TEST SUPERATI CON SUCCESSO!")
