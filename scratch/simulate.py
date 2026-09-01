import json
import sys
import os

sys.path.append('macchinetta_trend')
from core_engine import CoreEngine, Candle
from config import Config

with open('scratch_candles.json') as f:
    raw_candles = json.load(f)

# Convert all to Candle objects
all_candles = []
for c in raw_candles:
    all_candles.append({
        'time': c['time'],
        'candle': Candle(c['open'], c['high'], c['low'], c['close']),
        'raw': c
    })

# We want to start the trade at index 106 (19:05) at price 4346.0 Short
# Let's see what index is 19:05
start_idx = None
for i, item in enumerate(all_candles):
    if '19:05:00' in item['time']:
        start_idx = i
        break

print(f"Start index for 19:05:00 is {start_idx}")

# Test with different min_body values: 5.0 (default M5), 3.0, 4.0, 6.0, 10.0
for mb in [3.0, 4.0, 5.0, 6.0, 10.0]:
    print(f"\n==========================================")
    print(f"--- TEST CON MIN_BODY = {mb} ---")
    print(f"==========================================")
    
    cfg = Config()
    cfg.set("size_i", 3)
    cfg.set("size_f", 10)
    cfg.set("pip_value", 1.0)
    cfg.set("tk_periods", 21)
    cfg.set("kj_periods", 55)
    cfg.set("min_body", mb)
    
    engine = CoreEngine(cfg)
    
    # Feed candles before 19:05 as historical seed
    seed = [item['candle'] for item in all_candles[:start_idx]]
    engine.seed_history(seed)
    
    # Start SHORT at 19:05 at 4346.0
    engine.start(4346.0, direction="SHORT")
    
    # Iterate from 19:05 onwards up to 22:30 (included)
    end_idx = None
    for i in range(start_idx, len(all_candles)):
        item = all_candles[i]
        c = item['candle']
        t = item['time']
        raw = item['raw']
        
        # calculate TK and KJ before candle close or after?
        # on_candle_close calculates TK and KJ for the closed candle
        next_open = all_candles[i+1]['candle'].open if i+1 < len(all_candles) else c.close
        events = engine.on_candle_close(c, next_open_price=next_open)
        
        tk = engine.current_tk
        kj = engine.current_kj
        
        color = "VERDE" if c.close > c.open else "ROSSA"
        body = abs(c.close - c.open)
        
        ev_str = ""
        if events:
            ev_str = " | EVENTI: " + str([e['type'] for e in events])
            for e in events:
                if e['type'] == 'increment_opened':
                    ev_str += f" (Inc SHORT @ {e['price']:.2f})"
                elif e['type'] == 'increments_cleared':
                    ev_str += f" (Inc CLEAR @ {e.get('price', c.close):.2f})"
                elif e['type'] == 'reversal':
                    ev_str += f" (REVERSAL to {e['new_direction']})"
                    
        print(f"{t} | C: {c.close:.2f} (O:{c.open:.2f}) | {color:5s} (B:{body:.2f}) | TK:{tk:.2f} KJ:{kj:.2f} | IncAttivi:{len(engine.pm.increments)} Dir:{engine.current_direction}{ev_str}")
        
        if '22:30:00' in t:
            end_idx = i
            break

    print(f"\n--- RIEPILOGO FINALE ALLE 22:30 (min_body={mb}) ---")
    print(f"Core: {engine.pm.core_position.direction if engine.pm.core_position else 'NONE'} @ {engine.pm.core_position.entry_price if engine.pm.core_position else 0}")
    print(f"Numero Incrementi Attivi: {len(engine.pm.increments)}")
    for idx_inc, inc in enumerate(engine.pm.increments):
        print(f"  Inc #{idx_inc+1}: {inc.direction} @ {inc.entry_price:.2f} (Size: {inc.size})")
