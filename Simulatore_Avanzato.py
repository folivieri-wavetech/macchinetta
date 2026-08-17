import os
import pandas as pd
import numpy as np

ORIGINAL_DIR = os.getcwd()

def pulisci_nome_strumento(nome):
    return nome.replace("/", "").replace(" ", "").replace(".", "").upper()

def genera_prezzi(scenario, strumento_base_price=2400.0, tick_size=1.0, tic_totali=500):
    prices = []
    price = strumento_base_price
    prices.append(round(price, 2))
    for step in range(1, tic_totali):
        if scenario == "LATERALE":
            variazione = np.sin(step / 10.0) * tick_size * 5
            price += variazione
        elif scenario == "TREND_UP":
            variazione = abs(np.random.normal(0, tick_size * 3)) - (tick_size * 0.5)
            price += variazione
        elif scenario == "TREND_DOWN":
            variazione = -abs(np.random.normal(0, tick_size * 3)) + (tick_size * 0.5)
            price += variazione
        elif scenario == "CRASH":
            if 50 < step < 60:
                price -= tick_size * 20
            else:
                price += np.random.normal(0, tick_size)
        elif scenario == "RANDOM":
            variazione = np.random.normal(0, tick_size * 4)
            price += variazione
            
        prices.append(round(price, 2))
    return prices

def genera_base_dati(strumento, scenario, partenza, tick_size, tic_totali, size):
    strum_pulito = pulisci_nome_strumento(strumento)
    dir_path = os.path.join(ORIGINAL_DIR, "Simulatore", strum_pulito)
    os.makedirs(dir_path, exist_ok=True)
    
    prezzi = genera_prezzi(scenario, partenza, tick_size, tic_totali)
    
    file_name = f"{strum_pulito}.Start{int(partenza)}.SZ{int(size)}.ST{int(tic_totali)}.{scenario}.csv"
    file_path = os.path.join(dir_path, file_name)
    
    df = pd.DataFrame({"Price": prezzi})
    df.to_csv(file_path, index=False)
    return file_path

class SimulatoreMatematico:
    def __init__(self, tp, opp, dts, size, direzione_base):
        self.tp = float(tp)
        self.opp = float(opp)
        self.dts = float(dts)
        self.size = float(size)
        
        self.s_core = self.size
        self.s_mezzo = max(1.0, self.size / 2.0)
        self.s_quarto = max(1.0, self.size / 4.0)
        
        self.dir_base = "BUY" if direzione_base == "LONG" else "SELL"
        self.dir_contro = "SELL" if self.dir_base == "BUY" else "BUY"
        
        self.stato = "IN_ATTESA"
        self.posizioni = {}
        self.pendenti = {}
        
        self.pnl_realizzato = 0.0
        self.pnl_storico = []
        self.operazioni = []
        self.log_ws = []
        
        self.tick_corrente = 0
        self.prezzo_corrente = 0.0
        self.prezzo_base = 0.0

        self.id_counter = 1
        
        self.ticket2_active = False
        self.ticket2_dir = None
        self.ticket2_entry = None
        self.ticket2_tp_lvl = None
        
        self.attivo = True
        self.fase3_step = 0
        self.fase3_dir = None
        self.fase3_base = 0.0

    def wlog(self, msg):
        msg = msg.replace("BUY", "LONG").replace("SELL", "SHORT")
        self.log_ws.append(f"[EVENTO]: {msg}")

    def wstep(self, prezzo):
        self.log_ws.append(f"[STEP {self.tick_corrente}] prezzo raggiunto: {prezzo:.2f}")

    def aggiungi_posizione(self, nome, dir, size, entry, tp=None, sl=None):
        pos_id = f"POS_{self.id_counter}"
        self.id_counter += 1
        self.posizioni[pos_id] = {
            "nome": nome, "dir": dir, "size": size, "entry": entry, "tp": tp, "sl": sl
        }
        self.operazioni.append({
            "tick": self.tick_corrente, "prezzo": entry, "tipo": f"OPEN {dir} {nome}", "size": size, "pnl": 0
        })
        return pos_id

    def aggiungi_pendente(self, nome, dir, size, livello, tipo="LIMIT", tp=None, sl=None):
        pend_id = f"PEND_{self.id_counter}"
        self.id_counter += 1
        self.pendenti[pend_id] = {
            "nome": nome, "dir": dir, "size": size, "livello": livello, "tipo": tipo, "tp": tp, "sl": sl
        }
        return pend_id

    def chiudi_posizione(self, pos_id, prezzo_chiusura, motivo="Market"):
        pos = self.posizioni.pop(pos_id, None)
        if pos:
            if pos["dir"] == "BUY":
                pnl = (prezzo_chiusura - pos["entry"]) * pos["size"]
            else:
                pnl = (pos["entry"] - prezzo_chiusura) * pos["size"]
            
            pnl = round(pnl, 2)
            self.pnl_realizzato += pnl
            self.operazioni.append({
                "tick": self.tick_corrente, "prezzo": prezzo_chiusura, "tipo": f"CHIUSURA {pos['dir']} {pos['nome']} ({motivo})", "size": pos["size"], "pnl": pnl
            })
            return pnl, pos["nome"]
        return 0.0, ""

    def svuota_pendenti(self):
        self.pendenti.clear()

    def avvia_fase1(self, prezzo):
        self.prezzo_base = prezzo
        self.stato = "FASE_1"
        segno = "+" if self.dir_base in ["BUY", "LONG"] else "-"
        self.wlog(f"Core [{self.dir_base}] [{segno}{self.s_core}] a <u><b>{self.prezzo_base:.2f}</b></u>")
        
        self.aggiungi_posizione("Core Base", self.dir_base, self.s_core, self.prezzo_base)
        self.aggiungi_posizione("Assicurazione", self.dir_contro, self.s_mezzo, self.prezzo_base)
        
        tp4 = self.tp / 4.0
        
        if self.dir_base == "BUY":
            lvl_core_rev = self.prezzo_base - self.opp
            lvl_micro = self.prezzo_base + tp4
            self.aggiungi_pendente("ORDINE MICRO", "SELL", self.s_mezzo, lvl_micro, "LIMIT", tp=self.prezzo_base, sl=self.prezzo_base + 2*tp4)
            self.aggiungi_pendente("ORDINE CORE", "SELL", self.s_core, lvl_core_rev, "STOP")
        else:
            lvl_core_rev = self.prezzo_base + self.opp
            lvl_micro = self.prezzo_base - tp4
            self.aggiungi_pendente("ORDINE MICRO", "BUY", self.s_mezzo, lvl_micro, "LIMIT", tp=self.prezzo_base, sl=self.prezzo_base - 2*tp4)
            self.aggiungi_pendente("ORDINE CORE", "BUY", self.s_core, lvl_core_rev, "STOP")

    def attraversa(self, p_precedente, p_attuale, livello):
        return (p_precedente <= livello <= p_attuale) or (p_precedente >= livello >= p_attuale)

    def elabora_tick(self, tick_idx, prezzo):
        self.tick_corrente = tick_idx
        p_prec = self.prezzo_corrente
        self.prezzo_corrente = prezzo
        
        if self.stato == "IN_ATTESA":
            self.avvia_fase1(prezzo)
            self.pnl_storico.append({"tick": self.tick_corrente, "totale": self.pnl_realizzato})
            return

        eventi = []
        for pid, pos in self.posizioni.items():
            if pos["tp"] is not None and self.attraversa(p_prec, prezzo, pos["tp"]):
                eventi.append(("TP", pid, pos["tp"]))
            elif pos["sl"] is not None and self.attraversa(p_prec, prezzo, pos["sl"]):
                eventi.append(("SL", pid, pos["sl"]))
                
        for pid, pend in self.pendenti.items():
            if self.attraversa(p_prec, prezzo, pend["livello"]):
                eventi.append(("PEND", pid, pend["livello"]))
                
        tp_core_lvl = self.prezzo_base + self.tp if self.dir_base == "BUY" else self.prezzo_base - self.tp
        if self.stato in ["FASE_1", "FASE_2"] and self.attraversa(p_prec, prezzo, tp_core_lvl):
            eventi.append(("CORE_TP_HIT", None, tp_core_lvl))

        if self.stato == "FASE_2":
            sat1_pos = next((pos for pos in self.posizioni.values() if "SAT1" in pos["nome"]), None)
            if sat1_pos:
                if sat1_pos["sl"] is not None and self.attraversa(p_prec, prezzo, sat1_pos["sl"]):
                    eventi.append(("SAT1_SL_HIT", None, sat1_pos["sl"]))

        eventi.sort(key=lambda x: abs(x[2] - p_prec))

        for tipo, obj_id, lvl in eventi:
            self.wstep(lvl)
            
            if tipo == "CORE_TP_HIT":
                self.wlog("Take Profit CORE colpito! Avvio FASE 3 (Chiusura rami opposti)")
                self.svuota_pendenti()
                for pid in list(self.posizioni.keys()):
                    nome_pos = self.posizioni[pid]["nome"]
                    if "Core" not in nome_pos:
                        pnl, _ = self.chiudi_posizione(pid, lvl, "Inizio Fase 3")
                        self.wlog(f"Chiudo {nome_pos} a mercato. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                self.stato = "FASE_3"
                self.wlog("FASE 3: Il Core e' l'unica posizione rimasta.")
                
            elif tipo == "SAT1_SL_HIT":
                self.wlog("Stop SAT1 colpito (Falso innesco). Si torna a FASE 1")
                self.svuota_pendenti()
                for pid in list(self.posizioni.keys()):
                    nome_pos = self.posizioni[pid]["nome"]
                    if "Core" not in nome_pos and "Assicurazione" not in nome_pos:
                        pnl, _ = self.chiudi_posizione(pid, lvl, "Falso Innesco SAT1")
                        self.wlog(f"Chiudo {nome_pos} a mercato. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                        
                self.ticket2_active = False
                tp4 = self.tp / 4.0
                if self.dir_base == "BUY":
                    lvl_core_rev = self.prezzo_base - self.opp
                    lvl_micro = self.prezzo_base + tp4
                    self.aggiungi_pendente("ORDINE MICRO (SAT1)", "SELL", self.s_mezzo, lvl_micro, "LIMIT", tp=self.prezzo_base, sl=self.prezzo_base + 2*tp4)
                    self.aggiungi_pendente("ORDINE CORE", "SELL", self.s_core, lvl_core_rev, "STOP")
                else:
                    lvl_core_rev = self.prezzo_base + self.opp
                    lvl_micro = self.prezzo_base - tp4
                    self.aggiungi_pendente("ORDINE MICRO (SAT1)", "BUY", self.s_mezzo, lvl_micro, "LIMIT", tp=self.prezzo_base, sl=self.prezzo_base - 2*tp4)
                    self.aggiungi_pendente("ORDINE CORE", "BUY", self.s_core, lvl_core_rev, "STOP")
                self.stato = "FASE_1"
                
            elif tipo == "PEND":
                if obj_id not in self.pendenti: continue
                pend = self.pendenti.pop(obj_id)
                
                if self.stato == "FASE_1":
                    if "ORDINE MICRO" in pend["nome"]:
                        self.wlog(f"Posizione MICRO ({pend['dir']}) [{pend['size']}] a {lvl:.2f}")
                        self.aggiungi_posizione("MICRO", pend["dir"], pend["size"], lvl, tp=pend["tp"], sl=pend["sl"])
                        
                    elif "ORDINE CORE" in pend["nome"]:
                        # Chiude Assicurazione
                        pnl_ass = 0.0
                        for pid in list(self.posizioni.keys()):
                            if "Assicurazione" in self.posizioni[pid]["nome"]:
                                pnl_ass, _ = self.chiudi_posizione(pid, lvl, "Take Profit")
                        
                        self.wlog(f"Core Reverse innescato a <u><b>{lvl:.2f}</b></u>. Chiusura Assicurazione. [Parziale: {pnl_ass:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                        
                        # Aggiungi la nuova posizione Core Reverse
                        self.aggiungi_posizione(f"Core Reverse", pend["dir"], pend["size"], lvl)
                        
                        # Annulla Pendente MICRO
                        self.pendenti = {k: v for k, v in self.pendenti.items() if "ORDINE MICRO" not in v["nome"]}
                        
                        # Entra in Fase 2 Ticket 1
                        self.stato = "FASE_2_TICKET1"
                        t1_dir = self.dir_base # Ticket1 is same dir as original Core
                        t1_tp = lvl + self.opp if t1_dir == "BUY" else lvl - self.opp
                        t1_sl = lvl - self.opp if t1_dir == "BUY" else lvl + self.opp
                        
                        self.aggiungi_posizione("TICKET1", t1_dir, self.s_mezzo, lvl, tp=t1_tp, sl=t1_sl)
                        self.wlog(f"Entrata in Fase 2 - TICKET1 {t1_dir} [{self.s_mezzo}] a {lvl:.2f}")
                        
                elif self.stato == "FASE_2_SATELLITI":
                    if "SAT1" in pend["nome"]:
                        self.svuota_pendenti() # Remove the other OCO
                        
                        for pid in list(self.posizioni.keys()):
                            if self.posizioni[pid]["nome"] == "TICKET2":
                                pnl, _ = self.chiudi_posizione(pid, lvl, "Loss OCO")
                                self.ticket2_active = False
                                self.wlog(f"TICKET2 chiuso a mercato (Loss) a {lvl:.2f}. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")

                        nome_pulito = pend['nome'].replace("ORDINE ", "")
                        self.wlog(f"Posizione {nome_pulito} [{pend['size']}] a {lvl:.2f}")
                        
                        self.aggiungi_posizione("SAT1", pend["dir"], pend["size"], lvl, tp=pend["tp"], sl=pend["sl"])
                        sat2_dir = "SELL" if pend["dir"] == "BUY" else "BUY"
                        self.aggiungi_posizione("SAT2", sat2_dir, self.s_quarto, lvl)
                        self.wlog(f"Posizione SAT2 {sat2_dir} [{self.s_quarto}] a {lvl:.2f}")
                        self.sat_price = lvl
                        self.sat2_dir = sat2_dir
                        
                        tp4 = self.tp / 4.0
                        if sat2_dir == "SELL":
                            lvl_og = lvl + tp4
                            lvl_ol = lvl - tp4
                        else:
                            lvl_og = lvl - tp4
                            lvl_ol = lvl + tp4
                            
                        self.aggiungi_pendente("OVERGAIN", sat2_dir, self.s_mezzo, lvl_og, "LIMIT", tp=lvl)
                        self.aggiungi_pendente("OVERLOSS", sat2_dir, self.s_quarto, lvl_ol, "STOP", sl=lvl)
                        
                    elif pend["nome"] == "OVERGAIN":
                        self.wlog(f"Posizione OVERGAIN ({pend['dir']}) [{pend['size']}] a {lvl:.2f}")
                        self.aggiungi_posizione("OVERGAIN", pend["dir"], pend["size"], lvl, tp=pend["tp"])
                        
                    elif pend["nome"] == "OVERLOSS":
                        self.wlog(f"Posizione OVERLOSS ({pend['dir']}) [{pend['size']}] a {lvl:.2f}")
                        self.aggiungi_posizione("OVERLOSS", pend["dir"], pend["size"], lvl, sl=pend["sl"])
                            
                    elif "TICKET2" in pend["nome"]:
                        self.wlog(f"Posizione TICKET2 ({pend['dir']}) [{pend['size']}] a {lvl:.2f}")
                        self.aggiungi_posizione("TICKET2", pend["dir"], pend["size"], lvl, tp=pend["tp"])
                        
                elif self.stato == "FASE_3":
                    if pend["nome"] == "ULTIMA":
                        self.wlog(f"Posizione ULTIMA ({pend['dir']}) [{pend['size']}] a {lvl:.2f}")
                        self.aggiungi_posizione("ULTIMA", pend["dir"], pend["size"], lvl, tp=pend["tp"])
                        
            elif tipo in ["TP", "SL"]:
                if obj_id not in self.posizioni: continue
                pnl, pos_nome = self.chiudi_posizione(obj_id, lvl, "Take Profit" if tipo == "TP" else "Stop Loss")
                
                if pos_nome == "MICRO":
                    if tipo == "TP":
                        self.wlog(f"MICRO a target a {lvl:.2f}. Reinserisco ordine. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                        # Re-inserisci MICRO pendente
                        micro_pend_dir = "SELL" if self.dir_base == "BUY" else "BUY"
                        tp4 = self.tp / 4.0
                        lvl_micro = self.prezzo_base + tp4 if self.dir_base == "BUY" else self.prezzo_base - tp4
                        self.aggiungi_pendente("ORDINE MICRO", micro_pend_dir, self.s_mezzo, lvl_micro, "LIMIT", tp=self.prezzo_base, sl=self.prezzo_base + 2*tp4 if self.dir_base=="BUY" else self.prezzo_base - 2*tp4)
                    else:
                        pnl_micro = pnl
                        pnl_core = 0.0
                        pnl_ass = 0.0
                        for pid in list(self.posizioni.keys()):
                            nome_pos = self.posizioni[pid]["nome"]
                            if "Core Base" in nome_pos:
                                c_pnl, _ = self.chiudi_posizione(pid, lvl, "FLIP")
                                pnl_core += c_pnl
                            elif "Assicurazione" in nome_pos:
                                a_pnl, _ = self.chiudi_posizione(pid, lvl, "FLIP")
                                pnl_ass += a_pnl
                            else:
                                self.chiudi_posizione(pid, lvl, "FLIP")
                        
                        pnl_tot = pnl_core + pnl_ass + pnl_micro
                        self.wlog(f"Stop MICRO colpito a {lvl:.2f}. Chiusura posizioni *** FLIP. [Parziale: {pnl_tot:+.2f} €] (Core: {pnl_core:+.2f}€ | Ass: {pnl_ass:+.2f}€ | Micro: {pnl_micro:+.2f}€) [Totale: {self.pnl_realizzato:+.2f} €]")
                        self.svuota_pendenti()
                        self.dir_base = self.dir_contro
                        self.dir_contro = "SELL" if self.dir_base == "BUY" else "BUY"
                        self.avvia_fase1(lvl)

                elif pos_nome == "TICKET1":
                    if tipo == "TP":
                        t1_dir = "SELL" if self.posizioni.get(obj_id, {}).get("dir", self.dir_base) == "BUY" else "BUY"
                        dir_str = "SHORT" if t1_dir == "SELL" else "LONG"
                        self.wlog(f"TICKET1 a target a {lvl:.2f}! Ping-Pong: Rigirato in {dir_str}. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                        t1_tp = lvl + self.opp if t1_dir == "BUY" else lvl - self.opp
                        t1_sl = lvl - self.opp if t1_dir == "BUY" else lvl + self.opp
                        self.aggiungi_posizione("TICKET1", t1_dir, self.s_mezzo, lvl, tp=t1_tp, sl=t1_sl)
                    else:
                        core_long = [p for p in self.posizioni.values() if p['dir'] == "BUY" and "Core" in p['nome']]
                        core_short = [p for p in self.posizioni.values() if p['dir'] == "SELL" and "Core" in p['nome']]
                        
                        if core_long and core_short:
                            lvl_long = core_long[0]["entry"]
                            lvl_short = core_short[0]["entry"]
                        else:
                            # Fallback in caso di anomalie (non dovrebbe mai accadere se FASE 1 è completa)
                            lvl_long = lvl + (self.tp / 4.0)
                            lvl_short = lvl - (self.tp / 4.0)
                            
                        tp2_val = self.tp / 2.0
                        sat_long_lvl = lvl_long + tp2_val
                        sat_short_lvl = lvl_short - tp2_val
                        
                        self.wlog(f"Stop TICKET1 colpito a {lvl:.2f}. Inserisco Ordini SAT1 (OCO) a {sat_short_lvl:.2f} e {sat_long_lvl:.2f}. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                        self.stato = "FASE_2_SATELLITI"
                        tp2_val = self.tp / 2.0
                        self.aggiungi_pendente("ORDINE SAT1 OCO BUY", "BUY", self.s_mezzo, sat_long_lvl, "STOP", tp=sat_long_lvl+tp2_val, sl=sat_long_lvl-tp2_val)
                        self.aggiungi_pendente("ORDINE SAT1 OCO SELL", "SELL", self.s_mezzo, sat_short_lvl, "STOP", tp=sat_short_lvl-tp2_val, sl=sat_short_lvl+tp2_val)
                        
                        if abs(self.opp - self.tp/4.0) < 1e-4:
                            t2_dir = self.posizioni.get(obj_id, {}).get("dir", self.dir_base)
                            self.wlog(f"Posizione TICKET2 ({t2_dir}) [{self.s_mezzo}] a {lvl:.2f}")
                            tp4 = self.tp / 4.0
                            t2_tp = lvl + tp4 if t2_dir == "BUY" else lvl - tp4
                            self.aggiungi_posizione("TICKET2", t2_dir, self.s_mezzo, lvl, tp=t2_tp)
                            self.ticket2_active = True
                            self.ticket2_dir = t2_dir
                            self.ticket2_entry = lvl
                            self.ticket2_tp_lvl = t2_tp
                else:
                    if pos_nome == "SAT1" and tipo == "SL":
                        pnl_sat1 = pnl
                        pnl_sat2 = 0
                        pnl_og = 0
                        pnl_ol = 0
                        
                        self.svuota_pendenti()
                        for pid in list(self.posizioni.keys()):
                            n = self.posizioni[pid]["nome"]
                            if n == "SAT2":
                                pnl_sat2, _ = self.chiudi_posizione(pid, lvl, "Falso Innesco SAT1")
                            elif n == "OVERGAIN":
                                pnl_og, _ = self.chiudi_posizione(pid, lvl, "Falso Innesco SAT1")
                            elif n == "OVERLOSS":
                                pnl_ol, _ = self.chiudi_posizione(pid, lvl, "Falso Innesco SAT1")
                                
                        pnl_tot = pnl_sat1 + pnl_sat2 + pnl_og + pnl_ol
                        
                        dett_pnl = [f"SAT1: {pnl_sat1:+.2f}€"]
                        if pnl_sat2 != 0: dett_pnl.append(f"SAT2: {pnl_sat2:+.2f}€")
                        if pnl_og != 0: dett_pnl.append(f"OG: {pnl_og:+.2f}€")
                        if pnl_ol != 0: dett_pnl.append(f"OL: {pnl_ol:+.2f}€")
                        dettagli = " (" + " | ".join(dett_pnl) + ")"
                        
                        core_long = [p for p in self.posizioni.values() if p['dir'] == "BUY" and "Core" in p['nome']]
                        core_short = [p for p in self.posizioni.values() if p['dir'] == "SELL" and "Core" in p['nome']]
                        
                        if core_long and core_short:
                            lvl_long = core_long[0]["entry"]
                            lvl_short = core_short[0]["entry"]
                        else:
                            lvl_long = self.prezzo_base + self.opp if self.dir_base in ["SELL", "SHORT"] else self.prezzo_base
                            lvl_short = self.prezzo_base if self.dir_base in ["SELL", "SHORT"] else self.prezzo_base - self.opp
                            
                        tp2_val = self.tp / 2.0
                        sat_long_lvl = lvl_long + tp2_val
                        sat_short_lvl = lvl_short - tp2_val
                        
                        self.wlog(f"Stop SAT1 colpito a {lvl:.2f}. Reinserisco ENTRAMBI gli Ordini SAT1 (OCO) a {sat_short_lvl:.2f} e {sat_long_lvl:.2f}. [Parziale: {pnl_tot:+.2f} €] {dettagli} [Totale: {self.pnl_realizzato:+.2f} €]")
                        
                        self.aggiungi_pendente("ORDINE SAT1 OCO BUY", "BUY", self.s_mezzo, sat_long_lvl, "STOP", tp=sat_long_lvl+tp2_val, sl=sat_long_lvl-tp2_val)
                        self.aggiungi_pendente("ORDINE SAT1 OCO SELL", "SELL", self.s_mezzo, sat_short_lvl, "STOP", tp=sat_short_lvl-tp2_val, sl=sat_short_lvl+tp2_val)
                        self.ticket2_active = False
                        
                    else:
                        if pos_nome == "SAT1" and tipo == "TP":
                            self.svuota_pendenti()
                            pnl_sat1 = pnl
                            pnl_sat2 = 0.0
                            pnl_og = 0.0
                            pnl_ol = 0.0
                            pnl_t2 = 0.0
                            
                            for pid in list(self.posizioni.keys()):
                                n = self.posizioni[pid]["nome"]
                                if "Core" not in n:
                                    p, _ = self.chiudi_posizione(pid, lvl, "Avvio Fase 3")
                                    if n == "SAT2": pnl_sat2 += p
                                    elif n == "OVERGAIN": pnl_og += p
                                    elif n == "OVERLOSS": pnl_ol += p
                                    elif n == "TICKET2": pnl_t2 += p
                            
                            pnl_tot = pnl_sat1 + pnl_sat2 + pnl_og + pnl_ol + pnl_t2
                            
                            dett_pnl = [f"SAT1: {pnl_sat1:+.2f}€"]
                            if pnl_sat2 != 0: dett_pnl.append(f"SAT2: {pnl_sat2:+.2f}€")
                            if pnl_og != 0: dett_pnl.append(f"OG: {pnl_og:+.2f}€")
                            if pnl_ol != 0: dett_pnl.append(f"OL: {pnl_ol:+.2f}€")
                            if pnl_t2 != 0: dett_pnl.append(f"T2: {pnl_t2:+.2f}€")
                            dettagli_ibride = " (" + " | ".join(dett_pnl) + ")"
                            
                            sat_dir = self.posizioni[obj_id]["dir"] if obj_id in self.posizioni else ("BUY" if "BUY" in pos_nome else "SELL")
                            # Se non abbiamo sat_dir esatto dall'oggetto chiuso (già rimosso), lo deduciamo
                            # Ma obj_id non è in self.posizioni perché l'abbiamo già chiuso.
                            # Usiamo self.sat_price. In realtà SAT1 dir era self.sat2_dir opposto.
                            sat_dir = "BUY" if self.sat2_dir == "SELL" else "SELL"
                            
                            core_vincente = [p for p in self.posizioni.values() if p['dir'] == sat_dir and "Core" in p['nome']]
                            core_tossica = [p for p in self.posizioni.values() if p['dir'] != sat_dir and "Core" in p['nome']]
                            
                            pnl_c_vincente = 0.0
                            pnl_c_tossica = 0.0
                            
                            # Chiudiamo la core vincente al 100%
                            if core_vincente:
                                cv = core_vincente[0]
                                per_cv = next(pid for pid, p in self.posizioni.items() if p == cv)
                                pnl_c_vincente, _ = self.chiudi_posizione(per_cv, lvl, "Core Vincente 100%")
                                
                            # Chiudiamo il 50% della core tossica
                            if core_tossica:
                                ct = core_tossica[0]
                                per_ct = next(pid for pid, p in self.posizioni.items() if p == ct)
                                # Simuliamo chiusura parziale del 50% (s_mezzo)
                                entry_tossica = self.posizioni[per_ct]["entry"]
                                self.posizioni[per_ct]["size"] -= self.s_mezzo
                                if self.posizioni[per_ct]["dir"] == "BUY":
                                    pnl_c_tossica = (lvl - entry_tossica) * self.s_mezzo
                                else:
                                    pnl_c_tossica = (entry_tossica - lvl) * self.s_mezzo
                                pnl_c_tossica = round(pnl_c_tossica, 2)
                                self.pnl_realizzato += pnl_c_tossica
                                self.operazioni.append({"tick": self.tick_corrente, "prezzo": lvl, "tipo": "Chiusura Parziale Core Tossica (50%)", "size": self.s_mezzo, "pnl": pnl_c_tossica})
                                
                            pnl_tot_f3 = pnl_tot + pnl_c_vincente + pnl_c_tossica
                            self.wlog(f"TP Core [{sat_dir}] raggiunto a {lvl:.2f}. Avvio FASE 3. [Parziale: {pnl_tot_f3:+.2f} €] (Good: {pnl_c_vincente:+.2f}€ | 1/2 Bad: {pnl_c_tossica:+.2f}€){dettagli_ibride} [Totale: {self.pnl_realizzato:+.2f} €]")
                            
                            self.stato = "FASE_3"
                            self.fase3_step = 1
                            self.fase3_dir = sat_dir
                            self.fase3_base = lvl
                            
                            lim_core = lvl + (self.tp / 2.0) if sat_dir == "BUY" else lvl - (self.tp / 2.0)
                            stop_core = lvl - self.dts if sat_dir == "BUY" else lvl + self.dts
                            
                            self.aggiungi_posizione("Fase3_Core", sat_dir, self.s_core, lvl, tp=lim_core, sl=stop_core)
                            
                            dir_contro = "SELL" if sat_dir == "BUY" else "BUY"
                            lvl_last = lvl + (self.tp / 4.0) if sat_dir == "BUY" else lvl - (self.tp / 4.0)
                            self.aggiungi_pendente("ULTIMA", dir_contro, self.s_mezzo, lvl_last, "LIMIT", tp=lvl)
                            self.wlog(f"Entrata in Fase 3 a {lvl:.2f}. Inserita nuova core [{sat_dir} + {self.s_core}] e Ordine ULTIMA a [{lvl_last:.2f}].")
                            
                        else:
                            if pos_nome not in ["Fase3_Core", "ULTIMA"]:
                                self.wlog(f"{tipo} colpito su {pos_nome}. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                            
                            if pos_nome == "TICKET2" and tipo == "TP":
                                self.wlog(f"TICKET2 ha preso profitto! Re-inserisco Ordine a {self.ticket2_entry:.2f}")
                                self.aggiungi_pendente("TICKET2 PEND", self.ticket2_dir, self.s_mezzo, self.ticket2_entry, "LIMIT", tp=self.ticket2_tp_lvl)
                            elif pos_nome == "OVERGAIN" and tipo == "TP":
                                self.pendenti = {k: v for k, v in self.pendenti.items() if "OVERLOSS" not in v["nome"] and "OVERGAIN" not in v["nome"]}
                                tp4 = self.tp / 4.0
                                if self.sat2_dir == "SELL":
                                    l_og = self.sat_price + tp4
                                    l_ol = self.sat_price - tp4
                                else:
                                    l_og = self.sat_price - tp4
                                    l_ol = self.sat_price + tp4
                                self.wlog(f"OVERGAIN ha preso profitto! Reinserisco OG e OL a {l_og:.2f} e {l_ol:.2f}")
                                self.aggiungi_pendente("OVERGAIN", self.sat2_dir, self.s_mezzo, l_og, "LIMIT", tp=self.sat_price)
                                self.aggiungi_pendente("OVERLOSS", self.sat2_dir, self.s_quarto, l_ol, "STOP", sl=self.sat_price)
                            elif pos_nome == "OVERLOSS" and tipo == "SL":
                                self.pendenti = {k: v for k, v in self.pendenti.items() if "OVERLOSS" not in v["nome"] and "OVERGAIN" not in v["nome"]}
                                tp4 = self.tp / 4.0
                                if self.sat2_dir == "SELL":
                                    l_og = self.sat_price + tp4
                                    l_ol = self.sat_price - tp4
                                else:
                                    l_og = self.sat_price - tp4
                                    l_ol = self.sat_price + tp4
                                self.wlog(f"OVERLOSS colpito! Reinserisco OG e OL a {l_og:.2f} e {l_ol:.2f}")
                                self.aggiungi_pendente("OVERGAIN", self.sat2_dir, self.s_mezzo, l_og, "LIMIT", tp=self.sat_price)
                                self.aggiungi_pendente("OVERLOSS", self.sat2_dir, self.s_quarto, l_ol, "STOP", sl=self.sat_price)
                                
                            elif pos_nome == "ULTIMA" and tipo == "TP":
                                # SCENARIO A: ULTIMA prende profitto (Mungitura)
                                dir_contro = "SELL" if self.fase3_dir == "BUY" else "BUY"
                                s_last = self.s_core * 0.5 if self.fase3_step == 1 else (self.s_core * 0.15 if self.fase3_step == 2 else 0)
                                lvl_last = self.fase3_base + (self.tp / 4.0) if self.fase3_dir == "BUY" else self.fase3_base - (self.tp / 4.0)
                                
                                self.wlog(f"[ULTIMA] chiusa in profitto! [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]. Reinserisco ordine ULTIMA a {lvl_last:.2f}")
                                self.aggiungi_pendente("ULTIMA", dir_contro, s_last, lvl_last, "LIMIT", tp=self.fase3_base)
                                
                            elif pos_nome == "Fase3_Core" and tipo == "SL":
                                # SCENARIO C: Sconfitta Fase 3
                                self.wlog(f"Sconfitta in Fase 3 (SL colpito). Ciclo terminato in perdita. Macchinetta SPENTA. [Parziale: {pnl:+.2f} €] [Totale: {self.pnl_realizzato:+.2f} €]")
                                self.attivo = False
                                
                            elif pos_nome == "Fase3_Core" and tipo == "TP":
                                # SCENARIO B: Taglio Core Tossica
                                self.svuota_pendenti()
                                
                                # Dobbiamo chiudere la posizione ULTIMA che attualmente è in perdita
                                pnl_ultima = 0.0
                                for pid, pos in list(self.posizioni.items()):
                                    if pos["nome"] == "ULTIMA":
                                        p, _ = self.chiudi_posizione(pid, lvl, "Chiusura ULTIMA in perdita")
                                        pnl_ultima = p
                                        
                                core_tossica = [p for p in self.posizioni.values() if "Core" in p['nome']]
                                pnl_taglio = 0.0
                                if core_tossica:
                                    ct = core_tossica[0]
                                    per_ct = next(pid for pid, p in self.posizioni.items() if p == ct)
                                    entry_tossica = self.posizioni[per_ct]["entry"]
                                    
                                    s_cut_effettivo = self.s_core * 0.35 if self.fase3_step == 1 else self.s_core * 0.15
                                    self.posizioni[per_ct]["size"] -= s_cut_effettivo
                                    self.posizioni[per_ct]["size"] = round(self.posizioni[per_ct]["size"], 2)
                                    
                                    if self.posizioni[per_ct]["dir"] == "BUY":
                                        pnl_taglio = (lvl - entry_tossica) * s_cut_effettivo
                                    else:
                                        pnl_taglio = (entry_tossica - lvl) * s_cut_effettivo
                                    pnl_taglio = round(pnl_taglio, 2)
                                    self.pnl_realizzato += pnl_taglio
                                    self.operazioni.append({"tick": self.tick_corrente, "prezzo": lvl, "tipo": f"Taglio Core Tossica ({s_cut_effettivo})", "size": s_cut_effettivo, "pnl": pnl_taglio})
                                    
                                    if self.posizioni[per_ct]["size"] <= 0.01:
                                        self.chiudi_posizione(per_ct, lvl, "Pulizia Core")
                                
                                tot_step = pnl + pnl_ultima + pnl_taglio
                                
                                if self.fase3_step == 2:
                                    self.wlog(f"Fase 3 completata al {lvl:.2f}. Macchinetta SPENTA. [Parziale: {tot_step:+.2f} €] (Core: {pnl:+.2f}€ | ULTIMA: {pnl_ultima:+.2f}€ | Taglio: {pnl_taglio:+.2f}€) [Totale: {self.pnl_realizzato:+.2f} €]")
                                    self.attivo = False
                                else:
                                    self.fase3_step = 2
                                    self.fase3_base = lvl
                                    self.wlog(f"Taglio 35% effettuato. [Parziale: {tot_step:+.2f} €] (Core: {pnl:+.2f}€ | ULTIMA: {pnl_ultima:+.2f}€ | Taglio: {pnl_taglio:+.2f}€) [Totale: {self.pnl_realizzato:+.2f} €]")
                                    
                                    lim_core = lvl + (self.tp / 2.0) if self.fase3_dir == "BUY" else lvl - (self.tp / 2.0)
                                    stop_core = lvl - self.dts if self.fase3_dir == "BUY" else lvl + self.dts
                                    self.aggiungi_posizione("Fase3_Core", self.fase3_dir, self.s_core, lvl, tp=lim_core, sl=stop_core)
                                    
                                    dir_contro = "SELL" if self.fase3_dir == "BUY" else "BUY"
                                    lvl_last = lvl + (self.tp / 4.0) if self.fase3_dir == "BUY" else lvl - (self.tp / 4.0)
                                    self.aggiungi_pendente("ULTIMA", dir_contro, self.s_core * 0.15, lvl_last, "LIMIT", tp=lvl)
                                    
                                    dir_str = "LONG" if self.fase3_dir == "BUY" else "SHORT"
                                    self.wlog(f"Reinserisco Core [{dir_str}] a {lvl:.2f} e Ordine ULTIMA (15%) a {lvl_last:.2f}")

        self.pnl_storico.append({"tick": self.tick_corrente, "totale": self.pnl_realizzato})

def esegui_hedge_sincrono(file_path, strumento="Spot Gold", tp=50, opp=25, dts=50, size=1.0, modalita="Multiconto", direzione="LONG"):
    try:
        df = pd.read_csv(file_path)
        prezzi = df["Price"].tolist()
    except Exception as e:
        print(f"Errore caricamento CSV {file_path}: {e}")
        return None
        
    risultati = {
        "SIM_FIORDOK": {"pnl": [], "operazioni": [], "log_ws": []},
        "SIM_DANY": {"pnl": [], "operazioni": [], "log_ws": []}
    }
    
    if modalita == "Multiconto":
        sim_f = SimulatoreMatematico(tp, opp, dts, size, "LONG")
        sim_d = SimulatoreMatematico(tp, opp, dts, size, "SHORT")
        
        for idx, prezzo in enumerate(prezzi):
            if not sim_f.attivo and not sim_d.attivo:
                break
            if sim_f.attivo:
                sim_f.elabora_tick(idx, prezzo)
            if sim_d.attivo:
                sim_d.elabora_tick(idx, prezzo)
            
        ultimo_step = idx
        start_str_f = f"Start: {prezzi[0]:.2f} +{size} LONG"
        sim_f.log_ws.append(f"[STEP {ultimo_step}] Fine dati simulati - Prezzo: {prezzi[-1]:.2f} | {strumento} | {start_str_f}")
        sim_f.log_ws.append("-----------------------------------------------------------")
        sim_f.log_ws.append(f"[Totale: {sim_f.pnl_realizzato:+.2f} €]")
        
        start_str_d = f"Start: {prezzi[0]:.2f} -{size} SHORT"
        sim_d.log_ws.append(f"[STEP {ultimo_step}] Fine dati simulati - Prezzo: {prezzi[-1]:.2f} | {strumento} | {start_str_d}")
        sim_d.log_ws.append("-----------------------------------------------------------")
        sim_d.log_ws.append(f"[Totale: {sim_d.pnl_realizzato:+.2f} €]")
            
        risultati["SIM_FIORDOK"]["pnl"] = sim_f.pnl_storico
        risultati["SIM_FIORDOK"]["operazioni"] = sim_f.operazioni
        risultati["SIM_FIORDOK"]["log_ws"] = sim_f.log_ws
        
        risultati["SIM_DANY"]["pnl"] = sim_d.pnl_storico
        risultati["SIM_DANY"]["operazioni"] = sim_d.operazioni
        risultati["SIM_DANY"]["log_ws"] = sim_d.log_ws
    else:
        sim = SimulatoreMatematico(tp, opp, dts, size, direzione)
        for idx, prezzo in enumerate(prezzi):
            if not sim.attivo:
                break
            sim.elabora_tick(idx, prezzo)
            
        ultimo_step = idx
        segno_start = "+" if direzione in ["BUY", "LONG"] else "-"
        start_str = f"Start: {prezzi[0]:.2f} {segno_start}{size} {direzione}"
        sim.log_ws.append(f"[STEP {ultimo_step}] Fine dati simulati - Prezzo: {prezzi[-1]:.2f} | {strumento} | {start_str}")
        sim.log_ws.append("-----------------------------------------------------------")
        sim.log_ws.append(f"[Totale: {sim.pnl_realizzato:+.2f} €]")
            
        risultati["SIM_FIORDOK"]["pnl"] = sim.pnl_storico
        risultati["SIM_FIORDOK"]["operazioni"] = sim.operazioni
        risultati["SIM_FIORDOK"]["log_ws"] = sim.log_ws
        
    return {
        "prezzi": prezzi,
        "risultati": risultati,
        "modalita": modalita,
        "direzione": direzione
    }
