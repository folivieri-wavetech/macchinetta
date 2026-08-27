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
        # Se non esiste, creo il database iniziale con l'utente "Regista" derivato dall'ambiente
        utente_default = os.getenv("DASHBOARD_USER", "Marco")
        password_default = os.getenv("DASHBOARD_PASSWORD", "Bolzano&1971")
        
        db = {
            utente_default: {
                "ruolo": "REGISTA",
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
            return json.load(f)
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
            return {
                "success": True,
                "ruolo": user_data.get("ruolo", "VIEWER"),
                "tutti_i_conti": user_data.get("tutti_i_conti", False),
                "conti_autorizzati": user_data.get("conti_autorizzati", [])
            }
    return {"success": False}

def get_tutti_utenti():
    db = _carica_db()
    utenti_safe = {}
    for k, v in db.items():
        utenti_safe[k] = {
            "ruolo": v.get("ruolo", "VIEWER"),
            "tutti_i_conti": v.get("tutti_i_conti", False),
            "conti_autorizzati": v.get("conti_autorizzati", [])
        }
    return utenti_safe

def aggiungi_utente(username, password, ruolo="VIEWER", conti_autorizzati=None):
    if conti_autorizzati is None:
        conti_autorizzati = []
    
    db = _carica_db()
    if username in db:
        return False, "Utente già esistente."
        
    db[username] = {
        "ruolo": ruolo,
        "password_hash": generate_password_hash(password),
        "tutti_i_conti": (ruolo == "REGISTA"),
        "conti_autorizzati": conti_autorizzati
    }
    _salva_db(db)
    return True, "Utente aggiunto con successo."

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
    
    if db[username].get("ruolo") == "REGISTA":
        # Evita di eliminare l'ultimo regista
        registi = [u for u, v in db.items() if v.get("ruolo") == "REGISTA"]
        if len(registi) <= 1:
            return False, "Impossibile eliminare l'unico utente REGISTA."
            
    del db[username]
    _salva_db(db)
    return True, "Utente eliminato."
