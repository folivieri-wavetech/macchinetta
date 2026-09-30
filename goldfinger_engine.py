import os
import sys
import time
import json
import requests
import datetime
from dotenv import dotenv_values

try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTO_DIR = os.path.join(ROOT_DIR, "DANY_REALE")
if not os.path.exists(CONTO_DIR):
    CONTO_DIR = "/data/DANY_REALE"

ENV_FILE = os.path.join(CONTO_DIR, ".env")
TOKEN_FILE = os.path.join(CONTO_DIR, "token_ig.json")
STATO_FILE = os.path.join(CONTO_DIR, "stato_sistema.json")
CONFIG_GOLDFINGER_FILE = os.path.join(CONTO_DIR, "config_goldfinger.json")
STATO_GOLDFINGER_FILE = os.path.join(CONTO_DIR, "stato_goldfinger.json")
LOG_FILE = os.path.join(CONTO_DIR, "goldfinger.log")

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
VALUTA_GOLD = "EUR"
BASE_URL = "https://api.ig.com/gateway/deal"

def print_log(messaggio):
    ora = now_it().strftime("%d/%m %H:%M:%S")
    riga = f"[{ora}] [GOLDFINGER] {messaggio}"
    print(riga)
    try:
        righe = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                righe = f.readlines()
        righe.append(riga + "\n")
        if len(righe) > 2000:
            righe = righe[-2000:]
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(righe)
    except Exception:
        pass

def invia_notifica(titolo, messaggio, tags="trophy"):
    try:
        cfg = dotenv_values(ENV_FILE)
        topic = cfg.get("NTFY_TOPIC")
        if topic:
            ora = now_it().strftime("%H:%M:%S")
            body = f"[{ora}] {messaggio}"
            headers = {"Title": f"[GOLDFINGER] {titolo}".encode('utf-8'), "Tags": tags}
            requests.post(f"https://ntfy.sh/{topic}", data=body.encode('utf-8'), headers=headers, timeout=5)
    except Exception:
        pass

class GoldfingerEngine:
    def __init__(self):
        self.cfg = dotenv_values(ENV_FILE)
        self.api_key = self.cfg.get("IG_API_KEY")
        self.target_account_id = self.cfg.get("IG_ACCOUNT_ID", "DUACG").strip()
        self.ultimo_tentativo_ordine = 0
        self.ultimo_fallback_markets = 0
        self.cache_prezzo_live = (None, None)
        self.carica_stato()

    def carica_token(self):
        if not os.path.exists(TOKEN_FILE):
            return None, None
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                return d.get("CST"), d.get("X-SECURITY-TOKEN")
        except Exception:
            return None, None

    def get_auth_headers(self, version="1"):
        cst, xst = self.carica_token()
        return {
            "X-IG-API-KEY": self.api_key,
            "CST": cst,
            "X-SECURITY-TOKEN": xst,
            "Version": str(version),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def carica_config(self):
        if not os.path.exists(CONFIG_GOLDFINGER_FILE):
            return {}
        try:
            with open(CONFIG_GOLDFINGER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def carica_stato(self):
        if os.path.exists(STATO_GOLDFINGER_FILE):
            try:
                with open(STATO_GOLDFINGER_FILE, "r", encoding="utf-8") as f:
                    self.stato = json.load(f)
                    return
            except Exception:
                pass
        self.stato = {
            "attivo": False,
            "stato_operativo": "IDLE", # IDLE, ARMED_ROLLOVER, RUNNING
            "livello_1_prezzo": None,
            "passo_pip": 6.0,
            "size_scaglione": 3,
            "delta_totale": 0,
            "scaglioni": [],
            "minimo_discesa": None,
            "minimo_precedente": None,
            "pnl_sessione": 0.0,
            "totale_incassato": 0.0,
            "storico_operazioni": [],
            "ultimo_prezzo_bid": None,
            "ultimo_prezzo_ask": None,
            "ultimo_aggiornamento": now_it().strftime("%Y-%m-%d %H:%M:%S")
        }

    def salva_stato(self):
        self.stato["ultimo_aggiornamento"] = now_it().strftime("%Y-%m-%d %H:%M:%S")
        try:
            tmp = f"{STATO_GOLDFINGER_FILE}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.stato, f, indent=4)
            os.replace(tmp, STATO_GOLDFINGER_FILE)
        except Exception as e:
            print_log(f"⚠️ Errore salvataggio stato_goldfinger: {e}")

    def is_in_rollover(self):
        t = now_it().time()
        # Finestra di salvaguardia spread serale: 22:55 - 00:15
        if t >= datetime.time(22, 55) or t < datetime.time(0, 15):
            return True
        return False

    def calcola_scaglioni_interi(self, pz_start, passo, size_unit, delta_tot):
        if delta_tot <= 0 or pz_start is None or pz_start <= 0:
            return []
        
        num_scaglioni = max(1, delta_tot // size_unit)
        sizes = [int(size_unit)] * num_scaglioni
        residuo = delta_tot - sum(sizes)
        if residuo > 0:
            sizes[-1] += int(residuo)
            
        scaglioni = []
        for i, sz in enumerate(sizes):
            pz_lvl = round(pz_start - (i * passo), 2)
            scaglioni.append({
                "numero": i + 1,
                "prezzo_target": pz_lvl,
                "size": int(sz),
                "stato": "IN_ATTESA", # IN_ATTESA, APERTO, PROTETTO_BE, CHIUSO
                "deal_id": None,
                "open_price": None,
                "sl_price": None,
                "opened_at": None
            })
        return scaglioni

    def ottieni_prezzo_live_gold(self):
        # 1. Prova da stato_sistema.json di DANY_REALE se recente (< 15s)
        if os.path.exists(STATO_FILE):
            try:
                if (time.time() - os.path.getmtime(STATO_FILE)) < 20:
                    with open(STATO_FILE, "r", encoding="utf-8") as f:
                        d_st = json.load(f)
                        p_ba = d_st.get("prezzi_bid_ask", {}).get("Spot Gold")
                        if p_ba and "bid" in p_ba and "ask" in p_ba:
                            self.cache_prezzo_live = (float(p_ba["bid"]), float(p_ba["ask"]))
                            return self.cache_prezzo_live
            except Exception:
                pass

        # 2. Prova da posizioni_aperte.json di DANY_REALE se presente Spot Gold
        if os.path.exists(POSIZIONI_FILE):
            try:
                if (time.time() - os.path.getmtime(POSIZIONI_FILE)) < 20:
                    with open(POSIZIONI_FILE, "r", encoding="utf-8") as f:
                        pos_arr = json.load(f)
                        for p in pos_arr:
                            if "GOLD" in str(p.get("instrument", "")).upper() or "CFDGOLD" in str(p.get("epic", "")).upper():
                                b_val, o_val = p.get("bid"), p.get("offer")
                                if b_val and o_val:
                                    self.cache_prezzo_live = (float(b_val), float(o_val))
                                    return self.cache_prezzo_live
            except Exception:
                pass

        # 3. Prova dai feed streaming Lightstreamer degli altri conti condivisi (zero API IG)
        for c_demo in ["FIORDOK_DEMO", "BONGIOLO_DEMO", "DANY_DEMO"]:
            cand_paths = [
                os.path.join(ROOT_DIR, c_demo, "stato_sistema.json"),
                os.path.join("/data", c_demo, "stato_sistema.json"),
            ]
            for cp in cand_paths:
                if os.path.exists(cp):
                    try:
                        if (time.time() - os.path.getmtime(cp)) < 20:
                            with open(cp, "r", encoding="utf-8") as f_demo:
                                d_demo = json.load(f_demo)
                                p_ba = d_demo.get("prezzi_bid_ask", {}).get("Spot Gold")
                                if p_ba and "bid" in p_ba and "ask" in p_ba:
                                    self.cache_prezzo_live = (float(p_ba["bid"]), float(p_ba["ask"]))
                                    return self.cache_prezzo_live
                    except Exception:
                        pass

        # 4. Fallback a chiamata diretta /markets (MASSIMA PROTEZIONE ANTI-FLOOD: max 1 volta ogni 5 secondi!)
        now_t = time.time()
        if (now_t - self.ultimo_fallback_markets) < 5.0:
            return self.cache_prezzo_live
            
        self.ultimo_fallback_markets = now_t
        headers = self.get_auth_headers("3")
        try:
            r = requests.get(f"{BASE_URL}/markets/{EPIC_GOLD}", headers=headers, timeout=5)
            if r.status_code == 200:
                snap = r.json().get("snapshot", {})
                bid = snap.get("bid")
                offer = snap.get("offer")
                if bid and offer:
                    self.cache_prezzo_live = (float(bid), float(offer))
                    return self.cache_prezzo_live
            elif r.status_code == 401:
                print_log("🔄 Token non valido su /markets: ricarico credenziali...")
                self.carica_token()
        except Exception:
            pass
            
        return self.cache_prezzo_live

    def apri_short_mercato(self, size):
        now_t = time.time()
        if (now_t - self.ultimo_tentativo_ordine) < 3.0:
            # Salvaguardia anti-flood: rispetta almeno 3 secondi tra ordini consecutivi
            return False, None, None
        self.ultimo_tentativo_ordine = now_t

        headers = self.get_auth_headers("2")
        payload = {
            "epic": EPIC_GOLD,
            "expiry": "-",
            "direction": "SELL",
            "size": str(int(size)),
            "orderType": "MARKET",
            "guaranteedStop": "false",
            "forceOpen": "true",
            "currencyCode": VALUTA_GOLD
        }
        try:
            r = requests.post(f"{BASE_URL}/positions/otc", headers=headers, json=payload, timeout=8)
            if r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                time.sleep(1.2)
                # Verifica conferma
                r_conf = requests.get(f"{BASE_URL}/confirms/{deal_ref}", headers=self.get_auth_headers("1"), timeout=8)
                if r_conf.status_code == 200:
                    c_data = r_conf.json()
                    deal_status = c_data.get("dealStatus")
                    if deal_status == "ACCEPTED":
                        deal_id = c_data.get("dealId")
                        level = float(c_data.get("level", 0.0))
                        print_log(f"✅ Eseguito SHORT a mercato: {size} contratti @ {level:.2f} [ID: {deal_id}]")
                        return True, deal_id, level
                    else:
                        print_log(f"⚠️ Ordine SHORT rifiutato da IG: {c_data.get('reason')}")
            else:
                print_log(f"⚠️ Errore invio ordine SHORT IG: HTTP {r.status_code} - {r.text}")
        except Exception as e:
            print_log(f"⚠️ Eccezione invio ordine SHORT: {e}")
        return False, None, None

    def chiudi_short_mercato(self, deal_id, size):
        headers = self.get_auth_headers("1")
        payload = {
            "dealId": deal_id,
            "direction": "BUY", # Per chiudere uno SHORT si compra
            "size": str(int(size)),
            "orderType": "MARKET"
        }
        try:
            r = requests.post(f"{BASE_URL}/positions/otc", headers=headers, json=payload, timeout=8)
            if r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                time.sleep(1.2)
                r_conf = requests.get(f"{BASE_URL}/confirms/{deal_ref}", headers=self.get_auth_headers("1"), timeout=8)
                if r_conf.status_code == 200:
                    c_data = r_conf.json()
                    if c_data.get("dealStatus") == "ACCEPTED":
                        lvl = float(c_data.get("level", 0.0))
                        pnl = float(c_data.get("profit", 0.0) or 0.0)
                        print_log(f"✅ Chiuso SHORT ({deal_id}): {size} contratti @ {lvl:.2f} [PnL: {pnl:+.2f} €]")
                        return True, lvl, pnl
            print_log(f"⚠️ Errore chiusura SHORT {deal_id}: HTTP {r.status_code} - {r.text}")
        except Exception as e:
            print_log(f"⚠️ Eccezione chiusura SHORT {deal_id}: {e}")
        return False, None, None

    def ciclo_operativo(self):
        config_ui = self.carica_config()
        is_attivo_ui = config_ui.get("attivo", False)
        
        # 1. GESTIONE STOP
        if not is_attivo_ui:
            if self.stato.get("attivo"):
                print_log("🛑 Rilevato comando STOP da Dashboard. Goldfinger si arresta e passa il controllo a manuale.")
                self.stato["attivo"] = False
                self.stato["stato_operativo"] = "IDLE"
                self.salva_stato()
            return

        # 2. GESTIONE AVVIO
        if not self.stato.get("attivo") and is_attivo_ui:
            pz_start = config_ui.get("livello_1_prezzo")
            passo = float(config_ui.get("passo_pip", 6.0))
            sz = int(config_ui.get("size_scaglione", 3))
            delta = int(config_ui.get("delta_totale", 15))

            if pz_start is None or pz_start <= 0:
                print_log("🛑 Errore: Livello 1 non impostato o non valido. Avvio annullato.")
                config_ui["attivo"] = False
                with open(CONFIG_GOLDFINGER_FILE, "w", encoding="utf-8") as f:
                    json.dump(config_ui, f, indent=4)
                return

            self.stato["attivo"] = True
            self.stato["livello_1_prezzo"] = pz_start
            self.stato["passo_pip"] = passo
            self.stato["size_scaglione"] = sz
            self.stato["delta_totale"] = delta
            self.stato["scaglioni"] = self.calcola_scaglioni_interi(pz_start, passo, sz, delta)
            self.stato["minimo_discesa"] = None
            self.stato["minimo_precedente"] = None
            self.salva_stato()
            print_log(f"🚀 GOLDFINGER AVVIATO: Livello 1 @ {pz_start:.2f}, Passo {passo} pip, Delta {delta} contratti ({len(self.stato['scaglioni'])} scaglioni).")
            invia_notifica("AVVIO GOLDFINGER", f"Guardia avviata: Livello 1 a {pz_start:.2f}, Delta {delta} contratti.", "rocket")

        # 3. VERIFICA FINESTRA ROLLOVER
        if self.is_in_rollover():
            if self.stato.get("stato_operativo") != "ARMED_ROLLOVER":
                self.stato["stato_operativo"] = "ARMED_ROLLOVER"
                self.salva_stato()
                print_log("🌙 Pausa Rollover serale attiva (22:55 - 00:15). Monitoraggio silente senza nuovi ordini a mercato.")
            return
        else:
            if self.stato.get("stato_operativo") == "ARMED_ROLLOVER":
                self.stato["stato_operativo"] = "RUNNING"
                self.salva_stato()
                print_log("🟢 Fine Pausa Rollover. Guardia attiva e operativa a mercato.")

        # 4. LETTURA PREZZO LIVE
        bid, ask = self.ottieni_prezzo_live_gold()
        if not bid or not ask:
            return
        
        self.stato["ultimo_prezzo_bid"] = bid
        self.stato["ultimo_prezzo_ask"] = ask

        scaglioni = self.stato.get("scaglioni", [])
        aperti = [s for s in scaglioni if s["stato"] in ("APERTO", "PROTETTO_BE")]
        
        # 5. TRACCIAMENTO DEL MINIMO DISCESA
        if aperti:
            if self.stato.get("minimo_discesa") is None:
                self.stato["minimo_discesa"] = bid
            else:
                if bid < self.stato["minimo_discesa"]:
                    self.stato["minimo_discesa"] = bid
            self.salva_stato()

        # 6. VERIFICA ENTRATE A SCAGLIONI IN DISCESA
        for idx, sc in enumerate(scaglioni):
            if sc["stato"] == "IN_ATTESA":
                if bid <= sc["prezzo_target"]:
                    # Invia ordine SHORT a mercato
                    ok, deal_id, lvl = self.apri_short_mercato(sc["size"])
                    if ok:
                        sc["stato"] = "APERTO"
                        sc["deal_id"] = deal_id
                        sc["open_price"] = lvl
                        sc["sl_price"] = lvl + 6.0 # SL iniziale per falso allarme
                        sc["opened_at"] = time.time()
                        
                        # Protezione a Break-Even + 1 pip dello scaglione precedente!
                        if idx > 0 and scaglioni[idx - 1]["stato"] in ("APERTO", "PROTETTO_BE"):
                            sc_prev = scaglioni[idx - 1]
                            sc_prev["stato"] = "PROTETTO_BE"
                            sc_prev["sl_price"] = sc_prev["open_price"] - 1.0 # 1 pip sotto l'entrata SHORT = profitto blindato
                            print_log(f"🛡️ Scaglione {sc_prev['numero']} protetto a Break-Even+1 @ {sc_prev['sl_price']:.2f}")

                        invia_notifica("SCAGLIONE SHORT ESEGUITO", f"Agganciato Scaglione {sc['numero']} ({sc['size']} mini) @ {lvl:.2f}", "heavy_minus_sign")
                        self.salva_stato()
                    break # Gestisci un livello per tick

        # 7. CHIUSURA TOTALE SHORT SUL RIMBALZO (7 pip dal minimo)
        min_curr = self.stato.get("minimo_discesa")
        if aperti and min_curr is not None:
            soglia_sgancio = min_curr + 7.0
            if ask >= soglia_sgancio:
                print_log(f"💥 RIMBALZO RILEVATO: Prezzo {ask:.2f} >= Minimo ({min_curr:.2f}) + 7 pip ({soglia_sgancio:.2f}). Chiudo tutti gli SHORT all'incasso!")
                pnl_tot_rimbalzo = 0.0
                for sc in aperti:
                    ok, lvl_c, pnl = self.chiudi_short_mercato(sc["deal_id"], sc["size"])
                    if ok:
                        sc["stato"] = "CHIUSO"
                        pnl_tot_rimbalzo += pnl
                        self.stato["storico_operazioni"].append({
                            "data": now_it().strftime("%d/%m %H:%M:%S"),
                            "scaglione": sc["numero"],
                            "size": sc["size"],
                            "open": sc["open_price"],
                            "close": lvl_c,
                            "pnl": pnl,
                            "motivo": "RIMBALZO_INCASSO"
                        })
                self.stato["pnl_sessione"] += pnl_tot_rimbalzo
                self.stato["totale_incassato"] += pnl_tot_rimbalzo
                self.stato["minimo_precedente"] = min_curr
                self.stato["minimo_discesa"] = None
                print_log(f"💰 Chiusura rimbalzo completata. Incassati netti: {pnl_tot_rimbalzo:+.2f} €. Minimo precedente salvato a {min_curr:.2f}.")
                invia_notifica("INCASSO RIMBALZO", f"Tutti gli Short chiusi sul rimbalzo! Incasso netto: {pnl_tot_rimbalzo:+.2f} €", "moneybag")
                self.salva_stato()
                return

        # 8. RIARMO AUTOMATICO SULLA SECONDA ONDATA (Rottura Minimo Precedente di 5 pip)
        tutti_chiusi = len(scaglioni) > 0 and all(s["stato"] == "CHIUSO" for s in scaglioni)
        min_prec = self.stato.get("minimo_precedente")
        if tutti_chiusi and min_prec is not None:
            soglia_riarmo = round(min_prec - 5.0, 2)
            if bid <= soglia_riarmo:
                print_log(f"🛡️ SECONDA ONDATA: Prezzo {bid:.2f} <= Minimo prec ({min_prec:.2f}) - 5 pip ({soglia_riarmo:.2f}). Riarmo immediato della scala SHORT!")
                passo = float(self.stato.get("passo_pip", 6.0))
                sz = int(self.stato.get("size_scaglione", 3))
                delta = int(self.stato.get("delta_totale", 15))
                self.stato["scaglioni"] = self.calcola_scaglioni_interi(soglia_riarmo, passo, sz, delta)
                self.stato["minimo_precedente"] = None
                self.stato["minimo_discesa"] = None
                invia_notifica("RIARMO GOLDFINGER", f"Riarmo seconda ondata da {soglia_riarmo:.2f} in giù.", "arrows_counterclockwise")
                self.salva_stato()

        # 9. STOP LOSS SINGOLO SU FALSO ALLARME
        if len(aperti) == 1:
            sc_unica = aperti[0]
            if sc_unica.get("sl_price") and ask >= sc_unica["sl_price"]:
                print_log(f"🛑 Falso allarme Scaglione {sc_unica['numero']}: Colpito Stop Loss a {ask:.2f}. Chiudo in minima perdita.")
                ok, lvl_c, pnl = self.chiudi_short_mercato(sc_unica["deal_id"], sc_unica["size"])
                if ok:
                    sc_unica["stato"] = "CHIUSO"
                    self.stato["pnl_sessione"] += pnl
                    self.stato["minimo_discesa"] = None
                    self.stato["storico_operazioni"].append({
                        "data": now_it().strftime("%d/%m %H:%M:%S"),
                        "scaglione": sc_unica["numero"],
                        "size": sc_unica["size"],
                        "open": sc_unica["open_price"],
                        "close": lvl_c,
                        "pnl": pnl,
                        "motivo": "SL_FALSO_ALLARME"
                    })
                    self.salva_stato()

    def avvia_loop(self):
        print_log(f"🚀 Modulo Goldfinger Engine avviato in ascolto permanente per {self.target_account_id}...")
        consecutive_errors = 0
        while True:
            try:
                self.ciclo_operativo()
                consecutive_errors = 0
                time.sleep(1.5)
            except KeyboardInterrupt:
                print_log("🛑 Goldfinger Engine interrotto.")
                break
            except Exception as e:
                consecutive_errors += 1
                backoff = min(30, 5 * consecutive_errors)
                print_log(f"⚠️ Errore imprevisto nel ciclo Goldfinger ({consecutive_errors}° anomalia): {e}. Ripristino automatico e pausa di sicurezza di {backoff}s prima di riprendere...")
                time.sleep(backoff)

if __name__ == "__main__":
    engine = GoldfingerEngine()
    engine.avvia_loop()
