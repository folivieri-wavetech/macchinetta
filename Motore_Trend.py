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

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'macchinetta_trend'))
from core_engine import CoreEngine, Candle
from position_manager import PositionManager

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

# --- FUNZIONI API IG (MUTUATE DAL RANGE) ---
def formatta_numero(valore, dec):
    if valore is None: return None
    r = round(float(valore), dec)
    return f"{r:.{dec}f}"

def chiamata_api_sicura(metodo, url, headers, payload=None, max_retries=6):
    headers_req = headers.copy()
    headers_req["Version"] = "2"
    for _ in range(max_retries):
        try:
            if metodo.upper() == 'GET':
                r = requests.get(url, headers=headers_req, timeout=10)
            elif metodo.upper() == 'DELETE':
                r = requests.delete(url, headers=headers_req, timeout=10)
            else:
                r = requests.post(url, headers=headers_req, json=payload, timeout=10)
            
            if r.status_code == 403 and "exceeded-api-key" in r.text:
                time.sleep(30)
                continue
            return r
        except Exception:
            time.sleep(1.5)
    return None

def verifica_conferma_deal(deal_ref, headers):
    h_conf = headers.copy()
    h_conf["Version"] = "1"
    for _ in range(5): 
        try:
            time.sleep(2) 
            r = requests.get(f"{BASE_URL}/confirms/{deal_ref}", headers=h_conf, timeout=10)
            if r.status_code == 200:
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
    
    for tentativo in range(4): 
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
                        time.sleep(20)
                        continue
                    if isinstance(confirm_data, dict):
                        if confirm_data.get("level") is not None: real_level = float(confirm_data.get("level"))
                        if confirm_data.get("dealId"): deal_id = confirm_data.get("dealId")

                if real_level is None:
                    try:
                        time.sleep(1.0)
                        resp_p = chiamata_api_sicura('GET', f"{BASE_URL}/positions", headers)
                        if resp_p and resp_p.status_code == 200:
                            p_list = [pos for pos in resp_p.json().get('positions', []) if pos['market']['epic'] == epic and pos['position']['direction'] == direzione and abs(float(pos['position']['size']) - float(size)) < 0.001]
                            if p_list:
                                real_level = float(p_list[0]['position']['level'])
                                deal_id = p_list[0]['position']['dealId']
                    except Exception: pass

                if real_level is not None: real_level = round(float(real_level), dec)
                livello_log = f" a {formatta_numero(real_level, dec)}" if real_level is not None else ""
                print_log(nome_strumento, f"✅ {etichetta} eseguito con successo{livello_log}.")
                return True, real_level, deal_id
            else:
                if r.status_code == 403 and "exceeded-api-key" in r.text:
                    time.sleep(30)
                else:
                    print_log(nome_strumento, f"⚠️ Rifiuto API {etichetta} {direzione}: {r.text}")
                    time.sleep(20)
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione Rete su {etichetta} {direzione}: {e}")
            time.sleep(20)
    return False, None, None

def chiudi_parziale(nome_strumento, dealId, dir_chiusura, size, headers, etichetta="[POSIZIONE]"):
    h = headers.copy()
    h["Version"] = "1"
    h["_method"] = "DELETE"
    size_str = str(int(size)) if float(size).is_integer() else str(size)
    p = {"dealId": dealId, "direction": dir_chiusura, "size": size_str, "orderType": "MARKET"}
    for tentativo in range(4):
        try:
            r = requests.post(f"{BASE_URL}/positions/otc", headers=h, json=p, timeout=10)
            if r.status_code == 200: 
                print_log(nome_strumento, f"✅ Chiusura {etichetta} eseguita con successo.")
                return True
            else:
                if r.status_code == 403 and "exceeded-api-key" in r.text:
                    time.sleep(30)
                else:
                    print_log(nome_strumento, f"⚠️ Errore Chiusura {etichetta} ({dealId}): {r.text}")
                    time.sleep(20)
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione su Chiusura {etichetta}: {e}")
            time.sleep(20)
    return False

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

# --- FUNZIONI CORE ---
def scarica_candele(epic, timeframe, limit=100, headers=None):
    h = headers.copy()
    h["Version"] = "3"
    try:
        url = f"{BASE_URL}/prices/{epic}?resolution={timeframe}&max={limit}&pageSize=0"
        r = requests.get(url, headers=h, timeout=10)
        if r.status_code == 200:
            return r.json().get('prices', [])
        else:
            print_log("SISTEMA", f"Errore IG fetching prezzi {epic}: {r.status_code} {r.text}")
            if r.status_code == 403 and "historical-data-allowance" in r.text:
                return "QUOTA_ESAURITA"
    except Exception as e:
        print_log("SISTEMA", f"Errore fetching prezzi {epic}: {e}")
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

def esegui_ciclo_trend():
    headers = ottieni_headers_ig()
    if not headers:
        print_log("SISTEMA", "Manca token IG, impossibile proseguire.")
        return
        
    try:
        with open(FILE_MEMORIA, "r") as f: parametri = json.load(f)
    except Exception:
        return
        
    for nome, dati in parametri.items():
        if dati.get("tipo_strategia", "RANGE") != "TREND":
            continue
            
        is_attivo = dati.get("attivo", False)
        if not is_attivo:
            continue
            
        epic = CONFIG_STRUMENTI.get(nome, {}).get("epic")
        if not epic: continue
        
        # Recupera parametri
        tf = dati.get("timeframe", "MINUTE_5")
        size_i = dati.get("size", 1)
        size_max = dati.get("size_max", 3)
        min_body = dati.get("min_body", 10)
        auto_restart = dati.get("auto_restart", True)
        direzione = dati.get("direzione", "LONG")
        stato_corrente = dati.get("stato", "FLAT") # "FLAT", "LONG", "SHORT"
        
        # Inizializza/Recupera Engine
        if nome not in stato_motore.motori:
            cfg = {
                "size_i": size_i,
                "size_max": size_max,
                "tk_periods": 21,
                "kj_periods": 55,
                "min_body": min_body,
                "pip_value": CONFIG_STRUMENTI[nome]["moltiplicatore"]
            }
            stato_motore.motori[nome] = CoreEngine(cfg)
        
        engine = stato_motore.motori[nome]
        
        needs_start = not engine.is_running and stato_corrente == "FLAT" and direzione in ("LONG", "SHORT")
        
        # OTTIMIZZAZIONE API IG: Scarichiamo le candele storiche SOLO nei primi 20 secondi del nuovo blocco
        # o se l'utente ha esplicitamente richiesto l'avvio della macchina.
        now_t = now_it()
        min_tf = TF_MAP.get(tf, 5)
        min_tot = now_t.hour * 60 + now_t.minute
        offset = 60 if min_tf in (240, 1440) else 0
        is_candle_boundary = (min_tot - offset) % min_tf == 0
        is_just_closed = is_candle_boundary and now_t.second < 20
        
        if not is_just_closed and not needs_start:
            continue
        
        # 1. Recupera candele da IG per calcolo Donchian e chiusura
        prices = scarica_candele(epic, tf, limit=300, headers=headers)
        
        if prices == "QUOTA_ESAURITA":
            print_log(nome, "🛑 QUOTA IG ESAURITA! Arresto automatico del Trend per evitare chiamate a vuoto.")
            invia_notifica(f"🛑 QUOTA IG ESAURITA: {nome}", f"[{nome}] Raggiunto limite dati storici IG. Arresto Trend in corso.", "no_entry")
            aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "tipo_strategia": "RANGE"})
            if engine.is_running:
                engine.stop()
            continue
            
        if not prices: 
            print_log(nome, "⚠️ Nessuna candela restituita da IG!")
            continue
            
        if len(prices) < 2:
            continue
            
        # 2. Controllo Timestamp Lock
        last_closed_candle = prices[-2]
        snapshot_time = last_closed_candle.get("snapshotTime", "")
        saved_candle_time = dati.get("last_candle_time", "")
        
        # Se il timestamp è identico e non abbiamo un avvio manuale pendente, ignoriamo
        if snapshot_time == saved_candle_time and not needs_start:
            continue
            
        print_log(nome, f"DEBUG: Nuova candela chiusa rilevata. Snapshot: {snapshot_time}")
        
        # Seed dello storico (tutte le candele chiuse TRANNE l'ultima, che verrà aggiunta da on_candle_close)
        storic_candles = []
        for pr in prices[:-2]: 
            try:
                bid_o, ask_o = pr['openPrice']['bid'], pr['openPrice']['ask']
                bid_h, ask_h = pr['highPrice']['bid'], pr['highPrice']['ask']
                bid_l, ask_l = pr['lowPrice']['bid'], pr['lowPrice']['ask']
                bid_c, ask_c = pr['closePrice']['bid'], pr['closePrice']['ask']
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
        
        # Se eravamo FLAT e non c'è needs_start, abbiamo solo aggiornato le linee, possiamo saltare il calcolo trading
        if not engine.is_running and not needs_start:
            continue
        pos_core = dati.get("posizioni_core", [])
        pos_incr = dati.get("posizioni_incr", [])
        
        if not engine.is_running and (pos_core or pos_incr or (stato_corrente != "FLAT" and stato_corrente != "IN_ATTESA")):
            engine.is_running = True
            engine.current_direction = stato_corrente if stato_corrente in ("LONG", "SHORT") else direzione
            for c_d in pos_core:
                pos = engine.pm.open_core(c_d.get("entry", 0), c_d.get("size", 1), c_d.get("direction", "LONG"))
                pos.ticket = c_d.get("ticket")
            for i_d in pos_incr:
                pos = engine.pm.open_increment(i_d.get("entry", 0), i_d.get("size", 1), i_d.get("direction", "LONG"))
                pos.ticket = i_d.get("ticket")

        # Estrai candela chiusa
        last = prices[-1]
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
            pos = engine.start(closed_candle.close, direzione)
            ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, direzione, size_i, headers, dec, etichetta="[CORE]")
            if ok:
                pos.entry_price = real_lvl if real_lvl else closed_candle.close
                pos.ticket = deal_id
                aggiorna_memoria(nome, {"stato": direzione, "direzione": direzione, "posizioni_core": [pos.to_dict()], "posizioni_incr": [], "storico_wip_trend": [f"🚀 Apertura Core {direzione} a {pos.entry_price}"]})
                print_log(nome, f"🚀 Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.")
                invia_notifica(f"🚀 AVVIO TREND: {nome}", f"[{nome}] Motore Partito in {direzione}. Core piazzata a {pos.entry_price}.", "rocket")
            else:
                engine.reset()
                aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT", "errore_avvio": True})
                continue
                
        # Alimenta la candela all'Engine
        events = engine.on_candle_close(closed_candle, next_open_price=closed_candle.close)
        
        storico = dati.get("storico_wip_trend", [])
        ha_fatto_eventi = False
        
        for ev in events:
            tipo = ev['type']
            
            if tipo == 'increment_opened':
                dir_incr = ev['direction']
                pos = ev['position']
                ok, real_lvl, deal_id = invia_ordine_mercato(nome, epic, valuta, dir_incr, size_i, headers, dec, etichetta="[INCREMENTO]")
                if ok:
                    pos.entry_price = real_lvl if real_lvl else ev['price']
                    pos.ticket = deal_id
                    msg = f"➕ Incremento Aperto {dir_incr} a {pos.entry_price}"
                    print_log(nome, msg)
                    invia_notifica(f"➕ INCREMENTO TREND: {nome}", f"[{nome}] {msg}", "heavy_plus_sign")
                    storico.append(msg)
                    ha_fatto_eventi = True
                else:
                    engine.pm.increments.remove(pos)
                    
            elif tipo in ('core_closed', 'increment_closed', 'fifo_close', 'increments_cleared'):
                deal_id = ev.get('ticket')
                if deal_id:
                    dir_chiusura = "SELL" if ev['direction'] == "LONG" else "BUY"
                    sz = ev.get('size', size_i)
                    chiudi_parziale(nome, deal_id, dir_chiusura, sz, headers, etichetta=f"[{tipo.upper()}]")
                    msg = f"➖ Chiuso {tipo} ({sz}) PnL: {ev.get('pnl', 0):.2f}"
                    invia_notifica(f"➖ CHIUSURA TREND: {nome}", f"[{nome}] {msg}", "heavy_minus_sign")
                    storico.append(msg)
                    ha_fatto_eventi = True
            
            elif tipo == 'reversal':
                print_log(nome, f"🛑 REVERSAL! Chiusura globale per incrocio KJ.")
                invia_notifica(f"🛑 REVERSAL TREND: {nome}", f"[{nome}] Incrocio KJ! Chiusura globale e stop motore (o inversione se attiva).", "warning")
                if not auto_restart:
                    aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT"})
                    engine.reset()
                    print_log(nome, "💤 Auto-Restart disattivato. Macchina spenta.")
                else:
                    aggiorna_memoria(nome, {"stato": "FLAT", "direzione": ""})
                
        # Alla fine salvo sempre lo stato delle posizioni
        if engine.is_running:
            core_dict = [engine.pm.core_position.to_dict()] if engine.pm.core_position else []
            incr_dict = [p.to_dict() for p in engine.pm.increments]
            update_data = {
                "posizioni_core": core_dict, 
                "posizioni_incr": incr_dict
            }
            if ha_fatto_eventi:
                if len(storico) > 20: storico = storico[-20:]
                update_data["storico_wip_trend"] = storico
            aggiorna_memoria(nome, update_data)
        elif events and not auto_restart:
            # Se si è spento e ha svuotato le posizioni
            update_data_off = {"posizioni_core": [], "posizioni_incr": []}
            if ha_fatto_eventi:
                if len(storico) > 20: storico = storico[-20:]
                update_data_off["storico_wip_trend"] = storico
            aggiorna_memoria(nome, update_data_off)

def calcola_attesa_dinamica(parametri):
    now = now_it()
    next_wake = now + datetime.timedelta(days=1)
    has_active = False
    
    for nome, dati in parametri.items():
        if dati.get("tipo_strategia", "RANGE") != "TREND": continue
        if not dati.get("attivo", False): continue
        
        tf = dati.get("timeframe", "MINUTE_5")
        min_tf = TF_MAP.get(tf, 5)
        
        min_tot = now.hour * 60 + now.minute
        
        # Offset di 60 minuti per H4 (240) e DAY (1440) per centrare 1:00 italiana
        offset = 60 if min_tf in (240, 1440) else 0
        
        minuti_mancanti = min_tf - ((min_tot - offset) % min_tf)
        if minuti_mancanti == 0:
            minuti_mancanti = min_tf
            
        prossima = now + datetime.timedelta(minutes=minuti_mancanti)
        prossima = prossima.replace(second=1, microsecond=0)
        
        if prossima < next_wake:
            next_wake = prossima
        has_active = True
        
    if not has_active:
        return 10.0 # Se non c'è nulla, svegliati ogni 10 secondi
        
    attesa = (next_wake - now_it()).total_seconds()
    return max(1.0, attesa)

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
            with open(FILE_MEMORIA, "r") as f: parametri = json.load(f)
        except:
            parametri = {}
            
        attesa = calcola_attesa_dinamica(parametri)
        
        if attesa < 2.5:
            print(f"Candela in chiusura... attesa {attesa:.1f} secondi.")
            time.sleep(attesa + 1)
            try:
                esegui_ciclo_trend()
            except Exception as e:
                print(f"Errore ciclo Trend (Candle Close): {e}")
                traceback.print_exc()
        else:
            time.sleep(10) # Risveglio parziale ogni 10s per leggere eventuali nuovi avvii (needs_start)
            try:
                esegui_ciclo_trend()
            except Exception as e:
                print(f"Errore ciclo Trend (Wakeup): {e}")
                traceback.print_exc()
