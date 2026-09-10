import os
import sys
import time
import json
import requests
import datetime
try:
    import zoneinfo
    TZ_ITALIA = zoneinfo.ZoneInfo("Europe/Rome")
except Exception:
    TZ_ITALIA = datetime.timezone(datetime.timedelta(hours=2))
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding='utf-8')


CONFIG_STRUMENTI = {
    "AUD/NZD": {"epic": "CS.D.AUDNZD.MINI.IP"},
    "CAD/JPY": {"epic": "CS.D.CADJPY.MINI.IP"},
    "EUR/JPY": {"epic": "CS.D.EURJPY.MINI.IP"},
    "GBP/JPY": {"epic": "CS.D.GBPJPY.MINI.IP"},
    "GBP/USD": {"epic": "CS.D.GBPUSD.MINI.IP"},
    "USD/CAD": {"epic": "CS.D.USDCAD.MINI.IP"},
    "USD/CHF": {"epic": "CS.D.USDCHF.MINI.IP"},
    "USD/JPY": {"epic": "CS.D.USDJPY.MINI.IP"},
    "Spot Gold": {"epic": "CS.D.CFEGOLD.CBE.IP"},
    "US 500 Cash": {"epic": "IX.D.SPTRD.IBE.IP"},
    "Oil - US Crude": {"epic": "CC.D.CL.UBE.IP"}
}

TIMEFRAMES = ["HOUR", "HOUR_4", "DAY"]
FILE_LOCK_SYNC = "sync_settimanale.json"

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

def get_clean_name(nome):
    return nome.replace("/", "_").replace(" ", "_")

def trova_percorso_file(nome_file):
    for base in ["/data/Logs_e_Cache", "/data", "../Logs_e_Cache", "Logs_e_Cache", "."]:
        if os.path.exists(base) and os.path.isdir(base):
            return os.path.join(base, nome_file)
    return nome_file

def leggi_stato_sync():
    path = trova_percorso_file(FILE_LOCK_SYNC)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salva_stato_sync(data):
    path = trova_percorso_file(FILE_LOCK_SYNC)
    try:
        tmp = f"{path}.tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f"⚠️ Impossibile salvare stato sync: {e}")

def invia_ntfy(titolo, messaggio, tag="arrows_counterclockwise"):
    env_paths = ["FIORDOK_DEMO/.env", "/data/FIORDOK_DEMO/.env", "../FIORDOK_DEMO/.env", ".env"]
    topic = None
    for ep in env_paths:
        if os.path.exists(ep):
            cfg = dotenv_values(ep)
            topic = cfg.get("NTFY_TOPIC")
            if topic:
                break
    if not topic:
        topic = "Macchinetta_Alert"
        
    try:
        orario = now_it().strftime("%H:%M:%S")
        headers = {
            "Title": f"[MACCHINETTA] {titolo}".encode('utf-8'),
            "Tags": tag
        }
        requests.post(f"https://ntfy.sh/{topic}", data=f"[{orario}] {messaggio}".encode('utf-8'), headers=headers, timeout=5)
    except Exception:
        pass

def trova_env_fiordok():
    for p in ["FIORDOK_DEMO/.env", "/data/FIORDOK_DEMO/.env", "../FIORDOK_DEMO/.env", ".env"]:
        if os.path.exists(p):
            return p
    return None

def esegui_sync_candele(forza=False):
    """
    Esegue la sincronizzazione settimanale di 60 candele per H1, H4, D1
    utilizzando solo le credenziali FIORDOK e distribuendo a tutti i conti.
    """
    now = now_it()
    chiave_settimana = f"{now.year}-W{now.isocalendar()[1]}"
    stato = leggi_stato_sync()

    if not forza:
        # Verifica se già eseguito questa settimana
        if stato.get(chiave_settimana, {}).get("stato") == "SUCCESS":
            return False, f"Già eseguito per la settimana {chiave_settimana}"

    env_path = trova_env_fiordok()
    if not env_path:
        return False, "File .env di FIORDOK non trovato"

    cfg = dotenv_values(env_path)
    api_key = cfg.get("IG_API_KEY")
    username = cfg.get("IG_USERNAME")
    password = cfg.get("IG_PASSWORD")

    if not api_key or not username or not password:
        return False, "Credenziali IG incomplete nel file .env"

    print(f"🔄 Avvio sincronizzazione settimanale candele (Settimana {chiave_settimana})...")
    sess = requests.Session()
    auth_resp = sess.post(
        "https://demo-api.ig.com/gateway/deal/session",
        json={"identifier": username, "password": password},
        headers={
            "X-IG-API-KEY": api_key,
            "Version": "2",
            "Content-Type": "application/json",
            "Accept": "application/json; charset=UTF-8"
        },
        timeout=10
    )

    if auth_resp.status_code != 200:
        msg_err = f"Autenticazione IG fallita: {auth_resp.status_code}"
        print(f"❌ {msg_err}")
        return False, msg_err

    cst = auth_resp.headers.get("CST")
    xst = auth_resp.headers.get("X-SECURITY-TOKEN")
    req_headers = {
        "X-IG-API-KEY": api_key,
        "CST": cst,
        "X-SECURITY-TOKEN": xst,
        "Version": "3",
        "Accept": "application/json; charset=UTF-8"
    }

    # Circuit breaker: test chiamata singola
    test_url = "https://demo-api.ig.com/gateway/deal/prices/CS.D.GBPJPY.MINI.IP?resolution=HOUR&max=1"
    test_r = sess.get(test_url, headers=req_headers, timeout=5)
    if test_r.status_code == 403:
        msg_err = "Circuit breaker: Quota IG esaurita (403), sincronizzazione annullata."
        print(f"🛑 {msg_err}")
        invia_ntfy("SYNC SETTIMANALE BLOCCATA", msg_err, "warning")
        return False, msg_err

    target_dirs = [".", "Logs_e_Cache", "/data", "/data/Logs_e_Cache"]
    for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
        target_dirs.extend([acc, f"../{acc}", f"/data/{acc}"])

    valid_target_dirs = [d for d in set(target_dirs) if os.path.exists(d) and os.path.isdir(d)]

    totale_file_aggiornati = 0
    totale_candele = 0

    for nome, info in CONFIG_STRUMENTI.items():
        epic = info["epic"]
        clean = get_clean_name(nome)

        for tf in TIMEFRAMES:
            url = f"https://demo-api.ig.com/gateway/deal/prices/{epic}?resolution={tf}&max=60&pageSize=0"
            r = sess.get(url, headers=req_headers, timeout=10)
            if r.status_code == 200:
                prices = r.json().get("prices", [])
                if len(prices) > 0:
                    fname = f"candele_{clean}_{tf}.json"
                    totale_file_aggiornati += 1
                    totale_candele += len(prices)
                    for d in valid_target_dirs:
                        dest = os.path.join(d, fname)
                        try:
                            tmp = f"{dest}.tmp.{os.getpid()}"
                            with open(tmp, "w", encoding="utf-8") as f:
                                json.dump(prices, f, indent=2)
                            os.replace(tmp, dest)
                        except Exception:
                            pass
            time.sleep(0.5)

    # Registra successo
    stato[chiave_settimana] = {
        "stato": "SUCCESS",
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "file_aggiornati": totale_file_aggiornati,
        "totale_candele": totale_candele
    }
    salva_stato_sync(stato)

    msg_ok = f"Sincronizzazione completata: {totale_file_aggiornati}/33 file aggiornati ({totale_candele} candele totali distribuite su tutti i conti)."
    print(f"✅ {msg_ok}")
    invia_ntfy("SYNC CANDLE SETTIMANALE OK", msg_ok, "white_check_mark")
    return True, msg_ok

_LAST_CHECK_TS = 0

def controlla_schedulazione_settimanale(nome_conto):
    """
    Chiamata dal loop del motore ogni minuto.
    Esegue lo scarico solo se:
    1. Il conto è FIORDOK_DEMO (gli altri conti leggono i file distribuiti su PVC).
    2. È Lunedì (weekday == 0).
    3. L'orario è >= 05:30 italiane (a metà barra per non interferire con il cambio candela H1 delle 06:00).
    4. Non è ancora stato eseguito per la settimana corrente.
    """
    global _LAST_CHECK_TS
    if nome_conto != "FIORDOK_DEMO":
        return

    now_ts = time.time()
    if now_ts - _LAST_CHECK_TS < 60:
        return
    _LAST_CHECK_TS = now_ts

    now = now_it()
    # 0 = Lunedì, ore >= 05:30 (neutro da chiusure candele H1)
    if now.weekday() == 0 and (now.hour > 5 or (now.hour == 5 and now.minute >= 30)):
        chiave_settimana = f"{now.year}-W{now.isocalendar()[1]}"
        stato = leggi_stato_sync()
        if stato.get(chiave_settimana, {}).get("stato") != "SUCCESS":
            esegui_sync_candele(forza=False)

if __name__ == "__main__":
    if "--force" in sys.argv:
        success, message = esegui_sync_candele(forza=True)
        print(f"Risultato (FORZATO): success={success}, msg={message}")
    else:
        print("Verifica schedulazione settimanale (Lunedì ore 05:30)...")
        controlla_schedulazione_settimanale("FIORDOK_DEMO")
        print("Controllo completato.")
