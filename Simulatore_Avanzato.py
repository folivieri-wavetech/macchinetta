import os
import pandas as pd
import numpy as np

ORIGINAL_DIR = os.getcwd()

def pulisci_nome_strumento(nome):
    return nome.replace("/", "").replace(" ", "").replace(".", "").upper()

def genera_prezzi(scenario, strumento_base_price=2400.0, tick_size=1.0, tic_totali=500, decimali=5):
    prices = []
    price = strumento_base_price
    prices.append(round(price, decimali))
    momentum = 0.0
    
    for step in range(1, tic_totali):
        if scenario == "LATERALE":
            # Processo di Mean Reversion (Ritorno verso la media) + Rumore di mercato
            distanza_media = strumento_base_price - price
            forza_ritorno = 0.05 * distanza_media
            rumore = np.random.normal(0, tick_size * 3)
            price += forza_ritorno + rumore
        elif scenario == "TREND_UP":
            momentum = 0.8 * momentum + np.random.normal(0, tick_size)
            variazione = abs(np.random.normal(0, tick_size * 2)) + (tick_size * 0.2) + momentum * 0.3
            price += variazione
        elif scenario == "TREND_DOWN":
            momentum = 0.8 * momentum + np.random.normal(0, tick_size)
            variazione = -abs(np.random.normal(0, tick_size * 2)) - (tick_size * 0.2) + momentum * 0.3
            price += variazione
        elif scenario == "CRASH":
            if 50 < step < 60:
                price -= tick_size * 20
            else:
                price += np.random.normal(0, tick_size)
        elif scenario == "RANDOM":
            # Micro-trend locali autoregressivi (Swings realistici) e colpi di volatilità
            momentum = 0.85 * momentum + np.random.normal(0, tick_size * 1.5)
            price += momentum + np.random.normal(0, tick_size * 1.5)
            
        prices.append(round(price, decimali))
    return prices

def genera_base_dati(strumento, scenario, partenza, tick_size, tic_totali, size, decimali=5):
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
    def __init__(self, tp, opp, dts, size, direzione_base, mult=1.0, valore_punto=1.0, valuta="EUR", molt_strum=1.0):
        self.mult = float(mult)
        self.molt_strum = float(molt_strum)
        self.dec = 2 if molt_strum == 1.0 else (3 if molt_strum == 0.01 else 5)
        self.valore_punto = float(valore_punto)
        self.valuta = valuta
        self.mock_rates = {
            "EUR": 1.0, "USD": 0.92, "JPY": 0.0061, "GBP": 1.17, 
            "CAD": 0.68, "CHF": 1.03, "NZD": 0.56, "AUD": 0.60
        }
        self.rate = self.mock_rates.get(self.valuta, 1.0)
        
        self.tp = float(tp) * molt_strum
        self.opp = float(opp) * molt_strum
        self.dts = float(dts) * molt_strum
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
        self.fase3_perc = None
        self.fase3_pnl = 0.0
        
        self.max_pnl_reached = 0.0
        self.max_drawdown = 0.0
        
        self.stats = {
            "Micro": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Flip": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Ticket1": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Ticket2": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "OverGain": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "OverLoss": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Ultima": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Assicurazione": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0}
        }

    def registra_stat(self, nome, pnl):
        if nome in self.stats:
            self.stats[nome]["pnl"] += pnl
            self.stats[nome]["totale"] += 1
            if pnl > 0:
                self.stats[nome]["profit"] += 1
            elif pnl < 0:
                self.stats[nome]["loss"] += 1

    def wlog(self, msg):
        msg = msg.replace("BUY", "LONG").replace("SELL", "SHORT")
        self.log_ws.append(f"[EVENTO]: {msg}")

    def wstep(self, prezzo):
        self.log_ws.append(f"[STEP {self.tick_corrente}] prezzo raggiunto: {prezzo:.{self.dec}f}")

    def genera_riepilogo(self):
        riepilogo = []
        riepilogo.append("-----------------------------------------------------------")
        riepilogo.append("📊 RIEPILOGO GENERALE:")
        tot_subtrading = 0.0
        tot_profit = 0
        tot_loss = 0
        for key in ["Micro", "Flip", "Ticket1", "Ticket2", "OverGain", "OverLoss", "Ultima"]:
            st = self.stats[key]
            tot_subtrading += st['pnl']
            tot_profit += st['profit']
            tot_loss += st['loss']
            
        tot_trades = tot_profit + tot_loss
        perc_pos = (tot_profit / tot_trades * 100) if tot_trades > 0 else 0
        riga_totale = f"Totale Sottotrading [{tot_subtrading:+.{self.dec}f} €] - Profit: {tot_profit} - Loss: {tot_loss} [{perc_pos:.0f}%]"
        
        for key in ["Micro", "Flip", "Ticket1", "Ticket2", "OverGain", "OverLoss", "Ultima"]:
            st = self.stats[key]
            val = st['pnl']
            if val > 0:
                color = "#2ECC71" # Verde Smeraldo
            elif val < 0:
                color = "#FA8072" # Rosso Salmone
            else:
                color = "#A9A9A9" # Grigio scuro
            riga = f"{key} [{val:+.{self.dec}f} €] Totale: {st['totale']} - Profit: {st['profit']} - Loss: {st['loss']}"
            riepilogo.append(f"<span style='color: {color};'>{riga}</span>")
            
        riepilogo.append(f"<span style='color: #FFD700;'><b>{riga_totale}</b></span>")
        
        st_ass = self.stats["Assicurazione"]
        riga_ass = f"Assicurazione [{st_ass['pnl']:+.0f} €]"
        riepilogo.append(f"<span style='color: #FFD700;'>{riga_ass}</span>")
        
        val_f3 = self.fase3_pnl
        if val_f3 > 0:
            color_f3 = "#2ECC71"
        elif val_f3 < 0:
            color_f3 = "#FA8072"
        else:
            color_f3 = "#A9A9A9"
            
        if self.fase3_perc:
            riga_f3 = f"FASE3 [{val_f3:+.{self.dec}f} €] [{self.fase3_perc}]"
        else:
            riga_f3 = f"FASE3 [{val_f3:+.{self.dec}f} €] [Mai Avviata]"
            
        riepilogo.append(f"<span style='color: {color_f3};'>{riga_f3}</span>")
        
        return riepilogo

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
                pts = ((prezzo_chiusura - pos["entry"]) / self.molt_strum) * self.mult
            else:
                pts = ((pos["entry"] - prezzo_chiusura) / self.molt_strum) * self.mult
            
            pnl_valuta = pts * pos["size"] * self.valore_punto
            pnl = pnl_valuta * self.rate
            
            if self.valuta != "EUR":
                pnl = float(int(pnl))
            else:
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
        self.wlog(f"Core [{self.dir_base}] [{segno}{self.s_core}] a <u><b>{self.prezzo_base:.{self.dec}f}</b></u>")
        
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
                        self.wlog(f"Chiudo {nome_pos} a mercato. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")
                self.stato = "FASE_3"
                self.wlog("FASE 3: Il Core e' l'unica posizione rimasta.")
                
            elif tipo == "PEND":
                if obj_id not in self.pendenti: continue
                pend = self.pendenti.pop(obj_id)
                
                if self.stato == "FASE_1":
                    if "ORDINE MICRO" in pend["nome"]:
                        segno = "+" if pend['dir'] == "BUY" else "-"
                        self.wlog(f"Posizione MICRO ({pend['dir']}) [{segno}{pend['size']}] a {lvl:.{self.dec}f}")
                        self.aggiungi_posizione("MICRO", pend["dir"], pend["size"], lvl, tp=pend["tp"], sl=pend["sl"])
                        
                    elif "ORDINE CORE" in pend["nome"]:
                        # Chiude Assicurazione
                        pnl_ass = 0.0
                        for pid in list(self.posizioni.keys()):
                            if "Assicurazione" in self.posizioni[pid]["nome"]:
                                pnl_ass, _ = self.chiudi_posizione(pid, lvl, "Take Profit")
                                self.registra_stat("Assicurazione", pnl_ass)
                        
                        dir_str = "LONG" if pend["dir"] in ["BUY", "LONG"] else "SHORT"
                        segno = "+" if dir_str == "LONG" else "-"
                        self.wlog(f"Core [{dir_str}] [{segno}{pend['size']}] a <u><b>{lvl:.{self.dec}f}</b></u>. Chiusura Assicurazione. [Parziale: {pnl_ass:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")
                        
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
                        segno = "+" if t1_dir == "BUY" else "-"
                        self.wlog(f"Entrata in Fase 2 - TICKET1 {t1_dir} [{segno}{self.s_mezzo}] a {lvl:.{self.dec}f}")
                        
                elif self.stato == "FASE_2_SATELLITI":
                    if "SAT1" in pend["nome"]:
                        self.svuota_pendenti() # Remove the other OCO
                        
                        for pid in list(self.posizioni.keys()):
                            if self.posizioni[pid]["nome"] == "TICKET2":
                                pnl, _ = self.chiudi_posizione(pid, lvl, "Loss OCO")
                                self.registra_stat("Ticket2", pnl)
                                self.ticket2_active = False
                                self.wlog(f"TICKET2 chiuso a mercato (Loss) a {lvl:.{self.dec}f}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")

                        nome_pulito = pend['nome'].replace("ORDINE ", "")
                        segno = "+" if pend['dir'] == "BUY" else "-"
                        self.wlog(f"Posizione {nome_pulito} [{segno}{pend['size']}] a {lvl:.{self.dec}f}")
                        
                        self.aggiungi_posizione("SAT1", pend["dir"], pend["size"], lvl, tp=pend["tp"], sl=pend["sl"])
                        sat2_dir = "SELL" if pend["dir"] == "BUY" else "BUY"
                        self.aggiungi_posizione("SAT2", sat2_dir, self.s_quarto, lvl)
                        segno = "+" if sat2_dir == "BUY" else "-"
                        self.wlog(f"Posizione SAT2 {sat2_dir} [{segno}{self.s_quarto}] a {lvl:.{self.dec}f}")
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
                        segno = "+" if pend['dir'] == "BUY" else "-"
                        self.wlog(f"Posizione OVERGAIN ({pend['dir']}) [{segno}{pend['size']}] a {lvl:.{self.dec}f}")
                        self.aggiungi_posizione("OVERGAIN", pend["dir"], pend["size"], lvl, tp=pend["tp"])
                        
                    elif pend["nome"] == "OVERLOSS":
                        segno = "+" if pend['dir'] == "BUY" else "-"
                        self.wlog(f"Posizione OVERLOSS ({pend['dir']}) [{segno}{pend['size']}] a {lvl:.{self.dec}f}")
                        self.aggiungi_posizione("OVERLOSS", pend["dir"], pend["size"], lvl, sl=pend["sl"])
                            
                    elif "TICKET2" in pend["nome"]:
                        segno = "+" if pend['dir'] == "BUY" else "-"
                        self.wlog(f"Posizione TICKET2 ({pend['dir']}) [{segno}{pend['size']}] a {lvl:.{self.dec}f}")
                        self.aggiungi_posizione("TICKET2", pend["dir"], pend["size"], lvl, tp=pend["tp"])
                        
                elif self.stato == "FASE_3":
                    if pend["nome"] == "ULTIMA":
                        segno = "+" if pend['dir'] == "BUY" else "-"
                        self.wlog(f"Posizione ULTIMA ({pend['dir']}) [{segno}{pend['size']}] a {lvl:.{self.dec}f}")
                        self.aggiungi_posizione("ULTIMA", pend["dir"], pend["size"], lvl, tp=pend["tp"])
                        
            elif tipo in ["TP", "SL"]:
                if obj_id not in self.posizioni: continue
                pos_dir_pre_chiusura = self.posizioni[obj_id]["dir"]
                pnl, pos_nome = self.chiudi_posizione(obj_id, lvl, "Take Profit" if tipo == "TP" else "Stop Loss")
                
                if pos_nome == "MICRO":
                    if tipo == "TP":
                        self.registra_stat("Micro", pnl)
                        self.wlog(f"MICRO a target a {lvl:.{self.dec}f}. Reinserisco ordine. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")
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
                                self.registra_stat("Assicurazione", a_pnl)
                            else:
                                self.chiudi_posizione(pid, lvl, "FLIP")
                        
                        pnl_tot = pnl_core + pnl_ass + pnl_micro
                        self.registra_stat("Flip", pnl_tot)
                        self.wlog(f"Stop MICRO colpito a {lvl:.{self.dec}f}. Chiusura posizioni *** FLIP. [Parziale: {pnl_tot:+.0f} €] (Core: {pnl_core:+.0f}€ | Ass: {pnl_ass:+.0f}€ | Micro: {pnl_micro:+.0f}€) [Totale: {self.pnl_realizzato:+.0f} €]")
                        self.svuota_pendenti()
                        self.dir_base = self.dir_contro
                        self.dir_contro = "SELL" if self.dir_base == "BUY" else "BUY"
                        self.avvia_fase1(lvl)

                elif pos_nome == "TICKET1":
                    if tipo == "TP":
                        self.registra_stat("Ticket1", pnl)
                        t1_dir = "SELL" if pos_dir_pre_chiusura == "BUY" else "BUY"
                        dir_str = "SHORT" if t1_dir == "SELL" else "LONG"
                        self.wlog(f"TICKET1 a target a {lvl:.{self.dec}f}! Ping-Pong: Rigirato in {dir_str}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")
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
                        
                        self.registra_stat("Ticket1", pnl)
                        self.wlog(f"Stop TICKET1 colpito a {lvl:.{self.dec}f}. Inserisco Ordini SAT1 (OCO) a {sat_short_lvl:.{self.dec}f} e {sat_long_lvl:.{self.dec}f}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")
                        self.stato = "FASE_2_SATELLITI"
                        tp2_val = self.tp / 2.0
                        self.aggiungi_pendente("ORDINE SAT1 OCO BUY", "BUY", self.s_mezzo, sat_long_lvl, "STOP", tp=sat_long_lvl+tp2_val, sl=sat_long_lvl-tp2_val)
                        self.aggiungi_pendente("ORDINE SAT1 OCO SELL", "SELL", self.s_mezzo, sat_short_lvl, "STOP", tp=sat_short_lvl-tp2_val, sl=sat_short_lvl+tp2_val)
                        
                        if abs(self.opp - self.tp/4.0) < 1e-4:
                            t2_dir = self.posizioni.get(obj_id, {}).get("dir", self.dir_base)
                            segno = "+" if t2_dir == "BUY" else "-"
                            self.wlog(f"Posizione TICKET2 ({t2_dir}) [{segno}{self.s_mezzo}] a {lvl:.{self.dec}f}")
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
                        self.fase3_pnl += pnl_tot
                        
                        dett_pnl = [f"SAT1: {pnl_sat1:+.0f}€"]
                        if pnl_sat2 != 0: dett_pnl.append(f"SAT2: {pnl_sat2:+.0f}€")
                        if pnl_og != 0: dett_pnl.append(f"OG: {pnl_og:+.0f}€")
                        if pnl_ol != 0: dett_pnl.append(f"OL: {pnl_ol:+.0f}€")
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
                        
                        self.wlog(f"Stop SAT1 colpito a {lvl:.{self.dec}f}. Reinserisco ENTRAMBI gli Ordini SAT1 (OCO) a {sat_short_lvl:.{self.dec}f} e {sat_long_lvl:.{self.dec}f}. [Parziale: {pnl_tot:+.0f} €] {dettagli} [Totale: {self.pnl_realizzato:+.0f} €]")
                        
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
                            self.fase3_pnl += pnl_tot
                            
                            dett_pnl = [f"SAT1: {pnl_sat1:+.0f}€"]
                            if pnl_sat2 != 0: dett_pnl.append(f"SAT2: {pnl_sat2:+.0f}€")
                            if pnl_og != 0: dett_pnl.append(f"OG: {pnl_og:+.0f}€")
                            if pnl_ol != 0: dett_pnl.append(f"OL: {pnl_ol:+.0f}€")
                            if pnl_t2 != 0: dett_pnl.append(f"T2: {pnl_t2:+.0f}€")
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
                                    pts = ((lvl - entry_tossica) / self.molt_strum) * self.mult
                                else:
                                    pts = ((entry_tossica - lvl) / self.molt_strum) * self.mult
                                
                                pnl_valuta = pts * self.s_mezzo * self.valore_punto
                                pnl_c_tossica = pnl_valuta * self.rate
                                if self.valuta != "EUR":
                                    pnl_c_tossica = float(int(pnl_c_tossica))
                                else:
                                    pnl_c_tossica = round(pnl_c_tossica, 2)
                                
                                self.pnl_realizzato += pnl_c_tossica
                                self.operazioni.append({"tick": self.tick_corrente, "prezzo": lvl, "tipo": "Chiusura Parziale Core Tossica (50%)", "size": self.s_mezzo, "pnl": pnl_c_tossica})
                                
                            pnl_tot_f3 = pnl_tot + pnl_c_vincente + pnl_c_tossica
                            self.fase3_pnl = pnl_tot_f3
                            
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
                            
                            segno = "+" if sat_dir in ["BUY", "LONG"] else "-"
                            segno_u = "+" if dir_contro in ["BUY", "LONG"] else "-"
                            self.wlog(f"TP Core [{sat_dir}] raggiunto a {lvl:.{self.dec}f}. Avvio FASE 3. Taglio effettuato 50%. [Parziale: {pnl_tot_f3:+.0f} €] (Good: {pnl_c_vincente:+.0f}€ | 1/2 Bad: {pnl_c_tossica:+.0f}€){dettagli_ibride} [Totale: {self.pnl_realizzato:+.0f} €] Inserita nuova Core [{sat_dir}] [{segno}{self.s_core}] e Ordine ULTIMA ({dir_contro}) [{segno_u}{self.s_mezzo}] a {lvl_last:.{self.dec}f}")
                            
                        else:
                            if pos_nome == "TICKET2" and tipo == "TP":
                                self.registra_stat("Ticket2", pnl)
                                self.wlog(f"{tipo} colpito su {pos_nome} a {lvl:.{self.dec}f}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €] Re-inserisco Ordine ({self.ticket2_dir}) a {self.ticket2_entry:.{self.dec}f}")
                                self.aggiungi_pendente("TICKET2 PEND", self.ticket2_dir, self.s_mezzo, self.ticket2_entry, "LIMIT", tp=self.ticket2_tp_lvl)
                            elif pos_nome == "OVERGAIN" and tipo == "TP":
                                self.registra_stat("OverGain", pnl)
                                self.pendenti = {k: v for k, v in self.pendenti.items() if "OVERLOSS" not in v["nome"] and "OVERGAIN" not in v["nome"]}
                                tp4 = self.tp / 4.0
                                if self.sat2_dir == "SELL":
                                    l_og = self.sat_price + tp4
                                    l_ol = self.sat_price - tp4
                                else:
                                    l_og = self.sat_price - tp4
                                    l_ol = self.sat_price + tp4
                                self.wlog(f"{tipo} colpito su {pos_nome} a {lvl:.{self.dec}f}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €] Reinserisco OG e OL ({self.sat2_dir}) a {l_og:.{self.dec}f} e {l_ol:.{self.dec}f}")
                                self.aggiungi_pendente("OVERGAIN", self.sat2_dir, self.s_mezzo, l_og, "LIMIT", tp=self.sat_price)
                                self.aggiungi_pendente("OVERLOSS", self.sat2_dir, self.s_quarto, l_ol, "STOP", sl=self.sat_price)
                            elif pos_nome == "OVERLOSS" and tipo == "SL":
                                self.registra_stat("OverLoss", pnl)
                                self.pendenti = {k: v for k, v in self.pendenti.items() if "OVERLOSS" not in v["nome"] and "OVERGAIN" not in v["nome"]}
                                tp4 = self.tp / 4.0
                                if self.sat2_dir == "SELL":
                                    l_og = self.sat_price + tp4
                                    l_ol = self.sat_price - tp4
                                else:
                                    l_og = self.sat_price - tp4
                                    l_ol = self.sat_price + tp4
                                self.wlog(f"{tipo} colpito su {pos_nome} a {lvl:.{self.dec}f}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €] Reinserisco OG e OL ({self.sat2_dir}) a {l_og:.{self.dec}f} e {l_ol:.{self.dec}f}")
                                self.aggiungi_pendente("OVERGAIN", self.sat2_dir, self.s_mezzo, l_og, "LIMIT", tp=self.sat_price)
                                self.aggiungi_pendente("OVERLOSS", self.sat2_dir, self.s_quarto, l_ol, "STOP", sl=self.sat_price)
                            elif pos_nome == "ULTIMA" and tipo == "TP":
                                # SCENARIO A: ULTIMA prende profitto (Mungitura)
                                self.registra_stat("Ultima", pnl)
                                dir_contro = "SELL" if self.fase3_dir == "BUY" else "BUY"
                                s_last = self.s_core * 0.5 if self.fase3_step == 1 else (self.s_core * 0.15 if self.fase3_step == 2 else 0)
                                lvl_last = self.fase3_base + (self.tp / 4.0) if self.fase3_dir == "BUY" else self.fase3_base - (self.tp / 4.0)
                                
                                self.wlog(f"[ULTIMA] chiusa in profitto! [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]. Reinserisco ordine ULTIMA ({dir_contro}) a {lvl_last:.{self.dec}f}")
                                self.aggiungi_pendente("ULTIMA", dir_contro, s_last, lvl_last, "LIMIT", tp=self.fase3_base)
                                
                            elif pos_nome == "Fase3_Core" and tipo == "SL":
                                # SCENARIO C: Uscita da Fase 3 (SL nuova Core)
                                self.svuota_pendenti()
                                pnl_f3_core = pnl
                                pnl_ultima = 0.0
                                pnl_bad_core = 0.0
                                
                                for pid, pos in list(self.posizioni.items()):
                                    if pos["nome"] == "ULTIMA":
                                        p, _ = self.chiudi_posizione(pid, lvl, "Chiusura ULTIMA per Uscita C")
                                        pnl_ultima = p
                                        self.registra_stat("Ultima", p)
                                    elif "Core" in pos["nome"]:
                                        p, _ = self.chiudi_posizione(pid, lvl, "Chiusura Bad Core per Uscita C")
                                        pnl_bad_core = p
                                        
                                pnl_tot_step = pnl_f3_core + pnl_ultima + pnl_bad_core
                                self.fase3_perc = "50%" if self.fase3_step == 1 else "85%"
                                self.fase3_pnl += pnl_tot_step
                                self.wlog(f"USCITA FASE 3. Ciclo terminato. Macchinetta Spenta. [Parziale: {pnl_tot_step:+.0f} €] (Nuova Core: {pnl_f3_core:+.0f}€ | Bad Core: {pnl_bad_core:+.0f}€ | ULTIMA: {pnl_ultima:+.0f}€) [Totale: {self.pnl_realizzato:+.0f} €]")
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
                                        self.registra_stat("Ultima", p)
                                        
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
                                        pts = ((lvl - entry_tossica) / self.molt_strum) * self.mult
                                    else:
                                        pts = ((entry_tossica - lvl) / self.molt_strum) * self.mult
                                        
                                    pnl_valuta = pts * s_cut_effettivo * self.valore_punto
                                    pnl_taglio = pnl_valuta * self.rate
                                    if self.valuta != "EUR":
                                        pnl_taglio = float(int(pnl_taglio))
                                    else:
                                        pnl_taglio = round(pnl_taglio, 2)
                                        
                                    self.pnl_realizzato += pnl_taglio
                                    self.operazioni.append({"tick": self.tick_corrente, "prezzo": lvl, "tipo": f"Taglio Core Tossica ({s_cut_effettivo})", "size": s_cut_effettivo, "pnl": pnl_taglio})
                                    
                                    if self.posizioni[per_ct]["size"] <= 0.01:
                                        self.chiudi_posizione(per_ct, lvl, "Pulizia Core")
                                
                                tot_step = pnl + pnl_ultima + pnl_taglio
                                self.fase3_pnl += tot_step
                                
                                if self.fase3_step == 2:
                                    self.fase3_perc = "100%"
                                    self.wlog(f"Fase 3 completata al {lvl:.{self.dec}f}. Macchinetta SPENTA. [Parziale: {tot_step:+.0f} €] (Core: {pnl:+.0f}€ | ULTIMA: {pnl_ultima:+.0f}€ | Taglio: {pnl_taglio:+.0f}€) [Totale: {self.pnl_realizzato:+.0f} €]")
                                    self.attivo = False
                                else:
                                    self.fase3_step = 2
                                    self.fase3_base = lvl
                                    
                                    lim_core = lvl + (self.tp / 2.0) if self.fase3_dir == "BUY" else lvl - (self.tp / 2.0)
                                    stop_core = lvl - self.dts if self.fase3_dir == "BUY" else lvl + self.dts
                                    self.aggiungi_posizione("Fase3_Core", self.fase3_dir, self.s_core, lvl, tp=lim_core, sl=stop_core)
                                    
                                    dir_contro = "SELL" if self.fase3_dir == "BUY" else "BUY"
                                    lvl_last = lvl + (self.tp / 4.0) if self.fase3_dir == "BUY" else lvl - (self.tp / 4.0)
                                    s_ultima = self.s_core * 0.15
                                    self.aggiungi_pendente("ULTIMA", dir_contro, s_ultima, lvl_last, "LIMIT", tp=lvl)
                                    
                                    dir_str = "LONG" if self.fase3_dir == "BUY" else "SHORT"
                                    segno = "+" if self.fase3_dir in ["BUY", "LONG"] else "-"
                                    segno_u = "+" if dir_contro in ["BUY", "LONG"] else "-"
                                    self.wlog(f"Taglio 35% effettuato. [Parziale: {tot_step:+.0f} €] (Core: {pnl:+.0f}€ | ULTIMA: {pnl_ultima:+.0f}€ | Taglio: {pnl_taglio:+.0f}€) [Totale: {self.pnl_realizzato:+.0f} €] Reinserisco Core [{dir_str}] [{segno}{self.s_core}] a {lvl:.{self.dec}f} e Ordine ULTIMA ({dir_contro}) [{segno_u}{s_ultima}] a {lvl_last:.{self.dec}f}")
                            else:
                                if pos_nome not in ["Fase3_Core", "ULTIMA"]:
                                    self.wlog(f"{tipo} colpito su {pos_nome} a {lvl:.{self.dec}f}. [Parziale: {pnl:+.0f} €] [Totale: {self.pnl_realizzato:+.0f} €]")

        if self.pnl_realizzato > self.max_pnl_reached:
            self.max_pnl_reached = self.pnl_realizzato
            
        current_drawdown = self.max_pnl_reached - self.pnl_realizzato
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

        self.pnl_storico.append({"tick": self.tick_corrente, "totale": self.pnl_realizzato})

def esegui_hedge_sincrono(file_path, strumento="Spot Gold", tp=50, opp=25, dts=50, size=1.0, modalita="Multiconto", direzione="LONG", mult=1.0, valore_punto=1.0, valuta="EUR", molt_strum=1.0):
    dec = 2 if molt_strum == 1.0 else (3 if molt_strum == 0.01 else 5)
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
        sim_f = SimulatoreMatematico(tp, opp, dts, size, "LONG", mult, valore_punto, valuta, molt_strum=molt_strum)
        sim_d = SimulatoreMatematico(tp, opp, dts, size, "SHORT", mult, valore_punto, valuta, molt_strum=molt_strum)
        
        for idx, prezzo in enumerate(prezzi):
            if not sim_f.attivo and not sim_d.attivo:
                break
            if sim_f.attivo:
                sim_f.elabora_tick(idx, prezzo)
            if sim_d.attivo:
                sim_d.elabora_tick(idx, prezzo)
            
        ultimo_step = idx
        start_str_f = f"Start: {prezzi[0]:.{dec}f} +{size} LONG"
        sim_f.log_ws.append(f"[STEP {ultimo_step}] Fine dati simulati - Prezzo: {prezzi[ultimo_step]:.{dec}f} | {strumento} | {start_str_f}")
        sim_f.log_ws.append("-----------------------------------------------------------")
        sim_f.log_ws.extend(sim_f.genera_riepilogo())
        sim_f.log_ws.insert(0, f"[Totale: {sim_f.pnl_realizzato:+.0f} €]")
        
        start_str_d = f"Start: {prezzi[0]:.{dec}f} -{size} SHORT"
        sim_d.log_ws.append(f"[STEP {ultimo_step}] Fine dati simulati - Prezzo: {prezzi[ultimo_step]:.{dec}f} | {strumento} | {start_str_d}")
        sim_d.log_ws.append("-----------------------------------------------------------")
        sim_d.log_ws.extend(sim_d.genera_riepilogo())
        sim_d.log_ws.insert(0, f"[Totale: {sim_d.pnl_realizzato:+.0f} €]")
            
        risultati["SIM_FIORDOK"]["pnl"] = sim_f.pnl_storico
        risultati["SIM_FIORDOK"]["operazioni"] = sim_f.operazioni
        risultati["SIM_FIORDOK"]["log_ws"] = sim_f.log_ws
        
        risultati["SIM_DANY"]["pnl"] = sim_d.pnl_storico
        risultati["SIM_DANY"]["operazioni"] = sim_d.operazioni
        risultati["SIM_DANY"]["log_ws"] = sim_d.log_ws
    else:
        sim = SimulatoreMatematico(tp, opp, dts, size, direzione, mult, valore_punto, valuta, molt_strum=molt_strum)
        for idx, prezzo in enumerate(prezzi):
            if not sim.attivo:
                break
            sim.elabora_tick(idx, prezzo)
            
        ultimo_step = idx
        segno_start = "+" if direzione in ["BUY", "LONG"] else "-"
        start_str = f"Start: {prezzi[0]:.{dec}f} {segno_start}{size} {direzione}"
        sim.log_ws.append(f"[STEP {ultimo_step}] Fine dati simulati - Prezzo: {prezzi[ultimo_step]:.{dec}f} | {strumento} | {start_str}")
        sim.log_ws.append("-----------------------------------------------------------")
        sim.log_ws.extend(sim.genera_riepilogo())
        sim.log_ws.insert(0, f"[Totale: {sim.pnl_realizzato:+.0f} €]")
            
        risultati["SIM_FIORDOK"]["pnl"] = sim.pnl_storico
        risultati["SIM_FIORDOK"]["operazioni"] = sim.operazioni
        risultati["SIM_FIORDOK"]["log_ws"] = sim.log_ws
        
    return {
        "prezzi": prezzi,
        "risultati": risultati,
        "modalita": modalita,
        "direzione": direzione
    }

def esegui_ottimizzazione_griglia(file_paths, tp_range, dts_range, size=10.0, mult=1.0, valore_punto=1.0, valuta="EUR", molt_strum=1.0, save_median=False):
    import numpy as np
    
    tp_values = np.arange(tp_range['min'], tp_range['max'] + tp_range['step'], tp_range['step']).tolist()
    dts_values = np.arange(dts_range['min'], dts_range['max'] + dts_range['step'], dts_range['step']).tolist()
    
    risultati_ottimizzazione = []
    
    for tp in tp_values:
        for dts in dts_values:
            opp = tp / 4.0
            
            pnl_long_totale = 0.0
            pnl_short_totale = 0.0
            max_dd_long_avg = 0.0
            max_dd_short_avg = 0.0
            win_count = 0
            loss_count = 0
            
            file_results = []
            
            for file_path in file_paths:
                try:
                    df = pd.read_csv(file_path)
                    prezzi = df["Price"].tolist()
                except Exception as e:
                    print(f"Errore caricamento CSV {file_path}: {e}")
                    continue
                
                sim_f = SimulatoreMatematico(tp, opp, dts, size, "LONG", mult, valore_punto, valuta, molt_strum=molt_strum)
                sim_d = SimulatoreMatematico(tp, opp, dts, size, "SHORT", mult, valore_punto, valuta, molt_strum=molt_strum)
                
                # Disabilita i log_ws per massimizzare le performance ed evitare overflow memoria
                sim_f.log_ws = []
                sim_d.log_ws = []
                sim_f.wlog = lambda msg: None
                sim_f.wstep = lambda msg: None
                sim_d.wlog = lambda msg: None
                sim_d.wstep = lambda msg: None
                
                for idx, prezzo in enumerate(prezzi):
                    if not sim_f.attivo and not sim_d.attivo:
                        break
                    if sim_f.attivo:
                        sim_f.elabora_tick(idx, prezzo)
                    if sim_d.attivo:
                        sim_d.elabora_tick(idx, prezzo)
                        
                pnl_file = sim_f.pnl_realizzato + sim_d.pnl_realizzato
                file_results.append((file_path, pnl_file))
                        
                pnl_long_totale += sim_f.pnl_realizzato
                pnl_short_totale += sim_d.pnl_realizzato
                max_dd_long_avg += sim_f.max_drawdown
                max_dd_short_avg += sim_d.max_drawdown
                
                if pnl_file >= 0:
                    win_count += 1
                else:
                    loss_count += 1
                    
            n_files = len(file_paths)
            if n_files > 0:
                pnl_long_medio = pnl_long_totale / n_files
                pnl_short_medio = pnl_short_totale / n_files
                pnl_totale_medio = pnl_long_medio + pnl_short_medio
                max_dd_long_avg /= n_files
                max_dd_short_avg /= n_files
                
                win_rate = (win_count / n_files) * 100
                
                # Trova il file mediano
                if file_results:
                    best_file = min(file_results, key=lambda x: abs(x[1] - pnl_totale_medio))[0]
                    saved_path = ""
                    if save_median:
                        import shutil, os
                        salv_dir = os.path.join(os.path.dirname(best_file), "..", "salvataggi", "csv_mediani")
                        os.makedirs(salv_dir, exist_ok=True)
                        safe_name = f"Mediano_TP{int(tp)}_DTS{int(dts)}.csv"
                        new_path = os.path.join(salv_dir, safe_name)
                        shutil.copy2(best_file, new_path)
                        saved_path = new_path
                else:
                    saved_path = ""
                
                risultati_ottimizzazione.append({
                    "TP": tp,
                    "OPP": opp,
                    "DTS": dts,
                    "PNL Long": round(pnl_long_medio, 2),
                    "PNL Short": round(pnl_short_medio, 2),
                    "PNL Totale": round(pnl_totale_medio, 2),
                    "Max Drawdown": round(max_dd_long_avg + max_dd_short_avg, 2),
                    "Win Rate %": round(win_rate, 2),
                    "Median_CSV": saved_path
                })
                
    df_risultati = pd.DataFrame(risultati_ottimizzazione)
    return df_risultati
