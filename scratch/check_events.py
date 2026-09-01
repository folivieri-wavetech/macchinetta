import json
import sys

sys.path.append('macchinetta_trend')
from core_engine import CoreEngine, Candle
from config import Config

with open('scratch_candles.json') as f:
    raw_candles = json.load(f)

all_candles = []
for c in raw_candles:
    all_candles.append({
        'time': c['time'],
        'candle': Candle(c['open'], c['high'], c['low'], c['close']),
        'raw': c
    })

start_idx = None
for i, item in enumerate(all_candles):
    if '19:05:00' in item['time']:
        start_idx = i
        break

for mb in [3.0, 4.0, 5.0]:
    cfg = Config()
    cfg.set("size_i", 3)
    cfg.set("size_f", 10)
    cfg.set("pip_value", 1.0)
    cfg.set("tk_periods", 21)
    cfg.set("kj_periods", 55)
    cfg.set("min_body", mb)
    
    engine = CoreEngine(cfg)
    seed = [item['candle'] for item in all_candles[:start_idx]]
    engine.seed_history(seed)
    engine.start(4346.0, direction="SHORT")
    
    events_log = []
    for i in range(start_idx, len(all_candles)):
        item = all_candles[i]
        c = item['candle']
        t = item['time']
        next_open = all_candles[i+1]['candle'].open if i+1 < len(all_candles) else c.close
        events = engine.on_candle_close(c, next_open_price=next_open)
        
        if events:
            for e in events:
                events_log.append((t, e))
        if '22:30:00' in t:
            break
            
    print(f"\n==========================================")
    print(f"RISULTATI DETTAGLIATI CON MIN_BODY = {mb} pt:")
    print(f"==========================================")
    for t, e in events_log:
        print(f"[{t}] Evento: {e['type']} | Dettagli: {e}")
    print(f"-> Totale incrementi attivi alle 22:30: {len(engine.pm.increments)}")
    for idx_inc, inc in enumerate(engine.pm.increments):
        print(f"   Incremento #{idx_inc+1}: {inc.direction} aperto a {inc.entry_price:.2f}")
