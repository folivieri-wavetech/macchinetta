import json
import os
from werkzeug.security import generate_password_hash, check_password_hash

# Il file verrà salvato in Logs_e_Cache che dovrebbe essere persistente nel docker
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(ROOT_DIR, "Logs_e_Cache")
CONFIG_UTENTI_PATH = os.path.join(LOGS_DIR, "config_utenti.json")

def init_db():
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR, exist_ok=True)
        
    if not os.path.exists(CONFIG_UTENTI_PATH):
        # Se non esiste, creo il database iniziale con l'utente "Manager" derivato dall'ambiente
        utente_default = os.getenv("DASHBOARD_USER", "Marco")
        password_default = os.getenv("DASHBOARD_PASSWORD", "Bolzano&1971")
        
        db = {
            utente_default: {
                "ruolo": "MANAGER",
                "password_hash": generate_password_hash(password_default),
                "tutti_i_conti": True,
                "conti_autorizzati": []
            }
        }
        _salva_db(db)

def _carica_db():
    init_db()
    try:
        with open(CONFIG_UTENTI_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
            # Normalizzazione automatica ruoli legacy
            modificato = False
            for k, v in db.items():
                if v.get("ruolo") == "REGISTA":
                    v["ruolo"] = "MANAGER"
                    modificato = True
                elif v.get("ruolo") == "GUEST":
                    v["ruolo"] = "OWNER"
                    modificato = True
            if modificato:
                _salva_db(db)
            return db
    except Exception as e:
        print(f"Errore caricamento utenti: {e}")
        return {}

def _salva_db(db):
    try:
        with open(CONFIG_UTENTI_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4)
        return True
    except Exception as e:
        print(f"Errore salvataggio utenti: {e}")
        return False

def verifica_login(username, password):
    db = _carica_db()
    if username in db:
        user_data = db[username]
        if check_password_hash(user_data.get("password_hash", ""), password):
            ruolo = user_data.get("ruolo", "VIEWER")
            if ruolo == "REGISTA":
                ruolo = "MANAGER"
            elif ruolo == "GUEST":
                ruolo = "OWNER"
            return {
                "success": True,
                "ruolo": ruolo,
                "tutti_i_conti": user_data.get("tutti_i_conti", False),
                "conti_autorizzati": user_data.get("conti_autorizzati", [])
            }
    return {"success": False}

def get_tutti_utenti():
    db = _carica_db()
    utenti_safe = {}
    for k, v in db.items():
        ruolo = v.get("ruolo", "VIEWER")
        if ruolo == "REGISTA":
            ruolo = "MANAGER"
        elif ruolo == "GUEST":
            ruolo = "OWNER"
        utenti_safe[k] = {
            "ruolo": ruolo,
            "tutti_i_conti": v.get("tutti_i_conti", False),
            "conti_autorizzati": v.get("conti_autorizzati", []),
            "credenziali_ig": v.get("credenziali_ig", {})
        }
    return utenti_safe

def get_owner_accounts():
    """Restituisce un set con i nomi di tutti i conti associati a utenti OWNER (ex Guest)."""
    db = _carica_db()
    owner_accs = set()
    for k, v in db.items():
        if v.get("ruolo") in ["OWNER", "GUEST"]:
            for acc in v.get("conti_autorizzati", []):
                owner_accs.add(acc)
    return owner_accs

# Alias per compatibilità
get_guest_accounts = get_owner_accounts

def leggi_credenziali_env(nome_conto):
    """Legge le credenziali IG dal file .env del conto."""
    env_file = os.path.join(ROOT_DIR, nome_conto, ".env")
    creds = {"username": "", "password": "", "api_key": "", "account_id": ""}
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("IG_USERNAME="):
                        creds["username"] = line.split("=", 1)[1].strip()
                    elif line.startswith("IG_PASSWORD="):
                        creds["password"] = line.split("=", 1)[1].strip()
                    elif line.startswith("IG_API_KEY="):
                        creds["api_key"] = line.split("=", 1)[1].strip()
                    elif line.startswith("IG_ACCOUNT_ID="):
                        creds["account_id"] = line.split("=", 1)[1].strip()
        except Exception:
            pass
    return creds

def inizializza_cartella_conto(nome_conto, ig_username, ig_password, ig_api_key, tipo_conto="DEMO", ig_account_id=""):
    """Crea la cartella conto con il relativo file .env e i file operativi iniziali."""
    cartella = os.path.join(ROOT_DIR, nome_conto)
    os.makedirs(cartella, exist_ok=True)
    
    # 1. File .env
    env_path = os.path.join(cartella, ".env")
    tipo_ig = "REAL" if tipo_conto.upper() == "REALE" else "DEMO"
    acc_id_line = f"IG_ACCOUNT_ID={ig_account_id.strip()}\n" if ig_account_id else ""
    env_content = (
        f"IG_USERNAME={ig_username.strip()}\n"
        f"IG_PASSWORD={ig_password.strip()}\n"
        f"IG_API_KEY={ig_api_key.strip()}\n"
        f"{acc_id_line}"
        f"NTFY_TOPIC=Macchinetta_Alert\n"
        f"IG_ACCOUNT_TYPE={tipo_ig}\n"
    )
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)
        
    # 2. File memoria_parametri.json se non esiste (se possibile copia template esistente es. DANY_DEMO)
    memoria_path = os.path.join(cartella, "memoria_parametri.json")
    if not os.path.exists(memoria_path):
        tpl_path = os.path.join(ROOT_DIR, "DANY_DEMO", "memoria_parametri.json")
        if not os.path.exists(tpl_path):
            tpl_path = os.path.join(ROOT_DIR, "FIORDOK_DEMO", "memoria_parametri.json")
        if os.path.exists(tpl_path):
            try:
                import shutil
                shutil.copyfile(tpl_path, memoria_path)
            except Exception:
                with open(memoria_path, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=4)
        else:
            with open(memoria_path, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=4)
            
    # 3. File storico_operazioni.csv se non esiste
    storico_path = os.path.join(cartella, "storico_operazioni.csv")
    if not os.path.exists(storico_path):
        with open(storico_path, "w", encoding="utf-8") as f:
            f.write("Data Ora,Strumento,Operazione,Profitto EUR,Deal ID\n")
            
    # 4. File console_live.log se non esiste
    console_path = os.path.join(cartella, "console_live.log")
    if not os.path.exists(console_path):
        with open(console_path, "w", encoding="utf-8") as f:
            f.write("")
            
    # 5. File stato_sistema.json se non esiste
    stato_path = os.path.join(cartella, "stato_sistema.json")
    if not os.path.exists(stato_path):
        stato_init = {
            "saldo": "0.0",
            "disponibile": "0.0",
            "margine": "0.0",
            "drawdown": "0.0",
            "messaggio": "In attesa connessione",
            "durata_sessione": "--",
            "ultimo_aggiornamento": "--",
            "prezzi_live": {},
            "distanze_minime": {}
        }
        with open(stato_path, "w", encoding="utf-8") as f:
            json.dump(stato_init, f, indent=4)
            
    return True

def crea_nuovo_conto(nome_conto, ig_username, ig_password, ig_api_key, ig_account_id="", tipo_conto="REALE", associa_a_utente=""):
    """Censisce e crea un nuovo conto IG ordinario/istituzionale con le relative credenziali e cartella."""
    nome = (nome_conto or "").strip().upper()
    if not nome:
        return False, "Nome conto non valido."
        
    tipo_up = tipo_conto.upper()
    # Se il nome non termina già con _DEMO o _REALE, lo aggiungiamo
    if not (nome.endswith("_DEMO") or nome.endswith("_REALE")):
        nome = f"{nome}_{tipo_up}"
        
    u = (ig_username or "").strip()
    p = (ig_password or "").strip()
    k = (ig_api_key or "").strip()
    acc_id = (ig_account_id or "").strip()
    
    if not (u and p and k):
        return False, "Username, Password e API Key di IG sono obbligatori."
        
    inizializza_cartella_conto(nome, u, p, k, tipo_conto=tipo_up, ig_account_id=acc_id)
    
    # Se è stato indicato un utente a cui associarlo automaticamente:
    associa_clean = (associa_a_utente or "").strip()
    if associa_clean and associa_clean != "Nessuno (Istituzionale)":
        db = _carica_db()
        if associa_clean in db:
            if "conti_autorizzati" not in db[associa_clean]:
                db[associa_clean]["conti_autorizzati"] = []
            if nome not in db[associa_clean]["conti_autorizzati"]:
                db[associa_clean]["conti_autorizzati"].append(nome)
            _salva_db(db)
            return True, f"Conto '{nome}' creato e associato automaticamente all'utente '{associa_clean}'!"
            
    return True, f"Conto '{nome}' creato con successo!"

def aggiungi_utente(username, password, ruolo="VIEWER", conti_autorizzati=None):
    if conti_autorizzati is None:
        conti_autorizzati = []
    
    if ruolo == "REGISTA":
        ruolo = "MANAGER"
    elif ruolo == "GUEST":
        ruolo = "OWNER"
        
    db = _carica_db()
    if username in db:
        return False, "Utente già esistente."
        
    db[username] = {
        "ruolo": ruolo,
        "password_hash": generate_password_hash(password),
        "tutti_i_conti": (ruolo in ["MANAGER", "REGISTA"]),
        "conti_autorizzati": conti_autorizzati
    }
    _salva_db(db)
    return True, "Utente aggiunto con successo."

def aggiungi_owner(username, credenziali_demo=None, credenziali_reale=None, password="init"):
    """Crea un utente OWNER con relative cartelle conto DEMO e/o REALE configurate."""
    username = username.strip()
    if not username:
        return False, "Nickname non valido."
    db = _carica_db()
    if username in db:
        return False, f"L'utente '{username}' esiste già."
        
    conti_autorizzati = []
    credenziali_ig = {}
    
    # Gestione Conto Demo
    if credenziali_demo and credenziali_demo.get("attivo"):
        u_demo = credenziali_demo.get("username", "").strip()
        p_demo = credenziali_demo.get("password", "").strip()
        k_demo = credenziali_demo.get("api_key", "").strip()
        if not (u_demo and p_demo and k_demo):
            return False, "Credenziali Conto Demo incomplete (Username, Password o API Key mancanti)."
        nome_demo = f"{username.upper()}_DEMO"
        inizializza_cartella_conto(nome_demo, u_demo, p_demo, k_demo, tipo_conto="DEMO")
        conti_autorizzati.append(nome_demo)
        credenziali_ig["DEMO"] = {
            "username": u_demo,
            "password": p_demo,
            "api_key": k_demo
        }
        
    # Gestione Conto Reale
    if credenziali_reale and credenziali_reale.get("attivo"):
        u_reale = credenziali_reale.get("username", "").strip()
        p_reale = credenziali_reale.get("password", "").strip()
        k_reale = credenziali_reale.get("api_key", "").strip()
        if not (u_reale and p_reale and k_reale):
            return False, "Credenziali Conto Reale incomplete (Username, Password o API Key mancanti)."
        nome_reale = f"{username.upper()}_REALE"
        inizializza_cartella_conto(nome_reale, u_reale, p_reale, k_reale, tipo_conto="REALE")
        conti_autorizzati.append(nome_reale)
        credenziali_ig["REALE"] = {
            "username": u_reale,
            "password": p_reale,
            "api_key": k_reale
        }
        
    if not conti_autorizzati:
        return False, "Devi abilitare e configurare almeno uno tra Conto DEMO o Conto REALE."
        
    db[username] = {
        "ruolo": "OWNER",
        "password_hash": generate_password_hash(password),
        "tutti_i_conti": False,
        "conti_autorizzati": conti_autorizzati,
        "credenziali_ig": credenziali_ig
    }
    _salva_db(db)
    return True, f"Utente OWNER '{username}' creato con successo (Conti: {', '.join(conti_autorizzati)})."

# Alias per retrocompatibilità
aggiungi_guest = aggiungi_owner

def aggiorna_credenziali_owner(username, tipo_conto, ig_username, ig_password, ig_api_key, attivo=True):
    """Aggiorna, abilita o disabilita le credenziali DEMO o REALE di un utente OWNER."""
    db = _carica_db()
    if username not in db:
        return False, "Utente non trovato."
    user_data = db[username]
    if user_data.get("ruolo") not in ["OWNER", "GUEST"]:
        return False, "L'utente specificato non è un OWNER."
        
    if "credenziali_ig" not in user_data:
        user_data["credenziali_ig"] = {}
    if "conti_autorizzati" not in user_data:
        user_data["conti_autorizzati"] = []
        
    tipo_up = tipo_conto.upper()
    nome_conto = f"{username.upper()}_{tipo_up}"
    
    if attivo:
        ig_username = ig_username.strip()
        ig_password = ig_password.strip()
        ig_api_key = ig_api_key.strip()
        if not (ig_username and ig_password and ig_api_key):
            return False, f"Credenziali incomplete per Conto {tipo_conto} (Username, Password o API Key vuoti)."
        inizializza_cartella_conto(nome_conto, ig_username, ig_password, ig_api_key, tipo_conto=tipo_up)
        user_data["credenziali_ig"][tipo_up] = {
            "username": ig_username,
            "password": ig_password,
            "api_key": ig_api_key
        }
        if nome_conto not in user_data["conti_autorizzati"]:
            user_data["conti_autorizzati"].append(nome_conto)
    else:
        user_data["credenziali_ig"].pop(tipo_up, None)
        if nome_conto in user_data["conti_autorizzati"]:
            user_data["conti_autorizzati"].remove(nome_conto)
            
    _salva_db(db)
    return True, f"Conto {tipo_conto} per '{username}' aggiornato con successo."

# Alias per retrocompatibilità
aggiorna_credenziali_guest = aggiorna_credenziali_owner

def modifica_password(username, nuova_password):
    db = _carica_db()
    if username not in db:
        return False, "Utente non trovato."
    
    db[username]["password_hash"] = generate_password_hash(nuova_password)
    _salva_db(db)
    return True, "Password modificata."

def aggiorna_conti_utente(username, nuovi_conti):
    db = _carica_db()
    if username not in db:
        return False, "Utente non trovato."
    
    db[username]["conti_autorizzati"] = nuovi_conti
    _salva_db(db)
    return True, "Conti aggiornati."

def elimina_utente(username):
    db = _carica_db()
    if username not in db:
        return False, "Utente non trovato."
    
    if db[username].get("ruolo") in ["MANAGER", "REGISTA"]:
        managers = [u for u, v in db.items() if v.get("ruolo") in ["MANAGER", "REGISTA"]]
        if len(managers) <= 1:
            return False, "Impossibile eliminare l'unico utente MANAGER."
            
    del db[username]
    _salva_db(db)
    return True, "Utente eliminato."

def rinomina_utente(vecchio_username, nuovo_username):
    db = _carica_db()
    if vecchio_username not in db:
        return False, "Utente non trovato."
    if not nuovo_username or not nuovo_username.strip():
        return False, "Il nuovo Nickname non può essere vuoto."
    nuovo_username = nuovo_username.strip()
    if nuovo_username == vecchio_username:
        return True, "Nessuna modifica necessaria."
    if nuovo_username in db:
        return False, f"L'utente '{nuovo_username}' esiste già."
    
    user_data = db[vecchio_username]
    
    # Se OWNER (o GUEST legacy), rinomina anche le cartelle conto
    if user_data.get("ruolo") in ["OWNER", "GUEST"]:
        vecchi_conti = list(user_data.get("conti_autorizzati", []))
        nuovi_conti = []
        for c in vecchi_conti:
            tipo = "REALE" if "_REALE" in c.upper() else "DEMO"
            nuovo_nome_conto = f"{nuovo_username.upper()}_{tipo}"
            old_dir = os.path.join(ROOT_DIR, c)
            new_dir = os.path.join(ROOT_DIR, nuovo_nome_conto)
            if os.path.exists(old_dir):
                try:
                    os.rename(old_dir, new_dir)
                except Exception as e:
                    print(f"Errore rinomina cartella {old_dir} -> {new_dir}: {e}")
            nuovi_conti.append(nuovo_nome_conto)
        user_data["conti_autorizzati"] = nuovi_conti

    nuovo_db = {}
    for k, v in db.items():
        if k == vecchio_username:
            nuovo_db[nuovo_username] = v
        else:
            nuovo_db[k] = v
    _salva_db(nuovo_db)
    return True, f"Nickname aggiornato con successo a '{nuovo_username}'."
