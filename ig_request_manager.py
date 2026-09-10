"""
Modulo Centralizzato di Gestione Chiamate IG API con Rate Limiter e Tenacity Retryer.
Protegge le chiavi API da qualsiasi blocco 403 (Rate Limit al minuto o Allowance).
"""
import time
import os
import threading
import requests
import json
from collections import deque
from tenacity import Retrying, wait_exponential, retry_if_exception_type, stop_after_attempt

class ApiExceededException(Exception):
    """Sollevata quando IG restituisce 403 o rate limit / quota ecceduta."""
    pass

class IGRateLimiter:
    """
    Gatekeeper centralizzato per prevenire tassativamente il superamento dei limiti IG.
    - Spaziatura minima ferrea di 1.5s tra chiamate consecutive.
    - Finestra mobile: massimo 22 chiamate al minuto (ampiamente sotto la soglia di 30 req/min di IG).
    - Supporta sincronizzazione cross-process tramite ledger condiviso su file.
    - Se si tenta una chiamata troppo ravvicinata o oltre soglia, il thread/processo attende LOCALMENTE
      senza mai inviare traffico ad alto rischio verso IG.
    """
    def __init__(self, min_interval=1.5, max_per_minute=22, ledger_file=".ig_rate_limit_ledger.json"):
        self.min_interval = min_interval
        self.max_per_minute = max_per_minute
        self.ledger_file = ledger_file
        self.last_call_time = 0.0
        self.call_history = deque()
        self.lock = threading.Lock()

    def _read_ledger(self):
        try:
            if os.path.exists(self.ledger_file):
                with open(self.ledger_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
        return []

    def _write_ledger(self, timestamps):
        try:
            tmp = f"{self.ledger_file}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(timestamps, f)
            os.replace(tmp, self.ledger_file)
        except Exception:
            pass

    def acquire(self):
        with self.lock:
            # Sincronizzazione con ledger su disco per coordinare più processi (Motore + Motore_Trend)
            ledger = self._read_ledger()
            now = time.time()
            
            # 1. Filtra timestamp più vecchi di 60s
            ledger = [t for t in ledger if (now - t) <= 60.0]
            
            # 2. Controllo tetto al minuto cross-process
            if len(ledger) >= self.max_per_minute:
                attesa_slot = 60.0 - (now - ledger[0]) + 0.5
                if attesa_slot > 0:
                    time.sleep(attesa_slot)
                    now = time.time()
                    ledger = [t for t in ledger if (now - t) <= 60.0]

            # 3. Spaziatura minima dall'ultima chiamata registrata
            last_recorded = max(ledger[-1] if ledger else 0.0, self.last_call_time)
            diff = now - last_recorded
            if diff < self.min_interval:
                time.sleep(self.min_interval - diff)
                now = time.time()

            self.last_call_time = now
            ledger.append(now)
            self._write_ledger(ledger[-50:])

# Istanza globale condivisa
rate_limiter = IGRateLimiter(min_interval=1.5, max_per_minute=22)

# Configura il retry con backoff esponenziale (esattamente come richiesto)
retryer = Retrying(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(ApiExceededException),
    stop=stop_after_attempt(5),
    reraise=True
)

def ig_api_request(metodo, url, headers, payload=None, timeout=10, logger_func=None):
    """
    Esegue una richiesta HTTP a IG protetta da Rate Limiter e Tenacity Retryer con Backoff Esponenziale.
    Intercetta qualsiasi codice 403 (exceeded-api-key o rate-allowance) e applica backoff automatico.
    """
    def _do_request():
        rate_limiter.acquire()
        try:
            m = metodo.upper()
            if m == 'GET':
                r = requests.get(url, headers=headers, timeout=timeout)
            elif m == 'POST':
                r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            elif m == 'DELETE':
                r = requests.delete(url, headers=headers, json=payload, timeout=timeout)
            elif m == 'PUT':
                r = requests.put(url, headers=headers, json=payload, timeout=timeout)
            else:
                r = requests.request(m, url, headers=headers, json=payload, timeout=timeout)
                
            if r.status_code == 403:
                txt = r.text.lower()
                # Se è l'allowance settimanale dei dati storici candele, non è un rate limit temporaneo
                if "historical-data-allowance" in txt:
                    if logger_func:
                        logger_func("SISTEMA", "⚠️ Quota settimanale dati storici candele esaurita su IG.")
                    return r

                # Se è rate limit o quota ecceduta (es. exceeded-api-key-allowance)
                if "exceeded" in txt or "allowance" in txt or "rate" in txt:
                    msg = "⏳ [IG RATE LIMIT 403] Rilevato limite di frequenza IG. Attivazione Tenacity Backoff Esponenziale (nessuna nuova chiave necessaria)..."
                    if logger_func:
                        logger_func("SISTEMA", msg)
                    else:
                        print(msg)
                    raise ApiExceededException(f"IG Rate Limit 403: {r.text}")
                    
            return r
        except requests.exceptions.RequestException as e:
            if logger_func:
                logger_func("SISTEMA", f"⚠️ Errore Rete IG ({metodo} {url}): {e}")
            raise

    try:
        return retryer(_do_request)
    except Exception as e:
        if logger_func:
            logger_func("SISTEMA", f"❌ Fallimento richiesta IG dopo tentativi: {e}")
        return None
