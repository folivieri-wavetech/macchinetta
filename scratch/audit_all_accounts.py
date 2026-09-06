import sys
import requests
import json
import os

CONFIG_EPIC = {
    "Spot Gold": "CS.D.CFEGOLD.CBE.IP",
    "US 500 Cash": "IX.D.SPTRD.IFD.IP",
    "EUR/USD": "CS.D.EURUSD.MINI.IP",
    "GBP/USD": "CS.D.GBPUSD.MINI.IP",
    "USD/JPY": "CS.D.USDJPY.MINI.IP",
    "AUD/CAD": "CS.D.AUDCAD.MINI.IP",
    "AUD/NZD": "CS.D.AUDNZD.MINI.IP",
    "CAD/JPY": "CS.D.CADJPY.MINI.IP",
    "EUR/GBP": "CS.D.EURGBP.MINI.IP",
    "USD/CAD": "CS.D.USDCAD.MINI.IP",
    "USD/CHF": "CS.D.USDCHF.MINI.IP"
}
EPIC_TO_NAME = {v: k for k, v in CONFIG_EPIC.items()}

conti = [d for d in os.listdir('/data') if os.path.isdir(os.path.join('/data', d)) and (d.endswith('_DEMO') or d.endswith('_REALE'))]

print("=== AUDIT COMPLETO POSIZIONI IG VS MEMORIA ===")
for c in sorted(conti):
    print(f"\n==========================================")
    print(f"CONTO: {c}")
    print(f"==========================================")
    tok_f = os.path.join('/data', c, 'token_ig.json')
    if not os.path.exists(tok_f):
        print("token_ig.json non trovato")
        continue
    with open(tok_f, 'r') as f:
        tok = json.load(f)
    
    # Prendi API KEY dal file .env del conto
    env_f = os.path.join('/data', c, '.env')
    api_k = ""
    if os.path.exists(env_f):
        with open(env_f, 'r') as f:
            for l in f:
                if l.startswith("IG_API_KEY="):
                    api_k = l.split("=", 1)[1].strip().strip('"').strip("'")
    
    headers = {
        "CST": tok.get("CST") or tok.get("cst"),
        "X-SECURITY-TOKEN": tok.get("X-SECURITY-TOKEN") or tok.get("x_security_token"),
        "X-IG-API-KEY": api_k,
        "Version": "2"
    }
    base_url = "https://demo-api.ig.com/gateway/deal" if "_DEMO" in c else "https://api.ig.com/gateway/deal"
    try:
        r = requests.get(f"{base_url}/positions", headers=headers, timeout=10)
        if r.status_code == 200:
            positions = r.json().get("positions", [])
            print(f"Posizioni totali aperte su IG: {len(positions)}")
            
            p_mem = os.path.join('/data', c, 'memoria_parametri.json')
            mem = {}
            if os.path.exists(p_mem):
                with open(p_mem, 'r', encoding='utf-8') as f:
                    mem = json.load(f)
            
            # Analizza tutte le posizioni su IG
            for p in positions:
                m = p.get('market', {})
                pos = p.get('position', {})
                ins_name = m.get('instrumentName')
                epic = m.get('epic')
                direction = pos.get('direction')
                size = pos.get('size')
                level = pos.get('level')
                deal_id = pos.get('dealId')
                created = pos.get('createdDate')
                
                s_nome = EPIC_TO_NAME.get(epic, ins_name)
                mem_data = mem.get(s_nome, {})
                mem_strat = mem_data.get('tipo_strategia', 'RANGE')
                mem_attivo = mem_data.get('attivo', False)
                mem_stato = mem_data.get('stato', 'FLAT')
                mem_tf = mem_data.get('timeframe', '-')
                mem_core = mem_data.get('posizioni_core', [])
                
                sync_status = "✅ ALLINEATO"
                if mem_strat == "TREND":
                    if not mem_attivo or mem_stato not in ("LONG", "SHORT") or not mem_core:
                        sync_status = "🚨 DISALLINEATO (Posizione aperta su IG ma FLAT in memoria)"
                
                print(f"• IG: {s_nome:<12} | {direction:<4} {size} @ {level:<8} (ID: {deal_id}, {created}) | MEM: [Strat={mem_strat}, TF={mem_tf}, Attivo={mem_attivo}, Stato={mem_stato}, Core={len(mem_core)}] ➔ {sync_status}")
        else:
            print("Errore IG status:", r.status_code, r.text)
    except Exception as e:
        print("Errore:", e)
