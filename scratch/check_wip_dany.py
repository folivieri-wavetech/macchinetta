import json

with open('/data/DANY_DEMO/memoria_parametri.json', 'r', encoding='utf-8') as f:
    d = json.load(f)
    for k in ["Spot Gold", "AUD/CAD", "AUD/NZD", "CAD/JPY", "EUR/GBP", "GBP/USD", "USD/CAD", "USD/CHF"]:
        v = d.get(k, {})
        print(f"=== {k} ===")
        print(f"attivo: {v.get('attivo')}, stato: {v.get('stato')}, pos_core: {v.get('posizioni_core')}")
        print("WIP TREND:")
        for log in v.get("storico_wip_trend", [])[-5:]:
            print("  ", log)
