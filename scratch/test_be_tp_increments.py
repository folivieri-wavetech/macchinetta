import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from macchinetta_trend.core_engine import CoreEngine, Candle
from macchinetta_trend.position_manager import PositionManager

def test_forex_be_and_trailing():
    print("=== TEST FOREX BREAK-EVEN & TRAILING STOP ===")
    config = {
        "nome": "EUR/USD",
        "size_i": 4,
        "size_max": 10,
        "scala": 2,
        "pip_value": 0.0001
    }
    engine = CoreEngine(config)
    engine.start(1.0800, "LONG")
    engine.current_tk = 1.0800
    engine.current_kj = 1.0750
    assert engine.pm.core_position.size == 4
    assert engine.pm.total_active_size() == 4
    
    # Apri incremento da 2 a 1.0810
    inc = engine.pm.open_increment(1.0810, 2, "LONG")
    assert engine.pm.total_active_size() == 6
    assert inc.be_active == False
    
    # 1. Prezzo a +10 pip (1.0820): nessun BE (soglia 15)
    evs = engine.check_live_stops(1.0820)
    assert len(evs) == 0, f"Attesi 0 eventi a +10p, ottenuti: {evs}"
    assert inc.be_active == False
    
    # 2. Prezzo a +15 pip (1.0825): ATTIVAZIONE BREAK-EVEN (+1 pip = 1.0811, trailing 12p dal picco = 1.0813)
    evs = engine.check_live_stops(1.0825)
    assert len(evs) == 1, f"Atteso 1 evento (BE), ottenuti: {evs}"
    assert evs[0]["type"] == "increment_be_activated"
    assert round(evs[0]["sl_price"], 5) == 1.0811
    assert inc.be_active == True
    assert round(inc.sl_price, 5) == 1.0813
    
    # 3. Prezzo sale a 1.0824 (gain +14p): BE rimane attivo
    evs = engine.check_live_stops(1.0824)
    assert len(evs) == 0
    assert inc.be_active == True
    
    # 4. Prezzo sale a 1.0824 -> sale a 1.0824, poi sale a +24 pip (1.0834):
    # Trailing dist = 12 pip -> trail_level = 1.0834 - 0.0012 = 1.0822
    evs = engine.check_live_stops(1.0834)
    assert round(inc.sl_price, 5) == 1.0822
    
    # 5. Prezzo ritraccia a 1.0821: scatta Trailing Stop!
    evs = engine.check_live_stops(1.0821)
    assert len(evs) == 1
    assert evs[0]["type"] == "increment_closed"
    assert evs[0]["reason"] == "trailing_increment"
    assert evs[0]["size"] == 2
    assert engine.pm.total_active_size() == 4
    assert engine.pm.core_position is not None
    assert len(engine.pm.increments) == 0
    print("-> Test Forex BE & Trailing superato con successo!")

def test_forex_tp_bancomat():
    print("=== TEST FOREX TAKE PROFIT BANCOMAT (+25 PIP) ===")
    config = {
        "nome": "GBP/USD",
        "size_i": 4,
        "size_max": 10,
        "scala": 2,
        "pip_value": 0.0001
    }
    engine = CoreEngine(config)
    engine.start(1.2500, "LONG")
    engine.current_tk = 1.2500
    engine.current_kj = 1.2450
    
    inc = engine.pm.open_increment(1.2520, 2, "LONG")
    
    # Prezzo a +25 pip dall'entry incremento (1.2545)
    evs = engine.check_live_stops(1.2545)
    assert len(evs) >= 1
    tp_ev = next(e for e in evs if e["type"] == "tp_increment")
    assert tp_ev["size"] == 2
    assert tp_ev["tp_pips"] == 25
    assert len(engine.pm.increments) == 0
    assert engine.pm.total_active_size() == 4
    print("-> Test Forex TP Bancomat superato con successo!")

def test_gold_30_50_logic():
    print("=== TEST SPOT GOLD BE 30 PUNTI & TP 50 PUNTI ===")
    config = {
        "nome": "Spot Gold",
        "size_i": 4,
        "size_max": 10,
        "scala": 2,
        "pip_value": 1.0
    }
    engine = CoreEngine(config)
    engine.start(4250.0, "LONG")
    engine.current_tk = 4250.0
    engine.current_kj = 4200.0
    
    inc = engine.pm.open_increment(4300.0, 2, "LONG")
    
    # 1. Prezzo a +20 punti (4320.0): niente BE (soglia per Gold è 30)
    evs = engine.check_live_stops(4320.0)
    assert len(evs) == 0
    assert inc.be_active == False
    
    # 2. Prezzo a +30 punti (4330.0): scatta BE (+2 punti = 4302.0, trailing 15p dal picco = 4315.0)
    evs = engine.check_live_stops(4330.0)
    assert len(evs) == 1
    assert evs[0]["type"] == "increment_be_activated"
    assert evs[0]["sl_price"] == 4302.0
    assert evs[0]["be_pips"] == 30
    assert inc.be_active == True
    assert inc.sl_price == 4315.0
    
    # 3. Prezzo a +50 punti (4350.0): scatta TP Bancomat (+50 punti)
    evs = engine.check_live_stops(4350.0)
    tp_ev = next(e for e in evs if e["type"] == "tp_increment")
    assert tp_ev["size"] == 2
    assert tp_ev["tp_pips"] == 50
    assert len(engine.pm.increments) == 0
    assert engine.pm.total_active_size() == 4
    print("-> Test Spot Gold 30/50 superato con successo!")

def test_short_forex():
    print("=== TEST FOREX SHORT BE & TP ===")
    config = {
        "nome": "USD/JPY",
        "size_i": 4,
        "size_max": 10,
        "scala": 2,
        "pip_value": 0.01
    }
    engine = CoreEngine(config)
    engine.start(155.00, "SHORT")
    engine.current_tk = 155.00
    engine.current_kj = 155.50
    
    inc = engine.pm.open_increment(154.50, 2, "SHORT")
    
    # Prezzo scende a +15 pip (154.35): gain = 154.50 - 154.35 = 0.15 (+15 pip)
    evs = engine.check_live_stops(154.35)
    assert len(evs) == 1
    assert evs[0]["type"] == "increment_be_activated"
    # BE offset = 1 pip = 0.01 -> sl_price = 154.50 - 0.01 = 154.49
    assert round(evs[0]["sl_price"], 2) == 154.49
    assert inc.be_active == True
    
    # Prezzo scende a +25 pip (154.25): scatta TP Bancomat
    evs = engine.check_live_stops(154.25)
    tp_ev = next(e for e in evs if e["type"] == "tp_increment")
    assert tp_ev["tp_pips"] == 25
    assert len(engine.pm.increments) == 0
    assert engine.pm.total_active_size() == 4
    print("-> Test Forex SHORT superato con successo!")

def test_serialization_persistence():
    print("=== TEST SERIALIZZAZIONE & RIPRISTINO BOOT ===")
    pm = PositionManager()
    inc = pm.open_increment(
        1.0850, 
        2, 
        "LONG", 
        ticket="DEAL123", 
        highest_price=1.0870, 
        lowest_price=1.0850, 
        be_active=True, 
        sl_price=1.0851
    )
    d = inc.to_dict()
    assert d["highest_price"] == 1.0870
    assert d["lowest_price"] == 1.0850
    assert d["be_active"] == True
    assert d["sl_price"] == 1.0851
    assert d["ticket"] == "DEAL123"
    
    # Ripristino
    pm2 = PositionManager()
    inc2 = pm2.open_increment(
        d["entry"],
        d["size"],
        d["direction"],
        ticket=d["ticket"],
        highest_price=d["highest_price"],
        lowest_price=d["lowest_price"],
        be_active=d["be_active"],
        sl_price=d["sl_price"]
    )
    assert inc2.highest_price == 1.0870
    assert inc2.be_active == True
    assert inc2.sl_price == 1.0851
    print("-> Test Serializzazione & Ripristino superato con successo!")

if __name__ == "__main__":
    test_forex_be_and_trailing()
    test_forex_tp_bancomat()
    test_gold_30_50_logic()
    test_short_forex()
    test_serialization_persistence()
    print("\n>>> TUTTI I TEST SONO STATI SUPERATI CON SUCCESSO! <<<")
