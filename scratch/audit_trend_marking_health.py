import json, os, requests, sys
sys.path.insert(0, '/data')
from Dashboard import get_ig_headers, CONFIG_STRUMENTI

conti = ['FIORDOK_DEMO', 'BONGIOLO_DEMO', 'DANY_DEMO']
for c in conti:
    print(f"=== CONTO: {c} ===")
    h = get_ig_headers(c)
    if not h:
        print("Nessun header IG per", c)
        continue
    base_url = "https://demo-api.ig.com/gateway/deal"
    try:
        r = requests.get(f"{base_url}/positions", headers=h, timeout=10)
        pos_ig = r.json().get("positions", []) if r.status_code == 200 else []
    except Exception as e:
        print("Errore IG:", e)
        pos_ig = []
        
    print(f"Posizioni live su IG ({len(pos_ig)}):")
    for p in pos_ig:
        inst = p['market']['instrumentName']
        epic = p['market']['epic']
        dir_p = p['position']['direction']
        sz = p['position']['size']
        deal_id = p['position']['dealId']
        print(f"  - {inst} | epic={epic} | {dir_p} {sz} | dealId={deal_id}")
    
    # trend_active_deals.json
    p_deals = f"/data/{c}/trend_active_deals.json"
    deals = json.load(open(p_deals)) if os.path.exists(p_deals) else {}
    print(f"trend_active_deals.json: {deals}")
    
    # memoria_parametri.json
    p_mem = f"/data/{c}/memoria_parametri.json"
    mem = json.load(open(p_mem)) if os.path.exists(p_mem) else {}
    trend_mem = {k: {'attivo': v.get('attivo'), 'stato': v.get('stato'), 'core': [x.get('ticket') for x in v.get('posizioni_core', [])], 'incr': [x.get('ticket') for x in v.get('posizioni_incr', [])]} for k, v in mem.items() if v.get('tipo_strategia') == 'TREND'}
    print(f"Strumenti TREND in memoria: {trend_mem}")
    
    # Check for discrepancies:
    # 1. Any position on IG with epic matching a trend instrument: is it in trend_active_deals?
    for p in pos_ig:
        ep = p['market']['epic']
        d_id = p['position']['dealId']
        # Is this epic managed by Trend in this account?
        is_trend_inst = any(CONFIG_STRUMENTI.get(k, {}).get('epic') == ep for k in trend_mem.keys())
        is_marked = d_id in deals.get(ep, [])
        if is_trend_inst and not is_marked:
            print(f"  ⚠️ ANOMALIA: Posizione IG {p['market']['instrumentName']} dealId={d_id} e' in uno strumento Trend ma NON e' marchiata in trend_active_deals.json!")
    
    # 2. Any deal in trend_active_deals not on IG?
    live_deal_ids = {p['position']['dealId'] for p in pos_ig}
    for ep, deal_ids in deals.items():
        for d_id in deal_ids:
            if d_id not in live_deal_ids:
                print(f"  ℹ️ Deal registrato ma non piu' su IG (verra' rimosso da sync): epic={ep} dealId={d_id}")
                
    print()
