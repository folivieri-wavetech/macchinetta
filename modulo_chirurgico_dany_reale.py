import os
import sys
import json
import time
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
POSIZIONI_FILE = os.path.join(CONTO_DIR, "posizioni_aperte.json")
CONSOLE_FILE = os.path.join(CONTO_DIR, "console_live.log")

BASE_URL = "https://api.ig.com/gateway/deal"

def print_log(messaggio):
    ora = now_it().strftime("%H:%M:%S")
    riga = f"[{ora}] [DANY_REALE] {messaggio}"
    print(riga)
    try:
        righe = []
        if os.path.exists(CONSOLE_FILE):
            with open(CONSOLE_FILE, "r", encoding="utf-8") as f:
                righe = f.readlines()
        righe.append(riga + "\n")
        if len(righe) > 1000:
            righe = righe[-1000:]
        with open(CONSOLE_FILE, "w", encoding="utf-8") as f:
            f.writelines(righe)
    except Exception:
        pass

class ModuloChirurgicoDanyReale:
    def __init__(self):
        self.cfg = dotenv_values(ENV_FILE)
        self.username = self.cfg.get("IG_USERNAME")
        self.password = self.cfg.get("IG_PASSWORD")
        self.api_key = self.cfg.get("IG_API_KEY")
        self.target_account_id = self.cfg.get("IG_ACCOUNT_ID", "DUACG").strip()
        self.cst = None
        self.xst = None
        self.t_login = 0
        self.session_start = time.time()
        self.ultimo_gold_bid_ask = None
        self.gf_engine = None
        self.th_gf = None
        
    def calcola_durata_sessione(self):
        if not os.path.exists(TOKEN_FILE):
            return "0h 00m"
        tempo_creazione = os.path.getmtime(TOKEN_FILE)
        durata = now_it() - datetime.datetime.fromtimestamp(tempo_creazione, TZ_ITALIA)
        ore = int(durata.total_seconds() // 3600)
        minuti = int((durata.total_seconds() % 3600) // 60)
        return f"{ore}h {minuti:02d}m"

    def verifica_token_ig(self):
        if not os.path.exists(TOKEN_FILE):
            return self.login()
            
        tempo_creazione = os.path.getmtime(TOKEN_FILE)
        if (time.time() - tempo_creazione) > (70 * 3600):
            print_log("⚠️ Token sul disco vicino alle 72h (> 70h): eseguo rinnovo completo...")
            return self.login()

        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.cst = d.get("CST")
            self.xst = d.get("X-SECURITY-TOKEN")
            if not self.cst or not self.xst:
                return self.login()

            # Test rapido validità sessione esistente
            r = requests.get(f"{BASE_URL}/accounts", headers=self.get_auth_headers("1"), timeout=8)
            if r.status_code == 200:
                print_log(f"✅ Sessione IG Reale persistente ripristinata dal token (Durata: {self.calcola_durata_sessione()}).")
                return True
            else:
                print_log("🔄 Token persistente scaduto su IG (HTTP 401): eseguo nuovo login...")
                return self.login()
        except Exception as e:
            print_log(f"⚠️ Errore verifica token persistente: {e}, procedo con login...")
            return self.login()

    def login(self):
        h = {
            "X-IG-API-KEY": self.api_key,
            "Version": "2",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        p = {
            "identifier": self.username,
            "password": self.password
        }
        try:
            r = requests.post(f"{BASE_URL}/session", headers=h, json=p, timeout=12)
            if r.status_code == 200:
                self.cst = r.headers.get("CST")
                self.xst = r.headers.get("X-SECURITY-TOKEN")
                self.t_login = time.time()
                
                tok_data = {
                    "CST": self.cst,
                    "X-SECURITY-TOKEN": self.xst,
                    "accountId": self.target_account_id,
                    "aggiornato": now_it().strftime("%Y-%m-%d %H:%M:%S")
                }
                with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                    json.dump(tok_data, f, indent=4)
                    
                print_log("✅ Connessione IG Reale stabilita con successo. Token salvato.")
                return True
            else:
                print_log(f"⚠️ Errore autenticazione IG: HTTP {r.status_code} - {r.text}")
                return False
        except Exception as e:
            print_log(f"⚠️ Eccezione di rete durante il login IG: {e}")
            return False

    def get_auth_headers(self, version="1"):
        return {
            "X-IG-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.xst,
            "Version": str(version),
            "Accept": "application/json"
        }

    def aggiorna_saldo(self):
        try:
            r = requests.get(f"{BASE_URL}/accounts", headers=self.get_auth_headers("1"), timeout=10)
            if r.status_code == 401:
                print_log("🔄 Token scaduto, esecuzione rinnovo credenziali...")
                if self.login():
                    r = requests.get(f"{BASE_URL}/accounts", headers=self.get_auth_headers("1"), timeout=10)
                else:
                    return False
                    
            if r.status_code == 200:
                dati = r.json()
                accounts = dati.get("accounts", [])
                acc = next((a for a in accounts if a.get("accountId") == self.target_account_id), None)
                if not acc and accounts:
                    acc = accounts[0]
                    
                if acc:
                    bal = acc.get("balance", {})
                    saldo = str(bal.get("balance", 0.0))
                    disp = str(bal.get("available", 0.0))
                    marg = str(bal.get("deposit", 0.0))
                    dd = str(bal.get("profitLoss", 0.0))
                    
                    dur_str = self.calcola_durata_sessione()
                    
                    prezzi_ba = {}
                    if self.ultimo_gold_bid_ask:
                        prezzi_ba["Spot Gold"] = self.ultimo_gold_bid_ask
                        
                    stato = {
                        "saldo": saldo,
                        "disponibile": disp,
                        "margine": marg,
                        "drawdown": dd,
                        "messaggio": "Connesso Live IG Reale",
                        "durata_sessione": dur_str,
                        "ultimo_aggiornamento": now_it().strftime("%H:%M:%S"),
                        "prezzi_live": {},
                        "distanze_minime": {},
                        "prezzi_bid_ask": prezzi_ba
                    }
                    
                    tmp_st = f"{STATO_FILE}.tmp.{os.getpid()}"
                    with open(tmp_st, "w", encoding="utf-8") as f:
                        json.dump(stato, f, indent=4)
                    os.replace(tmp_st, STATO_FILE)
                    return True
            else:
                print_log(f"⚠️ Errore lettura /accounts: HTTP {r.status_code}")
                return False
        except Exception as e:
            print_log(f"⚠️ Eccezione lettura saldo: {e}")
            return False

    def aggiorna_posizioni(self):
        try:
            r = requests.get(f"{BASE_URL}/positions", headers=self.get_auth_headers("2"), timeout=10)
            if r.status_code == 200:
                pos_list = r.json().get("positions", [])
                posizioni_salvate = []
                for item in pos_list:
                    m = item.get("market", {})
                    p = item.get("position", {})
                    inst_name = str(m.get("instrumentName", ""))
                    epic_code = str(m.get("epic", ""))
                    bid_p = m.get("bid")
                    offer_p = m.get("offer")
                    
                    if "GOLD" in inst_name.upper() or "CFDGOLD" in epic_code.upper():
                        if bid_p and offer_p:
                            self.ultimo_gold_bid_ask = {"bid": float(bid_p), "ask": float(offer_p)}

                    posizioni_salvate.append({
                        "dealId": p.get("dealId"),
                        "instrument": inst_name,
                        "epic": epic_code,
                        "direction": p.get("direction"),
                        "size": p.get("dealSize") or p.get("size"),
                        "openLevel": p.get("openLevel") or p.get("level"),
                        "bid": bid_p,
                        "offer": offer_p,
                        "upl": p.get("upl"),
                        "currency": p.get("currency")
                    })
                tmp_p = f"{POSIZIONI_FILE}.tmp.{os.getpid()}"
                with open(tmp_p, "w", encoding="utf-8") as f:
                    json.dump(posizioni_salvate, f, indent=4)
                os.replace(tmp_p, POSIZIONI_FILE)
                return True
        except Exception as e:
            print_log(f"⚠️ Eccezione lettura posizioni: {e}")
            return False

    def avvia_gf_thread(self):
        try:
            import threading
            from goldfinger_engine import GoldfingerEngine
            self.gf_engine = GoldfingerEngine()
            self.th_gf = threading.Thread(target=self.gf_engine.avvia_loop, daemon=True, name="GoldfingerThread")
            self.th_gf.start()
            print_log("🧵 Thread Goldfinger Engine avviato con successo in background.")
            return True
        except Exception as e_th:
            print_log(f"⚠️ Impossibile avviare thread Goldfinger: {e_th}")
            return False

    def avvia_loop(self):
        print_log(f"🚀 Modulo Chirurgico DANY_REALE avviato per conto {self.target_account_id}")
        
        # Ripristino token persistente o login iniziale con retry
        while not self.verifica_token_ig():
            print_log("❌ Autenticazione iniziale fallita. Attesa prudente di 30 secondi prima di riprovare...")
            time.sleep(30)
                
        ultimo_log_hb = 0
        # Avvio iniziale thread dedicato per il motore Goldfinger
        self.avvia_gf_thread()
        
        while True:
            try:
                # 1. Watchdog: verifica che il thread Goldfinger sia costantemente attivo
                if self.th_gf is None or not self.th_gf.is_alive():
                    cfg_path = os.path.join(CONTO_DIR, "config_goldfinger.json")
                    cfg_gf = {}
                    if os.path.exists(cfg_path):
                        try:
                            with open(cfg_path, "r", encoding="utf-8") as f_cfg:
                                cfg_gf = json.load(f_cfg)
                        except Exception:
                            pass
                    if cfg_gf.get("attivo", False):
                        print_log("🛡️ Watchdog: Rilevato thread Goldfinger terminato inaspettatamente (errore di rete o IG). Riavvio automatico prudente tra 5 secondi...")
                        time.sleep(5)
                        self.avvia_gf_thread()

                # 2. Rinnovo preventivo automatico a 70 ore (standard granitico identico a Motore.py per tutti i conti)
                richiede_rinnovo = False
                if not os.path.exists(TOKEN_FILE):
                    richiede_rinnovo = True
                else:
                    tempo_creazione = os.path.getmtime(TOKEN_FILE)
                    if (time.time() - tempo_creazione) > (70 * 3600):
                        print_log("⚠️ Sessione vicina alle 72h: Rinnovo automatico preventivo del Token IG (regola 70 ore).")
                        richiede_rinnovo = True
                if richiede_rinnovo:
                    self.login()
                    
                self.aggiorna_saldo()
                self.aggiorna_posizioni()
                
                # Log di heartbeat ogni 5 minuti
                if (time.time() - ultimo_log_hb) > 300:
                    ultimo_log_hb = time.time()
                    print_log("💓 Heartbeat DANY_REALE attivo e sincronizzato.")
                    
                time.sleep(10)
            except KeyboardInterrupt:
                print_log("🛑 Modulo Chirurgico interrotto manualmente.")
                break
            except Exception as e:
                print_log(f"⚠️ Errore imprevisto nel loop principale: {e}")
                time.sleep(10)

if __name__ == "__main__":
    modulo = ModuloChirurgicoDanyReale()
    modulo.avvia_loop()
