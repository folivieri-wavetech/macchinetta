import sys
import requests
import json
import os

CONFIG_EPIC = {
    "Spot Gold": "CS.D.CFEGOLD.CBE.IP",
    "US 500 Cash": "IX.D.SPTRD.IFD.IP",
    "EUR/USD": "CS.D.EURUSD.CEBM.IP",
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

print("=== RIPARAZIONE E ALLINEAMENTO MEMORIA CON POSIZIONI REALI IG ===")

for c in sorted(conti):
    print(f"\n==========================================")
    print(f"VERIFICA & FIX CONTO: {c}")
    print(f"==========================================")
    tok_f = os.path.join('/data', c, 'token_ig.json')
    if not os.path.exists(tok_f):
        print("token_ig.json non trovato")
        continue
    with open(tok_f, 'r') as f:
        tok = json.load(f)
    
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
            
            mem_modificata = False
            
            # Raggruppa posizioni per EPIC
            pos_by_epic = {}
            for p in positions:
                ep = p.get('market', {}).get('epic')
                if ep not in pos_by_epic:
                    pos_by_epic[ep] = []
                pos_by_epic[ep].append(p)
            
            # Controlla ogni strumento
            for s_nome, epic in CONFIG_EPIC.items():
                pos_list = pos_by_epic.get(epic, [])
                mem_data = mem.get(s_nome, {})
                strat = mem_data.get("tipo_strategia", "TREND")
                
                if pos_list:
                    # Ordina per createdDate
                    pos_list_ord = sorted(pos_list, key=lambda x: x.get('position', {}).get('createdDate', ''))
                    p0 = pos_list_ord[0].get('position', {})
                    dir_pos = "LONG" if p0.get('direction') == "BUY" else "SHORT"
                    lvl_pos = float(p0.get('level', 0.0))
                    sz_pos = float(p0.get('size', 1.0))
                    deal_id = p0.get('dealId')
                    
                    core_dict = [{
                        "entry": lvl_pos,
                        "size": sz_pos,
                        "type": "core",
                        "direction": dir_pos,
                        "ticket": deal_id
                    }]
                    
                    incr_dict = []
                    for pi in pos_list_ord[1:]:
                        pipos = pi.get('position', {})
                        idir = "LONG" if pipos.get('direction') == "BUY" else "SHORT"
                        ilvl = float(pipos.get('level', 0.0))
                        isz = float(pipos.get('size', 1.0))
                        itkt = pipos.get('dealId')
                        incr_dict.append({
                            "entry": ilvl,
                            "size": isz,
                            "type": "increment",
                            "direction": idir,
                            "ticket": itkt
                        })
                    
                    old_stato = mem_data.get("stato")
                    old_core = mem_data.get("posizioni_core", [])
                    
                    if old_stato != dir_pos or len(old_core) == 0:
                        print(f"🔧 RIPARAZIONE {s_nome}: Imposto stato={dir_pos}, attivo=True, core={deal_id} ({sz_pos} @ {lvl_pos})")
                        mem_data["attivo"] = True
                        mem_data["stato"] = dir_pos
                        mem_data["direzione"] = dir_pos
                        mem_data["posizioni_core"] = core_dict
                        mem_data["posizioni_incr"] = incr_dict
                        if "tipo_strategia" not in mem_data or mem_data["tipo_strategia"] == "":
                            mem_data["tipo_strategia"] = "TREND"
                        
                        wip = mem_data.get("storico_wip_trend", [])
                        wip.append(f"[ALLINEAMENTO IG] Riagganciata posizione reale Core {dir_pos} a {lvl_pos} (ID: {deal_id})")
                        mem_data["storico_wip_trend"] = wip[-30:]
                        mem[s_nome] = mem_data
                        mem_modificata = True
                else:
                    # Nessuna posizione su IG
                    if mem_data.get("tipo_strategia") == "TREND" and (mem_data.get("posizioni_core") or mem_data.get("posizioni_incr")):
                        print(f"🧹 PULIZIA {s_nome}: Posizione non presente su IG. Resetto memoria a FLAT.")
                        mem_data["posizioni_core"] = []
                        mem_data["posizioni_incr"] = []
                        mem_data["trailing_sl_core"] = None
                        mem_data["trailing_sl_incr"] = None
                        mem_data["stato"] = "FLAT"
                        mem[s_nome] = mem_data
                        mem_modificata = True
            
            if mem_modificata:
                with open(p_mem, 'w', encoding='utf-8') as f:
                    json.dump(mem, f, indent=4)
                print(f"💾 Memoria aggiornata con successo per {c}!")
            else:
                print(f"✅ Memoria già perfettamente allineata per {c}.")
        else:
            print("Errore IG status:", r.status_code, r.text)
    except Exception as e:
        print("Errore:", e)

print("\n=== TUTTI I CONTI CONTROLLATI E RIPARATI! ===")
