import json
import time
import os
import requests
import traceback
import datetime
import sys
import socket
import hashlib
try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

from dotenv import dotenv_values

from macchinetta_trend.core_engine import CoreEngine, Candle
from macchinetta_trend.position_manager import PositionManager

# --- MAPPA TIMEFRAMES (IN MINUTI) ---
TF_MAP = {
    "MINUTE_2": 2,
    "MINUTE_3": 3,
    "MINUTE_5": 5,
    "MINUTE_10": 10,
    "MINUTE_15": 15,
    "MINUTE_30": 30,
    "HOUR": 60,
    "HOUR_2": 120,
    "HOUR_3": 180,
    "HOUR_4": 240,
    "DAY": 1440
}

# --- CONFIGURAZIONI GLOBALI ---
FILE_MEMORIA = "memoria_parametri.json"
FILE_TOKEN = "token_ig.json"
STATO_SISTEMA = "stato_sistema.json"
CONSOLE_LOG_FILE = "console_live.log"
STATO_TREND = "stato_trend.json"

if len(sys.argv) < 2:
    print("🚨 ERRORE: Devi specificare il nome della cartella del conto all'avvio!")
    sys.exit()

NOME_CONTO = sys.argv[1]
if not os.path.isdir(NOME_CONTO):
    print(f"🚨 ERRORE: La cartella '{NOME_CONTO}' non esiste.")
    sys.exit()

os.chdir(NOME_CONTO)
BASE_URL = "https://api.ig.com/gateway/deal" if "_REALE" in NOME_CONTO.upper() else "https://demo-api.ig.com/gateway/deal"
config = dotenv_values(".env")

# Vocabolario base
CONFIG_STRUMENTI = {
    "AUD/CAD": {"epic": "CS.D.AUDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD", "valore_punto": 1},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "EUR/GBP": {"epic": "CS.D.EURGBP.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "GBP", "valore_punto": 1},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF", "valore_punto": 1},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1, "decimali": 2, "valuta": "EUR", "valore_punto": 1}
}


def invia_notifica(titolo, messaggio, tags="rotating_light"):
    topic = config.get("NTFY_TOPIC")
    if topic:
        try:
            orario = now_it().strftime("%H:%M:%S")
            messaggio_con_orario = f"[{orario}] {messaggio}"
            headers = {
                "Title": f"[{NOME_CONTO}] {titolo}".encode('utf-8'),
                "Tags": tags
            }
            requests.post(f"https://ntfy.sh/{topic}", data=messaggio_con_orario.encode('utf-8'), headers=headers, timeout=5)
        except Exception as e:
            print_log("SISTEMA", f"⚠️ Errore invio notifica Push: {e}")

def print_log(strumento, messaggio):
    ora = now_it().strftime("%H:%M:%S")
    riga = f"[{ora}] [{strumento}] {messaggio}"
    print(f"[{NOME_CONTO}] {riga}")
    try:
        righe = []
        if os.path.exists(CONSOLE_LOG_FILE):
            with open(CONSOLE_LOG_FILE, "r", encoding="utf-8") as f:
                righe = f.readlines()
        righe.append(riga + "\n")
        if len(righe) > 100:
            righe = righe[-100:]
        with open(CONSOLE_LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(righe)
    except Exception:
        pass

def get_eur_rate(valuta, prezzi):
    if valuta == "EUR":
        return 1.0
    eur_gbp = prezzi.get("EUR/GBP")
    gbp_usd = prezzi.get("GBP/USD")
    if not eur_gbp or not gbp_usd:
        return 1.0
    eur_usd = eur_gbp * gbp_usd
    if valuta == "USD":
        return 1.0 / eur_usd
    if valuta == "GBP":
        return 1.0 / eur_gbp
    if valuta == "CAD":
        usd_cad = prezzi.get("USD/CAD")
        if usd_cad: return 1.0 / (eur_usd * usd_cad)
    if valuta == "CHF":
        usd_chf = prezzi.get("USD/CHF")
        if usd_chf: return 1.0 / (eur_usd * usd_chf)
    if valuta == "JPY":
        usd_jpy = prezzi.get("USD/JPY")
        if usd_jpy: return 1.0 / (eur_usd * usd_jpy)
    if valuta == "NZD":
        aud_nzd = prezzi.get("AUD/NZD")
        aud_cad = prezzi.get("AUD/CAD")
        usd_cad = prezzi.get("USD/CAD")
        if aud_nzd and aud_cad and usd_cad:
            eur_cad = eur_usd * usd_cad
            eur_nzd = (eur_cad / aud_cad) * aud_nzd
            return 1.0 / eur_nzd
    return 1.0

def ottieni_headers_ig():
    if not os.path.exists(FILE_TOKEN): return None
    try:
        with open(FILE_TOKEN, "r") as f: token_dati = json.load(f)
        return {
            "X-IG-API-KEY": config.get("IG_API_KEY"), 
            "CST": token_dati.get("CST"), 
            "X-SECURITY-TOKEN": token_dati.get("X-SECURITY-TOKEN"), 
            "Accept": "application/json"
        }
    except Exception: return None

# --- FUNZIONI API IG E RATE LIMITER ---
from collections import deque
import threading

class IGRateLimiter:
    """
    Gatekeeper centralizzato per prevenire rate-limiting / ingolfamento su IG API.
    - Spaziatura minima di 1.2s tra chiamate consecutive.
    - Tetto massimo a finestra mobile: max 25 richieste ogni 60 secondi.
    """
    def __init__(self, min_interval=1.2, max_per_minute=25):
        self.min_interval = min_interval
        self.max_per_minute = max_per_minute
        self.last_call_time = 0.0
        self.call_history = deque()
        self.lock = threading.Lock()
        
    def acquire(self):
        with self.lock:
            now = time.time()
            
            # 1. Pulizia chiamate più vecchie di 60 secondi
            while self.call_history and (now - self.call_history[0]) > 60.0:
                self.call_history.popleft()
                
            # 2. Controllo tetto massimo al minuto
            if len(self.call_history) >= self.max_per_minute:
                attesa_quota = 60.0 - (now - self.call_history[0]) + 0.1
                if attesa_quota > 0:
                    time.sleep(attesa_quota)
                    now = time.time()
                    
            # 3. Spaziatura minima di respiro
            diff = now - self.last_call_time
            if diff < self.min_interval:
                time.sleep(self.min_interval - diff)
                now = time.time()
                
            self.last_call_time = now
            self.call_history.append(now)

ig_rate_limiter = IGRateLimiter(min_interval=1.2, max_per_minute=25)

def formatta_numero(valore, dec):
    if valore is None: return None
    r = round(float(valore), dec)
    return f"{r:.{dec}f}"

def chiamata_api_sicura(metodo, url, headers, payload=None, max_retries=4):
    headers_req = headers.copy()
    headers_req["Version"] = "2"
    for _ in range(max_retries):
        ig_rate_limiter.acquire()
        try:
            if metodo.upper() == 'GET':
                r = requests.get(url, headers=headers_req, timeout=10)
            elif metodo.upper() == 'DELETE':
                r = requests.delete(url, headers=headers_req, timeout=10)
            else:
                r = requests.post(url, headers=headers_req, json=payload, timeout=10)
            
            if r.status_code == 403 and "exceeded-api-key" in r.text:
                time.sleep(15)
                continue
            return r
        except Exception:
            time.sleep(1.0)
    return None

def verifica_conferma_deal(deal_ref, headers):
    h_conf = headers.copy()
    h_conf["Version"] = "1"
    for _ in range(3): 
        try:
            ig_rate_limiter.acquire()
            r = requests.get(f"{BASE_URL}/confirms/{deal_ref}", headers=h_conf, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("dealStatus") == "ACCEPTED":
                    return True, data
                elif data.get("dealStatus") == "REJECTED":
                    return False, data.get("reason", "Unknown")
        except Exception:
            pass
        time.sleep(0.5)
    return True, {}

def invia_ordine_mercato(nome_strumento, epic, valuta, direzione, size, headers, dec, limit_lvl=None, stop_lvl=None, etichetta="[ORDINE]"):
    size_str = str(int(size)) if float(size).is_integer() else str(size)
    dir_ig = "BUY" if direzione.upper() == "LONG" else "SELL"
    p = {
        "epic": epic, "expiry": "-", "direction": dir_ig, "size": size_str, 
        "orderType": "MARKET", "timeInForce": "EXECUTE_AND_ELIMINATE", 
        "guaranteedStop": False, "forceOpen": True, "currencyCode": valuta
    }
    if limit_lvl is not None: p["limitLevel"] = formatta_numero(limit_lvl, dec)
    if stop_lvl is not None: p["stopLevel"] = formatta_numero(stop_lvl, dec)
    
    backoffs = [1.0, 2.0, 3.0]
    for tentativo in range(len(backoffs) + 1): 
        ig_rate_limiter.acquire()
        try:
            r = requests.post(f"{BASE_URL}/positions/otc", headers=headers, json=p, timeout=10)
            if r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                real_level = None
                deal_id = None
                if deal_ref:
                    accettato, confirm_data = verifica_conferma_deal(deal_ref, headers)
                    if not accettato:
                        print_log(nome_strumento, f"❌ [IG REJECT] {etichetta} {direzione}: {confirm_data}")
                        if tentativo < len(backoffs):
                            time.sleep(backoffs[tentativo])
                        continue
                    if isinstance(confirm_data, dict):
                        if confirm_data.get("level") is not None: real_level = float(confirm_data.get("level"))
                        if confirm_data.get("dealId"): deal_id = confirm_data.get("dealId")

                if real_level is None:
                    try:
                        time.sleep(0.5)
                        ig_rate_limiter.acquire()
                        resp_p = requests.get(f"{BASE_URL}/positions", headers=headers, timeout=10)
                        if resp_p and resp_p.status_code == 200:
                            p_list = [pos for pos in resp_p.json().get('positions', []) if pos['market']['epic'] == epic and pos['position']['direction'] == dir_ig and abs(float(pos['position']['size']) - float(size)) < 0.001]
                            if p_list:
                                real_level = float(p_list[0]['position']['level'])
                                deal_id = p_list[0]['position']['dealId']
                    except Exception: pass

                if real_level is not None: real_level = round(float(real_level), dec)
                livello_log = f" a {formatta_numero(real_level, dec)}" if real_level is not None else ""
                print_log(nome_strumento, f"✅ {etichetta} eseguito con successo{livello_log}.")
                return True, real_level, deal_id
            else:
                resp_txt = r.text
                if r.status_code == 403 and "exceeded-api-key" in resp_txt:
                    print_log(nome_strumento, f"🛑 Rate limit IG superato, attesa salvavita 15s...")
                    time.sleep(15)
                else:
                    print_log(nome_strumento, f"⚠️ Rifiuto API {etichetta} {direzione}: {resp_txt}")
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione Rete su {etichetta} {direzione}: {e}")
            
        if tentativo < len(backoffs):
            time.sleep(backoffs[tentativo])
            
    return False, None, None

def chiudi_parziale(nome_strumento, dealId, dir_chiusura, size, headers, etichetta="[POSIZIONE]"):
    h = headers.copy()
    h["Version"] = "1"
    h["_method"] = "DELETE"
    size_str = str(int(size)) if float(size).is_integer() else str(size)
    p = {"dealId": dealId, "direction": dir_chiusura, "size": size_str, "orderType": "MARKET"}
    
    backoffs = [1.0, 2.0, 3.0]
    for tentativo in range(len(backoffs) + 1):
        ig_rate_limiter.acquire()
        try:
            r = requests.post(f"{BASE_URL}/positions/otc", headers=h, json=p, timeout=10)
            if r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                if deal_ref:
                    accettato, confirm_data = verifica_conferma_deal(deal_ref, headers)
                    if not accettato:
                        reason = str(confirm_data)
                        if "POSITION_NOT_FOUND" in reason or "deal-not-found" in reason:
                            print_log(nome_strumento, f"ℹ️ Chiusura {etichetta} ({dealId}): posizione già chiusa su IG.")
                            return True
                        print_log(nome_strumento, f"⚠️ [IG REJECT] Chiusura {etichetta}: {confirm_data}")
                    else:
                        print_log(nome_strumento, f"✅ Chiusura {etichetta} eseguita con successo.")
                        return True
                else:
                    print_log(nome_strumento, f"✅ Chiusura {etichetta} inviata.")
                    return True
            else:
                resp_txt = r.text
                if r.status_code == 400 and ("deal-not-found" in resp_txt or "POSITION_NOT_FOUND" in resp_txt):
                    print_log(nome_strumento, f"ℹ️ Chiusura {etichetta} ({dealId}): già liquidata su IG.")
                    return True
                if r.status_code == 403 and "exceeded-api-key" in resp_txt:
                    print_log(nome_strumento, f"🛑 Rate limit IG superato, attesa salvavita 15s...")
                    time.sleep(15)
                else:
                    print_log(nome_strumento, f"⚠️ Errore Chiusura {etichetta} ({dealId}): {resp_txt}")
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione su Chiusura {etichetta}: {e}")
            
        if tentativo < len(backoffs):
            time.sleep(backoffs[tentativo])
            
    return False

def conta_posizioni_aperte_epic(epic, headers):
    """Conta quante posizioni reali sono attualmente aperte su IG per questo epic."""
    try:
        ig_rate_limiter.acquire()
        r = requests.get(f"{BASE_URL}/positions", headers=headers, timeout=10)
        if r and r.status_code == 200:
            pos = [p for p in r.json().get('positions', []) if p['market']['epic'] == epic]
            return len(pos)
    except Exception as e:
        print_log("SISTEMA", f"Errore verifica posizioni IG: {e}")
    return 0

def pulisci_posizioni_epic(nome, epic, headers):
    """Chiude tutte le posizioni aperte per quell'epic su IG con pacing anti-ingolfamento."""
    try:
        ig_rate_limiter.acquire()
        r = requests.get(f"{BASE_URL}/positions", headers=headers, timeout=10)
        if r and r.status_code == 200:
            pos_list = [p for p in r.json().get('positions', []) if p.get('market', {}).get('epic') == epic]
            for p in pos_list:
                pos_info = p.get('position', {})
                dir_c = "SELL" if pos_info.get('direction') == "BUY" else "BUY"
                deal_id = pos_info.get('dealId')
                sz = pos_info.get('dealSize', pos_info.get('size', 1))
                if deal_id:
                    chiudi_parziale(nome, deal_id, dir_c, sz, headers, etichetta="[CLEANUP]")
                    time.sleep(1.0)
    except Exception as e:
        print_log(nome, f"Errore pulizia reversal: {e}")

# --- STATO MOTORE TREND ---
class StatoMotoreTrend:
    def __init__(self):
        self.motori = {}
        self.carica_stato()

    def carica_stato(self):
        if os.path.exists(STATO_TREND):
            try:
                with open(STATO_TREND, "r") as f:
                    data = json.load(f)
                    # Non ricarichiamo direttamente gli oggetti CoreEngine, li ricostruiremo
            except Exception as e:
                print_log("SISTEMA", f"Errore caricamento stato trend: {e}")
                
    def salva_stato(self):
        # TODO: Serializzare lo stato dei vari CoreEngine (numero trade, fase, etc) per crash recovery
        pass

stato_motore = StatoMotoreTrend()

def get_file_candele(nome, tf):
    clean = nome.replace("/", "_").replace(" ", "_")
    return f"candele_{clean}_{tf}.json"

def carica_candele_locali(nome, tf):
    fpath = get_file_candele(nome, tf)
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if len(data) >= 55:
                    return data
        except Exception:
            pass
            
    # Fallback incrociato: cerca nei file degli altri conti nella PVC /data
    clean = nome.replace("/", "_").replace(" ", "_")
    fname = f"candele_{clean}_{tf}.json"
    for altro in ["FIORDOK_DEMO", "BONGIOLO_DEMO", "DANY_DEMO"]:
        alt_path = os.path.join("..", altro, fname)
        if os.path.exists(alt_path):
            try:
                with open(alt_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if len(d) >= 55:
                        salva_candele_locali(nome, tf, d)
                        return d
            except Exception:
                pass
    return []

def salva_candele_locali(nome, tf, candele_list):
    fpath = get_file_candele(nome, tf)
    try:
        buffer_100 = candele_list[-100:]
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(buffer_100, f, indent=2)
    except Exception as e:
        print_log(nome, f"Errore salvataggio candele locali: {e}")

# --- FUNZIONI CORE ---
def scarica_candele(epic, timeframe, limit=2, headers=None):
    h = headers.copy()
    h["Version"] = "3"
    for _ in range(3):
        try:
            ig_rate_limiter.acquire()
            url = f"{BASE_URL}/prices/{epic}?resolution={timeframe}&max={limit}&pageSize=0"
            r = requests.get(url, headers=h, timeout=10)
            if r.status_code == 200:
                return r.json().get('prices', [])
            elif r.status_code == 403 and "exceeded-api-key" in r.text:
                time.sleep(2.5)
                continue
            else:
                if r.status_code == 403 and ("historical-data-allowance" in r.text or "exceeded-account-allowance" in r.text or "exceeded-allowance" in r.text or "error.public-api.exceeded" in r.text):
                    return "QUOTA_ESAURITA"
                print_log("SISTEMA", f"Errore IG fetching prezzi {epic}: {r.status_code} {r.text}")
                return []
        except Exception as e:
            print_log("SISTEMA", f"Errore fetching prezzi {epic}: {e}")
            time.sleep(1.0)
    return []

def aggiorna_memoria(nome, update_dict):
    try:
        with open(FILE_MEMORIA, "r") as f: p = json.load(f)
        if nome in p:
            for k, v in update_dict.items():
                p[nome][k] = v
            with open(FILE_MEMORIA, "w") as f: json.dump(p, f, indent=4)
    except Exception:
        pass

def processa_eventi_engine(nome, engine, events, epic, valuta, size_i, headers, dec, auto_restart, dati):
    if not events:
        return
    storico = dati.get("storico_wip_trend", [])
    ha_fatto_eventi = False
    
    for ev in events:
        tipo = ev['type']
        ora_str = now_it().strftime("%d/%m %H:%M:%S")
        
        if tipo == 'auto_start':
            dir_auto = ev['direction']
            
            # --- SIGILLO DI SICUREZZA: ZERO POSIZIONI RESIDUE PRIMA DELLA NUOVA CORE ---
            pos_residue = conta_posizioni_aperte_epic(epic, headers)
            if pos_residue > 0:
                print_log(nome, f"🛑 [BLOCCO AUTO-RESTART] Rilevate {pos_residue} posizioni ancora aperte su IG! Pulizia obbligatoria prima della nuova Core...")
                pulisci_posizioni_epic(nome, epic, headers)
                time.sleep(1.0)
                pos_residue_2 = conta_posizioni_aperte_epic(epic, headers)
                if pos_residue_2 > 0:
                    print_log(nome, f"🚨 [BLOCCO REVERSAL] Core {dir_auto} annullata: {pos_residue_2} posizioni ancora bloccate su IG!")
                    invia_notifica(f"🚨 BLOCCO REVERSAL: {nome}", f"[{nome}] Trovate {pos_residue_2} posizioni residue non chiuse su IG. Auto-Restart bloccato per sicurezza.", "sos")
                    engine.reset()
                    aggiorna_memoria(nome, {"stato": "FLAT", "direzione": "", "posizioni_core": [], "posizioni_incr": [], "bancomat_sl": None})
                    continue

            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, dir_auto, size_i, headers, dec, etichetta="[CORE AUTO-RESTART]")
            if ok:
                entry_px = real_lvl if real_lvl else ev['price']
                if engine.pm.core_position:
                    engine.pm.core_position.entry_price = entry_px
                    engine.pm.core_position.ticket = deal_id
                msg = f"🚀 Auto-Restart: Apertura Core {dir_auto} a {entry_px}"
                print_log(nome, msg)
                invia_notifica(f"🚀 AUTO-RESTART TREND: {nome}", f"[{nome}] {msg}", "rocket")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
                aggiorna_memoria(nome, {"stato": dir_auto, "direzione": dir_auto})
            else:
                engine.reset()
                print_log(nome, "⚠️ Fallito inserimento a mercato Core Auto-Restart.")
        
        elif tipo == 'increment_opened':
            dir_incr = ev['direction']
            pos = ev['position']
            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, dir_incr, pos.size, headers, dec, etichetta="[INCREMENTO]")
            if ok:
                pos.entry_price = real_lvl if real_lvl else ev['price']
                pos.ticket = deal_id
                msg = f"➕ Incremento Aperto {dir_incr} a {pos.entry_price}"
                print_log(nome, msg)
                invia_notifica(f"➕ INCREMENTO TREND: {nome}", f"[{nome}] {msg}", "heavy_plus_sign")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
            else:
                engine.pm.increments.remove(pos)
                
        elif tipo in ('core_closed', 'increment_closed', 'fifo_close', 'increments_cleared'):
            deal_id = ev.get('ticket')
            if deal_id:
                dir_chiusura = "SELL" if ev['direction'] == "LONG" else "BUY"
                sz = ev.get('size', size_i)
                is_bancomat = (ev.get('reason') == 'bancomat')
                etichetta_tag = "[BANCOMAT]" if is_bancomat else f"[{tipo.upper()}]"
                chiudi_parziale(nome, deal_id, dir_chiusura, sz, headers, etichetta=etichetta_tag)
                
                raw_diff = ev.get('pnl', 0)
                c_cfg = CONFIG_STRUMENTI.get(nome, {})
                mult = c_cfg.get("moltiplicatore", 1)
                valore_punto = c_cfg.get("valore_punto", 1)
                valuta_c = c_cfg.get("valuta", "USD")
                
                prezzi_live = {}
                try:
                    if os.path.exists(STATO_SISTEMA):
                        with open(STATO_SISTEMA, "r") as f_st:
                            prezzi_live = json.load(f_st).get("prezzi_live", {})
                except Exception:
                    pass
                
                rate = get_eur_rate(valuta_c, prezzi_live)
                pnl_eur = (raw_diff / mult) * valore_punto * rate
                pnl_str = f" [PnL: {pnl_eur:+.0f} €]" if pnl_eur != 0 else ""
                
                if is_bancomat:
                    msg = f"💰 BANCOMAT Incassato! Chiuso Incremento ({sz}){pnl_str}"
                    invia_notifica(f"💰 BANCOMAT TREND: {nome}", f"[{nome}] {msg}", "moneybag")
                else:
                    msg = f"➖ Chiusura {tipo} ({sz}){pnl_str}"
                    invia_notifica(f"➖ CHIUSURA TREND: {nome}", f"[{nome}] {msg}", "heavy_minus_sign")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
        
        elif tipo == 'reversal':
            new_d = ev.get("new_direction", "FLAT")
            reason_str = ev.get("reason", "")
            tag_motivo = " (Live Stop KJ)" if "live_stop" in reason_str else ""
            msg = f"🛑 Reversal Kijun{tag_motivo}: chiusura globale e passaggio a {new_d}"
            print_log(nome, msg)
            invia_notifica(f"🛑 REVERSAL TREND: {nome}", f"[{nome}] {msg}", "warning")
            storico.append(f"[{ora_str}] {msg}")
            ha_fatto_eventi = True
            pulisci_posizioni_epic(nome, epic, headers)
            if not auto_restart:
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "direzione": "", "posizioni_core": [], "posizioni_incr": [], "trailing_sl_incr": None, "trailing_sl_core": None})
                engine.reset()
                print_log(nome, "💤 Auto-Restart disattivato. Macchina spenta.")
            else:
                aggiorna_memoria(nome, {"stato": "FLAT", "direzione": "", "posizioni_core": [], "posizioni_incr": [], "trailing_sl_incr": None, "trailing_sl_core": None})
            
    # Salvataggio posizioni aggiornate
    if engine.is_running:
        core_dict = [engine.pm.core_position.to_dict()] if engine.pm.core_position else []
        incr_dict = [p.to_dict() for p in engine.pm.increments]
        update_data = {
            "posizioni_core": core_dict, 
            "posizioni_incr": incr_dict,
            "trailing_sl_incr": engine.trailing_sl_incr,
            "trailing_sl_core": engine.trailing_sl_core
        }
        if ha_fatto_eventi:
            if len(storico) > 30: storico = storico[-30:]
            update_data["storico_wip_trend"] = storico
        aggiorna_memoria(nome, update_data)
    elif events and not auto_restart:
        update_data_off = {"posizioni_core": [], "posizioni_incr": [], "trailing_sl_incr": None, "trailing_sl_core": None}
        if ha_fatto_eventi:
            if len(storico) > 30: storico = storico[-30:]
            update_data_off["storico_wip_trend"] = storico
        aggiorna_memoria(nome, update_data_off)

def is_rollover_active():
    """
    Ritorna True se siamo nella finestra di Rollover notturno:
    Lun-Gio 22:45 - 23:59:59 (weekday 0, 1, 2, 3)
    Mar-Ven 00:00 - 00:29:59 (weekday 1, 2, 3, 4)
    """
    ora = now_it()
    t = ora.time()
    wd = ora.weekday()
    if wd in (0, 1, 2, 3) and (datetime.time(22, 45) <= t <= datetime.time(23, 59, 59)):
        return True
    if wd in (1, 2, 3, 4) and (datetime.time(0, 0) <= t <= datetime.time(0, 29, 59)):
        return True
    return False

LAST_FETCH_BOUNDARY = {}

def esegui_ciclo_trend():
    headers = ottieni_headers_ig()
    if not headers:
        print_log("SISTEMA", "Manca token IG, impossibile proseguire.")
        return
        
    # Lettura prezzi live locali e posizioni aperte reali (a 0 chiamate API a IG)
    prezzi_live = {}
    posizioni_live_ig = []
    has_pos_live_data = False
    if os.path.exists(STATO_SISTEMA):
        try:
            with open(STATO_SISTEMA, "r") as f_st:
                d_st = json.load(f_st)
                prezzi_live = d_st.get("prezzi_live", {})
                posizioni_live_ig = d_st.get("posizioni", [])
                has_pos_live_data = "posizioni" in d_st
        except Exception:
            pass

    try:
        with open(FILE_MEMORIA, "r") as f: parametri = json.load(f)
    except Exception:
        return
        
    for nome, dati in parametri.items():
        if dati.get("tipo_strategia", "RANGE") != "TREND":
            continue
            
        epic = CONFIG_STRUMENTI.get(nome, {}).get("epic")
        if not epic: continue
        
        # Recupera parametri
        tf = dati.get("timeframe", "MINUTE_5")
        size_i = dati.get("size", 1)
        size_max = dati.get("size_max", 3)
        scala = int(dati.get("scala", 1) or 1)
        min_body = dati.get("min_body", 10)
        auto_restart = dati.get("auto_restart", True)
        direzione = dati.get("direzione", "LONG")
        stato_corrente = dati.get("stato", "FLAT") # "FLAT", "LONG", "SHORT"
        valuta = CONFIG_STRUMENTI[nome]["valuta"]
        dec = CONFIG_STRUMENTI[nome]["decimali"]

        is_attivo = dati.get("attivo", False)
        candele_locali = carica_candele_locali(nome, tf)

        if not is_attivo:
            # Se la macchina è spenta MA risultano ancora posizioni registrate in memoria, ripuliscile e registra su WIP
            pos_core = dati.get("posizioni_core", [])
            pos_incr = dati.get("posizioni_incr", [])
            if pos_core or pos_incr:
                storico = dati.get("storico_wip_trend", [])
                ora_str = now_it().strftime("%d/%m %H:%M:%S")
                storico.append(f"[{ora_str}] 🛑 Macchinetta spenta: rimosse posizioni dal live.")
                aggiorna_memoria(nome, {
                    "posizioni_core": [], 
                    "posizioni_incr": [], 
                    "trailing_sl_core": None, 
                    "trailing_sl_incr": None, 
                    "stato": "FLAT",
                    "direzione": "",
                    "storico_wip_trend": storico[-30:]
                })
                if nome in stato_motore.motori:
                    stato_motore.motori[nome].reset()
            continue
        
        # Inizializza/Recupera Engine
        if nome not in stato_motore.motori:
            cfg = {
                "size_i": size_i,
                "size_max": size_max,
                "scala": scala,
                "timeframe": tf,
                "tk_periods": 21,
                "kj_periods": 55,
                "min_body": min_body,
                "pip_value": CONFIG_STRUMENTI[nome]["moltiplicatore"],
                "max_kj_distance": 50.0,
                "max_entry_delay": 5,
                "auto_restart": auto_restart
            }
            stato_motore.motori[nome] = CoreEngine(cfg)
        else:
            stato_motore.motori[nome].config["size_i"] = size_i
            stato_motore.motori[nome].config["size_max"] = size_max
            stato_motore.motori[nome].config["scala"] = scala
            stato_motore.motori[nome].config["timeframe"] = tf
            stato_motore.motori[nome].config["min_body"] = min_body
            stato_motore.motori[nome].config["pip_value"] = CONFIG_STRUMENTI[nome]["moltiplicatore"]
            stato_motore.motori[nome].config["auto_restart"] = auto_restart
        
        engine = stato_motore.motori[nome]
        
        # Sincronizza posizioni da memoria se engine è vuoto ma in memoria ci sono posizioni
        if not engine.is_running and stato_corrente in ("LONG", "SHORT"):
            pos_core = dati.get("posizioni_core", [])
            pos_incr = dati.get("posizioni_incr", [])
            if pos_core:
                engine.is_running = True
                engine.current_direction = stato_corrente
                for c_d in pos_core:
                    dir_pos = c_d.get("direction", stato_corrente)
                    pos = engine.pm.open_core(c_d.get("entry", 0), c_d.get("size", 1), dir_pos)
                    pos.ticket = c_d.get("ticket")
                for i_d in pos_incr:
                    dir_pos = i_d.get("direction", stato_corrente)
                    pos = engine.pm.open_increment(i_d.get("entry", 0), i_d.get("size", 1), dir_pos)
                    pos.ticket = i_d.get("ticket")
                engine.trailing_sl_incr = dati.get("trailing_sl_incr")
                engine.trailing_sl_core = dati.get("trailing_sl_core")
                engine.current_tk = dati.get("current_tk")
                engine.current_kj = dati.get("current_kj")
                
                # Inizializzazione rapida al boot dall'ultima candela locale se i trailing non sono ancora in memoria
                c_loc = carica_candele_locali(nome, tf)
                if c_loc:
                    try:
                        last_c = c_loc[-1]
                        c_close = (last_c['closePrice']['bid'] + last_c['closePrice']['ask']) / 2
                        pip_val = CONFIG_STRUMENTI[nome]["moltiplicatore"]
                        
                        # Trailing SL Core: KJ 40 / 40 (distanza KJ >= 40 pip -> stop a 40 pip da Close)
                        if engine.trailing_sl_core is None and engine.current_kj is not None:
                            if stato_corrente == "SHORT":
                                dist_kj = engine.current_kj - c_close
                                if dist_kj >= (40 * pip_val):
                                    engine.trailing_sl_core = c_close + (40 * pip_val)
                                    aggiorna_memoria(nome, {"trailing_sl_core": engine.trailing_sl_core})
                                    print_log(nome, f"🎯 Trailing SL Core inizializzato a {engine.trailing_sl_core:.5f} (distanza KJ: {dist_kj/pip_val:.1f} pip)")
                            elif stato_corrente == "LONG":
                                dist_kj = c_close - engine.current_kj
                                if dist_kj >= (40 * pip_val):
                                    engine.trailing_sl_core = c_close - (40 * pip_val)
                                    aggiorna_memoria(nome, {"trailing_sl_core": engine.trailing_sl_core})
                                    print_log(nome, f"🎯 Trailing SL Core inizializzato a {engine.trailing_sl_core:.5f} (distanza KJ: {dist_kj/pip_val:.1f} pip)")

                        # Trailing SL Incrementi: TK 20 / 20 (distanza TK >= 20 pip -> stop a 20 pip da Close)
                        if engine.trailing_sl_incr is None and len(pos_incr) > 0 and engine.current_tk is not None:
                            if stato_corrente == "SHORT":
                                dist_tk = engine.current_tk - c_close
                                if dist_tk >= (20 * pip_val):
                                    engine.trailing_sl_incr = c_close + (20 * pip_val)
                                    aggiorna_memoria(nome, {"trailing_sl_incr": engine.trailing_sl_incr})
                                    print_log(nome, f"🎯 Trailing SL incrementi inizializzato a {engine.trailing_sl_incr:.5f} (distanza TK: {dist_tk/pip_val:.1f} pip)")
                            elif stato_corrente == "LONG":
                                dist_tk = c_close - engine.current_tk
                                if dist_tk >= (20 * pip_val):
                                    engine.trailing_sl_incr = c_close - (20 * pip_val)
                                    aggiorna_memoria(nome, {"trailing_sl_incr": engine.trailing_sl_incr})
                                    print_log(nome, f"🎯 Trailing SL incrementi inizializzato a {engine.trailing_sl_incr:.5f} (distanza TK: {dist_tk/pip_val:.1f} pip)")
                    except Exception:
                        pass

        # -------------------------------------------------------------
        # RICONCILIAZIONE AUTOMATICA CON POSIZIONI REALI SU IG
        # -------------------------------------------------------------
        if has_pos_live_data and engine.is_running:
            ticket_aperti_epic = {p.get('position', {}).get('dealId') for p in posizioni_live_ig if p.get('market', {}).get('epic') == epic}
            storico_aggiornato = False
            storico = dati.get("storico_wip_trend", [])
            ora_str = now_it().strftime("%d/%m %H:%M:%S")
            valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
            mult = CONFIG_STRUMENTI[nome]["moltiplicatore"]
            px_live = prezzi_live.get(nome)
            
            # 1. Verifica se la Core è stata chiusa a mano su IG
            if engine.pm.core_position and engine.pm.core_position.ticket:
                if engine.pm.core_position.ticket not in ticket_aperti_epic:
                    pnl_txt = ""
                    if px_live and isinstance(px_live, (int, float)):
                        pts = (engine.pm.core_position.entry_price - px_live)/mult if engine.pm.core_position.direction == "SHORT" else (px_live - engine.pm.core_position.entry_price)/mult
                        rate = get_conversion_rate(valuta, prezzi_live)
                        pnl_est = pts * engine.pm.core_position.size * valore_punto * rate
                        pnl_txt = f" [PnL stimato: {pnl_est:+.0f} €]"
                    msg = f"🛑 Chiusura manuale su IG: Core {engine.pm.core_position.direction} ({engine.pm.core_position.size}){pnl_txt}"
                    storico.append(f"[{ora_str}] {msg}")
                    print_log(nome, f"ℹ️ Rilevata chiusura manuale Core ({engine.pm.core_position.ticket}) su IG. Posizione rimossa dal live.")
                    engine.pm.core_position = None
                    engine.trailing_sl_core = None
                    storico_aggiornato = True
            
            # 2. Verifica se qualche incremento è stato chiuso a mano su IG
            for inc in list(engine.pm.increments):
                if inc.ticket and inc.ticket not in ticket_aperti_epic:
                    pnl_txt = ""
                    if px_live and isinstance(px_live, (int, float)):
                        pts = (inc.entry_price - px_live)/mult if inc.direction == "SHORT" else (px_live - inc.entry_price)/mult
                        rate = get_conversion_rate(valuta, prezzi_live)
                        pnl_est = pts * inc.size * valore_punto * rate
                        pnl_txt = f" [PnL stimato: {pnl_est:+.0f} €]"
                    msg = f"🛑 Chiusura manuale su IG: Incremento ({inc.size}){pnl_txt}"
                    storico.append(f"[{ora_str}] {msg}")
                    print_log(nome, f"ℹ️ Rilevata chiusura manuale Incremento ({inc.ticket}) su IG. Rimosso dal live.")
                    engine.pm.increments.remove(inc)
                    storico_aggiornato = True
            
            if storico_aggiornato:
                core_dict = [engine.pm.core_position.to_dict()] if engine.pm.core_position else []
                incr_dict = [p.to_dict() for p in engine.pm.increments]
                up_dict = {
                    "posizioni_core": core_dict,
                    "posizioni_incr": incr_dict,
                    "trailing_sl_core": engine.trailing_sl_core,
                    "trailing_sl_incr": engine.trailing_sl_incr,
                    "storico_wip_trend": storico[-30:]
                }
                if not engine.pm.core_position and not engine.pm.increments:
                    engine.is_running = False
                    engine.current_direction = "FLAT"
                    engine.reset()
                    up_dict["stato"] = "FLAT"
                    up_dict["direzione"] = ""
                    if not auto_restart:
                        up_dict["attivo"] = False
                aggiorna_memoria(nome, up_dict)

        # -------------------------------------------------------------
        # GESTIONE AUTOMATICA PAUSA ROLLOVER (22:45 - 00:29)
        # -------------------------------------------------------------
        in_rollover = is_rollover_active()
        is_sosp_rollover = dati.get("sospeso_rollover", False)
        if in_rollover and not is_sosp_rollover:
            print_log(nome, "🌙 INIZIO PAUSA ROLLOVER (22:45): Stop live congelati e ingressi sospesi per protezione spread.")
            aggiorna_memoria(nome, {"sospeso_rollover": True})
            dati["sospeso_rollover"] = True
        elif not in_rollover and is_sosp_rollover:
            print_log(nome, "☀️ FINE PAUSA ROLLOVER (00:30): Ripristino controlli attivi.")
            aggiorna_memoria(nome, {"sospeso_rollover": False})
            dati["sospeso_rollover"] = False

        # -------------------------------------------------------------
        # FASE 1: CONTROLLO STOP LOSS LIVE INTRACANDELA (0 Chiamate API)
        # -------------------------------------------------------------
        if not in_rollover:
            live_px = prezzi_live.get(nome)
            if live_px and isinstance(live_px, (int, float)) and engine.is_running and engine.current_direction != "FLAT":
                live_events = engine.check_live_stops(live_px)
                if live_events:
                    processa_eventi_engine(nome, engine, live_events, epic, valuta, size_i, headers, dec, auto_restart, dati)

        # -------------------------------------------------------------
        # FASE 2: TIMING FINE CANDELA O AVVIO MANUALE
        # -------------------------------------------------------------
        if in_rollover:
            continue
        needs_start = not engine.is_running and stato_corrente == "FLAT" and direzione in ("LONG", "SHORT")
        
        now_t = now_it()
        min_tf = TF_MAP.get(tf, 5)
        min_tot = now_t.hour * 60 + now_t.minute
        offset = 60 if min_tf in (60, 240, 1440) else 0
        is_candle_boundary = (min_tot - offset) % min_tf == 0
        is_just_closed = is_candle_boundary and now_t.second < 25
        
        if not is_just_closed and not needs_start:
            continue
        
        candele_locali = carica_candele_locali(nome, tf)
        
        # 1. Recupero candele a fine candela
        limite_download = 100 if len(candele_locali) < 55 else 2
        boundary_id = f"{nome}_{tf}_{min_tot // min_tf}"
        
        prices = []
        if LAST_FETCH_BOUNDARY.get(nome) != boundary_id and (len(candele_locali) < 55 or is_just_closed):
            LAST_FETCH_BOUNDARY[nome] = boundary_id
            prices = scarica_candele(epic, tf, limit=limite_download, headers=headers)
        
        if prices == "QUOTA_ESAURITA" or not prices or not isinstance(prices, list) or len(prices) < 2:
            # Fallback automatico su sintesi locale se la quota IG è esaurita o API in errore
            if len(candele_locali) >= 55 and is_just_closed:
                live_px = prezzi_live.get(nome)
                if live_px and isinstance(live_px, (int, float)):
                    boundary_min = (min_tot // min_tf) * min_tf
                    b_h = boundary_min // 60
                    b_m = boundary_min % 60
                    snap_synth = now_t.replace(hour=b_h, minute=b_m, second=0).strftime("%Y/%m/%d %H:%M:00")
                    snap_esistenti = set(c.get("snapshotTime") for c in candele_locali if "snapshotTime" in c)
                    if snap_synth not in snap_esistenti:
                        last_c = candele_locali[-1]
                        prev_close = (last_c['closePrice']['bid'] + last_c['closePrice']['ask']) / 2
                        synth_candle = {
                            "snapshotTime": snap_synth,
                            "openPrice": {"bid": prev_close, "ask": prev_close, "lastTraded": None},
                            "highPrice": {"bid": max(prev_close, live_px), "ask": max(prev_close, live_px), "lastTraded": None},
                            "lowPrice": {"bid": min(prev_close, live_px), "ask": min(prev_close, live_px), "lastTraded": None},
                            "closePrice": {"bid": live_px, "ask": live_px, "lastTraded": None}
                        }
                        candele_locali.append(synth_candle)
                        salva_candele_locali(nome, tf, candele_locali)
                        print_log(nome, f"🕯️ Candela ({tf}) sintetizzata localmente: {snap_synth} a {live_px:.5f}.")
            prices = []
                
        # Unione e aggiornamento del buffer locale di 100 candele
        if prices and isinstance(prices, list) and len(prices) >= 2:
            snap_esistenti = set(c.get("snapshotTime") for c in candele_locali if "snapshotTime" in c)
            for pr in prices[:-1]: # tutte le chiuse tranne l'ancora aperta
                st = pr.get("snapshotTime")
                if st and st not in snap_esistenti:
                    # Verifica che i prezzi non siano nulli o negativi (glitch API IG)
                    try:
                        b_o, a_o = pr['openPrice']['bid'], pr['openPrice']['ask']
                        b_h, a_h = pr['highPrice']['bid'], pr['highPrice']['ask']
                        b_l, a_l = pr['lowPrice']['bid'], pr['lowPrice']['ask']
                        b_c, a_c = pr['closePrice']['bid'], pr['closePrice']['ask']
                        if all(v is not None and 0 < v < 1e8 for v in [b_o, a_o, b_h, a_h, b_l, a_l, b_c, a_c]):
                            candele_locali.append(pr)
                            snap_esistenti.add(st)
                    except Exception:
                        pass
            salva_candele_locali(nome, tf, candele_locali)
            
        if len(candele_locali) < 2:
            print_log(nome, "⚠️ Dati candele non ancora sufficienti.")
            continue
            
        # 2. Controllo Timestamp Lock
        last_closed_candle = candele_locali[-1]
        snapshot_time = last_closed_candle.get("snapshotTime", "")
        saved_candle_time = dati.get("last_candle_time", "")
        
        if snapshot_time == saved_candle_time and not needs_start:
            continue
            
        print_log(nome, f"DEBUG: Nuova candela chiusa rilevata ({tf}). Snapshot: {snapshot_time}")
        
        # Seed dello storico (tutte le candele chiuse TRANNE l'ultima, che verrà aggiunta da on_candle_close)
        storic_candles = []
        for pr in candele_locali[:-1]: 
            try:
                bid_o, ask_o = pr['openPrice']['bid'], pr['openPrice']['ask']
                bid_h, ask_h = pr['highPrice']['bid'], pr['highPrice']['ask']
                bid_l, ask_l = pr['lowPrice']['bid'], pr['lowPrice']['ask']
                bid_c, ask_c = pr['closePrice']['bid'], pr['closePrice']['ask']
                if all(v is not None and 0 < v < 1e8 for v in [bid_o, ask_o, bid_h, ask_h, bid_l, ask_l, bid_c, ask_c]):
                    c = Candle((bid_o+ask_o)/2, (bid_h+ask_h)/2, (bid_l+ask_l)/2, (bid_c+ask_c)/2)
                    storic_candles.append(c)
            except Exception: pass
            
        engine.seed_history(storic_candles)
        print_log(nome, f"DEBUG: engine.candles ha {len(engine.candles)} elementi. KJ periods: {engine.config.get('kj_periods', 26)}")
        
        tk_val = engine._calculate_donchian(engine.config.get("tk_periods", 9))
        kj_val = engine._calculate_donchian(engine.config.get("kj_periods", 26))
        
        # Salva SEMPRE tk, kj e il timestamp della candela
        aggiorna_memoria(nome, {
            "current_tk": tk_val, 
            "current_kj": kj_val,
            "last_candle_time": snapshot_time
        })
        
        pos_core = dati.get("posizioni_core", [])
        pos_incr = dati.get("posizioni_incr", [])
        
        if not engine.is_running and (pos_core or pos_incr or (stato_corrente != "FLAT" and stato_corrente != "IN_ATTESA") or auto_restart):
            engine.is_running = True
            engine.current_direction = stato_corrente if stato_corrente in ("LONG", "SHORT") else ("FLAT" if auto_restart else direzione)
            for c_d in pos_core:
                dir_pos = c_d.get("direction", engine.current_direction)
                pos = engine.pm.open_core(c_d.get("entry", 0), c_d.get("size", 1), dir_pos)
                pos.ticket = c_d.get("ticket")
            for i_d in pos_incr:
                dir_pos = i_d.get("direction", engine.current_direction)
                pos = engine.pm.open_increment(i_d.get("entry", 0), i_d.get("size", 1), dir_pos)
                pos.ticket = i_d.get("ticket")

        # Se eravamo FLAT e non c'è needs_start e non c'è auto_restart, abbiamo solo aggiornato le linee, possiamo saltare il calcolo trading
        if not engine.is_running and not needs_start and not auto_restart:
            continue

        # Estrai candela chiusa (l'ultima nel buffer locale)
        last = candele_locali[-1]
        try:
            bid_o, ask_o = last['openPrice']['bid'], last['openPrice']['ask']
            bid_h, ask_h = last['highPrice']['bid'], last['highPrice']['ask']
            bid_l, ask_l = last['lowPrice']['bid'], last['lowPrice']['ask']
            bid_c, ask_c = last['closePrice']['bid'], last['closePrice']['ask']
            closed_candle = Candle((bid_o+ask_o)/2, (bid_h+ask_h)/2, (bid_l+ask_l)/2, (bid_c+ask_c)/2)
        except Exception:
            continue
            
        valuta = CONFIG_STRUMENTI[nome]["valuta"]
        dec = CONFIG_STRUMENTI[nome]["decimali"]
        
        # Se lo stato su dashboard è FLAT ma l'utente ha premuto AVVIA LONG/SHORT, forziamo l'engine
        if needs_start:
            # Controllo preventivo di sicurezza Kijun con il prezzo live corrente
            px_live = prezzi_live.get(nome)
            px_start = px_live if (px_live and isinstance(px_live, (int, float))) else closed_candle.close
            
            if direzione == "LONG" and kj_val is not None and px_start < kj_val:
                print_log(nome, f"🛑 [BLOCCO SICUREZZA] Avvio manuale LONG bloccato: Prezzo ({px_start:.{dec}f}) SOTTO la Kijun ({kj_val:.{dec}f}).")
                invia_notifica(f"🛑 AVVIO RIFIUTATO: {nome}", f"[{nome}] Impossibile avviare LONG: Prezzo ({px_start:.{dec}f}) < Kijun ({kj_val:.{dec}f}).", "no_entry")
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "tipo_strategia": "TREND", "msg_manuale": f"❌ Avvio LONG bloccato: Prezzo ({px_start:.{dec}f}) sotto Kijun ({kj_val:.{dec}f})."})
                continue
            elif direzione == "SHORT" and kj_val is not None and px_start > kj_val:
                print_log(nome, f"🛑 [BLOCCO SICUREZZA] Avvio manuale SHORT bloccato: Prezzo ({px_start:.{dec}f}) SOPRA la Kijun ({kj_val:.{dec}f}).")
                invia_notifica(f"🛑 AVVIO RIFIUTATO: {nome}", f"[{nome}] Impossibile avviare SHORT: Prezzo ({px_start:.{dec}f}) > Kijun ({kj_val:.{dec}f}).", "no_entry")
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "tipo_strategia": "TREND", "msg_manuale": f"❌ Avvio SHORT bloccato: Prezzo ({px_start:.{dec}f}) sopra Kijun ({kj_val:.{dec}f})."})
                continue

            pos = engine.start(px_start, direzione)
            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, direzione, size_i, headers, dec, etichetta="[CORE]")
            if ok:
                pos.entry_price = real_lvl if real_lvl else closed_candle.close
                pos.ticket = deal_id
                ora_str = now_it().strftime("%d/%m %H:%M:%S")
                msg = f"🚀 Apertura Core {direzione} a {pos.entry_price}"
                aggiorna_memoria(nome, {
                    "stato": direzione, 
                    "direzione": direzione, 
                    "posizioni_core": [pos.to_dict()], 
                    "posizioni_incr": [], 
                    "storico_wip_trend": [f"[{ora_str}] {msg}"]
                })
                print_log(nome, f"🚀 Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.")
                invia_notifica(f"🚀 AVVIO TREND: {nome}", f"[{nome}] Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.", "rocket")
            else:
                engine.reset()
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "errore_avvio": True})
            continue
                
        # Alimenta la candela all'Engine
        events = engine.on_candle_close(closed_candle, next_open_price=closed_candle.close)
        processa_eventi_engine(nome, engine, events, epic, valuta, size_i, headers, dec, auto_restart, dati)

if __name__ == "__main__":
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        porta_unica = 15000 + int(hashlib.md5(f"{NOME_CONTO}_TREND".encode()).hexdigest(), 16) % 40000
        lock_socket.bind(("127.0.0.1", porta_unica))
    except socket.error:
        print(f"\n🚨 ERRORE CRITICO: Il Motore Trend per il conto '{NOME_CONTO}' è già in esecuzione!")
        sys.exit()

    print(f"🚀 Avvio Motore Trend Multi-Timeframe per il conto {NOME_CONTO}...")
    
    # Eseguiamo un ciclo immediato all'avvio per forzare le inizializzazioni
    try:
        esegui_ciclo_trend()
    except Exception as e:
        print(f"Errore primo ciclo Trend: {e}")
        traceback.print_exc()

    while True:
        try:
            esegui_ciclo_trend()
        except Exception as e:
            print(f"Errore ciclo Trend: {e}")
            traceback.print_exc()
        time.sleep(2.0)
