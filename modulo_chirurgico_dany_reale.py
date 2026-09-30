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
                    
                    dur_sec = int(time.time() - self.session_start)
                    dur_str = f"{dur_sec // 3600}h {(dur_sec % 3600) // 60}m"
                    
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
                        "prezzi_bid_ask": {}
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
                    posizioni_salvate.append({
                        "dealId": p.get("dealId"),
                        "instrument": m.get("instrumentName"),
                        "epic": m.get("epic"),
                        "direction": p.get("direction"),
                        "size": p.get("size"),
                        "openLevel": p.get("level"),
                        "bid": m.get("bid"),
                        "offer": m.get("offer"),
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

    def avvia_loop(self):
        print_log(f"🚀 Modulo Chirurgico DANY_REALE avviato per conto {self.target_account_id}")
        if not self.login():
            print_log("❌ Login iniziale fallito. Riprovo tra 10 secondi...")
            time.sleep(10)
            if not self.login():
                return
                
        ultimo_log_hb = 0
        while True:
            try:
                # Rinnovo proattivo del token ogni 45 minuti (la sessione IG scade dopo 1h)
                if (time.time() - self.t_login) > 2700:
                    print_log("🔄 Rinnovo proattivo sessione IG...")
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
