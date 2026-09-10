import json
import time
import os
import requests
import traceback
import datetime
from ig_request_manager import ig_api_request, rate_limiter
from datetime import timedelta
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
from macchinetta_trend.position_manager import PositionManager, Position

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
ULTIMO_LOG_ATTESA = {}
LIVE_OHLC_TRACKER = {}
LOCAL_CANDELE_CACHE = {}
LAST_RADAR_SCAN = 0

# --- TRACKER E COOLDOWN DEI TENTATIVI (REGOLA FERREA MAX 5 TENTATIVI) ---
COOLDOWN_OPERAZIONI = {}
CANDLE_FAILURES = {}

def is_operazione_in_cooldown(tipo_op, id_chiave):
    t_scadenza = COOLDOWN_OPERAZIONI.get((tipo_op, str(id_chiave)), 0)
    return time.time() < t_scadenza

def attiva_cooldown_operazione(tipo_op, id_chiave, durata_sec=300):
    COOLDOWN_OPERAZIONI[(tipo_op, str(id_chiave))] = time.time() + durata_sec

if len(sys.argv) < 2:
    print("🚨 ERRORE: Devi specificare il nome della cartella del conto all'avvio!")
    sys.exit()

NOME_CONTO = sys.argv[1]
if not os.path.isdir(NOME_CONTO):
    print(f"🚨 ERRORE: La cartella '{NOME_CONTO}' non esiste.")
    sys.exit()

os.chdir(NOME_CONTO)
if ".." not in sys.path:
    sys.path.insert(0, "..")
if "/data" not in sys.path:
    sys.path.insert(0, "/data")
BASE_URL = "https://api.ig.com/gateway/deal" if "_REALE" in NOME_CONTO.upper() else "https://demo-api.ig.com/gateway/deal"
config = dotenv_values(".env")

# Vocabolario base
CONFIG_STRUMENTI = {
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD", "valore_punto": 1},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "EUR/JPY": {"epic": "CS.D.EURJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "GBP/JPY": {"epic": "CS.D.GBPJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF", "valore_punto": 1},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1.0, "decimali": 2, "valuta": "EUR", "valore_punto": 1},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1.0, "decimali": 2, "valuta": "EUR", "valore_punto": 1},
    "Oil - US Crude": {"epic": "CC.D.CL.UBE.IP", "moltiplicatore": 1.0, "decimali": 1, "valuta": "EUR", "valore_punto": 1}
}

def pips_to_price(nome, pips):
    """Restituisce il delta di prezzo corrispondente a N pips reali per lo strumento."""
    mult = CONFIG_STRUMENTI.get(nome, {}).get("moltiplicatore", 0.0001)
    return pips * mult

def format_price_ig(nome, price):
    """Arrotonda e formatta il prezzo esattamente con i decimali richiesti da IG."""
    dec = CONFIG_STRUMENTI.get(nome, {}).get("decimali", 5)
    return round(float(price), dec)

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

FILE_NOTIFICHE_SISTEMA_DEDUP = "notifiche_sistema_dedup.json"

def invia_notifica_sistema(chiave_evento, titolo, messaggio, tags="information_source", cooldown_sec=14400):
    """
    Invia una notifica unificata a livello di MACCHINETTA (de-duplicata per tutti i conti e pod).
    Se un qualsiasi pod o conto ha già inviato questa notifica entro il cooldown, non viene reinviata.
    """
    topic = config.get("NTFY_TOPIC")
    if not topic:
        return
    
    target_path = None
    for base in ["/data/Logs_e_Cache", "../Logs_e_Cache", "Logs_e_Cache", "."]:
        if os.path.exists(base):
            target_path = os.path.join(base, FILE_NOTIFICHE_SISTEMA_DEDUP)
            break
    if not target_path:
        target_path = FILE_NOTIFICHE_SISTEMA_DEDUP

    now_ts = time.time()
    stato_notifiche = {}
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                stato_notifiche = json.load(f)
        except Exception:
            stato_notifiche = {}

    last_sent = stato_notifiche.get(chiave_evento, 0)
    if now_ts - last_sent < cooldown_sec:
        return

    # Registra subito il timestamp per prevenire race conditions tra pod
    stato_notifiche[chiave_evento] = now_ts
    stato_notifiche = {k: v for k, v in stato_notifiche.items() if (now_ts - v) < 7 * 86400}
    try:
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(stato_notifiche, f, indent=2)
    except Exception:
        pass

    try:
        orario = now_it().strftime("%H:%M:%S")
        messaggio_con_orario = f"[{orario}] {messaggio}"
        headers = {
            "Title": f"[MACCHINETTA] {titolo}".encode('utf-8'),
            "Tags": tags
        }
        requests.post(f"https://ntfy.sh/{topic}", data=messaggio_con_orario.encode('utf-8'), headers=headers, timeout=5)
        print_log("SISTEMA", f"📢 Notifica di Sistema inviata: {titolo}")
    except Exception as e:
        print_log("SISTEMA", f"⚠️ Errore invio notifica Sistema: {e}")

def verifica_notifiche_sistema_transizioni():
    """Verifica e notifica le transizioni temporali globali della Macchinetta (una sola volta a livello di sistema)."""
    now_t = now_it()
    wd = now_t.weekday()
    t = now_t.time()

    # 1. Venerdì ore 22:45 -> Sospensione operatività weekend
    if wd == 4 and datetime.time(22, 45) <= t <= datetime.time(23, 0):
        chiave = f"freeze_weekend_{now_t.strftime('%Y_%m_%d')}"
        invia_notifica_sistema(
            chiave,
            "SOSPENSIONE WEEKEND",
            "Fino a domenica alle 21:57:59",
            tags="pause_button",
            cooldown_sec=7200
        )

    # 2. Domenica ore 21:58 -> Inizio Pausa Rollover apertura mercati
    elif wd == 6 and datetime.time(21, 58) <= t <= datetime.time(22, 15):
        chiave = f"rollover_domenica_{now_t.strftime('%Y_%m_%d')}"
        invia_notifica_sistema(
            chiave,
            "START PAUSA ROLLOVER",
            "Fino alle 00:15",
            tags="crescent_moon",
            cooldown_sec=7200
        )

    # 3. Lun-Gio ore 22:45 -> Rollover notturno
    elif wd in (0, 1, 2, 3) and datetime.time(22, 45) <= t <= datetime.time(23, 0):
        chiave = f"rollover_notte_{now_t.strftime('%Y_%m_%d')}"
        invia_notifica_sistema(
            chiave,
            "PAUSA ROLLOVER NOTTURNA",
            "Fino alle 00:15",
            tags="crescent_moon",
            cooldown_sec=7200
        )

    # 4. Lunedì-Venerdì ore 00:15 -> Fine Rollover e ripresa attività normale
    elif wd in (0, 1, 2, 3, 4) and datetime.time(0, 15) <= t <= datetime.time(0, 30):
        chiave = f"fine_rollover_{now_t.strftime('%Y_%m_%d')}"
        invia_notifica_sistema(
            chiave,
            "STOP PAUSA ROLLOVER",
            "Ripresa regolare operatività",
            tags="sunny",
            cooldown_sec=7200
        )

    # 5. Alert Quota Storica IG se in esaurimento (controllo centralizzato)
    # Notifica SOLO quando la quota sta scendendo (fascia 500-1000). 
    # Quando è < 500 o già azzerata a 0, il Circuit Breaker è già attivo e non si inviano alert ripetuti in attesa del reset domenicale.
    rem_quota = get_remaining_quota_ig()
    if 500 <= rem_quota < 1000:
        chiave = f"quota_ig_warning_{now_t.strftime('%Y_%m_%d')}"
        invia_notifica_sistema(
            chiave,
            "DATI IG IN ESAURIMENTO",
            f"Quota residua: {rem_quota}. Attivazione protezione automatica",
            tags="warning",
            cooldown_sec=43200
        )

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
        if len(righe) > 500:
            righe = righe[-500:]
        with open(CONSOLE_LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(righe)
    except Exception:
        pass

CACHE_ULTIMI_KJ_FILE = "cache_ultimi_rilevamenti_kj.json"

def aggiorna_cache_ultimo_kj_motore(nome, tf_lbl, riga):
    try:
        data = {}
        if os.path.exists(CACHE_ULTIMI_KJ_FILE):
            with open(CACHE_ULTIMI_KJ_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        if nome not in data:
            data[nome] = {}
        data[nome][tf_lbl] = riga
        tmp = f"{CACHE_ULTIMI_KJ_FILE}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, CACHE_ULTIMI_KJ_FILE)
    except Exception:
        pass

def get_eur_rate(valuta, prezzi):
    if valuta == "EUR":
        return 1.0
    eur_usd = prezzi.get("EUR/USD")
    eur_jpy = prezzi.get("EUR/JPY")
    usd_jpy = prezzi.get("USD/JPY")
    gbp_usd = prezzi.get("GBP/USD")
    if not eur_usd and eur_jpy and usd_jpy:
        eur_usd = eur_jpy / usd_jpy
    elif not eur_usd:
        eur_gbp = prezzi.get("EUR/GBP")
        if eur_gbp and gbp_usd:
            eur_usd = eur_gbp * gbp_usd
        elif gbp_usd:
            eur_usd = 1.08
        else:
            eur_usd = 1.08
    if valuta == "USD":
        return 1.0 / eur_usd
    if valuta == "GBP":
        return (gbp_usd / eur_usd) if gbp_usd else (1.25 / eur_usd)
    if valuta == "CAD":
        usd_cad = prezzi.get("USD/CAD")
        if usd_cad: return 1.0 / (eur_usd * usd_cad)
    if valuta == "CHF":
        usd_chf = prezzi.get("USD/CHF")
        if usd_chf: return 1.0 / (eur_usd * usd_chf)
    if valuta == "JPY":
        if eur_jpy: return 1.0 / eur_jpy
        if usd_jpy: return 1.0 / (eur_usd * usd_jpy)
    if valuta == "NZD":
        aud_nzd = prezzi.get("AUD/NZD")
        aud_cad = prezzi.get("AUD/CAD")
        usd_cad = prezzi.get("USD/CAD")
        if aud_nzd and aud_cad and usd_cad:
            eur_cad = eur_usd * usd_cad
            eur_nzd = (eur_cad / aud_cad) * aud_nzd
            return 1.0 / eur_nzd
        return 0.58 / eur_usd
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
ig_rate_limiter = rate_limiter

def formatta_numero(valore, dec):
    if valore is None: return None
    r = round(float(valore), dec)
    return f"{r:.{dec}f}"

def chiamata_api_sicura(metodo, url, headers, payload=None, max_retries=4):
    headers_req = headers.copy()
    headers_req["Version"] = "2"
    return ig_api_request(metodo, url, headers_req, payload=payload, timeout=10, logger_func=print_log)

def verifica_conferma_deal(deal_ref, headers):
    h_conf = headers.copy()
    h_conf["Version"] = "1"
    for _ in range(3): 
        try:
            time.sleep(1.0)
            r = ig_api_request('GET', f"{BASE_URL}/confirms/{deal_ref}", h_conf, timeout=10, logger_func=print_log)
            if r and r.status_code == 200:
                data = r.json()
                if data.get("dealStatus") == "ACCEPTED":
                    return True, data
                elif data.get("dealStatus") == "REJECTED":
                    return False, data.get("reason", "Unknown")
        except Exception:
            pass
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
    
    id_op = f"{nome_strumento}_{etichetta}_{direzione}"
    if is_operazione_in_cooldown("ORDINE_MERCATO", id_op):
        print_log(nome_strumento, f"⏳ [COOLDOWN] Operazione {etichetta} {direzione} temporaneamente sospesa dopo 5 fallimenti precedenti.")
        return False, None, None

    MAX_TENTATIVI = 5
    for tentativo in range(1, MAX_TENTATIVI + 1): 
        try:
            r = ig_api_request('POST', f"{BASE_URL}/positions/otc", headers, payload=p, timeout=10, logger_func=print_log)
            if r and r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                real_level = None
                deal_id = None
                if deal_ref:
                    accettato, confirm_data = verifica_conferma_deal(deal_ref, headers)
                    if not accettato:
                        print_log(nome_strumento, f"❌ [IG REJECT] {etichetta} {direzione}: {confirm_data}")
                        if tentativo < MAX_TENTATIVI:
                            time.sleep(3.0)
                        continue
                    if isinstance(confirm_data, dict):
                        if confirm_data.get("level") is not None: real_level = float(confirm_data.get("level"))
                        if confirm_data.get("dealId"): deal_id = confirm_data.get("dealId")

                if real_level is None:
                    try:
                        time.sleep(1.0)
                        resp_p = ig_api_request('GET', f"{BASE_URL}/positions", headers, timeout=10, logger_func=print_log)
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
                resp_txt = r.text if r else "Nessuna risposta"
                if tentativo < MAX_TENTATIVI:
                    print_log(nome_strumento, f"⚠️ [TENTATIVO {tentativo}/{MAX_TENTATIVI}] Rifiuto API {etichetta} {direzione}: {resp_txt}")
                    time.sleep(3.0)
        except Exception as e:
            if tentativo < MAX_TENTATIVI:
                print_log(nome_strumento, f"⚠️ [TENTATIVO {tentativo}/{MAX_TENTATIVI}] Eccezione Rete su {etichetta} {direzione}: {e}")
                time.sleep(3.0)
            
    print_log(nome_strumento, f"🛑 [TENTATIVI (5)] 5 tentativi per invio ordine a mercato {etichetta} {direzione} non andati a buon fine. Operazione interrotta.")
    attiva_cooldown_operazione("ORDINE_MERCATO", id_op, durata_sec=300)
    return False, None, None

def chiudi_parziale(nome_strumento, dealId, dir_chiusura, size, headers, etichetta="[POSIZIONE]"):
    id_op = f"DEAL_{dealId}"
    if is_operazione_in_cooldown("CHIUSURA", id_op):
        return False

    h = headers.copy()
    h["Version"] = "1"
    h["_method"] = "DELETE"
    size_str = str(int(size)) if float(size).is_integer() else str(size)
    p = {"dealId": dealId, "direction": dir_chiusura, "size": size_str, "orderType": "MARKET"}
    
    MAX_TENTATIVI = 5
    for tentativo in range(1, MAX_TENTATIVI + 1):
        try:
            r = ig_api_request('POST', f"{BASE_URL}/positions/otc", h, payload=p, timeout=10, logger_func=print_log)
            if r and r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                if deal_ref:
                    accettato, confirm_data = verifica_conferma_deal(deal_ref, headers)
                    if not accettato:
                        reason = str(confirm_data)
                        if "POSITION_NOT_FOUND" in reason or "deal-not-found" in reason:
                            print_log(nome_strumento, f"ℹ️ Chiusura {etichetta} ({dealId}): posizione già chiusa su IG.")
                            return True
                        if tentativo < MAX_TENTATIVI:
                            print_log(nome_strumento, f"⚠️ [TENTATIVO {tentativo}/{MAX_TENTATIVI}] [IG REJECT] Chiusura {etichetta}: {confirm_data}")
                            time.sleep(2.0)
                    else:
                        print_log(nome_strumento, f"✅ Chiusura {etichetta} eseguita con successo.")
                        return True
                else:
                    print_log(nome_strumento, f"✅ Chiusura {etichetta} inviata.")
                    return True
            else:
                resp_txt = r.text if r else "Nessuna risposta"
                if r and r.status_code == 400 and ("deal-not-found" in resp_txt or "POSITION_NOT_FOUND" in resp_txt):
                    print_log(nome_strumento, f"ℹ️ Chiusura {etichetta} ({dealId}): già liquidata su IG.")
                    return True
                if tentativo < MAX_TENTATIVI:
                    print_log(nome_strumento, f"⚠️ [TENTATIVO {tentativo}/{MAX_TENTATIVI}] Errore Chiusura {etichetta} ({dealId}): {resp_txt}")
                    time.sleep(2.0)
        except Exception as e:
            if tentativo < MAX_TENTATIVI:
                print_log(nome_strumento, f"⚠️ [TENTATIVO {tentativo}/{MAX_TENTATIVI}] Eccezione su Chiusura {etichetta}: {e}")
                time.sleep(2.0)
            
    print_log(nome_strumento, f"🛑 [TENTATIVI (5)] 5 tentativi per chiusura posizione {etichetta} ({dealId}) non andati a buon fine. Operazione interrotta per sicurezza.")
    attiva_cooldown_operazione("CHIUSURA", id_op, durata_sec=600)
    return False

def conta_posizioni_aperte_epic(epic, headers):
    """Conta quante posizioni reali sono attualmente aperte su IG per questo epic."""
    try:
        r = ig_api_request("GET", f"{BASE_URL}/positions", headers=headers, timeout=10, logger_func=print_log)
        if r and r.status_code == 200:
            pos = [p for p in r.json().get('positions', []) if p['market']['epic'] == epic]
            return len(pos)
    except Exception as e:
        print_log("SISTEMA", f"Errore verifica posizioni IG: {e}")
    return 0

def pulisci_posizioni_epic(nome, epic, headers):
    """Chiude le posizioni aperte per quell'epic su IG con pacing anti-ingolfamento."""
    try:
        r = ig_api_request("GET", f"{BASE_URL}/positions", headers=headers, timeout=10, logger_func=print_log)
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

def is_valid_candele(data, tf=None, check_freshness=True):
    if not data or len(data) < 2:
        return False
    try:
        highs = [float(c.get('highPrice', {}).get('bid', c.get('high', 0))) for c in data if c.get('highPrice', {}).get('bid') or c.get('high')]
        lows = [float(c.get('lowPrice', {}).get('bid', c.get('low', 0))) for c in data if c.get('lowPrice', {}).get('bid') or c.get('low')]
        if not highs or not lows:
            return False
        if (max(highs) - min(lows)) <= 1e-6:
            return False
            
        if tf and tf in TF_MAP:
            expected_min = TF_MAP[tf]
            times = []
            for c in data[:10]:
                st_str = c.get('snapshotTime')
                if st_str:
                    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:00", "%Y-%m-%d %H:%M:%S"):
                        try:
                            times.append(datetime.datetime.strptime(st_str, fmt))
                            break
                        except Exception:
                            pass
            if len(times) >= 2:
                delta_m = round((times[1] - times[0]).total_seconds() / 60.0)
                if expected_min <= 15 and delta_m >= 30:
                    return False
                if expected_min == 60 and (delta_m < 30 or delta_m > 120):
                    return False
                if expected_min >= 1440 and delta_m < 720:
                    return False
                    
            # Controllo freschezza ultima candela (solo se richiesto esplicitamente)
            if check_freshness and not is_weekend_active():
                st_last = data[-1].get('snapshotTime')
                if st_last:
                    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:00", "%Y-%m-%d %H:%M:%S"):
                        try:
                            last_dt = datetime.datetime.strptime(st_last, fmt).replace(tzinfo=TZ_ITALIA)
                            age_m = (now_it() - last_dt).total_seconds() / 60.0
                            max_age_tollerata = max(expected_min * 4, 30)
                            if age_m > max_age_tollerata:
                                return False
                            break
                        except Exception:
                            pass
        return True
    except Exception:
        return False

def aggrega_candele_multitf(candele_src, tf_src, tf_dest):
    m_src = TF_MAP.get(tf_src, 5)
    m_dest = TF_MAP.get(tf_dest, 60)
    if m_dest <= m_src:
        return []
    # Raggruppa le candele sorgente in base al boundary esatto del timeframe destinazione
    groups = {}
    for c in candele_src:
        st_str = c.get("snapshotTime")
        if not st_str:
            continue
        dt = None
        for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M:00", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.datetime.strptime(st_str, fmt)
                break
            except Exception:
                pass
        if not dt:
            continue
        offset = 60 if m_dest in (60, 240, 1440) else 0
        min_tot = dt.hour * 60 + dt.minute
        boundary_min = ((min_tot - offset) // m_dest) * m_dest + offset
        base_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        target_dt = base_dt + datetime.timedelta(minutes=boundary_min)
        target_snap = target_dt.strftime("%Y/%m/%d %H:%M:00")
        
        if target_snap not in groups:
            groups[target_snap] = []
        groups[target_snap].append(c)

    res = []
    for snap_key in sorted(groups.keys()):
        chunk = groups[snap_key]
        try:
            o_bid = float(chunk[0].get('openPrice', {}).get('bid', chunk[0].get('open', 0)))
            h_bid = max(float(c.get('highPrice', {}).get('bid', c.get('high', 0))) for c in chunk)
            l_bid = min(float(c.get('lowPrice', {}).get('bid', c.get('low', 0))) for c in chunk)
            c_bid = float(chunk[-1].get('closePrice', {}).get('bid', chunk[-1].get('close', 0)))
            res.append({
                "snapshotTime": snap_key,
                "openPrice": {"bid": o_bid, "ask": o_bid, "lastTraded": None},
                "highPrice": {"bid": h_bid, "ask": h_bid, "lastTraded": None},
                "lowPrice": {"bid": l_bid, "ask": l_bid, "lastTraded": None},
                "closePrice": {"bid": c_bid, "ask": c_bid, "lastTraded": None}
            })
        except Exception:
            pass
    return res

def allinea_candele_live(candele_locali, nome, tf, px_live):
    """Proietta il prezzo live per formare l'ombra della candela ATTUALE, senza inventare i buchi."""
    if not candele_locali or not px_live or not isinstance(px_live, (int, float)):
        return candele_locali
    if is_weekend_active():
        return candele_locali
        
    now_t = now_it()
    min_tf = TF_MAP.get(tf, 5)
    offset = 60 if min_tf in (60, 240, 1440) else 0
    min_tot = now_t.hour * 60 + now_t.minute
    boundary_min = ((min_tot - offset) // min_tf) * min_tf + offset
    base_dt = now_t.replace(hour=0, minute=0, second=0, microsecond=0)
    target_dt = base_dt + datetime.timedelta(minutes=boundary_min)
    
    try:
        last_t_str = candele_locali[-1].get("snapshotTime")
        last_dt = datetime.datetime.strptime(last_t_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ_ITALIA)
    except Exception:
        return candele_locali

    if last_dt >= target_dt:
        return candele_locali
        
    snap_synth = target_dt.strftime("%Y/%m/%d %H:%M:00")
    last_c = candele_locali[-1]
    try:
        prev_close = (last_c['closePrice']['bid'] + last_c['closePrice']['ask']) / 2
    except Exception:
        prev_close = px_live
        
    synth_candle = {
        "snapshotTime": snap_synth,
        "openPrice": {"bid": prev_close, "ask": prev_close, "lastTraded": None},
        "highPrice": {"bid": max(prev_close, px_live), "ask": max(prev_close, px_live), "lastTraded": None},
        "lowPrice": {"bid": min(prev_close, px_live), "ask": min(prev_close, px_live), "lastTraded": None},
        "closePrice": {"bid": px_live, "ask": px_live, "lastTraded": None}
    }
    return list(candele_locali) + [synth_candle]

def carica_candele_locali(nome, tf, px_live=None):
    # Se presente in cache locale in memoria e valida (almeno 55 barre), usa subito la cache senza toccare il disco
    if (nome, tf) in LOCAL_CANDELE_CACHE:
        cached = LOCAL_CANDELE_CACHE[(nome, tf)]
        if len(cached) >= 55 and is_valid_candele(cached, tf, check_freshness=False):
            if px_live and isinstance(px_live, (int, float)):
                return allinea_candele_live(cached, nome, tf, px_live)
            return cached

    clean = nome.replace("/", "_").replace(" ", "_")
    fpath = get_file_candele(nome, tf)
    
    # 1. Controlla prima il file specifico locale
    local_data = []
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and is_valid_candele(data, tf, check_freshness=False):
                    local_data = data
                    if len(data) >= 55:
                        LOCAL_CANDELE_CACHE[(nome, tf)] = data[-60:]
                        if px_live and isinstance(px_live, (int, float)):
                            return allinea_candele_live(data, nome, tf, px_live)
                        return data
        except Exception:
            pass
            
    # 2. Cerca across accounts (se ha almeno 55 barre ed è valido per il tf)
    for altro in ["FIORDOK_DEMO", "BONGIOLO_DEMO", "DANY_DEMO", "Logs_e_Cache"]:
        alt_path = os.path.join("..", altro, f"candele_{clean}_{tf}.json")
        if os.path.exists(alt_path):
            try:
                with open(alt_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    if len(d) >= 55 and is_valid_candele(d, tf, check_freshness=False):
                        salva_candele_locali(nome, tf, d)
                        LOCAL_CANDELE_CACHE[(nome, tf)] = d[-60:]
                        if px_live and isinstance(px_live, (int, float)):
                            return allinea_candele_live(d, nome, tf, px_live)
                        return d
            except Exception:
                pass

    # 3. Aggregazione da timeframe minori a maggiori
    tf_order = ["MINUTE_5", "MINUTE_15", "HOUR", "HOUR_4", "DAY"]
    for tf_try in tf_order:
        if tf_try == tf or TF_MAP.get(tf_try, 0) >= TF_MAP.get(tf, 0):
            continue
        fname = f"candele_{clean}_{tf_try}.json"
        for altro in ["FIORDOK_DEMO", "BONGIOLO_DEMO", "DANY_DEMO", ".", "Logs_e_Cache"]:
            alt_path = os.path.join("..", altro, fname) if altro != "." else fname
            if os.path.exists(alt_path):
                try:
                    with open(alt_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                        if is_valid_candele(d, tf_try, check_freshness=False):
                            c_agg = aggrega_candele_multitf(d, tf_try, tf)
                            # Se abbiamo storico locale precedente, FONDILO (merge) invece di sovrascrivere!
                            if local_data:
                                snaps = {c.get("snapshotTime"): c for c in local_data if c.get("snapshotTime")}
                                for c in c_agg:
                                    s = c.get("snapshotTime")
                                    if s:
                                        snaps[s] = c
                                merged = sorted(snaps.values(), key=lambda x: x.get("snapshotTime", ""))[-60:]
                                if len(merged) >= 55 and is_valid_candele(merged, tf, check_freshness=False):
                                    if px_live and isinstance(px_live, (int, float)):
                                        merged = allinea_candele_live(merged, nome, tf, px_live)
                                    salva_candele_locali(nome, tf, merged)
                                    LOCAL_CANDELE_CACHE[(nome, tf)] = merged[-60:]
                                    return merged
                            # Se non c'è storico locale, accetta l'aggregazione SOLO se ha almeno 55 candele!
                            elif len(c_agg) >= 55 and is_valid_candele(c_agg, tf, check_freshness=False):
                                if px_live and isinstance(px_live, (int, float)):
                                    c_agg = allinea_candele_live(c_agg, nome, tf, px_live)
                                salva_candele_locali(nome, tf, c_agg)
                                LOCAL_CANDELE_CACHE[(nome, tf)] = c_agg[-60:]
                                return c_agg
                except Exception:
                    pass

    # 4. Fallback: se local_data esiste (anche se con meno di 55 barre), usalo piuttosto che inventare dati
    if local_data:
        LOCAL_CANDELE_CACHE[(nome, tf)] = local_data[-60:]
        if px_live and isinstance(px_live, (int, float)):
            return allinea_candele_live(local_data, nome, tf, px_live)
        return local_data

    # 5. Ultima ratio: solo se non c'è assolutamente nessun dato
    if px_live and isinstance(px_live, (int, float)):
        res = []
        now_dt = now_it()
        min_tf = TF_MAP.get(tf, 5)
        for i in range(60, 0, -1):
            t = now_dt - datetime.timedelta(minutes=i * min_tf)
            snap = t.strftime("%Y/%m/%d %H:%M:00")
            res.append({
                "snapshotTime": snap,
                "openPrice": {"bid": px_live, "ask": px_live, "lastTraded": None},
                "highPrice": {"bid": px_live, "ask": px_live, "lastTraded": None},
                "lowPrice": {"bid": px_live, "ask": px_live, "lastTraded": None},
                "closePrice": {"bid": px_live, "ask": px_live, "lastTraded": None}
            })
        salva_candele_locali(nome, tf, res)
        return res
        
    return []

FILE_QUOTA_IG = "ig_quota_status.json"

def get_remaining_quota_ig():
    for base in [".", ".."]:
        p = os.path.join(base, FILE_QUOTA_IG)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    q = json.load(f)
                    return q.get("remainingAllowance", 10000)
            except Exception:
                pass
    return 10000

def salva_quota_ig(allowance_dict):
    if not allowance_dict or not isinstance(allowance_dict, dict):
        return
    for base in [".", ".."]:
        p = os.path.join(base, FILE_QUOTA_IG)
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(allowance_dict, f, indent=2)
        except Exception:
            pass

def salva_candele_locali(nome, tf, candele_list):
    clean = nome.replace("/", "_").replace(" ", "_")
    fname = f"candele_{clean}_{tf}.json"
    buffer_60 = candele_list[-60:]
    LOCAL_CANDELE_CACHE[(nome, tf)] = buffer_60
    
    target_dirs = [".", "Logs_e_Cache", "../Logs_e_Cache", "/data/Logs_e_Cache"]
    for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
        target_dirs.extend([f"../{acc}", f"/data/{acc}", acc])
        
    for d in set(target_dirs):
        if os.path.exists(d) and os.path.isdir(d):
            dest = os.path.join(d, fname)
            try:
                tmp = f"{dest}.tmp.{os.getpid()}"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(buffer_60, f, indent=2)
                os.replace(tmp, dest)
            except Exception:
                pass

# --- FUNZIONI CORE ---
def scarica_candele(epic, timeframe, limit=60, headers=None):
    # REGOLA FERREA: MAI richiedere più di 60 candele per nessun motivo (budget quota IG blindato)
    limit = min(int(limit or 60), 60)
    
    # CIRCUIT BREAKER: se la quota residua nota scende sotto 500 punti, stop chiamate preventivo
    rem_quota = get_remaining_quota_ig()
    if rem_quota < 500:
        print_log("SISTEMA", f"🛑 CIRCUIT BREAKER ATTIVO: Quota residua dati storici IG ({rem_quota}) inferiore a 500. Chiamata bloccata a monte.")
        return "QUOTA_ESAURITA"

    k_candle = (epic, timeframe)
    if is_operazione_in_cooldown("CANDELE", f"{epic}_{timeframe}"):
        return []

    h = headers.copy()
    h["Version"] = "3"
    url = f"{BASE_URL}/prices/{epic}?resolution={timeframe}&max={limit}&pageSize=0"
    try:
        r = ig_api_request("GET", url, headers=h, timeout=12, logger_func=print_log)
        if r is not None and r.status_code == 200:
            CANDLE_FAILURES[k_candle] = 0
            dati = r.json()
            # Tracciamento ufficiale quota IG
            allowance = dati.get("allowance")
            if allowance and isinstance(allowance, dict):
                salva_quota_ig(allowance)
            return dati.get('prices', [])
        elif r is not None and r.status_code == 403 and "historical-data-allowance" in r.text:
            salva_quota_ig({"remainingAllowance": 0, "status": "QUOTA_ESAURITA"})
            return "QUOTA_ESAURITA"
        else:
            CANDLE_FAILURES[k_candle] = CANDLE_FAILURES.get(k_candle, 0) + 1
            if CANDLE_FAILURES[k_candle] >= 5:
                print_log("SISTEMA", f"🛑 [TENTATIVI (5)] 5 tentativi per download candele {epic} ({timeframe}) non andati a buon fine. Pausa 15 minuti.")
                attiva_cooldown_operazione("CANDELE", f"{epic}_{timeframe}", durata_sec=900)
                CANDLE_FAILURES[k_candle] = 0
            else:
                if r is not None:
                    print_log("SISTEMA", f"⚠️ [TENTATIVO {CANDLE_FAILURES[k_candle]}/5] Errore IG fetching prezzi {epic}: {r.status_code} {r.text}")
            return []
    except Exception as e:
        CANDLE_FAILURES[k_candle] = CANDLE_FAILURES.get(k_candle, 0) + 1
        if CANDLE_FAILURES[k_candle] >= 5:
            print_log("SISTEMA", f"🛑 [TENTATIVI (5)] 5 tentativi per download candele {epic} ({timeframe}) non andati a buon fine. Pausa 15 minuti.")
            attiva_cooldown_operazione("CANDELE", f"{epic}_{timeframe}", durata_sec=900)
            CANDLE_FAILURES[k_candle] = 0
        else:
            print_log("SISTEMA", f"⚠️ [TENTATIVO {CANDLE_FAILURES[k_candle]}/5] Errore fetching prezzi {epic}: {e}")
        return []

def aggiorna_memoria(nome, update_dict):
    try:
        with open(FILE_MEMORIA, "r") as f: p = json.load(f)
        if nome in p:
            for k, v in update_dict.items():
                p[nome][k] = v
            tmp_f = f"{FILE_MEMORIA}.tmp.{os.getpid()}"
            with open(tmp_f, "w", encoding="utf-8") as f:
                json.dump(p, f, indent=4)
            os.replace(tmp_f, FILE_MEMORIA)
    except Exception:
        pass

RADAR_LAST_ALERT = {} # (nome, tf) -> timestamp

def calcola_kj55_da_candele(candele_list, periods=55):
    """Calcola la mediana Donchian (Max+Min)/2 a 55 periodi sulle candele fornite."""
    if not candele_list:
        return None
    recent = candele_list[-periods:] if len(candele_list) >= periods else candele_list
    valid = []
    for c in recent:
        h = c.get('highPrice', {}).get('bid') or c.get('highPrice', {}).get('ask') or c.get('high')
        l = c.get('lowPrice', {}).get('bid') or c.get('lowPrice', {}).get('ask') or c.get('low')
        if h is not None and l is not None:
            try:
                vh, vl = float(h), float(l)
                if 0 < vh < 1e8 and 0 < vl < 1e8:
                    valid.append((vh, vl))
            except (ValueError, TypeError):
                pass
    min_needed = min(periods, 20)
    if not valid or len(valid) < min_needed:
        return None
    highest = max(v[0] for v in valid)
    lowest = min(v[1] for v in valid)
    return (highest + lowest) / 2.0

def aggiorna_radar_trend(prezzi_live, memoria_attuale):
    """Scansiona tutti gli strumenti sui 3 TF (H1, H4, D1) per calcolare la distanza da KJ55 e inviare alert di prossimità."""
    if not prezzi_live:
        return
    global LAST_RADAR_SCAN
    now_ts = time.time()
    if now_ts - LAST_RADAR_SCAN < 15:
        return
    LAST_RADAR_SCAN = now_ts
    radar_data = {}
    tfs_radar = ["HOUR", "HOUR_4", "DAY"]
    tf_labels = {"HOUR": "H1", "HOUR_4": "H4", "DAY": "D1"}
    
    for nome, cfg in CONFIG_STRUMENTI.items():
        px = prezzi_live.get(nome)
        if not px or not isinstance(px, (int, float)):
            continue
        mult = cfg.get("moltiplicatore", 0.0001)
        dec = cfg.get("decimali", 2)
        dati_mem = memoria_attuale.get(nome, {})
        is_in_trade = (dati_mem.get("stato") in ("LONG", "SHORT")) and dati_mem.get("attivo", False)
        
        radar_data[nome] = {
            "prezzo": px,
            "in_trade": is_in_trade,
            "direzione_trade": dati_mem.get("direzione", "") if is_in_trade else "",
            "timeframe_trade": format_tf_label(dati_mem.get("timeframe", "HOUR")),
            "timeframes": {}
        }
        
        for tf in tfs_radar:
            lbl = tf_labels[tf]
            candele = carica_candele_locali(nome, tf, px_live=px)
            kj = calcola_kj55_da_candele(candele, periods=55)
            tk = calcola_kj55_da_candele(candele, periods=21)
            if kj is not None:
                diff_pts = px - kj
                dist_pips = round(abs(diff_pts) / mult)
                dir_pos = "Possibile Entrata"
                is_vicino = (dist_pips <= 15)
                
                radar_data[nome]["timeframes"][lbl] = {
                    "kj": kj,
                    "tk": tk,
                    "dist_pips": int(dist_pips),
                    "dir": dir_pos,
                    "vicino": is_vicino
                }
                
                # Log radar senza invio notifica push (in Trend notifiche solo per trade ed incrementi)
                if is_vicino and not is_in_trade and not is_rollover_active():
                    k_alert = f"{nome}_{lbl}"
                    last_alert_time = RADAR_LAST_ALERT.get(k_alert, 0)
                    # Cooldown 1 ora (3600 secondi)
                    if now_ts - last_alert_time >= 3600:
                        RADAR_LAST_ALERT[k_alert] = now_ts
                        print_log("RADAR", f"📡 [{nome} {lbl}] {dir_pos} (distanza: {int(dist_pips)} punti, KJ55: {kj:.{dec}f})")
            else:
                radar_data[nome]["timeframes"][lbl] = {
                    "kj": None,
                    "dist_pips": None,
                    "dir": "-",
                    "vicino": False
                }
        
        # Allineamento automatico continuo di current_kj e current_tk per il timeframe configurato dello strumento
        tf_conf = dati_mem.get("timeframe", "HOUR")
        lbl_conf = tf_labels.get(tf_conf, "H1")
        kj_conf = radar_data[nome]["timeframes"].get(lbl_conf, {}).get("kj")
        if kj_conf is not None and (dati_mem.get("current_kj") != kj_conf):
            candele_conf = carica_candele_locali(nome, tf_conf, px_live=px)
            tk_conf = calcola_kj55_da_candele(candele_conf, periods=21)
            aggiorna_memoria(nome, {"current_kj": kj_conf, "current_tk": tk_conf})
            dati_mem["current_kj"] = kj_conf
            dati_mem["current_tk"] = tk_conf
                
    ts_radar = now_it().strftime("%d/%m/%Y %H:%M:%S")
    try:
        tmp_r = f"radar_trend.json.tmp.{os.getpid()}"
        with open(tmp_r, "w", encoding="utf-8") as f_r:
            json.dump({"radar_trend": radar_data, "radar_trend_ts": ts_radar}, f_r, indent=4)
        os.replace(tmp_r, "radar_trend.json")
    except Exception:
        pass

def aggiorna_candele_live_globale(prezzi_live):
    """
    Costruttore continuo di candele OHLC da tick streaming IG a ZERO chiamate API.
    Aggiorna in tempo reale M5, H1, H4 e D1 per TUTTI i 10 strumenti in CONFIG_STRUMENTI,
    anche quando gli strumenti sono spenti, FLAT o in RANGE, mantenendo i file sempre
    freschi, continui e privi di buchi temporali.
    Ritorna un dizionario di candele appena chiuse nel ciclo: {(nome, tf): closed_candle_dict}
    """
    if not prezzi_live or is_weekend_active():
        return {}

    now_t = now_it()
    min_tot = now_t.hour * 60 + now_t.minute
    candele_chiuse = {}
    
    for nome, cfg in CONFIG_STRUMENTI.items():
        live_px = prezzi_live.get(nome)
        if not live_px or not isinstance(live_px, (int, float)):
            continue
            
        for tf in ["HOUR", "HOUR_4", "DAY"]:
            min_tf = TF_MAP.get(tf, 60)
            # REGOLA FERREA H4: Chiusure rigorosamente alle 01:00, 05:00, 09:00, 13:00, 17:00, 21:00 ora italiana
            offset = 60 if min_tf in (60, 240, 1440) else 0
            boundary_min = ((min_tot - offset) // min_tf) * min_tf + offset
            base_dt = now_t.replace(hour=0, minute=0, second=0, microsecond=0)
            curr_dt = base_dt + datetime.timedelta(minutes=boundary_min)
            curr_snap = curr_dt.strftime("%Y/%m/%d %H:%M:00")
            
            tracker = LIVE_OHLC_TRACKER.get((nome, tf))
            if not tracker:
                LIVE_OHLC_TRACKER[(nome, tf)] = {
                    "snap": curr_snap,
                    "open": live_px,
                    "high": live_px,
                    "low": live_px,
                    "close": live_px
                }
            elif tracker["snap"] != curr_snap:
                # Candela conclusa al passaggio del boundary!
                closed_snap = tracker["snap"]
                closed_candle_dict = {
                    "snapshotTime": closed_snap,
                    "openPrice": {"bid": tracker["open"], "ask": tracker["open"], "lastTraded": None},
                    "highPrice": {"bid": tracker["high"], "ask": tracker["high"], "lastTraded": None},
                    "lowPrice": {"bid": tracker["low"], "ask": tracker["low"], "lastTraded": None},
                    "closePrice": {"bid": tracker["close"], "ask": tracker["close"], "lastTraded": None}
                }
                
                # Arricchimento per HOUR_4: unisci e consolida con le candele H1 orarie già chiuse
                if tf == "HOUR_4":
                    try:
                        c_h1 = carica_candele_locali(nome, "HOUR")
                        h1_match = [c for c in c_h1 if c.get("snapshotTime") and closed_snap <= c["snapshotTime"] < curr_snap]
                        if h1_match:
                            o_val = float(h1_match[0]["openPrice"]["bid"])
                            h_val = max(max(float(c["highPrice"]["bid"]) for c in h1_match), tracker["high"])
                            l_val = min(min(float(c["lowPrice"]["bid"]) for c in h1_match), tracker["low"])
                            c_val = float(h1_match[-1]["closePrice"]["bid"]) if h1_match[-1].get("closePrice") else tracker["close"]
                            closed_candle_dict["openPrice"] = {"bid": o_val, "ask": o_val, "lastTraded": None}
                            closed_candle_dict["highPrice"] = {"bid": h_val, "ask": h_val, "lastTraded": None}
                            closed_candle_dict["lowPrice"] = {"bid": l_val, "ask": l_val, "lastTraded": None}
                            closed_candle_dict["closePrice"] = {"bid": c_val, "ask": c_val, "lastTraded": None}
                    except Exception:
                        pass

                # Reset tracker per la nuova candela che si apre adesso
                LIVE_OHLC_TRACKER[(nome, tf)] = {
                    "snap": curr_snap,
                    "open": live_px,
                    "high": live_px,
                    "low": live_px,
                    "close": live_px
                }
                
                # Aggiornamento storico locale (FIFO: mantieni sempre ultime 60 candele)
                c_loc = carica_candele_locali(nome, tf)
                snaps = {c.get("snapshotTime") for c in c_loc if "snapshotTime" in c}
                if closed_snap not in snaps:
                    c_loc.append(closed_candle_dict)
                    if len(c_loc) > 60:
                        c_loc = c_loc[-60:]
                    salva_candele_locali(nome, tf, c_loc)
                
                tf_lbl = "H4" if tf == "HOUR_4" else ("H1" if tf == "HOUR" else "D1")
                dec = CONFIG_STRUMENTI.get(nome, {}).get("decimali", 2)
                kj_agg = calcola_kj55_da_candele(c_loc, periods=55)
                tk_agg = calcola_kj55_da_candele(c_loc, periods=21)
                kj_tk_str = ""
                if kj_agg is not None and tk_agg is not None:
                    kj_tk_str = f" | KJ: {kj_agg:.{dec}f} TK: {tk_agg:.{dec}f}"
                elif kj_agg is not None:
                    kj_tk_str = f" | KJ: {kj_agg:.{dec}f}"
                elif tk_agg is not None:
                    kj_tk_str = f" | TK: {tk_agg:.{dec}f}"
                
                o_val = closed_candle_dict['openPrice']['bid']
                h_val = closed_candle_dict['highPrice']['bid']
                l_val = closed_candle_dict['lowPrice']['bid']
                c_val = closed_candle_dict['closePrice']['bid']
                riga_log_candela = f"🕯️ Candela [{tf_lbl}] ore {now_t.strftime('%H:%M')} | O: {o_val:.{dec}f} H: {h_val:.{dec}f} L: {l_val:.{dec}f} C: {c_val:.{dec}f}{kj_tk_str}"
                print_log(nome, riga_log_candela)
                candele_chiuse[(nome, tf)] = closed_candle_dict
                try:
                    riga_persistente = f"[{now_t.strftime('%H:%M:%S')}] [{nome}] {riga_log_candela}"
                    aggiorna_cache_ultimo_kj_motore(nome, tf_lbl, riga_persistente)
                except Exception:
                    pass

            else:
                # Aggiorna candela in corso
                tracker["high"] = max(tracker["high"], live_px)
                tracker["low"] = min(tracker["low"], live_px)
                tracker["close"] = live_px
                
    return candele_chiuse

def format_tf_label(tf_val):
    tf_s = str(tf_val or "").upper()
    if tf_s in ("MINUTE_5", "M5"):
        return "M5"
    elif tf_s in ("MINUTE_15", "M15"):
        return "M15"
    elif tf_s in ("MINUTE_30", "M30"):
        return "M30"
    elif tf_s in ("HOUR", "HOUR_1", "H1"):
        return "H1"
    elif tf_s in ("HOUR_4", "H4"):
        return "H4"
    elif tf_s.startswith("MINUTE_"):
        return f"M{tf_s.replace('MINUTE_', '')}"
    elif tf_s.startswith("HOUR_"):
        return f"H{tf_s.replace('HOUR_', '')}"
    return tf_s if tf_s else "H1"

def processa_eventi_engine(nome, engine, events, epic, valuta, size_i, headers, dec, auto_restart, dati):
    if not events:
        return
    storico = dati.get("storico_wip_trend", [])
    ha_fatto_eventi = False
    tf_label = format_tf_label(dati.get("timeframe") or (engine.config.get("timeframe") if engine else "H1"))
    has_auto_start = any(e.get('type') == 'auto_start' for e in events)
    core_close_summary = None
    
    # Processiamo prima le chiusure e poi gli avvii/incrementi per garantire la sequenza logica corretta
    ordinati_events = sorted(events, key=lambda x: 0 if x.get('type') in ('core_closed', 'increment_closed', 'fifo_close', 'increments_cleared', 'tp_increment', 'reversal') else 1)
    
    for ev in ordinati_events:
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
                    invia_notifica(f"🚨 BLOCCO REVERSAL {tf_label}", f"[{nome}] Trovate {pos_residue_2} posizioni residue non chiuse su IG. Auto-Restart bloccato per sicurezza.", "sos")
                    engine.reset()
                    aggiorna_memoria(nome, {"stato": "FLAT", "direzione": "", "posizioni_core": [], "posizioni_incr": [], "bancomat_sl": None})
                    continue

            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, dir_auto, size_i, headers, dec, etichetta="[CORE AUTO-RESTART]")
            if ok:
                entry_px = real_lvl if real_lvl else ev['price']
                if engine.pm.core_position:
                    engine.pm.core_position.entry_price = entry_px
                    engine.pm.core_position.ticket = deal_id
                
                if core_close_summary:
                    msg = f"{core_close_summary} 🔄 Reverse {dir_auto} a {entry_px}"
                    print_log(nome, msg)
                    invia_notifica(f"🔄 STP&REV {tf_label}", f"[{nome}] {msg}", "arrows_counterclockwise")
                else:
                    msg = f"🚀 Restart {dir_auto} a {entry_px}"
                    print_log(nome, msg)
                    invia_notifica(f"🚀 RESTART {tf_label}", f"[{nome}] {msg}", "rocket")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
                aggiorna_memoria(nome, {"stato": dir_auto, "direzione": dir_auto})
            else:
                engine.reset()
                print_log(nome, "⚠️ Fallito Restart Core.")
                if core_close_summary:
                    invia_notifica(f"🛑 STOP KJ {tf_label}", f"[{nome}] {core_close_summary} ➡️ FLAT", "warning")
        
        elif tipo == 'increment_opened':
            dir_incr = ev['direction']
            pos = ev['position']
            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, dir_incr, pos.size, headers, dec, etichetta="[INCREMENTO]")
            if ok:
                pos.entry_price = real_lvl if real_lvl else ev['price']
                pos.ticket = deal_id
                msg = f"➕ Open Incr {dir_incr} a {pos.entry_price}"
                print_log(nome, msg)
                invia_notifica(f"➕ OPEN INCR {tf_label}", f"[{nome}] {msg}", "heavy_plus_sign")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
            else:
                engine.pm.increments.remove(pos)
                
        elif tipo in ('core_closed', 'increment_closed', 'fifo_close', 'increments_cleared', 'tp_increment'):
            deal_id = ev.get('ticket')
            if deal_id:
                dir_chiusura = "SELL" if ev['direction'] == "LONG" else "BUY"
                sz = ev.get('size', size_i)
                is_bancomat = (ev.get('reason') == 'bancomat')
                etichetta_tag = "[TP_INCR]" if tipo == 'tp_increment' else ("[BANCOMAT]" if is_bancomat else f"[{tipo.upper()}]")
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
                
                close_px = ev.get('price') or ev.get('exit_price') or prezzi_live.get(nome)
                px_str = f" a {close_px:.{dec}f}" if (close_px is not None and isinstance(close_px, (int, float))) else ""
                
                # Se la Core viene chiusa per Reversal / Stop Kijun, unifica in un unico messaggio telegrafico
                reversal_ev = next((e for e in events if e.get('type') == 'reversal'), None)
                if tipo == 'core_closed' and reversal_ev:
                    r_reason = reversal_ev.get("reason", "")
                    if "trailing" in r_reason:
                        tag_motivo = "Trailing Core"
                        tag_title = "TRAILING CORE"
                    elif "live_stop_kj_break_min" in r_reason:
                        tag_motivo = "Stop KJ (Break Min -5p)"
                        tag_title = "STOP KJ (BREAK MIN)"
                    elif "live_stop_kj_break_max" in r_reason:
                        tag_motivo = "Stop KJ (Break Max +5p)"
                        tag_title = "STOP KJ (BREAK MAX)"
                    elif "live_stop" in r_reason:
                        tag_motivo = "Paracadute KJ"
                        tag_title = "PARACADUTE KJ"
                    else:
                        tag_motivo = "Stop KJ"
                        tag_title = "STOP KJ"
                    core_close_summary = f"🛑 {tag_motivo} ({sz}){pnl_str}"
                    msg = f"🛑 {tag_motivo}: Close Core ({sz}){px_str}{pnl_str} ➡️ FLAT"
                    if not has_auto_start:
                        invia_notifica(f"🛑 {tag_title} {tf_label}", f"[{nome}] {msg}", "warning")
                elif tipo == 'tp_increment':
                    tp_p = ev.get('tp_pips', 20)
                    msg = f"🎯 TP Incr (+{tp_p}p) ({sz}){px_str}{pnl_str}"
                    print_log(nome, msg)
                    invia_notifica(f"🎯 TP INCR {tf_label}", f"[{nome}] {msg}", "dart")
                elif is_bancomat:
                    msg = f"💰 Bancomat ({sz}){px_str}{pnl_str}"
                    print_log(nome, msg)
                    invia_notifica(f"💰 BANCOMAT {tf_label}", f"[{nome}] {msg}", "moneybag")
                elif tipo == 'fifo_close':
                    msg = f"➖ FIFO Incr ({sz}){px_str}{pnl_str}"
                    print_log(nome, msg)
                    invia_notifica(f"➖ FIFO INCR {tf_label}", f"[{nome}] {msg}", "heavy_minus_sign")
                elif tipo == 'increment_closed':
                    msg = f"➖ Close Incr ({sz}){px_str}{pnl_str}"
                    print_log(nome, msg)
                    invia_notifica(f"➖ CLOSE INCR {tf_label}", f"[{nome}] {msg}", "heavy_minus_sign")
                elif tipo == 'increments_cleared':
                    r_incr = ev.get("reason", "")
                    if not r_incr:
                        inc_ev = next((e for e in events if e.get('type') == 'increments_cleared' and e.get('reason')), None)
                        if inc_ev:
                            r_incr = inc_ev.get('reason', '')
                    if "break_min" in r_incr:
                        tag_tk = "Stop TK (Break Min -5p)"
                    elif "break_max" in r_incr:
                        tag_tk = "Stop TK (Break Max +5p)"
                    elif "live_stop_tk" in r_incr:
                        tag_tk = "Paracadute TK"
                    elif "trailing" in r_incr:
                        tag_tk = "Trailing TK"
                    else:
                        tag_tk = "Stop TK"
                    msg = f"🛑 {tag_tk}: Close Incr ({sz}){px_str}{pnl_str}"
                    print_log(nome, msg)
                    invia_notifica(f"🛑 {tag_tk.upper()} {tf_label}", f"[{nome}] {msg}", "heavy_minus_sign")
                else:
                    msg = f"➖ Close Core ({sz}){px_str}{pnl_str}"
                    print_log(nome, msg)
                    invia_notifica(f"➖ CLOSE CORE {tf_label}", f"[{nome}] {msg}", "heavy_minus_sign")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
        
        elif tipo == 'signal_candle_kj':
            dir_s = ev.get('direction')
            stop_px = ev.get('stop_price')
            c_ext = ev.get('candle_low') if dir_s == "LONG" else ev.get('candle_high')
            ext_lbl = "Minimo" if dir_s == "LONG" else "Massimo"
            sign_str = "-5p" if dir_s == "LONG" else "+5p"
            msg_sig = f"⚠️ Candela chiusa oltre KJ. Candela Segnale attiva: Stop confermato a {stop_px:.{dec}f} ({ext_lbl} {c_ext:.{dec}f} {sign_str})"
            print_log(nome, msg_sig)
            storico.append(f"[{ora_str}] {msg_sig}")
            ha_fatto_eventi = True

        elif tipo == 'signal_candle_tk':
            dir_s = ev.get('direction')
            stop_px = ev.get('stop_price')
            c_ext = ev.get('candle_low') if dir_s == "LONG" else ev.get('candle_high')
            ext_lbl = "Minimo" if dir_s == "LONG" else "Massimo"
            sign_str = "-5p" if dir_s == "LONG" else "+5p"
            msg_sig = f"⚠️ Candela chiusa oltre TK. Candela Segnale TK attiva: Stop incrementi a {stop_px:.{dec}f} ({ext_lbl} {c_ext:.{dec}f} {sign_str})"
            print_log(nome, msg_sig)
            storico.append(f"[{ora_str}] {msg_sig}")
            ha_fatto_eventi = True

        elif tipo == 'reversal':
            new_d = ev.get("new_direction", "FLAT")
            reason_str = ev.get("reason", "")
            has_core_in_events = any(e.get('type') == 'core_closed' for e in events)
            
            # Se la Core è già stata registrata con il relativo motivo e passaggio a FLAT, evitiamo il doppio messaggio
            if not has_core_in_events and not has_auto_start:
                if "break_min" in reason_str:
                    tag_motivo = "Stop KJ (Break Min -5p)"
                elif "break_max" in reason_str:
                    tag_motivo = "Stop KJ (Break Max +5p)"
                elif "live_stop" in reason_str:
                    tag_motivo = "Paracadute KJ"
                else:
                    tag_motivo = "Stop KJ"
                msg = f"🛑 {tag_motivo} ➡️ {new_d}"
                print_log(nome, msg)
                invia_notifica(f"🛑 REVERSAL {tf_label}", f"[{nome}] {msg}", "warning")
                storico.append(f"[{ora_str}] {msg}")
                ha_fatto_eventi = True
                
            pulisci_posizioni_epic(nome, epic, headers)
            if not auto_restart:
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "direzione": "", "posizioni_core": [], "posizioni_incr": [], "trailing_sl_incr": None, "trailing_sl_core": None, "signal_candle_active": False, "signal_stop_price": None, "signal_candle_tk_active": False, "signal_stop_price_tk": None})
                engine.reset()
                print_log(nome, "💤 Auto-Restart disattivato. Macchina spenta.")
            else:
                aggiorna_memoria(nome, {"stato": "FLAT", "direzione": "", "posizioni_core": [], "posizioni_incr": [], "trailing_sl_incr": None, "trailing_sl_core": None, "signal_candle_active": False, "signal_stop_price": None, "signal_candle_tk_active": False, "signal_stop_price_tk": None})
            
    # Salvataggio posizioni aggiornate
    if engine.is_running:
        core_dict = [engine.pm.core_position.to_dict()] if engine.pm.core_position else []
        incr_dict = [p.to_dict() for p in engine.pm.increments]
        update_data = {
            "posizioni_core": core_dict, 
            "posizioni_incr": incr_dict,
            "trailing_sl_incr": engine.trailing_sl_incr,
            "trailing_sl_core": engine.trailing_sl_core,
            "signal_candle_active": getattr(engine, "signal_candle_active", False),
            "signal_stop_price": getattr(engine, "signal_stop_price", None),
            "signal_candle_tk_active": getattr(engine, "signal_candle_tk_active", False),
            "signal_stop_price_tk": getattr(engine, "signal_stop_price_tk", None)
        }

        if ha_fatto_eventi:
            if len(storico) > 30: storico = storico[-30:]
            update_data["storico_wip_trend"] = storico
        aggiorna_memoria(nome, update_data)
    elif events and not auto_restart:
        update_data_off = {
            "posizioni_core": [], "posizioni_incr": [], 
            "trailing_sl_incr": None, "trailing_sl_core": None,
            "signal_candle_active": False, "signal_stop_price": None,
            "signal_candle_tk_active": False, "signal_stop_price_tk": None
        }
        if ha_fatto_eventi:
            if len(storico) > 30: storico = storico[-30:]
            update_data_off["storico_wip_trend"] = storico
        aggiorna_memoria(nome, update_data_off)

def is_rollover_active():
    """
    Ritorna True se siamo nella finestra di Rollover notturno / apertura domenica:
    - Domenica sera: 21:58 - 23:59:59 (weekday 6)
    - Lun-Gio sera: 22:45 - 23:59:59 (weekday 0, 1, 2, 3)
    - Lun-Ven notte: 00:00 - 00:14:59 (weekday 0, 1, 2, 3, 4)
    - Venerdì sera: 22:45 - 23:00:59 (weekday 4, freeze operatività prima del weekend)
    """
    ora = now_it()
    t = ora.time()
    wd = ora.weekday()
    if wd == 6 and (datetime.time(21, 58) <= t <= datetime.time(23, 59, 59)):
        return True
    if wd in (0, 1, 2, 3) and (datetime.time(22, 45) <= t <= datetime.time(23, 59, 59)):
        return True
    if wd in (0, 1, 2, 3, 4) and (datetime.time(0, 0) <= t <= datetime.time(0, 14, 59)):
        return True
    if wd == 4 and (datetime.time(22, 45) <= t <= datetime.time(23, 0, 59)):
        return True
    return False

def is_weekend_active():
    """
    Ritorna True se siamo nel weekend a mercati chiusi:
    - Venerdì sera dalle 23:01 in poi (weekday 4, t >= 23:01, lasciando registrare la candela delle 23:00)
    - Sabato tutto il giorno (weekday 5)
    - Domenica fino alle 21:57:59 (weekday 6, t < 21:58)
    (Dalle 21:58 di domenica subentra la Pausa Rollover fino alle 00:15 di lunedì; i mercati aprono alle 22:00 e le candele vengono memorizzate regolarmente).
    """
    ora = now_it()
    t = ora.time()
    wd = ora.weekday()
    if wd == 4 and t >= datetime.time(23, 1):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58):
        return True
    return False

LAST_FETCH_BOUNDARY = {}

def esegui_ciclo_trend():
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

    parametri = {}
    try:
        with open(FILE_MEMORIA, "r") as f: 
            parametri = json.load(f)
    except Exception:
        pass
        
    # Aggiornamento continuo Radar Trend (calcolo distanze KJ55 su tutti i 4 TF a 0 API)
    # Eseguito SEMPRE anche a mercati chiusi per consentire il monitoraggio Dashboard
    try:
        aggiorna_radar_trend(prezzi_live, parametri)
    except Exception as e_rad:
        pass

    # Controllo e invio notifiche di sistema unificate per la Macchinetta (transizioni orarie e rollover)
    try:
        verifica_notifiche_sistema_transizioni()
    except Exception:
        pass

    if is_weekend_active():
        return

    # Costruzione continua e chiusura candele OHLC per TUTTI gli strumenti a ZERO chiamate API
    candele_appena_chiuse = {}
    try:
        candele_appena_chiuse = aggiorna_candele_live_globale(prezzi_live)
    except Exception as e_cg:
        pass

    headers = ottieni_headers_ig()
    if not headers:
        print_log("SISTEMA", "Manca token IG, impossibile proseguire.")
        return
        
    if not has_pos_live_data or not posizioni_live_ig:
        try:
            r_pos = ig_api_request("GET", f"{BASE_URL}/positions", headers=headers, timeout=8, logger_func=print_log)
            if r_pos is not None and r_pos.status_code == 200:
                posizioni_live_ig = r_pos.json().get('positions', [])
                has_pos_live_data = True
        except Exception:
            pass

    for nome, dati in parametri.items():
        if dati.get("tipo_strategia", "RANGE") != "TREND":
            continue
            
        epic = CONFIG_STRUMENTI.get(nome, {}).get("epic")
        if not epic: continue
        
        # Recupera parametri
        tf = dati.get("timeframe", "HOUR")
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
            # Se la macchina è spenta MA risultano ancora posizioni registrate in memoria o da chiudere per Trend, ripuliscile
            pos_core = dati.get("posizioni_core", [])
            pos_incr = dati.get("posizioni_incr", [])
            da_chiudere = dati.get("da_chiudere_a_riapertura", False) or (stato_corrente == "IN_ATTESA_CHIUSURA")
            
            # REGOLE FERREE:
            # Trend deve considerare SOLO ED ESCLUSIVAMENTE ticket che appartengono alle sue posizioni core o incr!
            # NON deve MAI toccare o chiudere posizioni generiche su IG che appartengono al motore RANGE!
            trend_tickets = set()
            for p in (pos_core + pos_incr):
                t_id = p.get("ticket")
                if t_id:
                    trend_tickets.add(t_id)
            
            if trend_tickets or da_chiudere:
                pos_ig_strum = [p for p in posizioni_live_ig if p.get('market', {}).get('epic') == epic and p.get('position', {}).get('dealId') in trend_tickets] if has_pos_live_data else []
                
                m_status = "TRADEABLE"
                if pos_ig_strum:
                    m_status = pos_ig_strum[0].get('market', {}).get('marketStatus', 'TRADEABLE')
                
                if m_status != "TRADEABLE":
                    t_now = time.time()
                    if t_now - ULTIMO_LOG_ATTESA.get(nome, 0) > 60:
                        ULTIMO_LOG_ATTESA[nome] = t_now
                        print_log(nome, f"⏳ Posizione in attesa liquidazione: mercato IG non negoziabile ({m_status}).")
                    
                    up_pend = {
                        "attivo": False,
                        "stato": "IN_ATTESA_CHIUSURA",
                        "da_chiudere_a_riapertura": True,
                        "msg_manuale": f"⚠️ Mercato {m_status} su IG. La posizione verrà chiusa automaticamente appena il mercato torna TRADEABLE."
                    }
                    aggiorna_memoria(nome, up_pend)
                    continue

                print_log(nome, f"Motore Trend spento o in attesa chiusura. Verifica liquidazione posizioni Trend su IG...")
                
                # Costruisci l'elenco delle posizioni Trend da chiudere
                tickets_da_chiudere = []
                for p in (pos_core + pos_incr):
                    t_id = p.get("ticket")
                    if t_id:
                        dir_c = "SELL" if p.get("direction") == "LONG" else "BUY"
                        sz = p.get("size", size_i)
                        tipo_pos = p.get("tipo", "core")
                        tickets_da_chiudere.append((t_id, dir_c, sz, f"[{tipo_pos.upper()}]"))
                
                tutti_chiusi = True
                if tickets_da_chiudere:
                    for t_id, dir_c, sz, tag in tickets_da_chiudere:
                        ok = chiudi_parziale(nome, t_id, dir_c, sz, headers, etichetta=tag)
                        if not ok:
                            tutti_chiusi = False
                        time.sleep(0.3)
                else:
                    tutti_chiusi = True
                
                storico = dati.get("storico_wip_trend", [])
                ora_str = now_it().strftime("%d/%m %H:%M:%S")
                
                if tutti_chiusi:
                    print_log(nome, f"✅ Motore spento e tutte le posizioni su IG chiuse con successo.")
                    invia_notifica(f"⏹️ MOTORE SPENTO: {nome}", f"[{nome}] Chiusura forzata completata su IG.", "stop_button")
                    storico.append(f"[{ora_str}] 🛑 STOP: Posizioni chiuse su IG e motore FLAT.")
                    aggiorna_memoria(nome, {
                        "attivo": False,
                        "posizioni_core": [], 
                        "posizioni_incr": [], 
                        "trailing_sl_core": None, 
                        "trailing_sl_incr": None, 
                        "stato": "FLAT",
                        "direzione": "",
                        "da_chiudere_a_riapertura": False,
                        "msg_manuale": "",
                        "storico_wip_trend": storico[-30:]
                    })
                    if nome in stato_motore.motori:
                        stato_motore.motori[nome].reset()
                else:
                    # Mercato chiuso o rifiutato (es. EDITS_ONLY): preserva la posizione in memoria
                    print_log(nome, f"⚠️ Impossibile chiudere posizioni su IG per {nome} (mercato chiuso o non negoziabile). In attesa di riapertura.")
                    up_pend = {
                        "attivo": False,
                        "stato": "IN_ATTESA_CHIUSURA",
                        "da_chiudere_a_riapertura": True,
                        "msg_manuale": "⚠️ Mercato chiuso/sospeso su IG. La posizione verrà chiusa automaticamente appena il mercato riapre.",
                        "storico_wip_trend": storico[-30:]
                    }
                    if pos_ig_strum and not pos_core:
                        p0 = pos_ig_strum[0].get('position', {})
                        d_str = "LONG" if p0.get('direction') == "BUY" else "SHORT"
                        up_pend["posizioni_core"] = [{
                            "entry": float(p0.get('level', 0.0)),
                            "size": float(p0.get('size', size_i)),
                            "ticket": p0.get('dealId'),
                            "direction": d_str,
                            "tipo": "core"
                        }]
                        up_pend["direzione"] = d_str
                    aggiorna_memoria(nome, up_pend)
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
                "max_kj_distance": 30.0,
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
            stato_motore.motori[nome].config["max_kj_distance"] = 30.0
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
                engine.signal_candle_active = dati.get("signal_candle_active", False)
                engine.signal_stop_price = dati.get("signal_stop_price")
                engine.signal_candle_tk_active = dati.get("signal_candle_tk_active", False)
                engine.signal_stop_price_tk = dati.get("signal_stop_price_tk")
                engine.current_tk = dati.get("current_tk")
                engine.current_kj = dati.get("current_kj")

                
                # Inizializzazione rapida al boot dall'ultima candela locale se i trailing non sono ancora in memoria
                c_loc = carica_candele_locali(nome, tf)
                if c_loc:
                    try:
                        last_c = c_loc[-1]
                        c_close = (last_c['closePrice']['bid'] + last_c['closePrice']['ask']) / 2
                        pip_val = CONFIG_STRUMENTI[nome]["moltiplicatore"]
                        
                        # Trailing SL Core: disattivato su H1, H4, D1
                        core_trailing_pips = None

                        if core_trailing_pips is not None and engine.trailing_sl_core is None and engine.current_kj is not None:
                            if stato_corrente == "SHORT":
                                dist_kj = engine.current_kj - c_close
                                if dist_kj >= (core_trailing_pips * pip_val):
                                    engine.trailing_sl_core = c_close + (core_trailing_pips * pip_val)
                                    aggiorna_memoria(nome, {"trailing_sl_core": engine.trailing_sl_core})
                                    print_log(nome, f"🎯 Trailing SL Core ({tf}) inizializzato a {engine.trailing_sl_core:.5f} (distanza KJ: {dist_kj/pip_val:.1f} pip)")
                            elif stato_corrente == "LONG":
                                dist_kj = c_close - engine.current_kj
                                if dist_kj >= (core_trailing_pips * pip_val):
                                    engine.trailing_sl_core = c_close - (core_trailing_pips * pip_val)
                                    aggiorna_memoria(nome, {"trailing_sl_core": engine.trailing_sl_core})
                                    print_log(nome, f"🎯 Trailing SL Core ({tf}) inizializzato a {engine.trailing_sl_core:.5f} (distanza KJ: {dist_kj/pip_val:.1f} pip)")

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
        # RICONCILIAZIONE AUTOMATICA BIDIREZIONALE CON POSIZIONI REALI SU IG
        # -------------------------------------------------------------
        if has_pos_live_data:
            pos_ig_strum = [p for p in posizioni_live_ig if p.get('market', {}).get('epic') == epic]
            ticket_aperti_epic = {p.get('position', {}).get('dealId') for p in pos_ig_strum}
            storico_aggiornato = False
            storico = dati.get("storico_wip_trend", [])
            ora_str = now_it().strftime("%d/%m %H:%M:%S")
            valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
            mult = CONFIG_STRUMENTI[nome]["moltiplicatore"]
            px_live = prezzi_live.get(nome)
            
            # CASO A: Esistono posizioni aperte reali su IG per questo strumento
            if pos_ig_strum:
                # Se il motore locale è spento, o FLAT, o ha perso la Core: RIAGGANCIA SUBITO!
                if engine.pm.core_position is None or not engine.is_running or engine.current_direction == "FLAT":
                    pos_ordinate = sorted(pos_ig_strum, key=lambda x: x.get('position', {}).get('createdDate', ''))
                    p_core_ig = pos_ordinate[0].get('position', {})
                    dir_core_str = "LONG" if p_core_ig.get('direction') == "BUY" else "SHORT"
                    lvl_core_val = float(p_core_ig.get('level', 0.0))
                    sz_core_val = float(p_core_ig.get('size', size_i))
                    deal_id_core = p_core_ig.get('dealId')
                    
                    pos_obj = Position(lvl_core_val, sz_core_val, "core", dir_core_str)
                    pos_obj.ticket = deal_id_core
                    engine.pm.core_position = pos_obj
                    engine.is_running = True
                    engine.current_direction = dir_core_str
                    
                    # Riaggancia eventuali incrementi residui
                    engine.pm.increments = []
                    for p_inc_ig in pos_ordinate[1:]:
                        pi = p_inc_ig.get('position', {})
                        dir_i_str = "LONG" if pi.get('direction') == "BUY" else "SHORT"
                        lvl_i_val = float(pi.get('level', 0.0))
                        sz_i_val = float(pi.get('size', 1.0))
                        deal_id_i = pi.get('dealId')
                        pos_i_obj = Position(lvl_i_val, sz_i_val, "increment", dir_i_str)
                        pos_i_obj.ticket = deal_id_i
                        engine.pm.increments.append(pos_i_obj)
                    
                    msg_reconcile = f"🛡️ Riconciliazione IG: Riagganciata Core {dir_core_str} ({sz_core_val}) a {lvl_core_val} [ID: {deal_id_core}]"
                    print_log(nome, msg_reconcile)
                    storico.append(f"[{ora_str}] {msg_reconcile}")
                    storico_aggiornato = True
                    
                    dati["attivo"] = True
                    dati["stato"] = dir_core_str
                    dati["direzione"] = dir_core_str
                    dati["tipo_strategia"] = "TREND"
                else:
                    # Il motore ha già una Core: controlla se il ticket è ancora aperto su IG
                    if engine.pm.core_position and engine.pm.core_position.ticket:
                        if engine.pm.core_position.ticket not in ticket_aperti_epic:
                            pnl_txt = ""
                            if px_live and isinstance(px_live, (int, float)):
                                pts = (engine.pm.core_position.entry_price - px_live)/mult if engine.pm.core_position.direction == "SHORT" else (px_live - engine.pm.core_position.entry_price)/mult
                                rate = get_conversion_rate(valuta, prezzi_live)
                                pnl_est = pts * engine.pm.core_position.size * valore_punto * rate
                                pnl_txt = f" [PnL: {pnl_est:+.0f} €]"
                            msg = f"🛑 Manual IG: Close Core {engine.pm.core_position.direction} ({engine.pm.core_position.size}){pnl_txt}"
                            storico.append(f"[{ora_str}] {msg}")
                            print_log(nome, f"ℹ️ Rilevata chiusura manuale Core ({engine.pm.core_position.ticket}) su IG. Posizione rimossa dal live.")
                            engine.pm.core_position = None
                            engine.trailing_sl_core = None
                            storico_aggiornato = True
                    
                    # Verifica incrementi
                    for inc in list(engine.pm.increments):
                        if inc.ticket and inc.ticket not in ticket_aperti_epic:
                            pnl_txt = ""
                            if px_live and isinstance(px_live, (int, float)):
                                pts = (inc.entry_price - px_live)/mult if inc.direction == "SHORT" else (px_live - inc.entry_price)/mult
                                rate = get_conversion_rate(valuta, prezzi_live)
                                pnl_est = pts * inc.size * valore_punto * rate
                                pnl_txt = f" [PnL: {pnl_est:+.0f} €]"
                            msg = f"🛑 Manual IG: Close Incr ({inc.size}){pnl_txt}"
                            storico.append(f"[{ora_str}] {msg}")
                            print_log(nome, f"ℹ️ Rilevata chiusura manuale Incremento ({inc.ticket}) su IG. Rimosso dal live.")
                            engine.pm.increments.remove(inc)
                            storico_aggiornato = True
                    
                    # Riaggancio incrementi presenti su IG ma mancanti nel motore locale
                    ticket_engine_incr = {inc.ticket for inc in engine.pm.increments if inc.ticket}
                    deal_id_core = engine.pm.core_position.ticket if engine.pm.core_position else None
                    for p_ig in pos_ig_strum:
                        t_id = p_ig.get('position', {}).get('dealId')
                        if t_id and t_id != deal_id_core and t_id not in ticket_engine_incr:
                            pi = p_ig.get('position', {})
                            dir_i_str = "LONG" if pi.get('direction') == "BUY" else "SHORT"
                            lvl_i_val = float(pi.get('level') or pi.get('openLevel') or 0.0)
                            sz_i_val = float(pi.get('size', 1.0))
                            pos_i_obj = Position(lvl_i_val, sz_i_val, "increment", dir_i_str)
                            pos_i_obj.ticket = t_id
                            engine.pm.increments.append(pos_i_obj)
                            print_log(nome, f"🛡️ Riconciliazione IG: Riagganciato incremento {dir_i_str} ({sz_i_val}) a {lvl_i_val} [ID: {t_id}]")
                            storico_aggiornato = True
                    
                    # Salvaguardia size_max: se la size totale eccede size_max, chiudi immediatamente l'incremento più redditizio
                    sz_max_val = float(dati.get("size_max", 10) or 10)
                    dec = CONFIG_STRUMENTI.get(nome, {}).get("decimali", 5)
                    valuta_c = CONFIG_STRUMENTI.get(nome, {}).get("valuta", "USD")
                    while engine.pm.total_active_size() > sz_max_val and len(engine.pm.increments) > 0:
                        px_cur = px_live if (px_live and isinstance(px_live, (int, float))) else engine.pm.increments[0].entry_price
                        best = engine.pm.force_close_best_increment(px_cur)
                        if best and best.ticket:
                            dir_c = "SELL" if best.direction == "LONG" else "BUY"
                            chiudi_parziale(nome, best.ticket, dir_c, best.size, headers, etichetta="[FIFO_SIZE_MAX]")
                            raw_d = best.pnl
                            rate_c = get_eur_rate(valuta_c, prezzi_live)
                            pnl_eur = (raw_d / mult) * valore_punto * rate_c
                            pnl_str = f" [PnL: {pnl_eur:+.0f} €]" if pnl_eur != 0 else ""
                            msg = f"➖ FIFO SizeMax Incr ({best.size}) a {px_cur:.{dec}f}{pnl_str}"
                            storico.append(f"[{ora_str}] {msg}")
                            print_log(nome, f"🛡️ Salvaguardia SizeMax: {msg}")
                            invia_notifica(f"➖ FIFO SIZEMAX {nome}", msg, "heavy_minus_sign")
                            storico_aggiornato = True
                        else:
                            break
            
            # CASO B: Nessuna posizione aperta su IG per questo strumento ma il motore pensa di essere in trade
            elif not pos_ig_strum and engine.is_running:
                if engine.pm.core_position or engine.pm.increments:
                    msg = f"ℹ️ Riconciliazione IG: Nessuna posizione aperta su IG per {nome}. Resetto motore a FLAT."
                    print_log(nome, msg)
                    storico.append(f"[{ora_str}] {msg}")
                    engine.pm.core_position = None
                    engine.pm.increments = []
                    engine.trailing_sl_core = None
                    engine.trailing_sl_incr = None
                    engine.is_running = False
                    engine.current_direction = "FLAT"
                    engine.reset()
                    storico_aggiornato = True
            
            if storico_aggiornato:
                core_dict = [engine.pm.core_position.to_dict()] if engine.pm.core_position else []
                incr_dict = [p.to_dict() for p in engine.pm.increments]
                up_dict = {
                    "posizioni_core": core_dict,
                    "posizioni_incr": incr_dict,
                    "trailing_sl_core": engine.trailing_sl_core,
                    "trailing_sl_incr": engine.trailing_sl_incr,
                    "signal_candle_active": getattr(engine, "signal_candle_active", False),
                    "signal_stop_price": getattr(engine, "signal_stop_price", None),
                    "storico_wip_trend": storico[-30:]
                }

                if engine.pm.core_position:
                    up_dict["stato"] = engine.pm.core_position.direction
                    up_dict["direzione"] = engine.pm.core_position.direction
                    up_dict["attivo"] = True
                    up_dict["tipo_strategia"] = "TREND"
                elif not engine.pm.core_position and not engine.pm.increments:
                    engine.is_running = False
                    engine.current_direction = "FLAT"
                    engine.reset()
                    up_dict["stato"] = "FLAT"
                    up_dict["direzione"] = ""
                    if not auto_restart:
                        up_dict["attivo"] = False
                aggiorna_memoria(nome, up_dict)

        # -------------------------------------------------------------
        # GESTIONE AUTOMATICA PAUSA ROLLOVER
        # -------------------------------------------------------------
        in_rollover = is_rollover_active()
        is_sosp_rollover = dati.get("sospeso_rollover", False)
        if in_rollover and not is_sosp_rollover:
            msg_ora = "21:58" if now_it().weekday() == 6 else "22:45"
            print_log(nome, f"🌙 INIZIO PAUSA ROLLOVER ({msg_ora}): Stop live congelati e ingressi sospesi per protezione spread.")
            aggiorna_memoria(nome, {"sospeso_rollover": True})
            dati["sospeso_rollover"] = True
        elif not in_rollover and is_sosp_rollover:
            print_log(nome, "☀️ FINE PAUSA ROLLOVER (00:15): Ripristino controlli attivi.")
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
        # FASE 2: TIMING FINE CANDELA (Accumulo candele da tick streaming IG)
        # -------------------------------------------------------------
        has_no_core = (engine.pm.core_position is None) if (engine and hasattr(engine, 'pm')) else True
        needs_start = dati.get("needs_manual_start", False) or (is_attivo and has_no_core and not dati.get("posizioni_core") and direzione in ("LONG", "SHORT"))
        
        # Nel weekend (mercati chiusi fino a domenica 21:45), nessuna candela chiude
        if is_weekend_active():
            continue

        live_px = prezzi_live.get(nome)
        if not live_px or not isinstance(live_px, (int, float)):
            continue

        candele_locali = carica_candele_locali(nome, tf)
        if not candele_locali and not needs_start:
            continue

        is_candle_just_closed = (nome, tf) in candele_appena_chiuse
        if not is_candle_just_closed and not needs_start:
            continue

        # Seed dello storico (tutte le candele chiuse TRANNE l'ultima se è fine candela appena chiusa)
        storic_candles = []
        subset = candele_locali[:-1] if (is_candle_just_closed and len(candele_locali) > 1) else candele_locali
        for pr in subset: 
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
        
        tk_val = engine._calculate_donchian(engine.config.get("tk_periods", 21))
        kj_val = engine._calculate_donchian(engine.config.get("kj_periods", 55))
        
        # Salva SEMPRE tk, kj e il timestamp della candela
        snapshot_time = candele_locali[-1].get("snapshotTime", "") if candele_locali else ""
        aggiorna_memoria(nome, {
            "current_tk": tk_val, 
            "current_kj": kj_val,
            "signal_candle_active": getattr(engine, "signal_candle_active", False),
            "signal_stop_price": getattr(engine, "signal_stop_price", None),
            "last_candle_time": snapshot_time
        })

        
        # -------------------------------------------------------------
        # PROTEZIONE SPREAD ROLLOVER: Candele e KJ calcolate regolarmente,
        # ma aperture trade ed esecuzioni a mercato congelate fino alle 00:15
        # -------------------------------------------------------------
        if in_rollover:
            continue

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

        valuta = CONFIG_STRUMENTI[nome]["valuta"]
        dec = CONFIG_STRUMENTI[nome]["decimali"]
        
        # Se l'utente ha premuto AVVIA LONG/SHORT (needs_start), avviamo l'engine e l'ordine SUBITO a mercato
        if needs_start:
            px_live = prezzi_live.get(nome)
            closed_close = 0.0
            if candele_locali:
                try:
                    c_last = candele_locali[-1]
                    closed_close = (c_last['closePrice']['bid'] + c_last['closePrice']['ask']) / 2
                except Exception:
                    pass
            px_start = px_live if (px_live and isinstance(px_live, (int, float))) else closed_close
            
            # Controllo di sicurezza vincolante Kijun:
            # SHORT consentito SOLO se px_start <= kj_val
            # LONG consentito SOLO se px_start >= kj_val
            if kj_val is not None and px_start:
                if direzione == "SHORT" and px_start > kj_val:
                    msg_blocco = f"🛑 Avvio SHORT BLOCCATO: Prezzo ({px_start:.{dec}f}) > Kijun ({kj_val:.{dec}f}). Operazione non consentita."
                    print_log(nome, msg_blocco)
                    invia_notifica(f"🛑 AVVIO BLOCCATO {format_tf_label(tf)}", f"[{nome}] {msg_blocco}", "alert")
                    engine.reset()
                    aggiorna_memoria(nome, {
                        "attivo": False, 
                        "stato": "FLAT", 
                        "errore_avvio": True, 
                        "needs_manual_start": False, 
                        "msg_manuale": msg_blocco
                    })
                    continue
                elif direzione == "LONG" and px_start < kj_val:
                    msg_blocco = f"🛑 Avvio LONG BLOCCATO: Prezzo ({px_start:.{dec}f}) < Kijun ({kj_val:.{dec}f}). Operazione non consentita."
                    print_log(nome, msg_blocco)
                    invia_notifica(f"🛑 AVVIO BLOCCATO {format_tf_label(tf)}", f"[{nome}] {msg_blocco}", "alert")
                    engine.reset()
                    aggiorna_memoria(nome, {
                        "attivo": False, 
                        "stato": "FLAT", 
                        "errore_avvio": True, 
                        "needs_manual_start": False, 
                        "msg_manuale": msg_blocco
                    })
                    continue

            pos = engine.start(px_start, direzione)
            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, direzione, size_i, headers, dec, etichetta="[CORE]")
            if ok:
                pos.entry_price = real_lvl if real_lvl else px_start
                pos.ticket = deal_id
                ora_str = now_it().strftime("%d/%m %H:%M:%S")
                msg = f"🚀 Open Core {direzione} a {pos.entry_price:.{dec}f}"
                aggiorna_memoria(nome, {
                    "stato": direzione, 
                    "direzione": direzione, 
                    "posizioni_core": [pos.to_dict()], 
                    "posizioni_incr": [], 
                    "needs_manual_start": False,
                    "msg_manuale": "",
                    "storico_wip_trend": [f"[{ora_str}] {msg}"]
                })
                print_log(nome, f"🚀 Open Core {direzione} a {pos.entry_price:.{dec}f}.")
                invia_notifica(f"🚀 OPEN CORE {format_tf_label(tf)}", f"[{nome}] {msg}", "rocket")
            else:
                engine.reset()
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "errore_avvio": True, "needs_manual_start": False})
            continue

        # Se eravamo FLAT e non c'è needs_start e non c'è auto_restart, abbiamo solo aggiornato le linee, possiamo saltare il calcolo trading
        if not engine.is_running and not auto_restart:
            continue

        # Estrai candela chiusa (l'ultima nel buffer locale)
        if not candele_locali:
            continue
        last = candele_locali[-1]
        try:
            bid_o, ask_o = last['openPrice']['bid'], last['openPrice']['ask']
            bid_h, ask_h = last['highPrice']['bid'], last['highPrice']['ask']
            bid_l, ask_l = last['lowPrice']['bid'], last['lowPrice']['ask']
            bid_c, ask_c = last['closePrice']['bid'], last['closePrice']['ask']
            closed_candle = Candle((bid_o+ask_o)/2, (bid_h+ask_h)/2, (bid_l+ask_l)/2, (bid_c+ask_c)/2)
        except Exception:
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

        try:
            from Sistema.sync_settimanale import controlla_schedulazione_settimanale
            controlla_schedulazione_settimanale(NOME_CONTO)
        except Exception:
            pass

        time.sleep(2.0)
