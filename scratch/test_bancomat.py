import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'macchinetta_trend'))
from core_engine import CoreEngine, Candle
from config import Config

def test_bancomat_short():
    cfg = Config()
    cfg.set("size_i", 3)
    cfg.set("size_f", 10)
    cfg.set("pip_value", 0.0001)
    cfg.set("tk_periods", 21)
    cfg.set("kj_periods", 55)
    cfg.set("min_body", 5)

    engine = CoreEngine(cfg)
    
    # 60 flat candles around 1.1000
    base_price = 1.1000
    seed = [Candle(base_price, base_price + 0.0002, base_price - 0.0002, base_price) for _ in range(60)]
    engine.seed_history(seed)
    
    # Start Short at 1.1000
    engine.start(1.1000, direction="SHORT")
    print(f"Start SHORT. Core size: {engine.pm.core_position.size}")
    
    # Add two increments manually via pm to simulate existing increments
    inc1 = engine.pm.open_increment(1.0980, size=1, direction="SHORT")
    inc1.ticket = "INC_1_OLDEST"
    inc2 = engine.pm.open_increment(1.0950, size=1, direction="SHORT")
    inc2.ticket = "INC_2_NEWER"
    
    print(f"Increments count: {len(engine.pm.increments)}")
    assert len(engine.pm.increments) == 2
    
    # Candle 1: Big drop to 1.0900. TK will be around ~1.0950.
    # Close is 1.0900, distance to TK is 0.0050 = 50 pips (> 10 pips).
    c1 = Candle(1.0950, 1.0950, 1.0890, 1.0900)
    events1 = engine.on_candle_close(c1)
    print(f"Candle 1 events: {events1}")
    print(f"Engine TK: {engine.current_tk}, Bancomat SL: {engine.bancomat_sl}")
    assert engine.bancomat_sl is not None
    # Expected SL = 1.0900 + 0.0010 = 1.0910
    assert abs(engine.bancomat_sl - 1.0910) < 1e-6
    assert len(engine.pm.increments) == 2, "No exit yet"
    
    # Candle 2: Drops further to 1.0870.
    # Bancomat SL should ratchet down to 1.0870 + 0.0010 = 1.0880!
    c2 = Candle(1.0900, 1.0905, 1.0860, 1.0870)
    events2 = engine.on_candle_close(c2)
    print(f"Candle 2 Bancomat SL: {engine.bancomat_sl}")
    assert abs(engine.bancomat_sl - 1.0880) < 1e-6
    assert len(engine.pm.increments) == 2
    
    # Candle 3: Red candle pause, closes at 1.0872 (below 1.0880 SL).
    # SL should NOT move up, must stay at 1.0880!
    c3 = Candle(1.0875, 1.0876, 1.0870, 1.0872)
    events3 = engine.on_candle_close(c3)
    print(f"Candle 3 Bancomat SL: {engine.bancomat_sl}")
    assert abs(engine.bancomat_sl - 1.0880) < 1e-6
    assert len(engine.pm.increments) == 2
    
    # Candle 4: Reversal bounce to 1.0885 (closes above 1.0880 SL, but still below TK).
    # Bancomat SL triggers! Only the OLDEST increment (INC_1_OLDEST) should be closed!
    c4 = Candle(1.0875, 1.0890, 1.0870, 1.0885)
    events4 = engine.on_candle_close(c4)
    print(f"Candle 4 events: {events4}")
    
    bancomat_events = [e for e in events4 if e.get('reason') == 'bancomat']
    assert len(bancomat_events) == 1, "Bancomat event triggered"
    closed_ev = bancomat_events[0]
    assert closed_ev['ticket'] == "INC_1_OLDEST"
    assert len(engine.pm.increments) == 1
    assert engine.pm.increments[0].ticket == "INC_2_NEWER", "Newer increment still open"
    assert engine.pm.core_position is not None, "Core position still open"
    print("[OK] TEST SHORT PASSED!")

def test_bancomat_long():
    cfg = Config()
    cfg.set("size_i", 3)
    cfg.set("size_f", 10)
    cfg.set("pip_value", 0.0001)
    cfg.set("tk_periods", 21)
    cfg.set("kj_periods", 55)
    cfg.set("min_body", 5)

    engine = CoreEngine(cfg)
    
    base_price = 1.1000
    seed = [Candle(base_price, base_price + 0.0002, base_price - 0.0002, base_price) for _ in range(60)]
    engine.seed_history(seed)
    
    engine.start(1.1000, direction="LONG")
    
    inc1 = engine.pm.open_increment(1.1020, size=1, direction="LONG")
    inc1.ticket = "INC_LONG_OLDEST"
    inc2 = engine.pm.open_increment(1.1050, size=1, direction="LONG")
    inc2.ticket = "INC_LONG_NEWER"
    
    # Candle 1: Big surge to 1.1100. TK ~ 1.1050. Dist = 50 pips.
    # Bancomat SL = 1.1100 - 0.0010 = 1.1090.
    c1 = Candle(1.1050, 1.1110, 1.1040, 1.1100)
    events1 = engine.on_candle_close(c1)
    assert abs(engine.bancomat_sl - 1.1090) < 1e-6
    
    # Candle 2: Surges to 1.1130.
    # Bancomat SL ratchets up to 1.1130 - 0.0010 = 1.1120.
    c2 = Candle(1.1100, 1.1135, 1.1090, 1.1130)
    events2 = engine.on_candle_close(c2)
    assert abs(engine.bancomat_sl - 1.1120) < 1e-6
    
    # Candle 3: Pullback closes at 1.1115 (below 1.1120 SL).
    # Triggers Bancomat on oldest!
    c3 = Candle(1.1130, 1.1130, 1.1110, 1.1115)
    events3 = engine.on_candle_close(c3)
    bancomat_events = [e for e in events3 if e.get('reason') == 'bancomat']
    assert len(bancomat_events) == 1
    assert bancomat_events[0]['ticket'] == "INC_LONG_OLDEST"
    assert len(engine.pm.increments) == 1
    assert engine.pm.increments[0].ticket == "INC_LONG_NEWER"
    print("[OK] TEST LONG PASSED!")

if __name__ == '__main__':
    test_bancomat_short()
    test_bancomat_long()
    print("[OK] ALL TESTS PASSED!")
