import json

with open('/data/DANY_DEMO/memoria_parametri.json', 'r', encoding='utf-8') as f:
    mem = json.load(f)

tot_pos = 0
for k, v in mem.items():
    if isinstance(v, dict) and v.get('attivo'):
        core = len(v.get('posizioni_core', []))
        incr = len(v.get('posizioni_incr', []))
        tot_pos += (core + incr)
        print(f"{k}: stato={v.get('stato')} Core={core} Incr={incr} Tot={core+incr}")

print(f"\nTOTALE POSIZIONI IN MEMORIA DANY: {tot_pos}")

gbp = mem.get('GBP/USD', {})
print("\n--- DETTAGLIO GBP/USD ---")
print("TP:", gbp.get("tp"), "SL:", gbp.get("sl"), "Step TP:", gbp.get("step_tp_pips"), "Dist Incr:", gbp.get("distanza_incrementi"))
print("Trailing SL:", gbp.get("trailing_sl"), "Trailing Step:", gbp.get("trailing_step"))
print("Current KJ:", gbp.get("current_kj"), "Current TK:", gbp.get("current_tk"))
print("Core:")
for c in gbp.get("posizioni_core", []):
    print(" ", c)
print(f"Incrementi ({len(gbp.get('posizioni_incr', []))}):")
for inc in gbp.get("posizioni_incr", []):
    print(" ", inc)
print("Storico WIP:")
for s in gbp.get("storico_wip_trend", []):
    print(" ", s)
