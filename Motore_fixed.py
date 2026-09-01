import json
import time
import os
import requests
import traceback
import datetime
try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

import sys
import socket
import hashlib
try:
    import winsound
except ImportError:
    winsound = None
from dotenv import dotenv_values
import io

# Fix per console Windows cp1252 (permette la stampa delle emoji nelle finestre nere)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- EFFETTI SONORI ---
def suona_drumroll():
    try:
        if winsound is None:
            return
        ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
        FILE_AUDIO = os.path.join(ROOT_DIR, "Sistema", "DRUMROLL.WAV")
        if os.path.exists(FILE_AUDIO):
            winsound.PlaySound(FILE_AUDIO, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass

# --- GESTIONE MULTI-CONTO ---
if len(sys.argv) < 2:
    print("🚨 ERRORE: Devi specificare il nome della cartella del conto all'avvio!")
    print("Esempio di avvio: python Motore.py ROSSI_DEMO")
    sys.exit()

NOME_CONTO = sys.argv[1]

if not os.path.isdir(NOME_CONTO):
    print(f"🚨 ERRORE: La cartella '{NOME_CONTO}' non esiste. Creala e inserisci il file .env all'interno.")
    sys.exit()

os.chdir(NOME_CONTO)

if "_REALE" in NOME_CONTO.upper():
    BASE_URL = "https://api.ig.com/gateway/deal"
else:
    BASE_URL = "https://demo-api.ig.com/gateway/deal"

# --- SISTEMA ANTI-DOPPIA ISTANZA MULTI-CONTO ---
try:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    porta_unica = 10000 + int(hashlib.md5(NOME_CONTO.encode()).hexdigest(), 16) % 40000
    lock_socket.bind(("127.0.0.1", porta_unica))
except socket.error:
    print(f"\n🚨 ERRORE CRITICO: Il Motore per il conto '{NOME_CONTO}' è già in esecuzione in background!")
    sys.exit()

# --- CONFIGURAZIONI ---
FILE_MEMORIA = "memoria_parametri.json"
FILE_TOKEN = "token_ig.json"
CONSOLE_LOG_FILE = "console_live.log"
config = dotenv_values(".env")
DEV_MODE = config.get("DEV_MODE", "False").lower() == "true"

# --- GESTIONE NOTIFICHE PUSH (NTFY) ---
def to_market_dir(d):
    if not d: return ""
    d_up = str(d).upper()
    if d_up in ["BUY", "LONG"]: return "LONG"
    if d_up in ["SELL", "SHORT"]: return "SHORT"
    return str(d)

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

# --- VOCABOLARIO ---
CONFIG_STRUMENTI = {
    "AUD/CAD": {"epic": "CS.D.AUDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "NZD", "valore_punto": 1},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "EUR/GBP": {"epic": "CS.D.EURGBP.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "GBP", "valore_punto": 1},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "USD", "valore_punto": 1},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CAD", "valore_punto": 1},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP", "moltiplicatore": 0.0001, "decimali": 5, "valuta": "CHF", "valore_punto": 1},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP", "moltiplicatore": 0.01, "decimali": 3, "valuta": "JPY", "valore_punto": 100},
    "Ethereum": {"epic": "CS.D.ETHUSD.CFD.IP", "moltiplicatore": 1, "decimali": 2, "valuta": "USD", "valore_punto": 1},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP", "moltiplicatore": 1, "decimali": 1, "valuta": "EUR", "valore_punto": 1},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP", "moltiplicatore": 1, "decimali": 2, "valuta": "EUR", "valore_punto": 1}
}

# --- STATO GLOBALE ---
falsi_allarmi_tracker = {}

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

def formatta_numero(valore, dec):
    if valore is None:
        return None
    r = round(float(valore), dec)
    return f"{r:.{dec}f}"

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
        usd_cad = prezzi.get("USD/CAD")
        aud_cad = prezzi.get("AUD/CAD")
        aud_nzd = prezzi.get("AUD/NZD")
        if usd_cad and aud_cad and aud_nzd:
            eur_cad = eur_usd * usd_cad
            eur_aud = eur_cad / aud_cad
            eur_nzd = eur_aud * aud_nzd
            return 1.0 / eur_nzd
            
    return 1.0

def calcola_pnl_chiusura(pos_da_chiudere, prezzo_live, nome_strumento, prezzi_globali):
    c = CONFIG_STRUMENTI.get(nome_strumento)
    if not c or not prezzo_live or not pos_da_chiudere:
        return 0.0
        
    mult = c["moltiplicatore"]
    valuta = c["valuta"]
    valore_punto = c.get("valore_punto", 1)
    pnl_valuta = 0.0
    
    for p in pos_da_chiudere:
        entry = float(p['position']['level'])
        size = float(p['position']['size'])
        dir_pos = p['position']['direction']
        
        if dir_pos == 'BUY':
            pts = (prezzo_live - entry) / mult
        else:
            pts = (entry - prezzo_live) / mult
            
        pnl_valuta += pts * size * valore_punto
        
    rate = get_eur_rate(valuta, prezzi_globali)
    return pnl_valuta * rate

def formatta_pnl(pnl):
    if pnl == 0:
        return ""
    segno = "+" if pnl > 0 else ""
    return f" [Parziale: {segno}{int(round(pnl))} €]"

# --- NUOVA REGISTRAZIONE STATISTICHE CHIRURGICA ---
def registra_operazione(nome_strumento, fase_label, pnl_eur):
    try:
        if abs(pnl_eur) < 0.01: 
            return
            
        suona_drumroll()
        
        # --- Aggiornamento Statistiche (Memoria) ---
        chiave = "Altro"
        fase_up = fase_label.upper()
        if "MICRO" in fase_up and "FLIP" not in fase_up: chiave = "Micro"
        elif "FLIP" in fase_up: chiave = "Flip"
        elif "TICKET1" in fase_up: chiave = "Ticket1"
        elif "TICKET2" in fase_up: chiave = "Ticket2"
        elif "OVERGAIN" in fase_up: chiave = "OverGain"
        elif "OVERLOSS" in fase_up: chiave = "OverLoss"
        elif "ULTIMA" in fase_up: chiave = "Ultima"
        elif "ASSICURAZIONE" in fase_up: chiave = "Assicurazione"
        elif "FASE 3" in fase_up or "FASE3" in fase_up or "MONETIZZAZIONE" in fase_up: chiave = "Fase3"
        
        for _ in range(5):
            try:
                with open(FILE_MEMORIA, "r") as fm:
                    dati = json.load(fm)
                if nome_strumento in dati:
                    if "stats" not in dati[nome_strumento]:
                        dati[nome_strumento]["stats"] = {
                            "Micro": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "Flip": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "Ticket1": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "Ticket2": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "OverGain": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "OverLoss": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "Ultima": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "Fase3": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
                            "Assicurazione": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0}
                        }
                    
                    if chiave != "Altro":
                        st = dati[nome_strumento]["stats"][chiave]
                        st["pnl"] += pnl_eur
                        st["totale"] += 1
                        if pnl_eur > 0:
                            st["profit"] += 1
                        else:
                            st["loss"] += 1
                    
                    with open(FILE_MEMORIA, "w") as fm:
                        json.dump(dati, fm, indent=4)
                break
            except:
                time.sleep(0.1)
        # ---------------------------------------------
        
        FILE_STORICO = "storico_operazioni.csv"
        file_esiste = os.path.exists(FILE_STORICO)
        
        with open(FILE_STORICO, "a", encoding="utf-8") as f:
            if not file_esiste:
                f.write("Data,Strumento,Fase,Profitto_EUR,DealID\n")
            
            ora = now_it().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{ora},{nome_strumento},{fase_label},{pnl_eur:.2f},LOCAL\n")
            
    except Exception as e:
        print_log("SISTEMA", f"⚠️ Errore scrittura storico CSV/Stats: {e}")

def stampa_riepilogo_statistiche(nome_strumento):
    try:
        with open(FILE_MEMORIA, "r") as f:
            dati = json.load(f)
            
        if nome_strumento not in dati or "stats" not in dati[nome_strumento]:
            return
            
        stats = dati[nome_strumento]["stats"]
        
        riepilogo = []
        riepilogo.append("-----------------------------------------------------------")
        riepilogo.append("📊 RIEPILOGO GENERALE CICLO OPERATIVO:")
        tot_subtrading = 0.0
        tot_profit = 0
        tot_loss = 0
        
        tot_subtrading = 0.0
        tot_profit = 0
        tot_loss = 0
        for key in ["Micro", "Flip", "Ticket1", "Ticket2", "OverGain", "OverLoss", "Ultima"]:
            st = stats[key]
            tot_subtrading += st['pnl']
            tot_profit += st['profit']
            tot_loss += st['loss']
            
        tot_trades = tot_profit + tot_loss
        perc_pos = (tot_profit / tot_trades * 100) if tot_trades > 0 else 0
        riga_totale = f"Totale Sottotrading [{tot_subtrading:+.0f} €] - Profit: {tot_profit} - Loss: {tot_loss} [{perc_pos:.0f}%]"
        
        for key in ["Micro", "Flip", "Ticket1", "Ticket2", "OverGain", "OverLoss", "Ultima"]:
            st = stats[key]
            val = st['pnl']
            riga = f"{key} [{val:+.0f} €] Totale: {st['totale']} - Profit: {st['profit']} - Loss: {st['loss']}"
            riepilogo.append(riga)
            
        riepilogo.append(riga_totale)
        
        st_ass = stats.get("Assicurazione", {"pnl": 0.0})
        riga_ass = f"Assicurazione [{st_ass['pnl']:+.0f} €]"
        riepilogo.append(riga_ass)
        
        st_f3 = stats.get("Fase3", {"pnl": 0.0})
        val_f3 = st_f3['pnl']
        riga_f3 = f"FASE3 [{val_f3:+.0f} €]"
        riepilogo.append(riga_f3)
        riepilogo.append("-----------------------------------------------------------")
        
        for r in riepilogo:
            print_log(nome_strumento, r)
            
        # Reset delle statistiche
        dati[nome_strumento]["stats"] = {
            "Micro": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Flip": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Ticket1": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Ticket2": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "OverGain": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "OverLoss": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Ultima": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Fase3": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0},
            "Assicurazione": {"pnl": 0.0, "totale": 0, "profit": 0, "loss": 0}
        }
        with open(FILE_MEMORIA, "w") as fm:
            json.dump(dati, fm, indent=4)
            
    except Exception as e:
        print_log("SISTEMA", f"⚠️ Errore stampa riepilogo statistiche: {e}")

def calcola_durata_sessione():
    if not os.path.exists(FILE_TOKEN):
        return "0h 00m"
    tempo_creazione = os.path.getmtime(FILE_TOKEN)
    durata = now_it() - datetime.datetime.fromtimestamp(tempo_creazione, TZ_ITALIA)
    ore = int(durata.total_seconds() // 3600)
    minuti = int((durata.total_seconds() % 3600) // 60)
    return f"{ore}h {minuti}m"

def aggiorna_memoria(nome_strumento, aggiornamenti, log_wip=None):
    for _ in range(10): 
        try:
            with open(FILE_MEMORIA, "r") as f:
                dati = json.load(f)
            
            if nome_strumento in dati:
                dati[nome_strumento].update(aggiornamenti)
                if log_wip:
                    log_wip = log_wip.replace("BUY", "LONG").replace("SELL", "SHORT")
                    if "storico_wip" not in dati[nome_strumento]:
                        dati[nome_strumento]["storico_wip"] = []
                    ora = now_it().strftime("%d/%m %H:%M:%S")
                    dati[nome_strumento]["storico_wip"].append(f"[{ora}] {log_wip}")
                
                with open(FILE_MEMORIA, "w") as f:
                    json.dump(dati, f, indent=4)
            return
        except Exception:
            time.sleep(0.5)
    print_log(nome_strumento, "⚠️ Errore salvataggio Diario: File bloccato.")

ULTIMO_SALVATAGGIO_REPORT = None

def salva_report_giornaliero(saldo, margine, drawdown):
    global ULTIMO_SALVATAGGIO_REPORT
    ora = now_it()
    
    # Lunedì=0, Venerdì=4. Escludiamo Sabato (5) e Domenica (6)
    if ora.weekday() > 4:
        return
        
    # Alle 21:30 o successivo
    if ora.hour >= 21:
        if ora.hour == 21 and ora.minute < 30:
            return
            
        data_odierna = ora.strftime("%Y-%m-%d")
        
        if ULTIMO_SALVATAGGIO_REPORT != data_odierna:
            file_report = "report_giornaliero.csv"
            file_esiste = os.path.exists(file_report)
            
            if file_esiste:
                try:
                    with open(file_report, "r", encoding="utf-8") as f:
                        for riga in f:
                            if riga.startswith(f"{data_odierna},"):
                                ULTIMO_SALVATAGGIO_REPORT = data_odierna
                                return
                except Exception:
                    pass
            
            try:
                with open(file_report, "a", encoding="utf-8") as f:
                    if not file_esiste:
                        f.write("Data,Capitale Totale,Margine Utilizzato,Drawdown\n")
                    f.write(f"{data_odierna},{saldo},{margine},{drawdown}\n")
                    
                ULTIMO_SALVATAGGIO_REPORT = data_odierna
                print_log("SISTEMA", "💾 Salvato report giornaliero delle 21:30.")
            except Exception as e:
                print_log("SISTEMA", f"⚠️ Errore salvataggio report giornaliero: {e}")

def scrivi_stato_sistema(saldo, disponibile, margine, drawdown, messaggio, prezzi_live=None, distanze_minime=None, prezzi_bid_ask=None):
    salva_report_giornaliero(saldo, margine, drawdown)
    dati = {
        "saldo": str(saldo),
        "disponibile": str(disponibile),
        "margine": str(margine),
        "drawdown": str(drawdown),
        "messaggio": messaggio,
        "durata_sessione": calcola_durata_sessione(),
        "ultimo_aggiornamento": now_it().strftime("%H:%M:%S"),
        "prezzi_live": prezzi_live or {},
        "distanze_minime": distanze_minime or {},
        "prezzi_bid_ask": prezzi_bid_ask or {}
    }
    with open("stato_sistema.json", "w") as f:
        json.dump(dati, f, indent=4)

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
                print_log("SISTEMA", "⏳ Rate Limit API (403) rilevato. Pausa 30s...")
                time.sleep(30)
                continue
                
            return r
        except Exception:
            time.sleep(1.5)
            
    return None

def esegui_login_ig():
    h = {"X-IG-API-KEY": config.get("IG_API_KEY"), "Version": "2", "Content-Type": "application/json"}
    p = {"identifier": config.get("IG_USERNAME"), "password": config.get("IG_PASSWORD")}
    
    try:
        r = requests.post(f"{BASE_URL}/session", headers=h, json=p, timeout=10)
        if r and r.status_code == 200:
            with open(FILE_TOKEN, "w") as f:
                json.dump({"CST": r.headers.get('CST'), "X-SECURITY-TOKEN": r.headers.get('X-SECURITY-TOKEN')}, f)
            return True
        else:
            print_log("SISTEMA", f"⚠️ IG Rifiuta Login: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print_log("SISTEMA", f"⚠️ Errore Rete al Login: {e}")
        return False

def ottieni_dati_mercati_batch(h):
    epics = [c["epic"] for c in CONFIG_STRUMENTI.values()]
    epics_str = ",".join(epics)
    h_batch = h.copy()
    h_batch["Version"] = "1"
    risultato = {}
    
    for _ in range(3):
        try:
            r = requests.get(f"{BASE_URL}/markets?epics={epics_str}", headers=h_batch, timeout=10)
            if r.status_code == 403 and "exceeded-api-key" in r.text:
                print_log("SISTEMA", "⏳ Rate Limit API (403) su Mercati Batch. Pausa 30s...")
                time.sleep(30)
                continue
            
            if r.status_code != 200:
                h_batch["Version"] = "2" if h_batch["Version"] == "1" else "1"
                r = requests.get(f"{BASE_URL}/markets?epics={epics_str}", headers=h_batch, timeout=10)
            
            if r.status_code == 200:
                markets = r.json().get("marketDetails", [])
                for m in markets:
                    epic_resp = m.get("instrument", {}).get("epic")
                    bid = m.get("snapshot", {}).get("bid")
                    ask = m.get("snapshot", {}).get("offer")
                    status = m.get("snapshot", {}).get("marketStatus")
                    min_dist = m.get("dealingRules", {}).get("minNormalStopOrLimitDistance", {}).get("value", 0)
                    
                    if epic_resp and bid is not None and ask is not None:
                        nome = next((n for n, c in CONFIG_STRUMENTI.items() if c["epic"] == epic_resp), None)
                        if nome:
                            dec = CONFIG_STRUMENTI[nome]["decimali"]
                            risultato[nome] = {
                                "bid": round(float(bid), dec),
                                "ask": round(float(ask), dec),
                                "status": status,
                                "min_dist": min_dist
                            }
                return risultato
        except Exception:
            time.sleep(1.5)
            
    return risultato

def ottieni_e_scrivi_saldo(h, prezzi_live=None, dist_min=None, prezzi_bid_ask=None):
    try:
        h_conti = h.copy()
        h_conti["Version"] = "1"
        r = requests.get(f"{BASE_URL}/accounts", headers=h_conti, timeout=10)
        if r.status_code == 200:
            dati = r.json()
            il_mio_conto = dati['accounts'][0]
            
            bal = il_mio_conto['balance'].get('balance', 0)
            disp = il_mio_conto['balance'].get('available', 0)
            marg = il_mio_conto['balance'].get('deposit', 0)
            dd = il_mio_conto['balance'].get('profitLoss', 0)
            
            scrivi_stato_sistema(bal, disp, marg, dd, "Sistema Online", prezzi_live, dist_min, prezzi_bid_ask)
    except Exception:
        pass

def verifica_token_ig():
    if not os.path.exists(FILE_TOKEN):
        return esegui_login_ig()
        
    with open(FILE_TOKEN, "r") as f:
        token_dati = json.load(f)
        
    h = {"X-IG-API-KEY": config.get("IG_API_KEY"), "CST": token_dati.get("CST"), "X-SECURITY-TOKEN": token_dati.get("X-SECURITY-TOKEN"), "Version": "1", "Accept": "application/json"}
    r = requests.get(f"{BASE_URL}/accounts", headers=h, timeout=10)
    
    if r and r.status_code == 200:
        return True
    else:
        return esegui_login_ig()

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
    
    p = {
        "epic": epic, 
        "expiry": "-", 
        "direction": direzione, 
        "size": size_str, 
        "orderType": "MARKET", 
        "timeInForce": "EXECUTE_AND_ELIMINATE", 
        "guaranteedStop": False, 
        "forceOpen": True, 
        "currencyCode": valuta
    }
    
    if limit_lvl is not None:
        p["limitLevel"] = formatta_numero(limit_lvl, dec)
    if stop_lvl is not None:
        p["stopLevel"] = formatta_numero(stop_lvl, dec)
    
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
                        motivo = confirm_data if isinstance(confirm_data, str) else "Unknown"
                        print_log(nome_strumento, f"❌ [IG REJECT] {etichetta} {direzione}: {motivo}")
                        print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s per assestamento server...")
                        time.sleep(20)
                        continue
                    if isinstance(confirm_data, dict):
                        if confirm_data.get("level") is not None:
                            real_level = float(confirm_data.get("level"))
                        if confirm_data.get("dealId"):
                            deal_id = confirm_data.get("dealId")

                if real_level is None:
                    try:
                        time.sleep(1.0)
                        resp_p = chiamata_api_sicura('GET', f"{BASE_URL}/positions", headers)
                        if resp_p and resp_p.status_code == 200:
                            p_list = [pos for pos in resp_p.json().get('positions', []) if pos['market']['epic'] == epic and pos['position']['direction'] == direzione and abs(float(pos['position']['size']) - float(size)) < 0.001]
                            if p_list:
                                real_level = float(p_list[0]['position']['level'])
                                deal_id = p_list[0]['position']['dealId']
                    except Exception:
                        pass

                if real_level is not None:
                    real_level = round(float(real_level), dec)

                livello_log = f" a {formatta_numero(real_level, dec)}" if real_level is not None else ""
                print_log(nome_strumento, f"✅ {etichetta} eseguito con successo{livello_log}.")
                suona_drumroll()
                return True, real_level, deal_id

            else:
                if r.status_code == 403 and "exceeded-api-key" in r.text:
                    print_log(nome_strumento, f"⏳ Rate Limit API (403). Pausa 30s...")
                    time.sleep(30)
                else:
                    print_log(nome_strumento, f"⚠️ Rifiuto API {etichetta} {direzione}: {r.text}")
                    print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s per assestamento server...")
                    time.sleep(20)
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione Rete su {etichetta} {direzione}: {e}")
            print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s per assestamento server...")
            time.sleep(20)
            
    return False, None, None

def invia_ordine_pendente(nome_strumento, epic, valuta, direzione, size, livello, tipo, lim, stop, headers, dec, etichetta="[ORDINE]"):
    size_str = str(int(size)) if float(size).is_integer() else str(size)
    
    p = {
        "epic": epic, 
        "expiry": "-", 
        "direction": direzione, 
        "size": size_str, 
        "level": formatta_numero(livello, dec), 
        "type": tipo, 
        "timeInForce": "GOOD_TILL_CANCELLED", 
        "forceOpen": True, 
        "guaranteedStop": False, 
        "currencyCode": valuta
    }
    
    if lim is not None:
        try:
            lim_val = float(lim)
            liv_val = float(livello)
            if liv_val > 0 and abs(lim_val - liv_val) / liv_val < 0.3:
                p["limitLevel"] = formatta_numero(lim_val, dec)
            else:
                p["limitDistance"] = str(int(round(lim_val)))
        except:
            p["limitLevel"] = formatta_numero(lim, dec)
            
    if stop is not None:
        try:
            stop_val = float(stop)
            liv_val = float(livello)
            if liv_val > 0 and abs(stop_val - liv_val) / liv_val < 0.3:
                p["stopLevel"] = formatta_numero(stop_val, dec)
            else:
                p["stopDistance"] = str(int(round(stop_val)))
        except:
            p["stopLevel"] = formatta_numero(stop, dec)
        
    headers_req = headers.copy()
    headers_req["Version"] = "2"
    
    for tentativo in range(4): 
        try:
            r = requests.post(f"{BASE_URL}/workingorders/otc", headers=headers_req, json=p, timeout=10)
            if r.status_code == 200:
                deal_ref = r.json().get("dealReference")
                if deal_ref:
                    accettato, motivo = verifica_conferma_deal(deal_ref, headers_req)
                    if not accettato:
                        print_log(nome_strumento, f"❌ [IG REJECT] {etichetta} {tipo} {direzione}: {motivo}")
                        print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s per assestamento server...")
                        time.sleep(20)
                        continue
                print_log(nome_strumento, f"✅ {etichetta} inserito con successo.")
                return True
            else:
                if r.status_code == 403 and "exceeded-api-key" in r.text:
                    print_log(nome_strumento, f"⏳ Rate Limit API (403). Pausa 30s...")
                    time.sleep(30)
                else:
                    print_log(nome_strumento, f"⚠️ Rifiuto API {etichetta} {direzione}: {r.text}")
                    print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s per assestamento server...")
                    time.sleep(20)
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione Rete su {etichetta} {direzione}: {e}")
            print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s per assestamento server...")
            time.sleep(20)
            
    return False
    
def chiudi_parziale(nome_strumento, dealId, epic, dir_chiusura, size, valuta, headers, etichetta="[POSIZIONE]"):
    h = headers.copy()
    h["Version"] = "1"
    h["_method"] = "DELETE"
    size_str = str(int(size)) if float(size).is_integer() else str(size)
    
    p = {
        "dealId": dealId, 
        "direction": dir_chiusura, 
        "size": size_str, 
        "orderType": "MARKET"
    }
    
    for tentativo in range(4):
        try:
            r = requests.post(f"{BASE_URL}/positions/otc", headers=h, json=p, timeout=10)
            if r.status_code == 200: 
                print_log(nome_strumento, f"✅ Chiusura posizione {etichetta} eseguita con successo.")
                return True
            else:
                if r.status_code == 403 and "exceeded-api-key" in r.text:
                    print_log(nome_strumento, f"⏳ Rate Limit API (403). Pausa 30s...")
                    time.sleep(30)
                else:
                    print_log(nome_strumento, f"⚠️ Errore Chiusura {etichetta} ({dealId}): {r.text}")
                    print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s...")
                    time.sleep(20)
        except Exception as e:
            print_log(nome_strumento, f"⚠️ Eccezione su Chiusura {etichetta}: {e}")
            print_log(nome_strumento, f"⏳ Tentativo {tentativo+1} fallito. Pausa 20s...")
            time.sleep(20)
            
    return False

def aggiorna_stop_posizione(deal_id, stop_level, headers):
    url = f"{BASE_URL}/positions/otc/{deal_id}"
    payload = {}
    if stop_level is not None:
        payload["stopLevel"] = str(stop_level)
    else:
        payload["stopLevel"] = None
    
    # Non usiamo chiamata_api_sicura qui perché vogliamo il codice di stato nudo e crudo
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            return True
        else:
            print(f"Errore aggiorna stop {deal_id}: {r.text}")
            return False
    except Exception as e:
        print(f"Eccezione aggiorna_stop_posizione: {e}")
        return False

def pulisci_mercato(epic, headers_auth, nome_strumento, solo_pendenti=False, mantieni_core_size=None):
    resp_ordini = chiamata_api_sicura('GET', f"{BASE_URL}/workingorders", headers_auth)
    
    if resp_ordini and resp_ordini.status_code == 200:
        for o in resp_ordini.json().get('workingOrders', []):
            if o['marketData']['epic'] == epic:
                chiamata_api_sicura('DELETE', f"{BASE_URL}/workingorders/otc/{o['workingOrderData']['dealId']}", headers_auth)
                time.sleep(1.5) 
    
    if solo_pendenti:
        return

    resp_pos = chiamata_api_sicura('GET', f"{BASE_URL}/positions", headers_auth)
    if resp_pos and resp_pos.status_code == 200:
        valuta = CONFIG_STRUMENTI.get(nome_strumento, {}).get("valuta", "USD")
        for p in resp_pos.json().get('positions', []):
            if p['market']['epic'] == epic:
                if mantieni_core_size and float(p['position']['size']) == mantieni_core_size:
                    continue 
                dir_chiusura = "SELL" if p['position']['direction'] == "BUY" else "BUY"
                chiudi_parziale(nome_strumento, p['position']['dealId'], epic, dir_chiusura, p['position']['size'], valuta, headers_auth, etichetta="[ORFANA]")
                time.sleep(1.5) 

# --- FUNZIONE CENTRALIZZATA DI SICUREZZA API ---
def verifica_falso_allarme_ig(nome_strumento, epic, headers, target_size, target_dir, etichetta, pos_attese=0, no_stop=False):
    tracker = falsi_allarmi_tracker.get(nome_strumento, {"count": 0, "last_time": 0, "ignored": {}})
    
    # Se abbiamo già superato i 5 tentativi di recente, ignoriamo silenziosamente per non bloccare il motore
    if tracker.get("ignored", {}).get(etichetta, 0) > time.time():
        return True

    print_log(nome_strumento, f"⏳ Ordine {etichetta} non rilevato. Pausa di 6s per assestamento server IG...")
    time.sleep(6.0)
    
    resp_pos_check = chiamata_api_sicura('GET', f"{BASE_URL}/positions", headers)
    falso_allarme_pos = False
    if resp_pos_check and resp_pos_check.status_code == 200:
        pos_agg = [p for p in resp_pos_check.json().get('positions', []) if p['market']['epic'] == epic]
        if no_stop:
            pos_agg = [p for p in pos_agg if p['position'].get('stopLevel') is None]
        if target_dir:
            falso_allarme_pos = len([p for p in pos_agg if float(p['position']['size']) == target_size and p['position']['direction'] == target_dir]) > pos_attese
        else:
            falso_allarme_pos = len([p for p in pos_agg if float(p['position']['size']) == target_size]) > pos_attese
            
    resp_ord_check = chiamata_api_sicura('GET', f"{BASE_URL}/workingorders", headers)
    falso_allarme_ord = False
    if resp_ord_check and resp_ord_check.status_code == 200:
        ord_agg = [o for o in resp_ord_check.json().get('workingOrders', []) if o['marketData']['epic'] == epic]
        if no_stop:
            ord_agg = [o for o in ord_agg if o['workingOrderData'].get('orderType') == 'LIMIT']
        if target_dir:
            falso_allarme_ord = len([o for o in ord_agg if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == target_size and o['workingOrderData']['direction'] == target_dir]) > 0
        else:
            falso_allarme_ord = len([o for o in ord_agg if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == target_size]) > 0
    
    if falso_allarme_pos or falso_allarme_ord:
        ora = time.time()
        
        # Reset se è passato più di 1 minuto dall'ultimo falso allarme
        if ora - tracker["last_time"] > 60:
            tracker["count"] = 0
            
        tracker["count"] += 1
        tracker["last_time"] = ora
        falsi_allarmi_tracker[nome_strumento] = tracker
        
        if tracker["count"] >= 5:
            testo_alert = f"Anomalia su {etichetta}: ordine non rilevato, ma possibili tracce trovate. Attesa verifica manuale."
            print_log(nome_strumento, f"🛑 Anomalia confermata ({etichetta}). Segnalo in Sintesi e interrompo i controlli attivi per 1 ora (Rimango in Automatico).")
            aggiorna_memoria(nome_strumento, {"alert_falso_allarme": testo_alert})
            
            if "ignored" not in tracker:
                tracker["ignored"] = {}
            tracker["ignored"][etichetta] = ora + 3600 # ignora per 1 ora
            tracker["count"] = 0
            return True

        print_log(nome_strumento, f"✅ Falso allarme IG. Ordine o Posizione {etichetta} rilevata dopo l'attesa. Nessun rimpiazzo. (Tentativo {tracker['count']}/5)")
        return True
        
    print_log(nome_strumento, f"⚠️ {etichetta} effettivamente mancante. Procedo con il rimpiazzo...")
    return False

def esegui_fase_1(nome, dir, size, tp, opp, dts, bid, ask, mult, dec, epic, val, h):
    base = round(float(ask if dir == "LONG" else bid), dec)
    
    s_core = size
    s_ass = max(1, size / 2)
    tp4 = round((tp / 4) * mult, dec)
    opp_val = round(opp * mult, dec)
    
    print_log(nome, f"🚀 [PRE-FLIGHT CHECK] Avvio test griglia FASE 1 in direzione {dir}")
    
    if dir == "LONG":
        pend_core_ok = invia_ordine_pendente(nome, epic, val, "SELL", s_core, round(base - opp_val, dec), "STOP", None, None, h, dec, etichetta="[ORDINE CORE]")
        time.sleep(3.0)
        pend_micro_ok = invia_ordine_pendente(nome, epic, val, "SELL", s_ass, round(base + tp4, dec), "LIMIT", base, round(base + (2 * tp4), dec), h, dec, etichetta="[ORDINE MICRO]")
        
        if pend_core_ok and pend_micro_ok:
            print_log(nome, "✅ Griglia accettata da IG. Procedo con l'entrata a mercato...")
            succ_core, lvl_core, deal_core = invia_ordine_mercato(nome, epic, val, "BUY", s_core, h, dec, etichetta="[ORDINE CORE]")
            time.sleep(3.0) 
            succ_ass, lvl_ass, deal_ass = invia_ordine_mercato(nome, epic, val, "SELL", s_ass, h, dec, etichetta="[ORDINE ASSICURAZIONE]")
            return succ_core, succ_ass, lvl_core
        else:
            print_log(nome, "❌ Griglia RIFIUTATA da IG. Rollback di sicurezza. Non entro a mercato.")
            pulisci_mercato(epic, h, nome, solo_pendenti=True)
            return False, False, None
            
    else:
        pend_core_ok = invia_ordine_pendente(nome, epic, val, "BUY", s_core, round(base + opp_val, dec), "STOP", None, None, h, dec, etichetta="[ORDINE CORE]")
        time.sleep(3.0)
        pend_micro_ok = invia_ordine_pendente(nome, epic, val, "BUY", s_ass, round(base - tp4, dec), "LIMIT", base, round(base - (2 * tp4), dec), h, dec, etichetta="[ORDINE MICRO]")
        
        if pend_core_ok and pend_micro_ok:
            print_log(nome, "✅ Griglia accettata da IG. Procedo con l'entrata a mercato...")
            succ_core, lvl_core, deal_core = invia_ordine_mercato(nome, epic, val, "SELL", s_core, h, dec, etichetta="[ORDINE CORE]")
            time.sleep(3.0)
            succ_ass, lvl_ass, deal_ass = invia_ordine_mercato(nome, epic, val, "BUY", s_ass, h, dec, etichetta="[ORDINE ASSICURAZIONE]")
            return succ_core, succ_ass, lvl_core
        else:
            print_log(nome, "❌ Griglia RIFIUTATA da IG. Rollback di sicurezza. Non entro a mercato.")
            pulisci_mercato(epic, h, nome, solo_pendenti=True)
            return False, False, None

def esegui_motore():
    try:
        print_log("SISTEMA", f"--- MOTORE AVVIATO PER CONTO: {NOME_CONTO} ---")
        
        if DEV_MODE:
            print_log("SISTEMA", "🔧 [DEV MODE ATTIVA] - Connessione IG bypassata. Modalità offline.")
        else:
            while not verifica_token_ig(): 
                print_log("SISTEMA", "❌ Accesso fallito. Riprovo tra 30 secondi...")
                time.sleep(30)
                
            print_log("SISTEMA", "✅ Connesso a IG con successo!")

        if os.path.exists(FILE_TOKEN):
            with open(FILE_TOKEN, "r") as f:
                token_dati = json.load(f)
            h = {
                "X-IG-API-KEY": config.get("IG_API_KEY"), 
                "CST": token_dati.get("CST"), 
                "X-SECURITY-TOKEN": token_dati.get("X-SECURITY-TOKEN"), 
                "Version": "1", 
                "Accept": "application/json"
            }
        else:
            h = {}
        
        ultimo_controllo_saldo = 0

        import random
        while True:
            if DEV_MODE:
                mem = carica_memoria(NOME_CONTO)
                for nome, dati in mem.items():
                    if dati.get("attivo", False):
                        if random.random() < 0.2:  # 20% probabilità ogni 10 secondi
                            msgs = [
                                "🎯 [EVENTO]: TICKET1 a target! Ping-Pong: Rigirato.",
                                "🔄 [EVENTO]: Rientro nel canale riuscito. SAT1 OCO piazzati.",
                                "🛑 [EVENTO]: SL colpito su TICKET2.",
                                "✅ [EVENTO]: FASE 3 COMPLETATA AL 100%!"
                            ]
                            aggiorna_memoria(nome, {}, log_wip=f"🔧 [TEST DEV]: {random.choice(msgs)}")
                time.sleep(10)
                continue

            ora_attuale = time.time()
            
            richiede_rinnovo = False
            if not os.path.exists(FILE_TOKEN):
                print_log("SISTEMA", "🔄 RESTART VM ricevuto o token mancante: Rinnovo sessione IG in corso...")
                richiede_rinnovo = True
            else:
                tempo_creazione = os.path.getmtime(FILE_TOKEN)
                if (time.time() - tempo_creazione) > (70 * 3600):
                    print_log("SISTEMA", "⚠️ Sessione vicina alle 72h: Mi preparo al rinnovo automatico del Token IG.")
                    richiede_rinnovo = True
            
            if richiede_rinnovo:
                esegui_login_ig()
                if os.path.exists(FILE_TOKEN):
                    with open(FILE_TOKEN, "r") as f:
                        token_dati = json.load(f)
                    h = {
                        "X-IG-API-KEY": config.get("IG_API_KEY"), 
                        "CST": token_dati.get("CST"), 
                        "X-SECURITY-TOKEN": token_dati.get("X-SECURITY-TOKEN"), 
                        "Version": "1", 
                        "Accept": "application/json"
                    }
                    invia_notifica(f"🔄 TOKEN RINNOVATO: {NOME_CONTO}", f"Il token di sessione IG per il conto {NOME_CONTO} è stato rinnovato o rigenerato con successo.", "arrows_counterclockwise")

            dati_mercati = ottieni_dati_mercati_batch(h)
            
            prezzi_live = {}
            distanze_minime = {}
            prezzi_bid_ask = {}
            
            for n, v in dati_mercati.items():
                prezzi_live[n] = round(float((v["bid"]+v["ask"])/2), CONFIG_STRUMENTI[n]["decimali"])
                distanze_minime[n] = v["min_dist"]
                prezzi_bid_ask[n] = {"bid": v["bid"], "ask": v["ask"]}
            
            if ora_attuale - ultimo_controllo_saldo >= 15:
                ottieni_e_scrivi_saldo(h, prezzi_live, distanze_minime, prezzi_bid_ask)
                ultimo_controllo_saldo = ora_attuale

            resp_pos_global = chiamata_api_sicura('GET', f"{BASE_URL}/positions", h)
            if resp_pos_global and resp_pos_global.status_code == 200:
                posizioni_totali = resp_pos_global.json().get('positions', [])
            else:
                posizioni_totali = []
            
            resp_ord_global = chiamata_api_sicura('GET', f"{BASE_URL}/workingorders", h)
            if resp_ord_global and resp_ord_global.status_code == 200:
                ordini_totali = resp_ord_global.json().get('workingOrders', [])
            else:
                ordini_totali = []

            if os.path.exists(FILE_MEMORIA):
                try:
                    with open(FILE_MEMORIA, "r") as f: 
                        dati = json.load(f)
                except Exception:
                    continue
                            
                for nome, param in dati.items():
                    if param.get("tipo_strategia", "RANGE") == "TREND":
                        continue
                        
                    epic = CONFIG_STRUMENTI.get(nome, {}).get("epic")
                    c = CONFIG_STRUMENTI.get(nome)
                    
                    if not c:
                        continue
                        
                    dec = c["decimali"]
                    mult = c["moltiplicatore"]
                    valuta = c["valuta"]
                    s_core = float(param.get("size", 0))
                    
                    dm = dati_mercati.get(nome)
                    bid = dm["bid"] if dm else None
                    ask = dm["ask"] if dm else None
                    stato_mercato = (dm["status"] == 'TRADEABLE') if dm else False
                    ig_min_dist = dm["min_dist"] if dm else 0

                    posizioni = [p for p in posizioni_totali if p['market']['epic'] == epic]
                    pendenti = [o for o in ordini_totali if o['marketData']['epic'] == epic]
                    
                    min_param_impostato = min(param.get("opp", 0), param.get("dts", 0), param.get("tp", 0) / 4)


                    if param.get("comando_reset", False):
                        print_log(nome, "🧹 RESET FORZATO richiesto.")
                        pnl_str = ""
                        if bid and ask:
                            pnl = calcola_pnl_chiusura([p for p in posizioni if p['market']['epic'] == epic], round((bid+ask)/2, dec), nome, prezzi_live)
                            pnl_str = formatta_pnl(pnl)
                            registra_operazione(nome, "Chiusura Manuale / Reset", pnl)
                        pulisci_mercato(epic, h, nome)
                        aggiorna_memoria(nome, {"comando_reset": False, "stato": "IN_ATTESA", "prezzo_base": None, "pausa_mercato": False, "attivo": False, "allarme_distanza": False, "errore_avvio": False, "errore_ripristino": False, "comando_manuale": False, "comando_riattiva_fase2": False, "comando_restore": None, "ticket2_active": False}, log_wip=f"🧹 RESET FORZATO completato. Posizioni chiuse.{pnl_str}")
                        continue

                    if param.get("comando_manuale", False):
                        print_log(nome, "👤 Comando MANUALE ricevuto. Pulizia ordini in corso...")
                        pulisci_mercato(epic, h, nome, solo_pendenti=True)
                        aggiorna_memoria(nome, {
                            "comando_manuale": False, 
                            "attivo": False, 
                            "stato": "MANUALE"
                        }, log_wip="👤 Motore Sospeso richiesto. Ordini orfani cancellati.")
                        continue
                        
                    if param.get("comando_restore"):
                        cmd = param["comando_restore"]
                        print_log(nome, f"🛠️ Ricevuto comando RECOVERY: {cmd.get('etichetta', '')}")
                        
                        if cmd["azione"] == "MERCATO":
                            succ, lvl_rec, deal_rec = invia_ordine_mercato(nome, epic, valuta, cmd["dir"], cmd["size"], h, dec, limit_lvl=cmd.get("lim"), stop_lvl=cmd.get("stop"), etichetta=cmd.get("etichetta", "[RECOVERY]"))
                        elif cmd["azione"] == "SAT1_OCO":
                            succ1 = invia_ordine_pendente(nome, epic, valuta, "BUY", cmd["size"], cmd["lvl_l"], "STOP", cmd["lim_l"], cmd["stop_l"], h, dec, etichetta="[ORDINE SAT1 OCO BUY]")
                            time.sleep(3.0)
                            succ2 = invia_ordine_pendente(nome, epic, valuta, "SELL", cmd["size"], cmd["lvl_s"], "STOP", cmd["lim_s"], cmd["stop_s"], h, dec, etichetta="[ORDINE SAT1 OCO SELL]")
                            succ = succ1 or succ2
                        else:
                            succ = invia_ordine_pendente(nome, epic, valuta, cmd["dir"], cmd["size"], cmd["livello"], cmd["tipo"], cmd.get("lim"), cmd.get("stop"), h, dec, etichetta=cmd.get("etichetta", "[RECOVERY]"))
                            
                        if succ:
                            invia_notifica(f"🛠️ RECOVERY: {nome}", f"[{nome}] Recovery {cmd.get('etichetta', '')} eseguito.", "wrench")
                            aggiorna_memoria(nome, {"comando_restore": None, "alert_falso_allarme": ""}, log_wip=f"🛠️ Eseguito comando RECOVERY manuale: {cmd.get('etichetta', '')}.")
                        else:
                            invia_notifica(f"⚠️ RECOVERY FALLITO: {nome}", f"[{nome}] Rifiuto ordine di Recovery da IG.", "warning")
                            aggiorna_memoria(nome, {"comando_restore": None}, log_wip=f"⚠️ Fallito inserimento RECOVERY manuale: {cmd.get('etichetta', '')}.")
                        continue
                        
                    if param.get("comando_riattiva_fase2", False):
                        print_log(nome, "🛰️ Richiesta RIATTIVAZIONE AUTO in Fase 2...")
                        aggiorna_memoria(nome, {"comando_riattiva_fase2": False}) 
                        
                        if not bid or not ask:
                            aggiorna_memoria(nome, {"msg_manuale": "❌ Dati di mercato live non disponibili. Riprova tra poco."})
                            continue
                            
                        prezzo_attuale = round((bid + ask) / 2, dec)
                        
                        core_long = [p for p in posizioni if p['position']['direction'] == "BUY" and float(p['position']['size']) == s_core]
                        core_short = [p for p in posizioni if p['position']['direction'] == "SELL" and float(p['position']['size']) == s_core]
                        
                        if not core_long or not core_short:
                            aggiorna_memoria(nome, {"msg_manuale": "❌ Impossibile riattivare: mancano le posizioni Core a mercato."})
                            continue
                            
                        lvl_long = float(core_long[0]['position']['level'])
                        lvl_short = float(core_short[0]['position']['level'])
                        
                        tp2_val = round((param.get("tp") / 2) * mult, dec)
                        
                        sat_long_lvl = round(lvl_long + tp2_val, dec)
                        sat_short_lvl = round(lvl_short - tp2_val, dec)
                        
                        dist_long = (sat_long_lvl - prezzo_attuale) / mult
                        dist_short = (prezzo_attuale - sat_short_lvl) / mult
                        limite_sicurezza = max(ig_min_dist, min_param_impostato) * 2.0
                        
                        fuori_canale = prezzo_attuale >= sat_long_lvl or prezzo_attuale <= sat_short_lvl
                        troppo_vicino = dist_long <= limite_sicurezza or dist_short <= limite_sicurezza
                        
                        if fuori_canale or troppo_vicino:
                            print_log(nome, "⚠️ Prezzo fuori parametri. Entro in FASE_2_STANDBY (Attesa Rientro).")
                            invia_notifica(f"⏳ STANDBY: {nome}", f"[{nome}] Prezzo fuori canale. Motore in STANDBY.", "hourglass_flowing_sand")
                            aggiorna_memoria(nome, {
                                "attivo": True,
                                "modalita_manuale": False,
                                "stato": "FASE_2_STANDBY",
                                "tentativi_sat": 0,
                                "msg_manuale": ""
                            }, log_wip=f"⏳ AUTO: In attesa di rientro a distanza di sicurezza dai SAT1 OCO (limite {limite_sicurezza}pt).")
                            continue
                        
                        s_mezzo = max(1.0, s_core / 2)
                        print_log(nome, "✅ Check superati. Piazzamento SAT1 OCO...")
                        
                        ris_l = invia_ordine_pendente(nome, epic, valuta, "BUY", s_mezzo, sat_long_lvl, "STOP", round(sat_long_lvl + tp2_val, dec), round(sat_long_lvl - tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO BUY]")
                        time.sleep(3.0)
                        ris_s = invia_ordine_pendente(nome, epic, valuta, "SELL", s_mezzo, sat_short_lvl, "STOP", round(sat_short_lvl - tp2_val, dec), round(sat_short_lvl + tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO SELL]")
                        
                        if ris_l and ris_s:
                            invia_notifica(f"🛰️ SAT1 OCO: {nome}", f"[{nome}] Riattivazione. SAT1 OCO (SHORT: {formatta_numero(sat_short_lvl, dec)} | LONG: {formatta_numero(sat_long_lvl, dec)}).", "satellite")
                            aggiorna_memoria(nome, {
                                "attivo": True,
                                "modalita_manuale": False,
                                "stato": "FASE_2_SATELLITI",
                                "prezzo_base": prezzo_attuale, 
                                "tentativi_sat": 1,
                                "msg_manuale": ""
                            }, log_wip=f"✅ [EVENTO]: Riattivazione AUTO (Fase 2). SAT1 OCO piazzati a {formatta_numero(sat_short_lvl, dec)} e {formatta_numero(sat_long_lvl, dec)}.")
                        else:
                            pulisci_mercato(epic, h, nome, solo_pendenti=True)
                            aggiorna_memoria(nome, {"msg_manuale": "❌ IG ha rifiutato i SAT1 OCO durante la riattivazione. Il Motore rimane in Manuale."})
                            
                        continue

                    if param.get("modalita_manuale", False):
                        continue
                        
                    if param.get("kill_switch", False):
                        print_log(nome, "🛑 Ricevuto comando STOP. Pulizia...")
                        pnl_str = ""
                        if bid and ask:
                            pnl = calcola_pnl_chiusura([p for p in posizioni if p['market']['epic'] == epic], round((bid+ask)/2, dec), nome, prezzi_live)
                            pnl_str = formatta_pnl(pnl)
                            registra_operazione(nome, "Stop Generale (Kill Switch)", pnl)
                        pulisci_mercato(epic, h, nome)
                        invia_notifica(f"🛑 STOP: {nome}", f"[{nome}] STOP premuto. Strumento chiuso.{pnl_str}", "octagonal_sign")
                        aggiorna_memoria(nome, {"kill_switch": False, "attivo": False, "stato": "IN_ATTESA", "sospeso_weekend": False, "allarme_distanza": False, "errore_avvio": False, "errore_ripristino": False, "ticket2_active": False}, log_wip=f"✅ [EVENTO]: Tutte le posizioni chiuse da Tasto STOP.{pnl_str}")
                        continue

                    # --- GESTIONE AUTOMATICA PAUSA ROLLOVER ---
                    ora_it = now_it()
                    is_rollover_time = False
                    # Dal lunedì sera al venerdì mattina presto:
                    # Lun-Gio 22:45 - 23:59:59 (weekday 0, 1, 2, 3)
                    # Mar-Ven 00:00 - 00:29:59 (weekday 1, 2, 3, 4)
                    t_curr = ora_it.time()
                    if ora_it.weekday() in (0, 1, 2, 3) and (datetime.time(22, 45) <= t_curr <= datetime.time(23, 59, 59)):
                        is_rollover_time = True
                    elif ora_it.weekday() in (1, 2, 3, 4) and (datetime.time(0, 0) <= t_curr <= datetime.time(0, 29, 59)):
                        is_rollover_time = True
                            
                    is_sosp_rollover = param.get("sospeso_rollover", False)
                    
                    if param.get("attivo", False) and not param.get("sospeso_weekend", False) and param.get("stato") != "MANUALE":
                        if is_rollover_time and not is_sosp_rollover:
                            print_log(nome, "🌙 INIZIO PAUSA ROLLOVER (22:45): Sgancio SL e cancello Pendenti...")
                            snap_pos = [{"dealId": p['position']['dealId'], "stopLevel": p['position'].get('stopLevel')} for p in posizioni if p['position'].get('stopLevel')]
                            snap_ord = [{"dealId": o['workingOrderData']['dealId'], "direction": o['workingOrderData']['direction'], "level": o['workingOrderData']['orderLevel'], "size": o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0)), "type": o['workingOrderData'].get('orderType', 'LIMIT'), "lim": o['workingOrderData'].get('limitLevel'), "stop": o['workingOrderData'].get('stopLevel')} for o in pendenti]
                            
                            for p in posizioni:
                                if p['position'].get('stopLevel'):
                                    aggiorna_stop_posizione(p['position']['dealId'], None, h)
                                    time.sleep(1.0)
                            
                            pulisci_mercato(epic, h, nome, solo_pendenti=True)
                            
                            aggiorna_memoria(nome, {"sospeso_rollover": True, "rollover_snapshot": {"posizioni": snap_pos, "pendenti": snap_ord}}, log_wip="🌙 [EVENTO]: Inizio Pausa Rollover. Pendenti rimossi e SL sganciati per protezione spread.")
                            continue
                            
                        elif is_sosp_rollover and not is_rollover_time:
                            print_log(nome, "☀️ FINE PAUSA ROLLOVER (00:29): Ripristino SL e Pendenti...")
                            snap = param.get("rollover_snapshot", {})
                            snap_pos = snap.get("posizioni", [])
                            snap_ord = snap.get("pendenti", [])
                            
                            for so in snap_ord:
                                invia_ordine_pendente(nome, epic, valuta, so['direction'], so['size'], so['level'], so['type'], so.get('lim'), so.get('stop'), h, dec, etichetta="[RIPRISTINO ROLLOVER]")
                                time.sleep(4.0)
                                
                            for sp in snap_pos:
                                pos_esiste = [p for p in posizioni if p['position']['dealId'] == sp['dealId']]
                                if pos_esiste:
                                    succ = aggiorna_stop_posizione(sp['dealId'], sp['stopLevel'], h)
                                    if not succ:
                                        print_log(nome, f"⚠️ Impossibile ripristinare SL su {sp['dealId']}. Probabile GAP. Chiudo a mercato.")
                                        dir_chiusura = "SELL" if pos_esiste[0]['position']['direction'] == "BUY" else "BUY"
                                        chiudi_parziale(nome, sp['dealId'], epic, dir_chiusura, pos_esiste[0]['position']['size'], valuta, h, etichetta="[CHIUSURA EMERGENZA GAP]")
                                    time.sleep(3.0)
                                
                            aggiorna_memoria(nome, {"sospeso_rollover": False, "rollover_snapshot": {}}, log_wip="☀️ [EVENTO]: Fine Pausa Rollover. SL e Pendenti ripristinati.")
                            continue
                            
                    if is_sosp_rollover:
                        continue
                        
                    if param.get("comando_weekend", False):
                        print_log(nome, "🌴 Avvio SOSPENSIONE WEEKEND. Isolo le Core...")
                        pnl_str = ""
                        if bid and ask:
                            pos_ibride = [p for p in posizioni if p['market']['epic'] == epic and float(p['position']['size']) != s_core]
                            if pos_ibride:
                                pnl = calcola_pnl_chiusura(pos_ibride, round((bid+ask)/2, dec), nome, prezzi_live)
                                pnl_str = formatta_pnl(pnl)
                                registra_operazione(nome, "Chiusura Pre-Weekend", pnl)
                        pulisci_mercato(epic, h, nome, mantieni_core_size=s_core)
                        pr_str = f" a {formatta_numero((bid+ask)/2, dec)}" if bid and ask else ""
                        aggiorna_memoria(nome, {"comando_weekend": False, "sospeso_weekend": True, "stato": "SOSPESO_WEEKEND", "msg_weekend": ""}, log_wip=f"✅ [EVENTO]: Sospensione Weekend{pr_str}. Isolate posizioni Core.{pnl_str}")
                        continue

                    if param.get("comando_riprendi", False):
                        if not stato_mercato:
                            aggiorna_memoria(nome, {"comando_riprendi": False, "msg_weekend": "Il mercato è attualmente CHIUSO. Attendi l'apertura prima di premere Riprendi."})
                            continue
                        print_log(nome, "▶️ Ripresa da Weekend. Controllo range prezzi...")
                        if not bid or not ask:
                            continue
                            
                        prezzo_attuale = round((bid + ask) / 2, dec)
                        
                        core_long = [p for p in posizioni if p['position']['direction'] == "BUY" and float(p['position']['size']) == s_core]
                        core_short = [p for p in posizioni if p['position']['direction'] == "SELL" and float(p['position']['size']) == s_core]
                        
                        if not core_long or not core_short:
                            aggiorna_memoria(nome, {"comando_riprendi": False, "msg_weekend": "Impossibile riprendere: mancano le posizioni Core a mercato."})
                            continue
                            
                        lvl_long = float(core_long[0]['position']['level'])
                        lvl_short = float(core_short[0]['position']['level'])
                        
                        tp2_val = round((param.get("tp") / 2) * mult, dec)
                        sat_long = round(lvl_long + tp2_val, dec)
                        sat_short = round(lvl_short - tp2_val, dec)
                        
                        if prezzo_attuale >= sat_long or prezzo_attuale <= sat_short:
                            msg = f"Prezzo a {formatta_numero(prezzo_attuale, dec)} FUORI RANGE. Deve tornare tra {formatta_numero(sat_short, dec)} e {formatta_numero(sat_long, dec)} per riprendere."
                            aggiorna_memoria(nome, {"comando_riprendi": False, "msg_weekend": msg})
                        else:
                            s_mezzo = max(1.0, s_core / 2)
                            invia_ordine_pendente(nome, epic, valuta, "BUY", s_mezzo, sat_long, "STOP", round(sat_long + tp2_val, dec), round(sat_long - tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO BUY]")
                            time.sleep(3.0) 
                            invia_ordine_pendente(nome, epic, valuta, "SELL", s_mezzo, sat_short, "STOP", round(sat_short - tp2_val, dec), round(sat_short + tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO SELL]")
                            
                            t2_str = ""
                            if param.get("ticket2_active"):
                                t2_dir = param.get("ticket2_dir")
                                t2_entry = param.get("ticket2_entry")
                                if t2_dir and t2_entry is not None:
                                    time.sleep(3.0)
                                    lim_lvl_t2 = round(t2_entry + (param.get("tp") / 4) * mult, dec) if t2_dir == "BUY" else round(t2_entry - (param.get("tp") / 4) * mult, dec)
                                    invia_ordine_pendente(nome, epic, valuta, t2_dir, s_mezzo, t2_entry, "LIMIT", lim_lvl_t2, None, h, dec, etichetta="[ORDINE TICKET2]")
                                    t2_str = f" + Ticket2 [{to_market_dir(t2_dir)} @ {formatta_numero(t2_entry, dec)}]"
                            
                            invia_notifica(f"🛰️ SAT1 OCO: {nome}", f"[{nome}] Ripresa weekend. SAT1 OCO (SHORT: {formatta_numero(sat_short, dec)} | LONG: {formatta_numero(sat_long, dec)}){t2_str}.", "satellite")
                            aggiorna_memoria(nome, {"comando_riprendi": False, "sospeso_weekend": False, "msg_weekend": "", "stato": "FASE_2_SATELLITI", "tentativi_sat": 1}, log_wip=f"✅ [EVENTO]: Ripresa da Weekend completata a {formatta_numero(prezzo_attuale, dec)}. Nuovi OCO piazzati{t2_str}.")
                            print_log(nome, f"✅ Ripresa completata. SAT1 OCO piazzati{t2_str}.")
                        continue

                    if param.get("sospeso_weekend", False):
                        continue

                    if not param.get("attivo", False):
                        if "IN_ATTESA" not in param.get("stato", "IN_ATTESA"):
                            pulisci_mercato(epic, h, nome)
                            aggiorna_memoria(nome, {"stato": "IN_ATTESA", "pausa_mercato": False, "tentativi_sat": 0, "allarme_distanza": False, "ticket2_active": False})
                        continue
                    
                    if not stato_mercato:
                        if not param.get("pausa_mercato", False):
                            print_log(nome, "🌙 MERCATO CHIUSO o NON DISPONIBILE. Standby...")
                            aggiorna_memoria(nome, {"pausa_mercato": True})
                        continue
                    elif stato_mercato:
                        if param.get("pausa_mercato", False):
                            print_log(nome, "☀️ MERCATO RIAPERTO! Ripresa operazioni.")
                            aggiorna_memoria(nome, {"pausa_mercato": False})

                    stato = param.get("stato", "IN_ATTESA")
                    
                    if ig_min_dist > 0 and min_param_impostato <= ig_min_dist:
                        if not param.get("allarme_distanza", False):
                            aggiorna_memoria(nome, {"allarme_distanza": True}, log_wip=f"✅ [EVENTO]: Avvio o prosecuzione sospesa. IG esige {ig_min_dist}pt di distanza minima. Il tuo parametro più stretto è {min_param_impostato}pt.")
                        continue
                    else:
                        if param.get("allarme_distanza", False):
                            aggiorna_memoria(nome, {"allarme_distanza": False}, log_wip=f"✅ [EVENTO]: Volatilità rientrata. Il limite di IG ({ig_min_dist}pt) permette ai tuoi parametri ({min_param_impostato}pt) di operare.")

                    if stato == "IN_ATTESA":
                        if bid and ask:
                            dir_core = param.get("direzione")
                            prezzo_base = round(float(ask if dir_core == "LONG" else bid), dec)
                            
                            dir_contro = "SELL" if dir_core == "LONG" else "BUY"
                            s_ass = max(1.0, s_core / 2)
                            succ_core, succ_ass, real_core_lvl = esegui_fase_1(nome, dir_core, s_core, param.get("tp"), param.get("opp"), param.get("dts"), bid, ask, mult, dec, epic, valuta, h)
                            
                            if succ_core and succ_ass:
                                if real_core_lvl is not None:
                                    prezzo_base = real_core_lvl
                                is_flip = len(param.get("storico_wip", [])) > 0
                                segno = "+" if to_market_dir(dir_core) == "LONG" else "-"
                                if not is_flip:
                                    invia_notifica(f"🚀 AVVIO FASE 1: {nome}", f"[{nome}] Core [{to_market_dir(dir_core)}] a {formatta_numero(prezzo_base, dec)} [{segno}{s_core}]", "rocket")
                                aggiorna_memoria(nome, {"stato": "FASE_1", "prezzo_base": prezzo_base, "errore_avvio": False, "errore_ripristino": False}, log_wip=f"✅ [EVENTO]: Core [{to_market_dir(dir_core)}] [{segno}{s_core}] a {formatta_numero(prezzo_base, dec)}")
                            else:
                                pulisci_mercato(epic, h, nome)
                                aggiorna_memoria(nome, {"attivo": False, "stato": "IN_ATTESA", "errore_avvio": True, "errore_ripristino": False, "ticket2_active": False}, log_wip=f"✅ [EVENTO]: Avvio Abortito: fallita immissione ordini a mercato (Core/Ass).")
                    
                    elif stato.startswith("FASE_1"): 
                        dir_core = param.get("direzione")
                        s_ass = max(1.0, s_core / 2)
                        
                        core_long = [p for p in posizioni if float(p['position']['size']) == s_core and p['position']['direction'] == "BUY"]
                        core_short = [p for p in posizioni if float(p['position']['size']) == s_core and p['position']['direction'] == "SELL"]
                        entrambe_core_attive = len(core_long) > 0 and len(core_short) > 0

                        p_base_orig = param.get("prezzo_base")
                        
                        if not entrambe_core_attive and p_base_orig is not None and (param.get("stato") == "FASE_1" or param.get("stato") == "FASE_1 + Micro"):
                            opp_val = round(param.get("opp") * mult, dec)
                            tp4 = round((param.get("tp") / 4) * mult, dec)

                            pend_core_dir = "SELL" if dir_core == "LONG" else "BUY"
                            pendenti_core = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_core and o['workingOrderData']['direction'] == pend_core_dir]
                            
                            if not pendenti_core:
                                if verifica_falso_allarme_ig(nome, epic, h, s_core, pend_core_dir, "[CORE]"):
                                    continue
                                
                                if dir_core == "LONG":
                                    succ = invia_ordine_pendente(nome, epic, valuta, "SELL", s_core, round(p_base_orig - opp_val, dec), "STOP", None, None, h, dec, etichetta="[ORDINE CORE]")
                                else:
                                    succ = invia_ordine_pendente(nome, epic, valuta, "BUY", s_core, round(p_base_orig + opp_val, dec), "STOP", None, None, h, dec, etichetta="[ORDINE CORE]")
                                
                                if succ:
                                    aggiorna_memoria(nome, {"tentativi_ripristino": 0})
                                else:
                                    tentativi = param.get("tentativi_ripristino", 0) + 1
                                    if tentativi >= 4:
                                        print_log(nome, "🛑 4 tentativi falliti. Sgancio Pilota Automatico e pulizia ordini orfani.")
                                        pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                        invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Falliti 4 tentativi consecutivi di ripristino ordine. Passaggio forzato a MANUALE per sicurezza.", "rotating_light")
                                        aggiorna_memoria(nome, {
                                            "attivo": False, 
                                            "errore_ripristino": True, 
                                            "tentativi_ripristino": 0
                                        }, log_wip="🛑 Spegnimento emergenza: falliti 4 tentativi di ripristino ordine. Motore Sospeso.")
                                    else:
                                        aggiorna_memoria(nome, {"tentativi_ripristino": tentativi})
                                time.sleep(3.0)
                                continue

                            pendenti_micro = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_ass]
                            micro_gia_a_mercato = len([p for p in posizioni if float(p['position']['size']) == s_ass]) >= 2 
                            
                            if not pendenti_micro and not micro_gia_a_mercato and param.get("stato") == "FASE_1":
                                if verifica_falso_allarme_ig(nome, epic, h, s_ass, None, "[MICRO]", pos_attese=1):
                                    continue
                                    
                                if dir_core == "LONG":
                                    succ = invia_ordine_pendente(nome, epic, valuta, "SELL", s_ass, round(p_base_orig + tp4, dec), "LIMIT", p_base_orig, round(p_base_orig + (2 * tp4), dec), h, dec, etichetta="[ORDINE MICRO]")
                                else:
                                    succ = invia_ordine_pendente(nome, epic, valuta, "BUY", s_ass, round(p_base_orig - tp4, dec), "LIMIT", p_base_orig, round(p_base_orig - (2 * tp4), dec), h, dec, etichetta="[ORDINE MICRO]")
                                
                                if succ:
                                    aggiorna_memoria(nome, {"tentativi_ripristino": 0})
                                else:
                                    tentativi = param.get("tentativi_ripristino", 0) + 1
                                    if tentativi >= 4:
                                        print_log(nome, "🛑 4 tentativi falliti. Sgancio Pilota Automatico e pulizia ordini orfani.")
                                        pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                        invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Falliti 4 tentativi consecutivi di ripristino ordine (Micro). Passaggio forzato a MANUALE.", "rotating_light")
                                        aggiorna_memoria(nome, {
                                            "attivo": False, 
                                            "errore_ripristino": True, 
                                            "tentativi_ripristino": 0
                                        }, log_wip="🛑 Spegnimento emergenza: falliti 4 tentativi di ripristino ordine. Motore Sospeso.")
                                    else:
                                        aggiorna_memoria(nome, {"tentativi_ripristino": tentativi})
                                time.sleep(3.0)
                                continue

                        micro_dir_attesa = "SELL" if dir_core == "LONG" else "BUY"
                        pos_micro_giuste = [p for p in posizioni if float(p['position']['size']) == s_ass and p['position']['direction'] == micro_dir_attesa]
                        
                        micro_gia_a_mercato = len([p for p in posizioni if float(p['position']['size']) == s_ass]) >= 2 
                        pendenti_micro = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_ass]

                        if micro_gia_a_mercato:
                            nuovo_stato = "FASE_1 + Micro"
                        else:
                            nuovo_stato = "FASE_1"
                            
                        is_micro_closing = False
                        if param.get("stato") != nuovo_stato:
                            is_micro_closing = (param.get("stato") == "FASE_1 + Micro" and nuovo_stato == "FASE_1")
                            
                            if not is_micro_closing and not entrambe_core_attive:
                                pr_str = ""
                                if nuovo_stato == "FASE_1 + Micro":
                                    pos_micro_vera = [p for p in posizioni if float(p['position']['size']) == s_ass and p['position'].get('limitLevel') is not None]
                                    dir_micro_str = "SHORT" if dir_core == "LONG" else "LONG"
                                    if pos_micro_vera:
                                        pr_str = f" a {formatta_numero(pos_micro_vera[0]['position']['level'], dec)}"
                                    msg_log = f"⚡ [MICRO {dir_micro_str}] innescata a mercato{pr_str}"
                                    invia_notifica(f"🔬 MICRO: {nome}", f"[{nome}] Micro [{dir_micro_str}]{pr_str}", "microscope")
                                    suona_drumroll()
                                else:
                                    msg_log = f"🔄 Ritorno in {nuovo_stato}"
                                        
                                aggiorna_memoria(nome, {"stato": nuovo_stato}, log_wip=msg_log)
                            else:
                                aggiorna_memoria(nome, {"stato": nuovo_stato})
                            
                        if entrambe_core_attive:
                            pos_ass = [p for p in pos_micro_giuste if p['position'].get('limitLevel') is None]
                            m_attiva = pos_ass[0] if pos_ass else (pos_micro_giuste[0] if pos_micro_giuste else None)
                            pnl_str = ""
                            
                            if m_attiva:
                                prezzo_att_tmp = round((bid+ask)/2, dec) if bid and ask else param.get("prezzo_base", 0)
                                pnl = calcola_pnl_chiusura([m_attiva], prezzo_att_tmp, nome, prezzi_live)
                                pnl_str = formatta_pnl(pnl)
                                registra_operazione(nome, "Chiusura Assicurazione (Pre-Ticket)", pnl)
                                chiudi_parziale(nome, m_attiva['position']['dealId'], epic, "BUY" if m_attiva['position']['direction'] == "SELL" else "SELL", m_attiva['position']['size'], valuta, h, etichetta="[ASSICURAZIONE]")
                                time.sleep(3.0) 
                            
                            print_log(nome, "➡️ Inserisco Ordine [TICKET1]...")
                            pulisci_mercato(epic, h, nome, solo_pendenti=True)
                            time.sleep(3.0) 
                            
                            ticket1_dir = "BUY" if dir_core == "LONG" else "SELL"
                            
                            if dir_core == "LONG":
                                ticket1_base = float(core_short[0]['position']['level'])
                            else:
                                ticket1_base = float(core_long[0]['position']['level'])
                            
                            opp_val = round(param.get("opp") * mult, dec)
                            lim_lvl = round(ticket1_base + opp_val, dec) if ticket1_dir == "BUY" else round(ticket1_base - opp_val, dec)
                            stop_lvl = round(ticket1_base - opp_val, dec) if ticket1_dir == "BUY" else round(ticket1_base + opp_val, dec)
                            
                            successo_ticket1, real_t1_lvl, new_deal_id = invia_ordine_mercato(nome, epic, valuta, ticket1_dir, s_ass, h, dec, limit_lvl=lim_lvl, stop_lvl=stop_lvl, etichetta="[TICKET1]")
                            time.sleep(3.0) 
                            
                            real_ticket1_lvl = real_t1_lvl if real_t1_lvl is not None else ticket1_base
                            
                            if successo_ticket1:
                                if real_t1_lvl is None or new_deal_id is None:
                                    resp_ticket = chiamata_api_sicura('GET', f"{BASE_URL}/positions", h)
                                    if resp_ticket and resp_ticket.status_code == 200:
                                        pos_t = [p for p in resp_ticket.json().get('positions', []) if p['market']['epic'] == epic and p['position']['direction'] == ticket1_dir and float(p['position']['size']) == s_ass]
                                        if pos_t:
                                            real_ticket1_lvl = float(pos_t[0]['position']['level'])
                                            new_deal_id = pos_t[0]['position']['dealId']
                                
                                invia_notifica(f"🎫 ENTRY FASE 2: {nome}", f"[{nome}] Assicurazione chiusa{pnl_str}. Ticket1 [{to_market_dir(ticket1_dir)}] a {formatta_numero(real_ticket1_lvl, dec)}", "ticket")
                                aggiorna_memoria(nome, {
                                    "stato": "FASE_2_TICKET1", 
                                    "ticket1_dir": ticket1_dir, 
                                    "ticket1_base": ticket1_base, 
                                    "ticket1_entry": real_ticket1_lvl,
                                    "ticket1_deal_id": new_deal_id
                                }, log_wip=f"✅ [EVENTO]: ASSICURAZIONE chiusa{pnl_str}. ➡️ Entrata in Fase 2 - [TICKET1] {ticket1_dir} eseguito a {formatta_numero(real_ticket1_lvl, dec)}.")
                                continue
                            else:
                                print_log(nome, "⚠️ [TICKET1] Impossibile aprire. Riprovo al prossimo giro.")
                                continue

                        if not micro_gia_a_mercato and not pendenti_micro and is_micro_closing:
                            if not bid or not ask:
                                continue
                                
                            prezzo_attuale = round((bid + ask) / 2, dec)
                            p_base_orig = param.get("prezzo_base")
                            if prezzo_attuale is None or p_base_orig is None:
                                continue  

                            tp4 = round((param.get("tp") / 4) * mult, dec)
                            
                            lvl_ingresso_micro_long = round(p_base_orig + tp4, dec)
                            lvl_ingresso_micro_short = round(p_base_orig - tp4, dec)

                            valore_punto = c.get("valore_punto", 1)
                            pnl_micro_valuta = (param.get("tp") / 4) * s_ass * valore_punto
                            rate = get_eur_rate(valuta, prezzi_live)
                            pnl_micro_eur = pnl_micro_valuta * rate
                            pnl_str = formatta_pnl(pnl_micro_eur)

                            if dir_core == "LONG":
                                if prezzo_attuale < lvl_ingresso_micro_long: 
                                    print_log(nome, "🔄 Profitto parziale. Inserisco Ordine [MICRO]...")
                                    invia_ordine_pendente(nome, epic, valuta, "SELL", s_ass, lvl_ingresso_micro_long, "LIMIT", p_base_orig, round(p_base_orig + (2 * tp4), dec), h, dec, etichetta="[ORDINE MICRO]")
                                    time.sleep(3.0)
                                    registra_operazione(nome, "Take Profit MICRO (Fase 1)", pnl_micro_eur)
                                    invia_notifica(f"💰 MICRO PROFIT: {nome}", f"[{nome}] Micro [SHORT] a target a {formatta_numero(prezzo_attuale, dec)}.{pnl_str} Ordine Micro [SHORT] a {formatta_numero(lvl_ingresso_micro_long, dec)}", "moneybag")
                                    aggiorna_memoria(nome, {}, log_wip=f"✅ [EVENTO]: MICRO a target a {formatta_numero(prezzo_attuale, dec)}. Reinserisco Ordine MICRO (SHORT) a {formatta_numero(lvl_ingresso_micro_long, dec)}.{pnl_str}")
                                else: 
                                    print_log(nome, "🎯 Target Fase 1 raggiunto. Chiusura posizioni *** FLIP")
                                    
                                    c_pos = [p for p in posizioni if float(p['position']['size']) == s_core]
                                    pnl_c = calcola_pnl_chiusura(c_pos, prezzo_attuale, nome, prezzi_live)
                                    
                                    a_pos = [p for p in posizioni if float(p['position']['size']) == s_ass and abs(float(p['position']['level']) - p_base_orig) < (tp4/2)]
                                    pnl_a = calcola_pnl_chiusura(a_pos, prezzo_attuale, nome, prezzi_live)
                                    
                                    m_pos = [p for p in posizioni if float(p['position']['size']) == s_ass and abs(float(p['position']['level']) - p_base_orig) >= (tp4/2)]
                                    if m_pos:
                                        pnl_m = calcola_pnl_chiusura(m_pos, prezzo_attuale, nome, prezzi_live)
                                    else:
                                        pts = (lvl_ingresso_micro_long - prezzo_attuale) / mult
                                        pnl_m = pts * s_ass * c.get("valore_punto", 1) * rate
                                        
                                    pnl = pnl_c + pnl_a + pnl_m
                                    pnl_str_base = formatta_pnl(pnl)
                                    dettaglio_pnl = f"{pnl_str_base} (Core: {pnl_c:+.0f}€ | Ass: {pnl_a:+.0f}€ | Micro: {pnl_m:+.0f}€)"
                                    
                                    pulisci_mercato(epic, h, nome)
                                    time.sleep(3.0) 
                                    registra_operazione(nome, "Stop Loss MICRO / FLIP (Fase 1)", pnl)
                                    invia_notifica(f"🔄 FLIP FASE 1: {nome}", f"[{nome}] Micro [SHORT] a target a {formatta_numero(prezzo_attuale, dec)}. FLIP.{dettaglio_pnl}", "arrows_counterclockwise")
                                    segno = "+" if dir_core in ["BUY", "LONG"] else "-"
                                    aggiorna_memoria(nome, {"direzione": "SHORT", "stato": "IN_ATTESA", "ticket2_active": False}, log_wip=f"✅ [EVENTO]: Stop MICRO colpito a {formatta_numero(prezzo_attuale, dec)}. Chiusura posizioni *** FLIP.{dettaglio_pnl} \n Reinserisco Core [SHORT] [{segno}{s_core}] a {formatta_numero(prezzo_attuale, dec)}")
                            else:
                                if prezzo_attuale > lvl_ingresso_micro_short: 
                                    print_log(nome, "🔄 Profitto parziale. Inserisco Ordine [MICRO]...")
                                    invia_ordine_pendente(nome, epic, valuta, "BUY", s_ass, lvl_ingresso_micro_short, "LIMIT", p_base_orig, round(p_base_orig - (2 * tp4), dec), h, dec, etichetta="[ORDINE MICRO]")
                                    time.sleep(3.0)
                                    registra_operazione(nome, "Take Profit MICRO (Fase 1)", pnl_micro_eur)
                                    invia_notifica(f"💰 MICRO PROFIT: {nome}", f"[{nome}] Micro [LONG] a target a {formatta_numero(prezzo_attuale, dec)}.{pnl_str} Ordine Micro [LONG] a {formatta_numero(lvl_ingresso_micro_short, dec)}", "moneybag")
                                    aggiorna_memoria(nome, {}, log_wip=f"✅ [EVENTO]: MICRO a target a {formatta_numero(prezzo_attuale, dec)}. Reinserisco Ordine MICRO (LONG) a {formatta_numero(lvl_ingresso_micro_short, dec)}.{pnl_str}")
                                else: 
                                    print_log(nome, "🎯 Target Fase 1 raggiunto. Chiusura posizioni *** FLIP")
                                    
                                    c_pos = [p for p in posizioni if float(p['position']['size']) == s_core]
                                    pnl_c = calcola_pnl_chiusura(c_pos, prezzo_attuale, nome, prezzi_live)
                                    
                                    a_pos = [p for p in posizioni if float(p['position']['size']) == s_ass and abs(float(p['position']['level']) - p_base_orig) < (tp4/2)]
                                    pnl_a = calcola_pnl_chiusura(a_pos, prezzo_attuale, nome, prezzi_live)
                                    
                                    m_pos = [p for p in posizioni if float(p['position']['size']) == s_ass and abs(float(p['position']['level']) - p_base_orig) >= (tp4/2)]
                                    if m_pos:
                                        pnl_m = calcola_pnl_chiusura(m_pos, prezzo_attuale, nome, prezzi_live)
                                    else:
                                        pts = (prezzo_attuale - lvl_ingresso_micro_short) / mult
                                        pnl_m = pts * s_ass * c.get("valore_punto", 1) * rate
                                        
                                    pnl = pnl_c + pnl_a + pnl_m
                                    pnl_str_base = formatta_pnl(pnl)
                                    dettaglio_pnl = f"{pnl_str_base} (Core: {pnl_c:+.0f}€ | Ass: {pnl_a:+.0f}€ | Micro: {pnl_m:+.0f}€)"
                                    
                                    pulisci_mercato(epic, h, nome)
                                    time.sleep(3.0) 
                                    registra_operazione(nome, "Stop Loss MICRO / FLIP (Fase 1)", pnl)
                                    invia_notifica(f"🔄 FLIP FASE 1: {nome}", f"[{nome}] Micro [LONG] a target a {formatta_numero(prezzo_attuale, dec)}. FLIP.{dettaglio_pnl}", "arrows_counterclockwise")
                                    segno = "+" if dir_core in ["BUY", "LONG"] else "-"
                                    aggiorna_memoria(nome, {"direzione": "LONG", "stato": "IN_ATTESA", "ticket2_active": False}, log_wip=f"✅ [EVENTO]: Stop MICRO colpito a {formatta_numero(prezzo_attuale, dec)}. Chiusura posizioni *** FLIP.{dettaglio_pnl} \n Reinserisco Core [LONG] [{segno}{s_core}] a {formatta_numero(prezzo_attuale, dec)}")

                    elif stato == "FASE_2_STANDBY":
                        if not bid or not ask:
                            continue
                            
                        prezzo_attuale = round((bid + ask) / 2, dec)
                        
                        core_long = [p for p in posizioni if p['position']['direction'] == "BUY" and float(p['position']['size']) == s_core]
                        core_short = [p for p in posizioni if p['position']['direction'] == "SELL" and float(p['position']['size']) == s_core]
                        
                        if not core_long or not core_short:
                            print_log(nome, "⚠️ [STANDBY] Core mancanti. Ritorno in MANUALE.")
                            aggiorna_memoria(nome, {"attivo": False, "msg_manuale": "❌ Core mancanti durante l'attesa. Sospensione Motore."}, log_wip="✅ [EVENTO]: Attesa annullata. Core mancanti.")
                            continue
                            
                        lvl_long = float(core_long[0]['position']['level'])
                        lvl_short = float(core_short[0]['position']['level'])
                        
                        tp2_val = round((param.get("tp") / 2) * mult, dec)
                        sat_long_lvl = round(lvl_long + tp2_val, dec)
                        sat_short_lvl = round(lvl_short - tp2_val, dec)
                        
                        dist_long = (sat_long_lvl - prezzo_attuale) / mult
                        dist_short = (prezzo_attuale - sat_short_lvl) / mult
                        limite_sicurezza = max(ig_min_dist, min_param_impostato) * 2.0
                        
                        fuori_canale = prezzo_attuale >= sat_long_lvl or prezzo_attuale <= sat_short_lvl
                        troppo_vicino = dist_long <= limite_sicurezza or dist_short <= limite_sicurezza
                        
                        if not fuori_canale and not troppo_vicino:
                            s_mezzo = max(1.0, s_core / 2)
                            print_log(nome, "🎯 Condizioni di rientro raggiunte! Piazzamento SAT1 OCO...")
                            
                            ris_l = invia_ordine_pendente(nome, epic, valuta, "BUY", s_mezzo, sat_long_lvl, "STOP", round(sat_long_lvl + tp2_val, dec), round(sat_long_lvl - tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO BUY]")
                            time.sleep(3.0)
                            ris_s = invia_ordine_pendente(nome, epic, valuta, "SELL", s_mezzo, sat_short_lvl, "STOP", round(sat_short_lvl - tp2_val, dec), round(sat_short_lvl + tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO SELL]")
                            time.sleep(3.0)
                            
                            if ris_l and ris_s:
                                invia_notifica(f"🛰️ SAT1 OCO: {nome}", f"[{nome}] Rientro canale a {formatta_numero(prezzo_attuale, dec)}. SAT1 OCO piazzati.", "satellite")
                                aggiorna_memoria(nome, {
                                    "stato": "FASE_2_SATELLITI",
                                    "prezzo_base": prezzo_attuale, 
                                    "tentativi_sat": 1
                                }, log_wip=f"✅ [EVENTO]: Rientro nel canale riuscito a {formatta_numero(prezzo_attuale, dec)}. SAT1 OCO piazzati.")
                            else:
                                pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                aggiorna_memoria(nome, {"attivo": False, "msg_manuale": "❌ IG ha rifiutato i SAT1 OCO dopo l'attesa. Il Motore passa in Manuale."}, log_wip="✅ [EVENTO]: IG ha rifiutato i SAT1 OCO. Sospensione Motore.")

                    elif stato == "FASE_2_TICKET1":
                        s_mezzo = max(1.0, s_core / 2)
                        dir_core = param.get("direzione")
                        core_ig_dir = "BUY" if dir_core == "LONG" else "SELL"
                        ticket1_dir = param.get("ticket1_dir")
                        ticket1_base = param.get("ticket1_base")
                        opp_val = round(param.get("opp") * mult, dec)
                        
                        primary_core = [p for p in posizioni if float(p['position']['size']) == s_core and p['position']['direction'] == core_ig_dir]
                        if not primary_core:
                            continue 

                        ticket1_attivo = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == ticket1_dir]
                        
                        if ticket1_attivo:
                            continue
                        
                        if not bid or not ask:
                            continue
                                
                        prezzo_attuale = round((bid + ask) / 2, dec)
                        
                        vittoria = False
                        if ticket1_dir == "BUY" and prezzo_attuale > ticket1_base:
                            vittoria = True
                        elif ticket1_dir == "SELL" and prezzo_attuale < ticket1_base:
                            vittoria = True
                        
                        if vittoria:
                            print_log(nome, "➡️ Profitto incassato. FLIP del [TICKET1] a mercato...")
                            
                            nuova_ticket_dir = "SELL" if ticket1_dir == "BUY" else "BUY"
                            nuova_ticket_base = round(ticket1_base + opp_val, dec) if ticket1_dir == "BUY" else round(ticket1_base - opp_val, dec)
                            
                            lim_lvl = round(nuova_ticket_base - opp_val, dec) if nuova_ticket_dir == "SELL" else round(nuova_ticket_base + opp_val, dec)
                            stop_lvl = round(nuova_ticket_base + opp_val, dec) if nuova_ticket_dir == "SELL" else round(nuova_ticket_base - opp_val, dec)
                            
                            succ_tick, real_t1_lvl, new_deal_id = invia_ordine_mercato(nome, epic, valuta, nuova_ticket_dir, s_mezzo, h, dec, limit_lvl=lim_lvl, stop_lvl=stop_lvl, etichetta="[TICKET1]")
                            time.sleep(3.0)
                            
                            if succ_tick:
                                valore_punto = c.get("valore_punto", 1)
                                pnl_valuta = param.get("opp") * s_mezzo * valore_punto
                                rate = get_eur_rate(valuta, prezzi_live)
                                pnl_eur = pnl_valuta * rate
                                
                                registra_operazione(nome, "Ping-Pong TICKET1 (Fase 2)", pnl_eur)
                                
                                real_ticket1_lvl = real_t1_lvl if real_t1_lvl is not None else nuova_ticket_base
                                if real_t1_lvl is None or new_deal_id is None:
                                    resp_ticket = chiamata_api_sicura('GET', f"{BASE_URL}/positions", h)
                                    if resp_ticket and resp_ticket.status_code == 200:
                                        pos_t = [p for p in resp_ticket.json().get('positions', []) if p['market']['epic'] == epic and p['position']['direction'] == nuova_ticket_dir and float(p['position']['size']) == s_mezzo]
                                        if pos_t:
                                            real_ticket1_lvl = float(pos_t[0]['position']['level'])
                                            new_deal_id = pos_t[0]['position']['dealId']
                                
                                invia_notifica(f"🎫 PING-PONG TICKET1: {nome}", f"[{nome}] Ticket1 a target a {formatta_numero(prezzo_attuale, dec)}! Rigirato [{to_market_dir(nuova_ticket_dir)}] a {formatta_numero(real_ticket1_lvl, dec)}.{formatta_pnl(pnl_eur)}", "ticket")
                                        
                                aggiorna_memoria(nome, {
                                    "stato": "FASE_2_TICKET1",
                                    "ticket1_dir": nuova_ticket_dir,
                                    "ticket1_base": nuova_ticket_base,
                                    "ticket1_entry": real_ticket1_lvl,
                                    "ticket1_deal_id": new_deal_id
                                }, log_wip=f"✅ [EVENTO]: TICKET1 a target a {formatta_numero(prezzo_attuale, dec)}! Ping-Pong: Rigirato in {nuova_ticket_dir} a {formatta_numero(real_ticket1_lvl, dec)}.{formatta_pnl(pnl_eur)}")
                            else:
                                print_log(nome, "⚠️ IG ha rifiutato il FLIP del Ticket.")
                        else:
                            time.sleep(3.0)
                            resp_check = chiamata_api_sicura('GET', f"{BASE_URL}/positions", h)
                            pos_check = [p for p in resp_check.json().get('positions', []) if p['market']['epic'] == epic]
                            ticket1_check = [p for p in pos_check if float(p['position']['size']) == s_mezzo and p['position']['direction'] == ticket1_dir]
                            
                            if not ticket1_check:
                                att_t1 = len([p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == ticket1_dir])
                                falso_allarme_t1 = verifica_falso_allarme_ig(nome, epic, h, s_mezzo, ticket1_dir, "[TICKET1 (LOSS?)]", pos_attese=att_t1)
                                if falso_allarme_t1:
                                    continue
                                    
                                valore_punto = c.get("valore_punto", 1)
                                pnl_ticket_loss_valuta = - (param.get("opp") * s_mezzo * valore_punto)
                                rate = get_eur_rate(valuta, prezzi_live)
                                pnl_ticket_loss_eur = pnl_ticket_loss_valuta * rate
                                pnl_str = formatta_pnl(pnl_ticket_loss_eur)
                                
                                registra_operazione(nome, "Stop Loss TICKET1 (Fase 2)", pnl_ticket_loss_eur)
                                
                                core_long = [p for p in posizioni if p['position']['direction'] == "BUY" and float(p['position']['size']) == s_core]
                                core_short = [p for p in posizioni if p['position']['direction'] == "SELL" and float(p['position']['size']) == s_core]
                                if core_long and core_short:
                                    lvl_long = float(core_long[0]['position']['level'])
                                    lvl_short = float(core_short[0]['position']['level'])
                                    tp2_val = round((param.get("tp") / 2) * mult, dec)
                                    sat_long = round(lvl_long + tp2_val, dec)
                                    sat_short = round(lvl_short - tp2_val, dec)
                                    oco_str = f" a {formatta_numero(sat_short, dec)} e {formatta_numero(sat_long, dec)}"
                                else:
                                    oco_str = ""
                                    
                                oco_str_short = f" (SHORT: {formatta_numero(sat_short, dec)} | LONG: {formatta_numero(sat_long, dec)})" if oco_str else ""
                                if param.get("opp") == param.get("tp") / 4:
                                    print_log(nome, "➡️ Condizione OPP == TP/4 verificata. Apertura [TICKET2] a mercato...")
                                    ticket2_dir = ticket1_dir
                                    lim_lvl_t2 = round(prezzo_attuale + (param.get("tp") / 4) * mult, dec) if ticket2_dir == "BUY" else round(prezzo_attuale - (param.get("tp") / 4) * mult, dec)
                                    succ_t2, real_t2_lvl, deal_id_t2 = invia_ordine_mercato(nome, epic, valuta, ticket2_dir, s_mezzo, h, dec, limit_lvl=lim_lvl_t2, stop_lvl=None, etichetta="[TICKET2]")
                                    if succ_t2:
                                        real_t2_entry = real_t2_lvl if real_t2_lvl is not None else prezzo_attuale
                                        extra_mem = {
                                            "ticket2_active": True,
                                            "ticket2_entry": real_t2_entry,
                                            "ticket2_dir": ticket2_dir,
                                            "ticket2_deal_id": deal_id_t2
                                        }
                                        invia_notifica(f"🛰️ STOP TICKET1: {nome}", f"[{nome}] Stop Ticket1 a {formatta_numero(prezzo_attuale, dec)}.{pnl_str} SAT1 OCO{oco_str_short} + Ticket2 [{to_market_dir(ticket2_dir)}] a {formatta_numero(real_t2_entry, dec)}", "satellite")
                                        aggiorna_memoria(nome, {**extra_mem, "stato": "FASE_2_SATELLITI", "tentativi_sat": 0}, log_wip=f"✅ [EVENTO]: Stop TICKET1 colpito a {formatta_numero(prezzo_attuale, dec)}.{pnl_str} PIAZZATI: SAT1 OCO{oco_str_short} + Ticket2 [{to_market_dir(ticket2_dir)}] a {formatta_numero(real_t2_entry, dec)}")
                                    else:
                                        invia_notifica(f"🛰️ STOP TICKET1: {nome}", f"[{nome}] Stop Ticket1 a {formatta_numero(prezzo_attuale, dec)}.{pnl_str} SAT1 OCO{oco_str_short}", "satellite")
                                        aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITI", "tentativi_sat": 0}, log_wip=f"✅ [EVENTO]: Stop TICKET1 colpito a {formatta_numero(prezzo_attuale, dec)}. PIAZZATI: SAT1 OCO{oco_str_short}.{pnl_str}")
                                else:
                                    invia_notifica(f"🛰️ STOP TICKET1: {nome}", f"[{nome}] Stop Ticket1 a {formatta_numero(prezzo_attuale, dec)}.{pnl_str} SAT1 OCO{oco_str_short}", "satellite")
                                    aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITI", "tentativi_sat": 0}, log_wip=f"✅ [EVENTO]: Stop TICKET1 colpito a {formatta_numero(prezzo_attuale, dec)}. PIAZZATI: SAT1 OCO{oco_str_short}.{pnl_str}")

                    elif stato == "FASE_2_SATELLITI":
                        if not bid or not ask:
                            continue
                        prezzo_attuale = round((bid + ask) / 2, dec)
                        s_mezzo = max(1.0, s_core / 2)
                        dir_core = param.get("direzione")
                        prezzo_base = param.get("prezzo_base") 
                        opp_val = round(param.get("opp") * mult, dec)
                        tp2_val = round((param.get("tp") / 2) * mult, dec)
                        tp4_val = round((param.get("tp") / 4) * mult, dec)
                        
                        core_ids = [p['position']['dealId'] for p in posizioni if float(p['position']['size']) == s_core]
                        is_ticket2 = lambda p: param.get("ticket2_active") and p['position']['direction'] == param.get("ticket2_dir") and p['position'].get('limitLevel') is not None
                        
                        sat1_attivi = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['dealId'] not in core_ids and not is_ticket2(p)]
                        
                        if param.get("ticket2_active"):
                            ticket2_attivi = [p for p in posizioni if float(p['position']['size']) == s_mezzo and is_ticket2(p)]
                            ticket2_pendenti = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_mezzo and o['workingOrderData']['direction'] == param.get("ticket2_dir") and o['workingOrderData'].get('orderType') == 'LIMIT']
                            
                            if not ticket2_attivi and not ticket2_pendenti:
                                t2_dir = param.get("ticket2_dir")
                                falso_allarme_t2 = verifica_falso_allarme_ig(nome, epic, h, s_mezzo, t2_dir, "[ORDINE TICKET2]", no_stop=True)
                                
                                if not falso_allarme_t2:
                                    t2_entry = param.get("ticket2_entry")
                                    
                                    valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
                                    rate = get_eur_rate(valuta, prezzi_live)
                                    
                                    # Capiamo se ha preso TP o SL guardando il prezzo attuale
                                    hit_tp = False
                                    if (t2_dir == "BUY" and prezzo_attuale > t2_entry) or (t2_dir == "SELL" and prezzo_attuale < t2_entry):
                                        hit_tp = True
                                        
                                    if hit_tp:
                                        print_log(nome, f"🎯 [TICKET2] chiuso in profitto. Reinserisco ordine pendente a {formatta_numero(t2_entry, dec)}...")
                                        lim_lvl_t2 = round(t2_entry + (param.get("tp") / 4) * mult, dec) if t2_dir == "BUY" else round(t2_entry - (param.get("tp") / 4) * mult, dec)
                                        invia_ordine_pendente(nome, epic, valuta, t2_dir, s_mezzo, t2_entry, "LIMIT", lim_lvl_t2, None, h, dec, etichetta="[ORDINE TICKET2]")
                                        
                                        pnl_t2_win_eur = (param.get("tp") / 4) * s_mezzo * valore_punto * rate
                                        pnl_str = formatta_pnl(pnl_t2_win_eur)
                                        registra_operazione(nome, "Take Profit TICKET2", pnl_t2_win_eur)
                                        
                                        invia_notifica(f"🎫 TICKET2 PROFIT: {nome}", f"[{nome}] Ticket2 a target a {formatta_numero(lim_lvl_t2, dec)}.{pnl_str} Ordine [{to_market_dir(t2_dir)}] a {formatta_numero(t2_entry, dec)}", "ticket")
                                        aggiorna_memoria(nome, {}, log_wip=f"✅ [EVENTO]: TP colpito su TICKET2 a {formatta_numero(lim_lvl_t2, dec)}.{pnl_str} Re-inserisco Ordine ({t2_dir}) a {formatta_numero(t2_entry, dec)}")
                                        time.sleep(2.0)
                                    else:
                                        print_log(nome, f"📉 [TICKET2] chiuso in STOP LOSS.")
                                        pnl_t2_loss_eur = -(param.get("tp") / 4) * s_mezzo * valore_punto * rate
                                        pnl_str = formatta_pnl(pnl_t2_loss_eur)
                                        registra_operazione(nome, "Stop Loss TICKET2", pnl_t2_loss_eur)
                                        invia_notifica(f"📉 TICKET2 SL: {nome}", f"[{nome}] Ticket2 Stop Loss a {formatta_numero(prezzo_attuale, dec)}.{pnl_str}", "chart_with_downwards_trend")
                                        aggiorna_memoria(nome, {"ticket2_active": False}, log_wip=f"✅ [EVENTO]: SL colpito su TICKET2.{pnl_str}")
                                        time.sleep(2.0)
                        
                        if sat1_attivi:
                            sat_pos = sat1_attivi[0]
                            sat_dir = sat_pos['position']['direction']
                            sat_price = float(sat_pos['position']['level'])
                            
                            if param.get("ticket2_active"):
                                print_log(nome, f"🚨 OCO entrato a mercato. Pulizia [TICKET2] in corso...")
                                ticket2_attivi = [p for p in posizioni if float(p['position']['size']) == s_mezzo and is_ticket2(p)]
                                if ticket2_attivi:
                                    t2_deal_id = ticket2_attivi[0]['position']['dealId']
                                    t2_entry = float(ticket2_attivi[0]['position']['level'])
                                    dir_chiusura_t2 = "SELL" if ticket2_attivi[0]['position']['direction'] == "BUY" else "BUY"
                                    
                                    valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
                                    rate = get_eur_rate(valuta, prezzi_live)
                                    pts = (sat_price - t2_entry)/mult if ticket2_attivi[0]['position']['direction'] == 'BUY' else (t2_entry - sat_price)/mult
                                    pnl_t2_loss_eur = pts * s_mezzo * valore_punto * rate
                                    pnl_str = formatta_pnl(pnl_t2_loss_eur)
                                    
                                    print_log(nome, f"📉 Chiusura a mercato del [TICKET2] (Loss)...")
                                    chiudi_parziale(nome, t2_deal_id, epic, dir_chiusura_t2, s_mezzo, valuta, h, etichetta="[TICKET2 CLOSURE]")
                                    registra_operazione(nome, "Stop Loss TICKET2", pnl_t2_loss_eur)
                                    aggiorna_memoria(nome, {}, log_wip=f"✅ [EVENTO]: SL colpito su TICKET2 a {formatta_numero(sat_price, dec)}.{pnl_str}")
                                    time.sleep(1.0)
                            
                            pulisci_mercato(epic, h, nome, solo_pendenti=True)
                            
                            sat2_dir = "SELL" if sat_dir == "BUY" else "BUY"
                            s_quarto = max(0.1, s_core / 4)
                            
                            sat2_gia_presente = [p for p in posizioni if float(p['position']['size']) == s_quarto and p['position']['direction'] == sat2_dir]
                            if not sat2_gia_presente:
                                print_log(nome, f"➡️ Inserisco [SAT2] a mercato...")
                                succ_sat2, lvl_sat2, deal_sat2 = invia_ordine_mercato(nome, epic, valuta, sat2_dir, s_quarto, h, dec, etichetta=f"[SAT2]")
                                time.sleep(3.0) 
                            else:
                                print_log(nome, f"✅ [SAT2] già presente a mercato. Salto inserimento.")
                                succ_sat2 = True
                            
                            if succ_sat2:
                                resp_ticket = chiamata_api_sicura('GET', f"{BASE_URL}/positions", h)
                                if resp_ticket and resp_ticket.status_code == 200:
                                    pos_t = [p for p in resp_ticket.json().get('positions', []) if p['market']['epic'] == epic and p['position']['direction'] == sat2_dir and float(p['position']['size']) == s_quarto]
                                    if not pos_t:
                                        print_log(nome, f"⚠️ Posizione [SAT2] non trovata su IG. Motore Sospeso.")
                                        pulisci_mercato(epic, h, nome)
                                        invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] [SAT2] fantasma evitato (Rifiuto asincrono). Passaggio forzato a MANUALE.", "rotating_light")
                                        aggiorna_memoria(nome, {
                                            "attivo": False, 
                                            "msg_manuale": f"❌ IG ha confermato [SAT2] ma non risulta a mercato. Rifiuto asincrono. Motore Sospeso."
                                        }, log_wip=f"✅ [EVENTO]: Spegnimento emergenza: [SAT2] fantasma evitato. Motore Sospeso.")
                                        continue
                            else:
                                print_log(nome, f"⚠️ Impossibile inserire [SAT2]. Motore Sospeso.")
                                pulisci_mercato(epic, h, nome)
                                invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Fallimento inserimento [SAT2] (dopo 4 tentativi). Passaggio forzato a MANUALE.", "rotating_light")
                                aggiorna_memoria(nome, {"attivo": False, "msg_manuale": f"❌ Fallita immissione [SAT2] a mercato dopo 4 tentativi."}, log_wip=f"✅ [EVENTO]: Emergenza: fallimento [SAT2]. Macchina Sospesa.")
                                continue
                            
                            lvl_og_sell = round(sat_price + tp4_val, dec)
                            lvl_ol_sell = round(sat_price - tp4_val, dec)
                            lvl_og_buy = round(sat_price - tp4_val, dec)
                            lvl_ol_buy = round(sat_price + tp4_val, dec)
                            
                            if sat2_dir == "SELL":
                                print_log(nome, f"➡️ Inserisco Ordine [OVERGAIN] a {lvl_og_sell} e [OVERLOSS] a {lvl_ol_sell}...")
                                succ_og = invia_ordine_pendente(nome, epic, valuta, "SELL", s_mezzo, lvl_og_sell, "LIMIT", round(sat_price, dec), None, h, dec, etichetta="[ORDINE OVERGAIN]")
                                time.sleep(3.0) 
                                succ_ol = invia_ordine_pendente(nome, epic, valuta, "SELL", s_quarto, lvl_ol_sell, "STOP", None, None, h, dec, etichetta="[ORDINE OVERLOSS]")
                                time.sleep(3.0)
                            else:
                                print_log(nome, f"➡️ Inserisco Ordine [OVERGAIN] a {lvl_og_buy} e [OVERLOSS] a {lvl_ol_buy}...")
                                succ_og = invia_ordine_pendente(nome, epic, valuta, "BUY", s_mezzo, lvl_og_buy, "LIMIT", round(sat_price, dec), None, h, dec, etichetta="[ORDINE OVERGAIN]")
                                time.sleep(3.0) 
                                succ_ol = invia_ordine_pendente(nome, epic, valuta, "BUY", s_quarto, lvl_ol_buy, "STOP", None, None, h, dec, etichetta="[ORDINE OVERLOSS]")
                                time.sleep(3.0)
                                
                            if not succ_og or not succ_ol:
                                print_log(nome, f"⚠️ Impossibile inserire [OVERGAIN]/[OVERLOSS]. Motore Sospeso.")
                                pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Fallimento immissione ordini FASE 2 (OG/OL) (dopo 4 tentativi). Passaggio forzato a MANUALE.", "rotating_light")
                                aggiorna_memoria(nome, {"attivo": False, "msg_manuale": f"❌ Fallita immissione ordini FASE 2 (OG/OL) a mercato dopo 4 tentativi."}, log_wip=f"✅ [EVENTO]: Emergenza: fallimento ordini FASE 2 (OG/OL). Macchina Sospesa.")
                                continue
                                
                            lvl_og = round(sat_price + tp4_val, dec) if sat2_dir == "SELL" else round(sat_price - tp4_val, dec)
                            lvl_ol = round(sat_price - tp4_val, dec) if sat2_dir == "SELL" else round(sat_price + tp4_val, dec)
                            
                            msg_dettagliato = f"SAT1 [{to_market_dir(sat_dir)}] a {formatta_numero(sat_price, dec)}. SAT2 [{to_market_dir(sat2_dir)}] a mercato. Ordini: OG {formatta_numero(lvl_og, dec)}, OL {formatta_numero(lvl_ol, dec)}"
                            
                            invia_notifica(f"🎯 SAT1 INNESCATO: {nome}", f"[{nome}] {msg_dettagliato}", "dart")
                            suona_drumroll()
                            
                            aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITE_(OG-OL)", "sat_dir": sat_dir, "sat_price": sat_price, "tentativi_sat": 0, "ticket2_active": False}, 
                                log_wip=msg_dettagliato)
                            
                        else:
                            pend_sat_l = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_mezzo and o['workingOrderData']['direction'] == 'BUY']
                            pend_sat_s = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_mezzo and o['workingOrderData']['direction'] == 'SELL']

                            if not pend_sat_l or not pend_sat_s:
                                falso_allarme_l = False
                                falso_allarme_s = False
                                
                                if not pend_sat_l:
                                    att_l = len([p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == 'BUY'])
                                    falso_allarme_l = verifica_falso_allarme_ig(nome, epic, h, s_mezzo, 'BUY', "[ORDINE SAT1 OCO BUY]", pos_attese=att_l)
                                if not pend_sat_s:
                                    att_s = len([p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == 'SELL'])
                                    falso_allarme_s = verifica_falso_allarme_ig(nome, epic, h, s_mezzo, 'SELL', "[ORDINE SAT1 OCO SELL]", pos_attese=att_s)
                                    
                                if falso_allarme_l or falso_allarme_s:
                                    continue
                                    
                                if prezzo_base is None:
                                    if bid and ask:
                                        prezzo_base = round(float(ask if dir_core == "LONG" else bid), dec)
                                        aggiorna_memoria(nome, {"prezzo_base": prezzo_base})
                                    else:
                                        time.sleep(10)
                                        continue

                                if dir_core == "LONG":
                                    prezzo_sat_long = round(prezzo_base + tp2_val, dec)
                                    prezzo_sat_short = round((prezzo_base - opp_val) - tp2_val, dec)
                                else:
                                    prezzo_sat_long = round((prezzo_base + opp_val) + tp2_val, dec)
                                    prezzo_sat_short = round(prezzo_base - tp2_val, dec)
                                    
                                fallito_rimpiazzo = False
                                if not pend_sat_l:
                                    succ_l = invia_ordine_pendente(nome, epic, valuta, "BUY", s_mezzo, prezzo_sat_long, "STOP", round(prezzo_sat_long + tp2_val, dec), round(prezzo_sat_long - tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO BUY]")
                                    if not succ_l: fallito_rimpiazzo = True
                                    else: time.sleep(3.0) 
                                
                                if not pend_sat_s and not fallito_rimpiazzo:
                                    succ_s = invia_ordine_pendente(nome, epic, valuta, "SELL", s_mezzo, prezzo_sat_short, "STOP", round(prezzo_sat_short - tp2_val, dec), round(prezzo_sat_short + tp2_val, dec), h, dec, etichetta="[ORDINE SAT1 OCO SELL]")
                                    if not succ_s: fallito_rimpiazzo = True
                                    else: time.sleep(3.0) 
                                    
                                if fallito_rimpiazzo:
                                    print_log(nome, "⚠️ Impossibile ripristinare ordini OCO (possibile gap). Passo in FASE_2_STANDBY.")
                                    pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                    aggiorna_memoria(nome, {"stato": "FASE_2_STANDBY"}, log_wip="✅ [EVENTO]: Rimpiazzo OCO fallito (gap). Passaggio in STANDBY.")
                                    continue 

                    elif stato.startswith("FASE_2_SATELLITE_"):
                        s_mezzo = max(1.0, s_core / 2)
                        s_quarto = max(0.1, s_core / 4)
                        sat_dir = param.get("sat_dir")
                        sat_price = param.get("sat_price")
                        sat2_dir = "SELL" if sat_dir == "BUY" else "BUY"
                        
                        satellite_attivo = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == sat_dir]
                        pos_sat2_mezzo = [p for p in posizioni if float(p['position']['size']) == s_mezzo and p['position']['direction'] == sat2_dir]
                        pos_sat2_quarto = [p for p in posizioni if float(p['position']['size']) == s_quarto and p['position']['direction'] == sat2_dir]

                        over_gain_attivo = len(pos_sat2_mezzo) > 0
                        over_loss_attivo = len(pos_sat2_quarto) > 1

                        if over_gain_attivo:
                            nuovo_stato = "FASE_2_SATELLITE_OG"
                        elif over_loss_attivo:
                            nuovo_stato = "FASE_2_SATELLITE_OL"
                        else:
                            nuovo_stato = "FASE_2_SATELLITE_(OG-OL)"
                            
                        if param.get("stato") != nuovo_stato:
                            is_satellite_closing = not satellite_attivo
                            if not is_satellite_closing:
                                pr_str = ""
                                if nuovo_stato == "FASE_2_SATELLITE_OG" and pos_sat2_mezzo:
                                    pr_str = f" a {formatta_numero(float(pos_sat2_mezzo[-1]['position']['level']), dec)}"
                                elif nuovo_stato == "FASE_2_SATELLITE_OL" and pos_sat2_quarto:
                                    pr_str = f" a {formatta_numero(float(pos_sat2_quarto[-1]['position']['level']), dec)}"
                                else:
                                    if bid and ask:
                                        pr_str = f" a {formatta_numero((bid+ask)/2, dec)}"
                                
                                if nuovo_stato == "FASE_2_SATELLITE_OG":
                                    msg_log = f"⚡ [OVERGAIN] innescato a mercato{pr_str}"
                                    invia_notifica(f"💸 OVERGAIN: {nome}", f"[{nome}] OverGain [{to_market_dir(sat2_dir)}]{pr_str}", "money_with_wings")
                                elif nuovo_stato == "FASE_2_SATELLITE_OL":
                                    msg_log = f"⚡ [OVERLOSS] innescato a mercato{pr_str}"
                                    invia_notifica(f"🛡️ OVERLOSS: {nome}", f"[{nome}] OverLoss [{to_market_dir(sat2_dir)}]{pr_str}", "shield")
                                else:
                                    msg_log = f"🔄 Passaggio a: {nuovo_stato}{pr_str}"
                                    vecchio_stato = param.get("stato")
                                    valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
                                    rate = get_eur_rate(valuta, prezzi_live)
                                    
                                    if vecchio_stato == "FASE_2_SATELLITE_OG":
                                        pnl = (param.get("tp") / 4) * s_mezzo * valore_punto * rate
                                        registra_operazione(nome, "Take Profit OVERGAIN", pnl)
                                        tp4_v = round((param.get("tp") / 4) * mult, dec)
                                        l_og = round(sat_price + tp4_v, dec) if sat2_dir == "SELL" else round(sat_price - tp4_v, dec)
                                        l_ol = round(sat_price - tp4_v, dec) if sat2_dir == "SELL" else round(sat_price + tp4_v, dec)
                                        msg_log = f"✅ [EVENTO]: TP colpito su OVERGAIN.{formatta_pnl(pnl)} Reinserisco OG e OL ({sat2_dir}) a {formatta_numero(l_og, dec)} e {formatta_numero(l_ol, dec)}"
                                    elif vecchio_stato == "FASE_2_SATELLITE_OL":
                                        pnl = -(param.get("tp") / 4) * s_quarto * valore_punto * rate
                                        registra_operazione(nome, "Stop Loss OVERLOSS", pnl)
                                        tp4_v = round((param.get("tp") / 4) * mult, dec)
                                        l_og = round(sat_price + tp4_v, dec) if sat2_dir == "SELL" else round(sat_price - tp4_v, dec)
                                        l_ol = round(sat_price - tp4_v, dec) if sat2_dir == "SELL" else round(sat_price + tp4_v, dec)
                                        msg_log = f"✅ [EVENTO]: SL colpito su OVERLOSS.{formatta_pnl(pnl)} Reinserisco OG e OL ({sat2_dir}) a {formatta_numero(l_og, dec)} e {formatta_numero(l_ol, dec)}"
                                    
                                aggiorna_memoria(nome, {"stato": nuovo_stato}, log_wip=msg_log)
                            else:
                                aggiorna_memoria(nome, {"stato": nuovo_stato})

                        if not satellite_attivo:
                            if not bid or not ask:
                                continue
                                
                            prezzo_attuale = round((bid+ask)/2, dec)
                            
                            if (sat_dir == "BUY" and prezzo_attuale > sat_price) or (sat_dir == "SELL" and prezzo_attuale < sat_price):
                                pos_ibride = [p for p in posizioni if float(p['position']['size']) != s_core]
                                pnl_rimaste = calcola_pnl_chiusura(pos_ibride, prezzo_attuale, nome, prezzi_live)
                                
                                # Calcolo PNL teorico del SAT1 che è stato chiuso in automatico (Take Profit)
                                valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
                                rate = get_eur_rate(valuta, prezzi_live)
                                pnl_sat1_teorico = (param.get("tp") / 2) * s_mezzo * valore_punto * rate
                                pnl_sottotrading = pnl_rimaste + pnl_sat1_teorico
                                
                                dir_vincente = sat_dir
                                dir_tossica = "SELL" if sat_dir == "BUY" else "BUY"
                                core_vinc = [p for p in posizioni if p['position']['direction'] == dir_vincente and float(p['position']['size']) == s_core]
                                core_toss = [p for p in posizioni if p['position']['direction'] == dir_tossica and float(p['position']['size']) == s_core]
                                
                                pnl_c_vincente = calcola_pnl_chiusura(core_vinc, prezzo_attuale, nome, prezzi_live) if core_vinc else 0.0
                                pnl_c_tossica_full = calcola_pnl_chiusura(core_toss, prezzo_attuale, nome, prezzi_live) if core_toss else 0.0
                                pnl_c_tossica = pnl_c_tossica_full / 2.0
                                
                                pnl_tot_f3 = pnl_sottotrading + pnl_c_vincente + pnl_c_tossica
                                
                                v_str = f"+{int(round(pnl_c_vincente))}" if pnl_c_vincente > 0 else str(int(round(pnl_c_vincente)))
                                t_str = f"{int(round(pnl_c_tossica))}"
                                sub_str = f"+{int(round(pnl_sottotrading))}" if pnl_sottotrading > 0 else str(int(round(pnl_sottotrading)))
                                dett_macro = f" (Good: {v_str}€ | 1/2 Bad: {t_str}€ | Sottotrading: {sub_str}€)"
                                
                                registra_operazione(nome, f"TP Core [{to_market_dir(sat_dir)}] (Avvio Fase 3)", pnl_tot_f3)
                                pulisci_mercato(epic, h, nome, mantieni_core_size=s_core)
                                aggiorna_memoria(nome, {"stato": "FASE_3_INIT", "fase3_dir": sat_dir, "fase3_base": sat_price, "temp_fase3_log": f"TP Core [{to_market_dir(sat_dir)}] a {formatta_numero(prezzo_attuale, dec)}. Avvio FASE 3. Taglio 50%.{formatta_pnl(pnl_tot_f3)}{dett_macro}"})
                            else:
                                pos_ibride = [p for p in posizioni if float(p['position']['size']) != s_core]
                                pnl_rimaste = calcola_pnl_chiusura(pos_ibride, prezzo_attuale, nome, prezzi_live)
                                
                                # Calcolo PNL teorico del SAT1 che è stato chiuso in automatico (Stop Loss)
                                valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
                                rate = get_eur_rate(valuta, prezzi_live)
                                pnl_sat1_teorico = -(param.get("tp") / 2) * s_mezzo * valore_punto * rate
                                
                                pnl_totale = pnl_rimaste + pnl_sat1_teorico
                                
                                dett_pnl = []
                                p_s2 = sum(calcola_pnl_chiusura([p], prezzo_attuale, nome, prezzi_live) for p in pos_ibride if float(p['position']['size']) == s_mezzo and p['position']['direction'] == sat2_dir and abs(float(p['position']['level']) - sat_price) < 0.1)
                                p_og = sum(calcola_pnl_chiusura([p], prezzo_attuale, nome, prezzi_live) for p in pos_ibride if float(p['position']['size']) == s_mezzo and p['position']['direction'] == sat2_dir and abs(float(p['position']['level']) - sat_price) > 0.1)
                                p_ol = sum(calcola_pnl_chiusura([p], prezzo_attuale, nome, prezzi_live) for p in pos_ibride if float(p['position']['size']) == s_quarto and p['position']['direction'] == sat2_dir and abs(float(p['position']['level']) - sat_price) > 0.1)
                                
                                dett_pnl.append(f"SAT1: {pnl_sat1_teorico:+.0f}€")
                                if p_s2 != 0: dett_pnl.append(f"SAT2: {p_s2:+.0f}€")
                                if p_og != 0: dett_pnl.append(f"OG: {p_og:+.0f}€")
                                if p_ol != 0: dett_pnl.append(f"OL: {p_ol:+.0f}€")
                                dett_str = " (" + " | ".join(dett_pnl) + ")" if dett_pnl else ""
                                
                                core_long = [p for p in posizioni if p['position']['direction'] == "BUY" and float(p['position']['size']) == s_core]
                                core_short = [p for p in posizioni if p['position']['direction'] == "SELL" and float(p['position']['size']) == s_core]
                                lvl_long = float(core_long[0]['position']['level']) if core_long else param.get("prezzo_base")
                                lvl_short = float(core_short[0]['position']['level']) if core_short else param.get("prezzo_base")
                                tp2_val = round((param.get("tp") / 2) * mult, dec)
                                sat_l_lvl = round(lvl_long + tp2_val, dec)
                                sat_s_lvl = round(lvl_short - tp2_val, dec)
                                oco_str = f" a {formatta_numero(sat_s_lvl, dec)} e {formatta_numero(sat_l_lvl, dec)}"
                                
                                registra_operazione(nome, "Falso Innesco SAT1 (Rientro)", pnl_totale)
                                pulisci_mercato(epic, h, nome, mantieni_core_size=s_core)
                                invia_notifica(f"🛰️ SAT1 OCO: {nome}", f"[{nome}] SAT1 OCO (SHORT: {formatta_numero(sat_s_lvl, dec)} | LONG: {formatta_numero(sat_l_lvl, dec)}).{formatta_pnl(pnl_totale)}", "satellite")
                                aggiorna_memoria(nome, {"stato": "FASE_2_SATELLITI", "tentativi_sat": 0}, log_wip=f"✅ [EVENTO]: Stop SAT1 colpito a {formatta_numero(prezzo_attuale, dec)}. Reinserisco ENTRAMBI gli Ordini SAT1 (OCO){oco_str}.{formatta_pnl(pnl_totale)}{dett_str}")
                        
                        else:
                            if over_gain_attivo or over_loss_attivo:
                                if pendenti:
                                    pulisci_mercato(epic, h, nome, solo_pendenti=True)
                            elif not over_gain_attivo and not over_loss_attivo:
                                pend_og = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_mezzo and o['workingOrderData']['direction'] == sat2_dir]
                                pend_ol = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_quarto and o['workingOrderData']['direction'] == sat2_dir]
                                
                                if not pend_og or not pend_ol:
                                    falso_allarme_og = False
                                    falso_allarme_ol = False
                                    
                                    if not pend_og:
                                        falso_allarme_og = verifica_falso_allarme_ig(nome, epic, h, s_mezzo, sat2_dir, "[OVERGAIN]")
                                    if not pend_ol:
                                        falso_allarme_ol = verifica_falso_allarme_ig(nome, epic, h, s_quarto, sat2_dir, "[OVERLOSS]", pos_attese=1)
                                        
                                    if falso_allarme_og or falso_allarme_ol:
                                        continue
                                        
                                    tp4_val = round((param.get("tp") / 4) * mult, dec)
                                    lvl_og_sell = round(sat_price + tp4_val, dec)
                                    lvl_ol_sell = round(sat_price - tp4_val, dec)
                                    lvl_og_buy = round(sat_price - tp4_val, dec)
                                    lvl_ol_buy = round(sat_price + tp4_val, dec)
                                    
                                    if sat2_dir == "SELL":
                                        print_log(nome, f"➡️ Inserisco Ordine [OVERGAIN] a {lvl_og_sell} / [OVERLOSS] a {lvl_ol_sell} mancante...")
                                        fallito_f3 = False
                                        if not pend_og:
                                            succ_og = invia_ordine_pendente(nome, epic, valuta, "SELL", s_mezzo, lvl_og_sell, "LIMIT", round(sat_price, dec), None, h, dec, etichetta="[ORDINE OVERGAIN]")
                                            if not succ_og: fallito_f3 = True
                                            else: time.sleep(3.0) 
                                        if not pend_ol and not fallito_f3:
                                            succ_ol = invia_ordine_pendente(nome, epic, valuta, "SELL", s_quarto, lvl_ol_sell, "STOP", None, None, h, dec, etichetta="[ORDINE OVERLOSS]")
                                            if not succ_ol: fallito_f3 = True
                                            else: time.sleep(3.0)
                                            
                                        if fallito_f3:
                                            pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                            aggiorna_memoria(nome, {"attivo": False, "msg_manuale": "❌ Fallito rimpiazzo ordini FASE 2 (OG/OL) (possibile gap). Sospensione Motore."}, log_wip="🛑 Fallito rimpiazzo FASE 2 (OG/OL). Macchina Sospesa.")
                                            continue
                                    else:
                                        print_log(nome, f"➡️ Inserisco Ordine [OVERGAIN] a {lvl_og_buy} / [OVERLOSS] a {lvl_ol_buy} mancante...")
                                        fallito_f3 = False
                                        if not pend_og:
                                            succ_og = invia_ordine_pendente(nome, epic, valuta, "BUY", s_mezzo, lvl_og_buy, "LIMIT", round(sat_price, dec), None, h, dec, etichetta="[ORDINE OVERGAIN]")
                                            if not succ_og: fallito_f3 = True
                                            else: time.sleep(3.0) 
                                        if not pend_ol and not fallito_f3:
                                            succ_ol = invia_ordine_pendente(nome, epic, valuta, "BUY", s_quarto, lvl_ol_buy, "STOP", None, None, h, dec, etichetta="[ORDINE OVERLOSS]")
                                            if not succ_ol: fallito_f3 = True
                                            else: time.sleep(3.0)
                                            
                                        if fallito_f3:
                                            pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                            aggiorna_memoria(nome, {"attivo": False, "msg_manuale": "❌ Fallito rimpiazzo ordini FASE 2 (OG/OL) (possibile gap). Sospensione Motore."}, log_wip="🛑 Fallito rimpiazzo FASE 2 (OG/OL). Macchina Sospesa.")
                                            continue

                    elif stato == "FASE_3_INIT":
                        sat_dir = param.get("fase3_dir")
                        dir_contro = "SELL" if sat_dir == "BUY" else "BUY"
                        s_mezzo = max(1.0, s_core / 2)
                        
                        if not bid or not ask:
                            continue
                            
                        prezzo_attuale = round((bid + ask) / 2, dec)
                        pos_to_close_init = []
                        
                        core_trend_pos = [p for p in posizioni if p['position']['direction'] == sat_dir and float(p['position']['size']) >= s_core * 0.9]
                        chiusure_effettuate = []
                        if core_trend_pos: 
                            chiudi_parziale(nome, core_trend_pos[0]['position']['dealId'], epic, dir_contro, core_trend_pos[0]['position']['size'], valuta, h, etichetta="[CORE VINCITRICE]")
                            time.sleep(3.0) 
                            pos_to_close_init.append(core_trend_pos[0])
                            chiusure_effettuate.append("100% Core Originale")
                            
                        core_contro_pos = [p for p in posizioni if p['position']['direction'] == dir_contro and float(p['position']['size']) >= s_core * 0.9]
                        if core_contro_pos: 
                            chiudi_parziale(nome, core_contro_pos[0]['position']['dealId'], epic, sat_dir, s_mezzo, valuta, h, etichetta="[MEZZA CORE IN LOSS]")
                            time.sleep(3.0) 
                            pos_to_close_init.append({'position': {**core_contro_pos[0]['position'], 'size': s_mezzo}})
                            chiusure_effettuate.append("50% Core Tossica")
                            
                        pnl_str = ""
                        if pos_to_close_init:
                            pnl = calcola_pnl_chiusura(pos_to_close_init, prezzo_attuale, nome, prezzi_live)
                            pnl_str_base = formatta_pnl(pnl)
                            
                            pnl_c_vincente = 0
                            pnl_c_tossica = 0
                            if core_trend_pos:
                                pnl_c_vincente = calcola_pnl_chiusura([core_trend_pos[0]], prezzo_attuale, nome, prezzi_live)
                            if core_contro_pos:
                                pos_tossica_chiusa = {'position': {**core_contro_pos[0]['position'], 'size': s_mezzo}}
                                pnl_c_tossica = calcola_pnl_chiusura([pos_tossica_chiusa], prezzo_attuale, nome, prezzi_live)
                            
                            pnl_str = f"{pnl_str_base} (Good: {pnl_c_vincente:+.0f}€ | 1/2 Bad: {pnl_c_tossica:+.0f}€)"
                            registra_operazione(nome, "Entrata FASE 3 (Monetizzazione vecchie Core)", pnl)
                        
                        f3_base = round(float(ask if sat_dir == "BUY" else bid), dec)
                        tp2_val = round((param.get("tp") / 2) * mult, dec)
                        dts_val = round(param.get("dts") * mult, dec)
                        tp4_val = round((param.get("tp") / 4) * mult, dec)
                        
                        lim_core = round(f3_base + tp2_val, dec) if sat_dir == "BUY" else round(f3_base - tp2_val, dec)
                        stop_core = round(f3_base - dts_val, dec) if sat_dir == "BUY" else round(f3_base + dts_val, dec)
                        succ_f3, lvl_f3, deal_f3 = invia_ordine_mercato(nome, epic, valuta, sat_dir, s_core, h, dec, limit_lvl=lim_core, stop_lvl=stop_core, etichetta="[ORDINE FASE 3]")
                        if not succ_f3:
                            pulisci_mercato(epic, h, nome)
                            invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Fallimento immissione [ORDINE FASE 3] a mercato (dopo 4 tentativi). Passaggio forzato a MANUALE.", "rotating_light")
                            aggiorna_memoria(nome, {"attivo": False, "msg_manuale": f"❌ Fallita immissione [ORDINE FASE 3] a mercato dopo 4 tentativi."}, log_wip=f"✅ [EVENTO]: Emergenza: fallimento [ORDINE FASE 3]. Macchina Sospesa.")
                            continue
                            
                        if lvl_f3 is not None:
                            f3_base = lvl_f3
                            
                        time.sleep(3.0) 
                        
                        lvl_last = round(f3_base + tp4_val, dec) if sat_dir == "BUY" else round(f3_base - tp4_val, dec)
                        invia_ordine_pendente(nome, epic, valuta, dir_contro, s_mezzo, lvl_last, "LIMIT", round(f3_base, dec), None, h, dec, etichetta="[ORDINE ULTIMA FASE 3]")
                        
                        segno = "+" if sat_dir in ["BUY", "LONG"] else "-"
                        segno_u = "+" if dir_contro in ["BUY", "LONG"] else "-"
                        base_log = param.get("temp_fase3_log", f"Avvio FASE 3.")
                        msg_init = f"{base_log} Nuova Core [{to_market_dir(sat_dir)}] [{segno}{s_core}] a {formatta_numero(f3_base, dec)} e Ordine ULTIMA [{to_market_dir(dir_contro)}] [{segno_u}{s_mezzo}] a {formatta_numero(lvl_last, dec)}"
                        invia_notifica(f"🔥 ENTRATA FASE 3: {nome}", f"[{nome}] {msg_init}", "fire")
                        aggiorna_memoria(nome, {"stato": "FASE_3", "fase3_step": 1, "fase3_current_base": f3_base}, log_wip=f"✅ [EVENTO]: {msg_init}")

                    elif stato in ["FASE_3", "FASE_3 + Ultima"]:
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
                            is_ultima_closing = (param.get("stato") == "FASE_3 + Ultima" and nuovo_stato == "FASE_3")
                            if not is_ultima_closing and last_pos:
                                pr_str = f" a {formatta_numero(last_pos[0]['position']['level'], dec)}"
                                msg_log = f"✅ [EVENTO]: ULTIMA innescata a mercato{pr_str}"
                                invia_notifica(f"🔪 ULTIMA: {nome}", f"[{nome}] Ultima [{to_market_dir(dir_contro)}]{pr_str}", "dagger")
                                aggiorna_memoria(nome, {"stato": nuovo_stato}, log_wip=msg_log)
                            else:
                                if is_ultima_closing:
                                    valore_punto = CONFIG_STRUMENTI[nome].get("valore_punto", 1)
                                    rate = get_eur_rate(valuta, prezzi_live)
                                    pnl = (param.get("tp") / 4) * s_last * valore_punto * rate
                                    registra_operazione(nome, "Take Profit ULTIMA", pnl)
                                    msg_log = f"💰 [ULTIMA] chiusa in profitto.{formatta_pnl(pnl)}"
                                    invia_notifica(f"💰 ULTIMA TP: {nome}", f"[{nome}] Ultima chiusa in profitto.{formatta_pnl(pnl)}", "moneybag")
                                    aggiorna_memoria(nome, {"stato": nuovo_stato}, log_wip=msg_log)
                                else:
                                    aggiorna_memoria(nome, {"stato": nuovo_stato})

                        if not core_trend:
                            if not bid or not ask:
                                continue
                                
                            prezzo_attuale = round((bid + ask) / 2, dec)
                            
                            tp2_val = round((param.get("tp") / 2) * mult, dec)
                            dts_val = round(param.get("dts") * mult, dec)
                            
                            vittoria = False
                            if sat_dir == "BUY" and prezzo_attuale > f3_base + (tp2_val - dts_val) / 2:
                                vittoria = True
                            elif sat_dir == "SELL" and prezzo_attuale < f3_base - (tp2_val - dts_val) / 2:
                                vittoria = True
                            
                            if not vittoria:
                                valore_punto = c.get("valore_punto", 1)
                                pnl_core_valuta = - (param.get("dts") * s_core * valore_punto)
                                pnl_contro_eur = calcola_pnl_chiusura(core_contro_pos, prezzo_attuale, nome, prezzi_live)
                                rate = get_eur_rate(valuta, prezzi_live)
                                pnl_tot = (pnl_core_valuta * rate) + pnl_contro_eur
                                
                                registra_operazione(nome, "Stop Loss FASE 3", pnl_tot)
                                
                                pulisci_mercato(epic, h, nome)
                                invia_notifica(f"🏁 FASE 3 STOP: {nome}", f"[{nome}] Uscita da Fase 3, colpito SL nuova Core a {formatta_numero(prezzo_attuale, dec)}. Macchinetta SPENTA.{formatta_pnl(pnl_tot)}", "checkered_flag")
                                aggiorna_memoria(nome, {"stato": "IN_ATTESA", "tentativi_sat": 0, "attivo": False, "ticket2_active": False}, log_wip=f"✅ [EVENTO]: Uscita da Fase 3, colpito SL nuova Core a {formatta_numero(prezzo_attuale, dec)}. Macchinetta SPENTA.{formatta_pnl(pnl_tot)}")
                                stampa_riepilogo_statistiche(nome)
                            else:
                                if pendenti:
                                    pulisci_mercato(epic, h, nome, solo_pendenti=True)
                                    
                                pos_to_close_f3 = list(last_pos)
                                for p in last_pos: 
                                    chiudi_parziale(nome, p['position']['dealId'], epic, sat_dir, p['position']['size'], valuta, h, etichetta="[ORDINE TAGLIO]")
                                    time.sleep(3.0) 
                                
                                core_contro_pos = [p for p in posizioni if p['position']['direction'] == dir_contro]
                                new_step = step
                                if core_contro_pos:
                                    c = core_contro_pos[0]
                                    if step == 1:
                                        s_cut_effettivo = s_core * 0.35 
                                        succ_cut = chiudi_parziale(nome, c['position']['dealId'], epic, sat_dir, s_cut_effettivo, valuta, h, etichetta=f"[TAGLIO CORE STEP {step}]")
                                        if not succ_cut:
                                            invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Fallimento [TAGLIO CORE STEP {step}] (dopo 4 tentativi). Passaggio forzato a MANUALE.", "rotating_light")
                                            aggiorna_memoria(nome, {"attivo": False, "msg_manuale": f"❌ Fallito [TAGLIO CORE STEP {step}] dopo 4 tentativi."}, log_wip=f"🛑 Emergenza: fallimento [TAGLIO CORE STEP {step}]. Macchina Sospesa.")
                                            continue
                                        time.sleep(3.0) 
                                        new_step = 2
                                    elif step == 2:
                                        s_cut_effettivo = float(c['position']['size']) 
                                        succ_cut = chiudi_parziale(nome, c['position']['dealId'], epic, sat_dir, s_cut_effettivo, valuta, h, etichetta=f"[TAGLIO CORE STEP {step}]")
                                        if not succ_cut:
                                            invia_notifica(f"🚨 EMERGENZA MOTORE: {nome}", f"[{nome}] Fallimento [TAGLIO CORE STEP {step}] (dopo 4 tentativi). Passaggio forzato a MANUALE.", "rotating_light")
                                            aggiorna_memoria(nome, {"attivo": False, "msg_manuale": f"❌ Fallito [TAGLIO CORE STEP {step}] dopo 4 tentativi."}, log_wip=f"🛑 Emergenza: fallimento [TAGLIO CORE STEP {step}]. Macchina Sospesa.")
                                            continue
                                        time.sleep(3.0) 
                                        new_step = 3
                                        
                                    pos_to_close_f3.append({'position': {**c['position'], 'size': s_cut_effettivo}})
                                    
                                pnl = calcola_pnl_chiusura(pos_to_close_f3, prezzo_attuale, nome, prezzi_live)
                                
                                if new_step == 3:
                                    registra_operazione(nome, "Vittoria 100% (Fine Fase 3)", pnl)
                                    pulisci_mercato(epic, h, nome)
                                    invia_notifica(f"🏆 FASE 3 VITTORIA 100%: {nome}", f"[{nome}] Ciclo completato al 100% a {formatta_numero(prezzo_attuale, dec)}! Macchinetta SPENTA.{formatta_pnl(pnl)}", "trophy")
                                    aggiorna_memoria(nome, {"stato": "IN_ATTESA", "tentativi_sat": 0, "attivo": False, "ticket2_active": False}, log_wip=f"✅ [EVENTO]: FASE 3 COMPLETATA AL 100% a {formatta_numero(prezzo_attuale, dec)}! Ciclo concluso. Macchinetta SPENTA.{formatta_pnl(pnl)}")
                                    stampa_riepilogo_statistiche(nome)
                                else:
                                    registra_operazione(nome, f"Taglio Core {35 if new_step==2 else 15}% (Fase 3)", pnl)
                                    
                                    tp2_val = round((param.get("tp") / 2) * mult, dec)
                                    dts_val = round(param.get("dts") * mult, dec)
                                    tp4_val = round((param.get("tp") / 4) * mult, dec)
                                    
                                    lim_core = round(prezzo_attuale + tp2_val, dec) if sat_dir == "BUY" else round(prezzo_attuale - tp2_val, dec)
                                    stop_core = round(prezzo_attuale - dts_val, dec) if sat_dir == "BUY" else round(prezzo_attuale + dts_val, dec)
                                    
                                    succ_f3_taglio, lvl_f3_taglio, deal_f3_taglio = invia_ordine_mercato(nome, epic, valuta, sat_dir, s_core, h, dec, limit_lvl=lim_core, stop_lvl=stop_core, etichetta="[ORDINE FASE 3]")
                                    time.sleep(3.0) 
                                    
                                    base_taglio = lvl_f3_taglio if lvl_f3_taglio is not None else prezzo_attuale
                                    new_s_last = s_core * 0.15
                                    lvl_last = round(base_taglio + tp4_val, dec) if sat_dir == "BUY" else round(base_taglio - tp4_val, dec)
                                    
                                    invia_ordine_pendente(nome, epic, valuta, dir_contro, new_s_last, lvl_last, "LIMIT", round(base_taglio, dec), None, h, dec, etichetta="[ORDINE ULTIMA FASE 3]")
                                    
                                    segno = "+" if sat_dir in ["BUY", "LONG"] else "-"
                                    segno_u = "+" if dir_contro in ["BUY", "LONG"] else "-"
                                    pct = 35 if new_step==2 else 15
                                    msg_taglio = f"Taglio {pct}%.{formatta_pnl(pnl)} Nuova Core [{to_market_dir(sat_dir)}] [{segno}{s_core}] a {formatta_numero(base_taglio, dec)} e ULTIMA [{to_market_dir(dir_contro)}] [{segno_u}{new_s_last}] a {formatta_numero(lvl_last, dec)}"
                                    invia_notifica(f"✂️ TAGLIO FASE 3: {nome}", f"[{nome}] {msg_taglio}", "scissors")
                                    aggiorna_memoria(nome, {"fase3_step": new_step, "fase3_current_base": base_taglio, "stato": "FASE_3"}, log_wip=f"✅ [EVENTO]: {msg_taglio}")
                        else:
                            if not last_pos:
                                pend_ultima = [o for o in pendenti if float(o['workingOrderData'].get('orderSize', o['workingOrderData'].get('size', 0))) == s_last and o['workingOrderData']['direction'] == dir_contro]
                                if not pend_ultima:
                                    if verifica_falso_allarme_ig(nome, epic, h, s_last, dir_contro, "[ORDINE ULTIMA FASE 3]"):
                                        continue
                                        
                                    tp4_val = round((param.get("tp") / 4) * mult, dec)
                                    lvl_last = round(f3_base + tp4_val, dec) if sat_dir == "BUY" else round(f3_base - tp4_val, dec)
                                    invia_ordine_pendente(nome, epic, valuta, dir_contro, s_last, lvl_last, "LIMIT", round(f3_base, dec), None, h, dec, etichetta="[ORDINE ULTIMA FASE 3]")
                                    aggiorna_memoria(nome, {"stato": "FASE_3"})

            time.sleep(4)

    except KeyboardInterrupt:
        print(f"\n🛑 Motore per {NOME_CONTO} fermato manualmente (CTRL+C).")
    except Exception as e:
        print(f"\n❌ CRASH DEL MOTORE {NOME_CONTO}: {e}")
        invia_notifica("💀 CRASH DI SISTEMA", f"[{NOME_CONTO}] Il Motore si è arrestato in modo anomalo: {e}", "skull")
        traceback.print_exc()

if __name__ == "__main__":
    esegui_motore()
