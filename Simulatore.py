import json
import os

# --- CONFIGURAZIONI ---
FILE_MEMORIA = "memoria_parametri.json"

CONFIG_STRUMENTI = {
    "AUD/CAD": {"epic": "CS.D.AUDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD"},
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD"},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY"},
    "EUR/GBP": {"epic": "CS.D.EURGBP.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "GBP"},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD"},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD"},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF"},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY"},
    "Ethereum": {"epic": "CS.D.ETHUSD.CFD.IP", "moltiplicatore": 1, "decimali": 2, "valuta": "USD"},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR"},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1, "decimali": 2, "valuta": "EUR"}
}

# --- STATO FINTO DEL BROKER ---
BROKER_POSIZIONI = []
BROKER_ORDINI = []
DEAL_COUNTER = 1
CASSA_SIMULATA = 0.0  # La cassaforte che tiene traccia dei profitti/perdite realizzati

def aggiorna_memoria(nome_strumento, aggiornamenti):
    try:
        with open(FILE_MEMORIA, "r") as f: dati = json.load(f)
        if nome_strumento in dati:
            dati[nome_strumento].update(aggiornamenti)
            with open(FILE_MEMORIA, "w") as f: json.dump(dati, f, indent=4)
    except: pass

def fake_chiudi_parziale(dealId, epic, dir_chiusura, size_da_chiudere, prezzo_attuale, mult):
    global BROKER_POSIZIONI, CASSA_SIMULATA
    rimaste = []
    for p in BROKER_POSIZIONI:
        if p['position']['dealId'] == dealId:
            vecchia_size = float(p['position']['size'])
            size_chiusa = float(size_da_chiudere)
            nuova_size = vecchia_size - size_chiusa
            
            # --- CALCOLO PNL ---
            dir_apertura = p['position']['direction']
            entry = float(p['position']['level'])
            if dir_apertura == "BUY":
                pips = (prezzo_attuale - entry) / mult
            else:
                pips = (entry - prezzo_attuale) / mult
            
            profitto = pips * size_chiusa
            CASSA_SIMULATA += profitto
            
            if nuova_size > 0:
                p['position']['size'] = str(nuova_size)
                rimaste.append(p)
            print(f"✂️ [MOTORE] Chiusura (totale o parziale) eseguita per {dealId}. PnL Incassato: {profitto:+.2f} €")
        else:
            rimaste.append(p)
    BROKER_POSIZIONI = rimaste

def fake_pulisci_mercato(epic, solo_pendenti=False, mantieni_core_size=None, prezzo_attuale=None, mult=None):
    global BROKER_ORDINI, BROKER_POSIZIONI, CASSA_SIMULATA
    print("🧹 [BROKER FINTO] Pulizia in corso...")
    BROKER_ORDINI = [o for o in BROKER_ORDINI if o['marketData']['epic'] != epic]
    
    if not solo_pendenti:
        rimaste = []
        for p in BROKER_POSIZIONI:
            if p['market']['epic'] != epic or (mantieni_core_size and float(p['position']['size']) == mantieni_core_size):
                rimaste.append(p)
            else:
                # Se viene "spazzata via", realizza PnL (Es. reset per Sconfitta o Vittoria)
                if prezzo_attuale is not None and mult is not None:
                    dir_apertura = p['position']['direction']
                    entry = float(p['position']['level'])
                    size = float(p['position']['size'])
                    pips = (prezzo_attuale - entry) / mult if dir_apertura == "BUY" else (entry - prezzo_attuale) / mult
                    profitto = pips * size
                    CASSA_SIMULATA += profitto
                    print(f"   💸 [PULIZIA] Posizione {p['position']['dealId']} chiusa al mercato. PnL Incassato: {profitto:+.2f} €")
        BROKER_POSIZIONI = rimaste

def fake_invia_ordine_mercato(epic, valuta, direzione, size, prezzo_esecuz, limit_lvl=None, stop_lvl=None):
    global DEAL_COUNTER, BROKER_POSIZIONI
    BROKER_POSIZIONI.append({
        "market": {"epic": epic},
        "position": {
            "dealId": f"POS_{DEAL_COUNTER}",
            "direction": direzione,
            "size": str(size),
            "level": str(prezzo_esecuz),
            "limitLevel": limit_lvl,
            "stopLevel": stop_lvl
        }
    })
    DEAL_COUNTER += 1
    print(f"🟢 [BROKER FINTO] Eseguito MKT {direzione} a {prezzo_esecuz} | Size: {size}")
    return True

def fake_invia_ordine_pendente(epic, valuta, direzione, size, livello, tipo, lim, stop):
    global DEAL_COUNTER, BROKER_ORDINI
    BROKER_ORDINI.append({
        "marketData": {"epic": epic},
        "workingOrderData": {
            "dealId": f"ORD_{DEAL_COUNTER}",
            "direction": direzione,
            "orderSize": str(size),
            "level": str(livello),
            "type": tipo,
            "limitLevel": lim,
            "stopLevel": stop
        }
    })
    DEAL_COUNTER += 1
    print(f"🟡 [BROKER FINTO] Piazzato PENDENTE {tipo} {direzione} | Lvl: {livello} | Size: {size}")
    return True

def verifica_trigger_broker(prezzo_attuale, epic, mult):
    global BROKER_ORDINI, BROKER_POSIZIONI, CASSA_SIMULATA
    
    # 1. CONTROLLO SL/TP DELLE POSIZIONI GIA' APERTE
    posizioni_rimaste = []
    for p in BROKER_POSIZIONI:
        if p['market']['epic'] != epic:
            posizioni_rimaste.append(p)
            continue
            
        dir = p['position']['direction']
        lim = p['position']['limitLevel']
        stop = p['position']['stopLevel']
        
        chiusa = False
        motivo = ""
        esito = ""
        prezzo_esec = prezzo_attuale
        
        if dir == "BUY":
            if lim and prezzo_attuale >= float(lim): 
                chiusa = True; motivo = "Take Profit"; esito = "✅ PROFITTO"; prezzo_esec = float(lim)
            if stop and prezzo_attuale <= float(stop): 
                chiusa = True; motivo = "Stop Loss"; esito = "❌ PERDITA"; prezzo_esec = float(stop)
        elif dir == "SELL":
            if lim and prezzo_attuale <= float(lim): 
                chiusa = True; motivo = "Take Profit"; esito = "✅ PROFITTO"; prezzo_esec = float(lim)
            if stop and prezzo_attuale >= float(stop): 
                chiusa = True; motivo = "Stop Loss"; esito = "❌ PERDITA"; prezzo_esec = float(stop)
            
        if chiusa:
            entry = float(p['position']['level'])
            sz = float(p['position']['size'])
            if dir == "BUY":
                pips = (prezzo_esec - entry) / mult
            else:
                pips = (entry - prezzo_esec) / mult
            profitto = pips * sz
            CASSA_SIMULATA += profitto
            print(f"\n💰 [CHIUSURA BROKER] {esito}! {p['position']['dealId']} ({dir}) chiusa per {motivo} a {prezzo_esec}. PnL: {profitto:+.2f} €")
        else:
            posizioni_rimaste.append(p)
    BROKER_POSIZIONI = posizioni_rimaste

    # 2. CONTROLLO INNESCO DEGLI ORDINI PENDENTI
    ordini_rimasti = []
    for o in BROKER_ORDINI:
        if o['marketData']['epic'] != epic:
            ordini_rimasti.append(o)
            continue
            
        tipo = o['workingOrderData']['type']
        dir = o['workingOrderData']['direction']
        lvl = float(o['workingOrderData']['level'])
        size = float(o['workingOrderData']['orderSize'])
        lim = o['workingOrderData']['limitLevel']
        stop = o['workingOrderData']['stopLevel']
        
        trigger = False
        if dir == "BUY" and tipo == "LIMIT" and prezzo_attuale <= lvl: trigger = True
        elif dir == "BUY" and tipo == "STOP" and prezzo_attuale >= lvl: trigger = True
        elif dir == "SELL" and tipo == "LIMIT" and prezzo_attuale >= lvl: trigger = True
        elif dir == "SELL" and tipo == "STOP" and prezzo_attuale <= lvl: trigger = True
        
        if trigger:
            print(f"\n💥 [TRIGGER] Ordine Pendente {o['workingOrderData']['dealId']} innescato! (Eseguito a {prezzo_attuale})")
            fake_invia_ordine_mercato(epic, "USD", dir, size, prezzo_attuale, limit_lvl=lim, stop_lvl=stop)
        else:
            ordini_rimasti.append(o)
            
    BROKER_ORDINI = ordini_rimasti


# ==========================================
# LA LOGICA ESATTA DEL MOTORE (Copiata e allineata)
# ==========================================
def logica_motore_finto(nome, prezzo_attuale):
    with open(FILE_MEMORIA, "r") as f: param = json.load(f).get(nome, {})
    
    # --- FIX: Impedisce al simulatore di operare se la macchinetta è spenta ---
    if not param.get("attivo", True):
        return 
    # --------------------------------------------------------------------------

    epic = CONFIG_STRUMENTI[nome]["epic"]
    dec = CONFIG_STRUMENTI[nome]["decimali"]
    mult = CONFIG_STRUMENTI[nome]["moltiplicatore"]
    valuta = CONFIG_STRUMENTI[nome]["valuta"]
    s_core = float(param.get("size", 0))
    stato = param.get("stato", "IN_ATTESA")
    
    print(f"\n--- ELABORAZIONE LOGICA MACCHINETTA ({stato}) ---")

    if stato == "IN_ATTESA":
        s_ass = max(1.0, s_core / 2)
        tp4 = (param.get("tp") / 4) * mult
        opp_val = param.get("opp") * mult
        dir_core = param.get("direzione", "LONG")
        
        print(f"🚀 Avvio FASE 1 simulata su {nome} in dir {dir_core} a {prezzo_attuale}")
        if dir_core == "LONG":
            fake_invia_ordine_mercato(epic, valuta, "BUY", s_core, prezzo_attuale)
            fake_invia_ordine_mercato(epic, valuta, "SELL", s_ass, prezzo_attuale)
            fake_invia_ordine_pendente(epic, valuta, "SELL", s_core, round(prezzo_attuale - opp_val, dec), "STOP", None, None)
            fake_invia_ordine_pendente(epic, valuta, "SELL", s_ass, round(prezzo_attuale + tp4, dec), "LIMIT", prezzo_attuale, round(prezzo_attuale + (2 * tp4), dec))
        else:
            fake_invia_ordine_mercato(epic, valuta, "SELL", s_core, prezzo_attuale)
            fake_invia_ordine_mercato(epic, valuta, "BUY", s_ass, prezzo_attuale)
            fake_invia_ordine_pendente(epic, valuta, "BUY", s_core, round(prezzo_attuale + opp_val, dec), "STOP", None, None)
            fake_invia_ordine_pendente(epic, valuta, "BUY", s_ass, round(prezzo_attuale - tp4, dec), "LIMIT", prezzo_attuale, round(prezzo_attuale - (2 * tp4), dec))
            
        aggiorna_memoria(nome, {"stato": "FASE_1", "prezzo_base": prezzo_attuale})

    elif stato.startswith("FASE_1"):
        posizioni = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        pendenti = [o for o in BROKER_ORDINI if o['marketData']['epic'] == epic]
        
        dir_core = param.get("direzione")
        s_ass = max(1.0, s_core / 2)
        core_long = [p for p in posizioni if float(p['position']['size']) == s_core and p['position']['direction'] == "BUY"]
        core_short = [p for p in posizioni if float(p['position']['size']) == s_core and p['position']['direction'] == "SELL"]
        
        micro_dir_attesa = "SELL" if dir_core == "LONG" else "BUY"
        pos_micro_giuste = [p for p in posizioni if float(p['position']['size']) == s_ass and p['position']['direction'] == micro_dir_attesa]
        
        num_pos = len(posizioni)
        num_ord = len(pendenti)
        micro_attiva = (num_pos >= 3)
        pendenti_micro = [o for o in pendenti if float(o['workingOrderData']['orderSize']) == s_ass]
        
        # --- FIX: AGGIORNAMENTO STATO VISIVO MICRO ---
        if num_pos == 3 and num_ord == 1:
            nuovo_stato = "FASE_1 + Micro"
        elif num_pos == 2 and num_ord == 2:
            nuovo_stato = "FASE_1"
        else:
            nuovo_stato = "FASE_1 + Micro" if micro_attiva else "FASE_1"
        
        if param.get("stato") != nuovo_stato:
            aggiorna_memoria(nome, {"stato": nuovo_stato})
        # ---------------------------------------------

        if core_long and core_short:
            print("➡️ Rilevato Split! Transizione a Fase 2 Ticket in corso...")
            if pos_micro_giuste:
                m_attiva = pos_micro_giuste[0]
                fake_chiudi_parziale(m_attiva['position']['dealId'], epic, "BUY" if m_attiva['position']['direction'] == "SELL" else "SELL", m_attiva['position']['size'], prezzo_attuale, mult)
            
            if dir_core == "LONG":
                prezzo_riferimento = float(core_short[0]['position']['level'])
                ticket_dir = "BUY"
            else:
                prezzo_riferimento = float(core_long[0]['position']['level'])
                ticket_dir = "SELL"
            
            fake_pulisci_mercato(epic, solo_pendenti=True)
            
            opp_val = param.get("opp") * mult
            lim_lvl = round(prezzo_riferimento + opp_val, dec) if ticket_dir == "BUY" else round(prezzo_riferimento - opp_val, dec)
            stop_lvl = round(prezzo_riferimento - opp_val, dec) if ticket_dir == "BUY" else round(prezzo_riferimento + opp_val, dec)
            
            fake_invia_ordine_mercato(epic, valuta, ticket_dir, s_ass, prezzo_riferimento, limit_lvl=lim_lvl, stop_lvl=stop_lvl)
            aggiorna_memoria(nome, {"stato": "FASE_2_TICKET", "ticket_dir": ticket_dir, "ticket_base": prezzo_riferimento})
            return
        
        if not micro_attiva and not pendenti_micro:
            p_base_orig = param.get("prezzo_base")
            if p_base_orig is None: return
            tp4 = (param.get("tp") / 4) * mult
            
            lvl_ingresso_micro_long = p_base_orig + tp4
            lvl_ingresso_micro_short = p_base_orig - tp4
            
            print("➡️ Micro assicurazione caduta. Valuto rimbalzo o vittoria...")
            if dir_core == "LONG":
                if prezzo_attuale < lvl_ingresso_micro_long: 
                    print("🔄 Micro in Profit! Riarmo il pendente...")
                    fake_invia_ordine_pendente(epic, valuta, "SELL", s_ass, round(p_base_orig + tp4, dec), "LIMIT", p_base_orig, round(p_base_orig + (2 * tp4), dec))
                else: 
                    print("🎯 VITTORIA FASE 1! Resetto...")
                    fake_pulisci_mercato(epic, prezzo_attuale=prezzo_attuale, mult=mult)
                    # --- FIX: Ping-Pong Automatico in Fase 1 ---
                    aggiorna_memoria(nome, {"direzione": "SHORT", "stato": "IN_ATTESA"})
                    # -------------------------------------------
            else:
                if prezzo_attuale > lvl_ingresso_micro_short: 
                    print("🔄 Micro in Profit! Riarmo il pendente...")
                    fake_invia_ordine_pendente(epic, valuta, "BUY", s_ass, round(p_base_orig - tp4, dec), "LIMIT", p_base_orig, round(p_base_orig - (2 * tp4), dec))
                else: 
                    print("🎯 VITTORIA FASE 1! Resetto...")
                    fake_pulisci_mercato(epic, prezzo_attuale=prezzo_attuale, mult=mult)
                    # --- FIX: Ping-Pong Automatico in Fase 1 ---
                    aggiorna_memoria(nome, {"direzione": "LONG", "stato": "IN_ATTESA"})
                    # -------------------------------------------

    elif stato == "FASE_2_TICKET":
        posizioni = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        s_mezzo = max(1.0, s_core / 2)
        ticket_dir = param.get("ticket_dir")
        ticket_base = param.get("ticket_base")
        opp_val = param.get("opp") * mult
        
        ticket_attivo = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == ticket_dir]
        
        if not ticket_attivo:
            print("➡️ Ticket chiuso dal finto IG! Verifico vittoria...")
            vittoria = False
            if ticket_dir == "BUY" and prezzo_attuale > ticket_base: vittoria = True
            elif ticket_dir == "SELL" and prezzo_attuale < ticket_base: vittoria = True
            
            if vittoria:
                print("🎯 TICKET IN GAIN! Apro ticket inverso...")
                nuova_dir = "SELL" if ticket_dir == "BUY" else "BUY"
                nuovo_lim = round(prezzo_attuale - opp_val, dec) if nuova_dir == "SELL" else round(prezzo_attuale + opp_val, dec)
                nuovo_stop = round(prezzo_attuale + opp_val, dec) if nuova_dir == "SELL" else round(prezzo_attuale - opp_val, dec)
                fake_invia_ordine_mercato(epic, valuta, nuova_dir, s_mezzo, prezzo_attuale, limit_lvl=nuovo_lim, stop_lvl=nuovo_stop)
                aggiorna_memoria(nome, {"ticket_dir": nuova_dir, "ticket_base": prezzo_attuale})
            else:
                print("❌ TICKET IN LOSS! Passo ai Satelliti...")
                aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITI", "tentativi_sat": 0})

    elif stato == "FASE_2_SATELLITI":
        posizioni = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        ordini = [o for o in BROKER_ORDINI if o['marketData']['epic'] == epic]
        
        s_mezzo = max(1.0, s_core / 2)
        dir_core = param.get("direzione")
        prezzo_base = param.get("prezzo_base") 
        opp_val = param.get("opp") * mult
        tp2_val = (param.get("tp") / 2) * mult
        
        core_ids = [p['position']['dealId'] for p in posizioni if float(p['position']['size']) >= s_core * 0.9]
        satelliti_attivi = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['dealId'] not in core_ids]
        
        if satelliti_attivi:
            print("🎯 SATELLITE INNESCATO! Transizione a Sat. Attivo...")
            sat_pos = satelliti_attivi[0]
            sat_dir = sat_pos['position']['direction']
            sat_price = float(sat_pos['position']['level'])
            
            fake_pulisci_mercato(epic, solo_pendenti=True)
            ibrida_dir = "SELL" if sat_dir == "BUY" else "BUY"
            s_quarto = max(0.1, s_core / 4)
            tp4_val = (param.get("tp") / 4) * mult
            
            fake_invia_ordine_mercato(epic, valuta, ibrida_dir, s_quarto, sat_price)
            
            if ibrida_dir == "SELL":
                fake_invia_ordine_pendente(epic, valuta, "SELL", s_mezzo, round(sat_price + tp4_val, dec), "LIMIT", round(sat_price, dec), None)
                fake_invia_ordine_pendente(epic, valuta, "SELL", s_quarto, round(sat_price - tp4_val, dec), "STOP", None, round(sat_price, dec))
            else:
                fake_invia_ordine_pendente(epic, valuta, "BUY", s_mezzo, round(sat_price - tp4_val, dec), "LIMIT", round(sat_price, dec), None)
                fake_invia_ordine_pendente(epic, valuta, "BUY", s_quarto, round(sat_price + tp4_val, dec), "STOP", None, round(sat_price, dec))
                
            aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITE_ATTIVO", "sat_dir": sat_dir, "sat_price": sat_price})
            return 

        if len(ordini) == 0:
            print("➡️ Piazzamento Ordini OCO Satelliti...")
            if dir_core == "LONG":
                prezzo_sat_long = round(prezzo_base + tp2_val, dec)
                prezzo_sat_short = round((prezzo_base - opp_val) - tp2_val, dec)
            else:
                prezzo_sat_long = round((prezzo_base + opp_val) + tp2_val, dec)
                prezzo_sat_short = round(prezzo_base - tp2_val, dec)
                
            fake_invia_ordine_pendente(epic, valuta, "BUY", s_mezzo, prezzo_sat_long, "STOP", round(prezzo_sat_long + tp2_val, dec), round(prezzo_sat_long - tp2_val, dec))
            fake_invia_ordine_pendente(epic, valuta, "SELL", s_mezzo, prezzo_sat_short, "STOP", round(prezzo_sat_short - tp2_val, dec), round(prezzo_sat_short + tp2_val, dec))
            return 

    elif stato.startswith("FASE_2_SATELLITE_ATTIVO") or stato == "FASE_2_SATELLITE_ATTESA":
        posizioni = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        pendenti_correnti = [o for o in BROKER_ORDINI if o['marketData']['epic'] == epic]
        
        s_mezzo = max(1.0, s_core / 2)
        s_quarto = max(0.1, s_core / 4)
        sat_dir = param.get("sat_dir")
        sat_price = param.get("sat_price")
        
        if not sat_dir or not sat_price:
            aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITI"})
            return
            
        ibrida_dir = "SELL" if sat_dir == "BUY" else "BUY"
        satellite_attivo = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == sat_dir]
        
        pos_ibride_mezzo = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == ibrida_dir]
        pos_ibride_quarto = [p for p in posizioni if float(p['position']['size']) == s_quarto and p['position']['direction'] == ibrida_dir]
        
        over_gain_attivo = len(pos_ibride_mezzo) > 0
        over_loss_attivo = len(pos_ibride_quarto) > 1 
        
        if over_gain_attivo:
            nuovo_stato = "FASE_2_SATELLITE_ATTIVO / OverGain"
        elif over_loss_attivo:
            nuovo_stato = "FASE_2_SATELLITE_ATTIVO / OverLoss"
        else:
            nuovo_stato = "FASE_2_SATELLITE_ATTESA"
            
        if param.get("stato") != nuovo_stato:
            aggiorna_memoria(nome, {"stato": nuovo_stato})
        
        if (over_gain_attivo or over_loss_attivo) and pendenti_correnti:
            print("🧹 Pulizia OCO dopo innesco Ibrida...")
            fake_pulisci_mercato(epic, solo_pendenti=True)
            pendenti_correnti = []
        
        if not satellite_attivo:
            print("➡️ Satellite Chiuso! Verifico se entrare in FASE 3 o resettare i satelliti...")
            fake_pulisci_mercato(epic, mantieni_core_size=s_core, prezzo_attuale=prezzo_attuale, mult=mult)
            
            if (sat_dir == "BUY" and prezzo_attuale > sat_price) or (sat_dir == "SELL" and prezzo_attuale < sat_price):
                print("🚨 CONDIZIONE FASE 3 RAGGIUNTA!")
                aggiorna_memoria(nome, {"stato": "FASE_3_INIT", "fase3_dir": sat_dir, "fase3_base": sat_price})
            else:
                print("♻️ Satellite in LOSS, si riparte coi satelliti.")
                aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITI", "tentativi_sat": 0})
        
        elif not over_gain_attivo and not over_loss_attivo and not pendenti_correnti:
            print("🔄 Riarmo Pendenti OCO (OverGain / OverLoss)...")
            tp4_val = (param.get("tp") / 4) * mult
            if ibrida_dir == "SELL":
                fake_invia_ordine_pendente(epic, valuta, "SELL", s_mezzo, round(sat_price + tp4_val, dec), "LIMIT", round(sat_price, dec), None)
                fake_invia_ordine_pendente(epic, valuta, "SELL", s_quarto, round(sat_price - tp4_val, dec), "STOP", None, round(sat_price, dec))
            else:
                fake_invia_ordine_pendente(epic, valuta, "BUY", s_mezzo, round(sat_price - tp4_val, dec), "LIMIT", round(sat_price, dec), None)
                fake_invia_ordine_pendente(epic, valuta, "BUY", s_quarto, round(sat_price + tp4_val, dec), "STOP", None, round(sat_price, dec))
            return

    elif stato == "FASE_3_INIT":
        print("➡️ Inizializzazione FASE 3: Taglio core contro-trend, inserimento ordini...")
        sat_dir = param.get("fase3_dir")
        dir_contro = "SELL" if sat_dir == "BUY" else "BUY"
        s_mezzo = max(1.0, s_core / 2)
        
        posizioni = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        core_trend_pos = [p for p in posizioni if p['position']['direction'] == sat_dir and float(p['position']['size']) >= s_core * 0.9]
        if core_trend_pos: fake_chiudi_parziale(core_trend_pos[0]['position']['dealId'], epic, dir_contro, core_trend_pos[0]['position']['size'], prezzo_attuale, mult)
            
        core_contro_pos = [p for p in posizioni if p['position']['direction'] == dir_contro and float(p['position']['size']) >= s_core * 0.9]
        if core_contro_pos: fake_chiudi_parziale(core_contro_pos[0]['position']['dealId'], epic, sat_dir, s_mezzo, prezzo_attuale, mult)
            
        tp2_val = (param.get("tp") / 2) * mult
        dts_val = param.get("dts") * mult
        tp4_val = (param.get("tp") / 4) * mult
        
        lim_core = round(prezzo_attuale + tp2_val, dec) if sat_dir == "BUY" else round(prezzo_attuale - tp2_val, dec)
        stop_core = round(prezzo_attuale - dts_val, dec) if sat_dir == "BUY" else round(prezzo_attuale + dts_val, dec)
        fake_invia_ordine_mercato(epic, valuta, sat_dir, s_core, prezzo_attuale, limit_lvl=lim_core, stop_lvl=stop_core)
        
        lvl_last = round(prezzo_attuale + tp4_val, dec) if sat_dir == "BUY" else round(prezzo_attuale - tp4_val, dec)
        fake_invia_ordine_pendente(epic, valuta, dir_contro, s_mezzo, lvl_last, "LIMIT", round(prezzo_attuale, dec), None)
        
        aggiorna_memoria(nome, {"stato": "FASE_3", "fase3_step": 1, "fase3_current_base": prezzo_attuale})

    elif stato in ["FASE_3", "FASE_3 + Ultima"]:
        posizioni = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        pendenti = [o for o in BROKER_ORDINI if o['marketData']['epic'] == epic]
        
        sat_dir = param.get("fase3_dir")
        dir_contro = "SELL" if sat_dir == "BUY" else "BUY"
        step = param.get("fase3_step")
        f3_base = param.get("fase3_current_base")
        s_last = s_core / 2 if step == 1 else (s_core * 0.15 if step == 2 else 0)
        
        core_trend = [p for p in posizioni if p['position']['direction'] == sat_dir and float(p['position']['size']) >= s_core * 0.9]
        
        last_pos = [p for p in posizioni if p['position']['direction'] == dir_contro and float(p['position']['size']) == s_last and p['position'].get('limitLevel') is not None]
        core_contro_pos = [p for p in posizioni if p['position']['direction'] == dir_contro and p['position'].get('limitLevel') is None]
        
        nuovo_stato = "FASE_3 + Ultima" if last_pos else "FASE_3"
        if param.get("stato") != nuovo_stato:
            aggiorna_memoria(nome, {"stato": nuovo_stato})
        
        if not core_trend:
            print("➡️ Core Trend in Fase 3 chiusa! Verifico condizione di step...")
            tp2_val = (param.get("tp") / 2) * mult
            dts_val = param.get("dts") * mult
            
            vittoria = False
            if sat_dir == "BUY":
                midpoint = f3_base + (tp2_val - dts_val) / 2
                if prezzo_attuale > midpoint: vittoria = True
            elif sat_dir == "SELL":
                midpoint = f3_base - (tp2_val - dts_val) / 2
                if prezzo_attuale < midpoint: vittoria = True
            
            if not vittoria:
                print("♻️ Sconfitta in Fase 3, resetto tutto...")
                fake_pulisci_mercato(epic, prezzo_attuale=prezzo_attuale, mult=mult)
                # --- FIX: SPEGNIMENTO MANUALE DOPO SCONFITTA ---
                aggiorna_memoria(nome, {"stato": "IN_ATTESA", "tentativi_sat": 0, "attivo": False})
                # -----------------------------------------------
            else:
                if pendenti: fake_pulisci_mercato(epic, solo_pendenti=True)
                for p in last_pos: fake_chiudi_parziale(p['position']['dealId'], epic, sat_dir, p['position']['size'], prezzo_attuale, mult)
                
                new_step = step
                if core_contro_pos:
                    c = core_contro_pos[0]
                    if step == 1:
                        s_cut = s_core * 0.35 
                        print(f"✂️ Taglio step 1: chiudo {s_cut} di Core Contro...")
                        fake_chiudi_parziale(c['position']['dealId'], epic, sat_dir, s_cut, prezzo_attuale, mult)
                        new_step = 2
                    elif step == 2:
                        s_cut = float(c['position']['size']) 
                        print(f"✂️ Taglio step 2: chiudo resto Core Contro...")
                        fake_chiudi_parziale(c['position']['dealId'], epic, sat_dir, s_cut, prezzo_attuale, mult)
                        new_step = 3
                
                if new_step == 3:
                    print("🏆 FASE 3 COMPLETATA AL 100%! Resetto la Macchinetta...")
                    fake_pulisci_mercato(epic, prezzo_attuale=prezzo_attuale, mult=mult)
                    # --- FIX: SPEGNIMENTO MANUALE DOPO VITTORIA TOTALE FASE 3 ---
                    aggiorna_memoria(nome, {"stato": "IN_ATTESA", "tentativi_sat": 0, "attivo": False})
                    # ------------------------------------------------------------
                else:
                    tp2_val = (param.get("tp") / 2) * mult
                    dts_val = param.get("dts") * mult
                    tp4_val = (param.get("tp") / 4) * mult
                    
                    lim_core = round(prezzo_attuale + tp2_val, dec) if sat_dir == "BUY" else round(prezzo_attuale - tp2_val, dec)
                    stop_core = round(prezzo_attuale - dts_val, dec) if sat_dir == "BUY" else round(prezzo_attuale + dts_val, dec)
                    print(f"📈 Riapertura nuova Core Trend a {prezzo_attuale}...")
                    fake_invia_ordine_mercato(epic, valuta, sat_dir, s_core, prezzo_attuale, limit_lvl=lim_core, stop_lvl=stop_core)
                    
                    new_s_last = s_core * 0.15
                    lvl_last = round(prezzo_attuale + tp4_val, dec) if sat_dir == "BUY" else round(prezzo_attuale - tp4_val, dec)
                    print(f"🟡 Piazzamento nuovo Ordine Ultima (Step {new_step}) a {lvl_last}...")
                    fake_invia_ordine_pendente(epic, valuta, dir_contro, new_s_last, lvl_last, "LIMIT", round(prezzo_attuale, dec), None)
                    
                    aggiorna_memoria(nome, {"fase3_step": new_step, "fase3_current_base": prezzo_attuale, "stato": "FASE_3"})
                    return 
                    
        else:
            if not last_pos and not pendenti:
                print("🔄 Riarmo Ordine Ultima (Fase 3)...")
                tp4_val = (param.get("tp") / 4) * mult
                lvl_last = round(f3_base + tp4_val, dec) if sat_dir == "BUY" else round(f3_base - tp4_val, dec)
                fake_invia_ordine_pendente(epic, valuta, dir_contro, s_last, lvl_last, "LIMIT", round(f3_base, dec), None)
                aggiorna_memoria(nome, {"stato": "FASE_3"})
                return

def avvia_simulatore():
    global CASSA_SIMULATA, DEAL_COUNTER, BROKER_POSIZIONI, BROKER_ORDINI
    CASSA_SIMULATA = 0.0  # Reset della cassa all'avvio
    DEAL_COUNTER = 1      # Reset del contatore ordini
    BROKER_POSIZIONI.clear()
    BROKER_ORDINI.clear()
    
    print("=" * 40)
    print("   🎮 SIMULATORE MACCHINETTA IG OFF-LINE")
    print("=" * 40)

    # --- FIX 1: STAMPA ELENCO STRUMENTI ---
    lista_strumenti = ", ".join(CONFIG_STRUMENTI.keys())
    print(f"\n📋 STRUMENTI DISPONIBILI:\n{lista_strumenti}")
    print("-" * 50)
    # --------------------------------------

    # --- FIX 2: LOOP ANTI-ERRORE DI BATTITURA ---
    while True:
        strumento = input("\nQuale strumento vuoi simulare?: ").strip()
        if strumento in CONFIG_STRUMENTI:
            break  # Il nome è corretto, interrompe il loop e va avanti!
        else:
            print("❌ Non riconosco lo strumento. Controlla l'elenco qui sopra e ridigita (rispetta maiuscole e spazi).")
    # --------------------------------------------

    print(f"\n✨ Lettura parametri sacri per {strumento}...")
    
    try:
        with open(FILE_MEMORIA, "r") as f:
            dati_completi = json.load(f)
            dati_strumento = dati_completi.get(strumento, {})
    except:
        dati_strumento = {}
        
    if not dati_strumento:
        print(f"❌ Errore: {strumento} non ha dati salvati nel file {FILE_MEMORIA}.")
        print("Apri la Dashboard web, imposta i valori dello strumento almeno una volta e riprova.")
        return

    size_test = dati_strumento.get("size")
    tp_test = dati_strumento.get("tp")
    opp_test = dati_strumento.get("opp")
    dts_test = dati_strumento.get("dts")
    
    scelta_dir = input(f"In che direzione vuoi avviare {strumento}? (Scrivi L per LONG, S per SHORT): ").strip().upper()
    dir_test = "SHORT" if scelta_dir == "S" else "LONG"

    print("-" * 50)
    print(f"📌 PARAMETRI SACRI RILEVATI SUL DISCO FISSO:")
    print(f"   Direzione: {dir_test} | Size: {size_test} | TP: {tp_test} | OPP: {opp_test} | DTS: {dts_test}")
    print("-" * 50)
    
    aggiorna_memoria(strumento, {
        "attivo": True, 
        "direzione": dir_test, 
        "tp": tp_test, 
        "opp": opp_test, 
        "dts": dts_test, 
        "size": size_test, 
        "stato": "IN_ATTESA",
        "prezzo_base": None,
        "tentativi_sat": 0
    })

    prezzo_input = input(f"Inserisci il PREZZO DI PARTENZA per {strumento} (Es. 1.2500): ").strip()
    try: prezzo = float(prezzo_input)
    except: return

    # --- FOTOGRAFIA CONDIZIONI INIZIALI PER IL RESET ---
    prezzo_start_sessione = prezzo
    dir_start_sessione = dir_test
    # ---------------------------------------------------

    epic = CONFIG_STRUMENTI[strumento]["epic"]
    mult = CONFIG_STRUMENTI[strumento]["moltiplicatore"]
    logica_motore_finto(strumento, prezzo)

    while True:
        with open(FILE_MEMORIA, "r") as f:
            dati_dash = json.load(f).get(strumento, {})
            stato_attuale = dati_dash.get("stato", "Sconosciuto")
            attivo_dash = dati_dash.get("attivo", True)
            
        posizioni_correnti = [p for p in BROKER_POSIZIONI if p['market']['epic'] == epic]
        ordini_correnti = [o for o in BROKER_ORDINI if o['marketData']['epic'] == epic]
        
        # --- STAMPA DEL DASHBOARD MIGLIORATA CON PNL FLUTTUANTE ---
        floating_totale = 0.0
        
        # Codici per i colori (Sfondo colorato, Testo nero)
        GIALLO = "\033[43m\033[30m"
        VERDE = "\033[102m\033[30m"  # Sfondo verde chiaro (102)
        ROSSO = "\033[101m\033[30m"  # Sfondo rosso chiaro (101)
        RESET = "\033[0m"            # Spegne l'evidenziatore
        
        # --- FIX: Feedback Visivo Macchinetta Spenta ---
        stato_visivo = stato_attuale
        if not attivo_dash:
            stato_visivo = "SPENTA (Attesa avvio manuale)"
        # -----------------------------------------------

        # Impostiamo la larghezza globale a 100 caratteri per non far sbordare le righe lunghe
        LARGHEZZA = 100
        LARGHEZZA_EMOJI = 99  # Compensa il fatto che l'emoji occupa 2 spazi fisici a schermo

        print(f"\n{GIALLO}{'='*LARGHEZZA}{RESET}")
        riga_stato = f"📊 STATO MACCHINETTA: {stato_visivo} | Prezzo Sim: {prezzo}"
        print(f"{GIALLO}{riga_stato:<{LARGHEZZA_EMOJI}}{RESET}") 
        print(f"{GIALLO}{'-'*LARGHEZZA}{RESET}")

        # --- BLOCCO POSIZIONI A MERCATO (VERDE) ---
        titolo_posizioni = "📦 POSIZIONI A MERCATO:"
        print(f"{VERDE}{titolo_posizioni:<{LARGHEZZA_EMOJI}}{RESET}")
        if posizioni_correnti:
            for p in posizioni_correnti:
                p_id = p['position']['dealId']
                d = p['position']['direction']
                sz = p['position']['size']
                en = p['position'].get('level', '0.0')
                tp_str = p['position'].get('limitLevel')
                sl_str = p['position'].get('stopLevel')
                
                tp_str = tp_str if tp_str else "-"
                sl_str = sl_str if sl_str else "-"
                
                # Calcolo Fluttuante
                entry = float(en)
                sz_float = float(sz)
                if d == "BUY":
                    pips = (prezzo - entry) / mult
                else:
                    pips = (entry - prezzo) / mult
                pnl_pos = pips * sz_float
                floating_totale += pnl_pos
                
                riga_pos = f"   -> {p_id} | {d} | Size: {sz} | Entry: {en} | TP: {tp_str} | SL: {sl_str} | PnL: {pnl_pos:+.2f} €"
                print(f"{VERDE}{riga_pos:<{LARGHEZZA}}{RESET}") 
        else:
            print(f"{VERDE}{'   (Nessuna)':<{LARGHEZZA}}{RESET}")
            
        # --- BLOCCO ORDINI PENDENTI (ROSSO) ---
        print("") # Riga vuota per separare visivamente i blocchi
        titolo_ordini = "⏳ ORDINI PENDENTI:"
        print(f"{ROSSO}{titolo_ordini:<{LARGHEZZA_EMOJI}}{RESET}") 
        if ordini_correnti:
            for o in ordini_correnti:
                o_id = o['workingOrderData']['dealId']
                t = o['workingOrderData']['type']
                d = o['workingOrderData']['direction']
                sz = o['workingOrderData']['orderSize']
                lvl = o['workingOrderData']['level']
                tp_str = o['workingOrderData'].get('limitLevel')
                sl_str = o['workingOrderData'].get('stopLevel')
                
                tp_str = tp_str if tp_str else "-"
                sl_str = sl_str if sl_str else "-"
                
                riga_ord = f"   -> {o_id} | {t} {d} | Lvl: {lvl} | Size: {sz} | TP: {tp_str} | SL: {sl_str}"
                print(f"{ROSSO}{riga_ord:<{LARGHEZZA}}{RESET}")
        else:
            print(f"{ROSSO}{'   (Nessuno)':<{LARGHEZZA}}{RESET}")
            
        print(f"\n{'-'*LARGHEZZA}")
        print(f"🏦 PROFIT/LOSS: {CASSA_SIMULATA:+.2f} €")
        print(f"📈 DRAWDOWN:    {floating_totale:+.2f} €")
        print(f"💼 TOTALE FASE: {(CASSA_SIMULATA + floating_totale):+.2f} €")
        print(f"{'='*LARGHEZZA}\n")
        # -------------------------------------------------------------

        cmd = input("Inserisci il NUOVO PREZZO (o 'q' per uscire, 'r' per reset, INVIO per tick successivo): ").strip().lower()
        
        if cmd == 'q': break
        
        # --- LOGICA DI RESET ---
        if cmd == 'r':
            print(f"\n{'='*100}")
            print(f"🔄 RESET IN CORSO: Ripristino {strumento} alle condizioni iniziali...")
            print(f"{'='*100}\n")
            
            BROKER_POSIZIONI.clear()
            BROKER_ORDINI.clear()
            CASSA_SIMULATA = 0.0
            DEAL_COUNTER = 1
            prezzo = prezzo_start_sessione
            
            aggiorna_memoria(strumento, {
                "stato": "IN_ATTESA", 
                "attivo": True, 
                "direzione": dir_start_sessione, 
                "prezzo_base": None,
                "comando_reset": False,
                "tentativi_sat": 0
            })
            
            logica_motore_finto(strumento, prezzo)
            continue
        # -----------------------
        
        # --- SEPARATORE VISIVO PER BACKTEST ---
        print(f"\n{'▼'*100}")
        if cmd == '':
            print("        ⬇️  TICK SUCCESSIVO (Stesso Prezzo)  ⬇️")
        else:
            print(f"        ⬇️  NUOVO PREZZO INSERITO: {cmd}  ⬇️")
        print(f"{'▼'*100}\n")
        
        try:
            if cmd != '': 
                nuovo_prezzo = float(cmd.replace(',', '.'))
                prezzo = nuovo_prezzo
                
            verifica_trigger_broker(prezzo, epic, mult)
            
            # --- AUTO-TICK SULLE TRANSIZIONI DI STATO ---
            stato_precedente = None
            while True:
                with open(FILE_MEMORIA, "r") as f:
                    dati = json.load(f)
                    stato_attuale = dati.get(strumento, {}).get("stato", "")
                
                if stato_attuale == stato_precedente:
                    break 
                
                stato_precedente = stato_attuale
                logica_motore_finto(strumento, prezzo)
            
        except ValueError:
            print("❌ Valore non valido. Inserisci un numero.")
        
if __name__ == "__main__":
    avvia_simulatore()