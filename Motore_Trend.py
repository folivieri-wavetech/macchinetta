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

# --- CONFIGURAZIONI GLOBALI ---
FILE_MEMORIA = "memoria_parametri.json"
FILE_TOKEN = "token_ig.json"
STATO_SISTEMA = "stato_sistema.json"
CONSOLE_LOG_FILE = "console_live_trend.log"
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
        url = f"{BASE_URL}/prices/{epic}?resolution={timeframe}&max={limit}"
        r = requests.get(url, headers=h, timeout=10)
        if r.status_code == 200:
            return r.json().get('prices', [])
        else:
            print_log("SISTEMA", f"Errore IG fetching prezzi {epic}: {r.status_code} {r.text}")
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
    except Exception as e:
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
        
        # 1. Recupera candele da IG per calcolo Donchian e close
        prices = scarica_candele(epic, tf, limit=100, headers=headers)
        if not prices: continue
        
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
        
        # Seed dello storico
        storic_candles = []
        for pr in prices[:-1]: # Escludiamo l'ultima candela che è quella appena chiusa
            try:
                bid_o, ask_o = pr['openPrice']['bid'], pr['openPrice']['ask']
                bid_h, ask_h = pr['highPrice']['bid'], pr['highPrice']['ask']
                bid_l, ask_l = pr['lowPrice']['bid'], pr['lowPrice']['ask']
                bid_c, ask_c = pr['closePrice']['bid'], pr['closePrice']['ask']
                c = Candle((bid_o+ask_o)/2, (bid_h+ask_h)/2, (bid_l+ask_l)/2, (bid_c+ask_c)/2)
                storic_candles.append(c)
            except Exception: pass
            
        engine.seed_history(storic_candles)
        
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
            
        # Se lo stato su dashboard è FLAT ma l'utente ha premuto AVVIA LONG, forziamo l'engine
        if not engine.is_running and stato_corrente == "FLAT":
            # Usiamo il close price dell'ultima candela per simulare il next open
            engine.start(closed_candle.close, direzione)
            aggiorna_memoria(nome, {"stato": direzione})
            print_log(nome, f"🚀 Motore Partito in {direzione}. Core piazzata virtualmente a {closed_candle.close}.")
            
            # TODO: INVIA ORDINE A MERCATO CORE (IG API MARKET ORDER)
            
        # Alimenta la candela all'Engine
        # In live IG, il prezzo open della candela successiva potrebbe essere leggermente diverso, ma passiamo il close
        events = engine.on_candle_close(closed_candle, next_open_price=closed_candle.close)
        
        for ev in events:
            if ev['type'] == 'reversal':
                print_log(nome, f"🛑 REVERSAL! Chiusura globale verso {ev['direction']}.")
                # TODO: INVIA ORDINE IG CHIUSURA
                if not auto_restart:
                    aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT"})
                    engine.reset()
                    print_log(nome, "💤 Auto-Restart disattivato. Macchina spenta.")
                else:
                    aggiorna_memoria(nome, {"stato": ev['direction'], "direzione": ev['direction']})
                    # L'engine è già ripartito dentro on_candle_close
                    # TODO: INVIA ORDINE IG APERTURA NUOVA CORE
            elif ev['type'] == 'increment_opened':
                print_log(nome, f"➕ INCREMENTO APERTO: Size={ev['size']} a {ev['price']}")
                # TODO: INVIA ORDINE IG INCREMENTO
            elif ev['type'] == 'stop_loss_hit':
                print_log(nome, f"💥 STOP LOSS COLPITO globale. Uscita totale.")
                # TODO: INVIA ORDINE IG CHIUSURA
                if not auto_restart:
                    aggiorna_memoria(nome, {"attivo": False, "stato": "FLAT"})
                    engine.reset()
                    print_log(nome, "💤 Auto-Restart disattivato. Macchina spenta.")
                else:
                    aggiorna_memoria(nome, {"stato": "FLAT", "direzione": ""})
            elif ev['type'] == 'max_loss_cut':
                print_log(nome, f"✂️ TAGLIO INCREMENTI per Max Distanza (Kijun lontana).")
                # TODO: CHIUSURA PARZIALE INCREMENTI SU IG
                
    stato_motore.salva_stato()

def calcola_attesa(min_tf=5):
    ora_attuale = now_it()
    minuti_attuali = ora_attuale.minute
    minuti_mancanti = min_tf - (minuti_attuali % min_tf)
    prossima_scadenza = ora_attuale + datetime.timedelta(minutes=minuti_mancanti)
    prossima_scadenza = prossima_scadenza.replace(second=1, microsecond=0)
    attesa_sec = (prossima_scadenza - now_it()).total_seconds()
    return max(1, attesa_sec)

if __name__ == "__main__":
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.socket.SOCK_STREAM)
        porta_unica = 15000 + int(hashlib.md5(f"{NOME_CONTO}_TREND".encode()).hexdigest(), 16) % 40000
        lock_socket.bind(("127.0.0.1", porta_unica))
    except socket.error:
        print(f"\n🚨 ERRORE CRITICO: Il Motore Trend per il conto '{NOME_CONTO}' è già in esecuzione!")
        sys.exit()

    print(f"🚀 Avvio Motore Trend per il conto {NOME_CONTO}...")
    while True:
        # Trova TF min. Per ora hardcodato a 5 minuti per il loop principale. 
        # IG API accetta timestamp precisi. Il loop si sveglierà ai 5 minuti e valuterà le candele.
        attesa = calcola_attesa(5)
        print(f"Zzz... Attesa prossima chiusura candela: {attesa:.0f} secondi.")
        time.sleep(attesa)
        
        try:
            esegui_ciclo_trend()
        except Exception as e:
            print(f"Errore ciclo Trend: {e}")
            traceback.print_exc()
