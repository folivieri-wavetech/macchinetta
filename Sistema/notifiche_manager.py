# -*- coding: utf-8 -*-
"""
Sistema/notifiche_manager.py - Guardiano Quota e Circuit Breaker per notifiche Push (ntfy.sh).
Protegge l'IP della Macchinetta da ban Fail2Ban e rate-limiting (HTTP 429).
Condiviso tra tutti i processi (Motore Range, Motore Trend, Hyper, Goldfinger, Dashboard).
"""

import os
import time
import json
import socket
import logging
from datetime import datetime, timezone, timedelta
import threading
import requests

# Disabilita IPv6 a livello di urllib3 per prevenire [Errno 101] Network is unreachable
# nei container Kubernetes configurati in IPv4 puro.
try:
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.HAS_IPV6 = False
except Exception:
    pass

logger = logging.getLogger("NotificheManager")

# --- PARAMETRI DI SICUREZZA E RATE LIMITING ---
MAX_NOTIFICHE_1MIN = 20      # Max notifiche consentite in 1 minuto (burst di trading)
MAX_NOTIFICHE_10MIN = 60    # Max notifiche consentite in 10 minuti
MAX_NOTIFICHE_24H = 200     # Max notifiche consentite nelle 24 ore

SOGLIA_RISERVA_TRADING = 15 # Se in 1 minuto ci sono >= 15 notifiche, solo i trade prioritari passano

DURATA_BLOCCO_429_SEC = 1800  # 30 minuti di stop se ntfy risponde 429 Too Many Requests
DURATA_BLOCCO_RETE_SEC = 300  # 5 minuti di stop se la rete verso ntfy fallisce

FILE_RATE_LIMITER = "notifiche_rate_limiter.json"
_LOCK_LOCALE = threading.Lock()

def now_it():
    """Ritorna datetime corrente nel fuso di Roma (UTC+1 o UTC+2)."""
    utc_now = datetime.now(timezone.utc)
    return utc_now.astimezone(timezone(timedelta(hours=2)))  # CEST (+2) o standard

def _get_shared_file_path():
    for base in ["/data/Logs_e_Cache", "../Logs_e_Cache", "Logs_e_Cache", "/data", "."]:
        if os.path.exists(base):
            return os.path.join(base, FILE_RATE_LIMITER)
    return FILE_RATE_LIMITER

def _carica_stato():
    p = _get_shared_file_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "circuit_open_until": 0,
        "circuit_reason": "",
        "cronologia_ts": [],
        "chiavi_dedup": {}
    }

def _salva_stato(stato):
    p = _get_shared_file_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    except Exception:
        pass
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(stato, f, indent=2)
    except Exception:
        pass

def invia_notifica(topic: str, titolo: str, messaggio: str, tags: str = "information_source",
                   prioritario: bool = True, prefisso_conto: str = None,
                   chiave_dedup: str = None, cooldown_dedup_sec: int = 60) -> tuple:
    """
    Invia notifica Push su ntfy.sh con:
    1. Circuit Breaker attivo (sospensione preventiva se vicini al limite).
    2. Token Bucket Rate Limiter (finestre 1 min, 10 min, 24h).
    3. Protezione 429 / Connessione (congelamento automatico).
    4. Deduplicazione intelligente (per chiave o per contenuto esatto).
    5. Prioritizzazione trade su avvisi generici.
    
    Ritorna: (success: bool, dettaglio: str)
    """
    if not topic or not str(topic).strip():
        return False, "Topic mancante"

    now = time.time()

    with _LOCK_LOCALE:
        stato = _carica_stato()

        # 1. Verifica Circuit Breaker (se il circuito è aperto per blocco 429 o errore di rete)
        blocco_fino_a = stato.get("circuit_open_until", 0)
        if now < blocco_fino_a:
            secondi_rimanenti = int(blocco_fino_a - now)
            motivo = stato.get("circuit_reason", "Circuit breaker attivo")
            return False, f"🛡️ Sospensione attiva ({motivo}). Rimanenti: {secondi_rimanenti}s"

        # 2. Pulizia finestre temporali
        cronologia = [t for t in stato.get("cronologia_ts", []) if (now - t) < 86400]
        c_1min = [t for t in cronologia if (now - t) < 60]
        c_10min = [t for t in cronologia if (now - t) < 600]

        # 3. Verifica Deduplicazione specifica
        chiavi_dedup = stato.get("chiavi_dedup", {})
        if chiave_dedup:
            last_k = chiavi_dedup.get(chiave_dedup, 0)
            if (now - last_k) < cooldown_dedup_sec:
                return False, f"Deduplicato per chiave '{chiave_dedup}' (cooldown {cooldown_dedup_sec}s)"
        else:
            # Deduplicazione automatica contenuto identico (anti-loop stretto 15s)
            h_msg = f"{titolo.strip()}|{messaggio.strip()}"
            last_h = chiavi_dedup.get(h_msg, 0)
            if (now - last_h) < 15:
                return False, "Deduplicato contenuto identico entro 15s"

        # 4. Verifica Limiti Rate Limiter
        if len(cronologia) >= MAX_NOTIFICHE_24H:
            stato["circuit_open_until"] = now + 1800
            stato["circuit_reason"] = f"Raggiunto tetto 24h ({MAX_NOTIFICHE_24H})"
            _salva_stato(stato)
            return False, f"🛡️ Tetto 24h raggiunto ({MAX_NOTIFICHE_24H}). Invio sospeso 30 min."

        if len(c_10min) >= MAX_NOTIFICHE_10MIN:
            stato["circuit_open_until"] = now + 300
            stato["circuit_reason"] = f"Raggiunto tetto 10 min ({MAX_NOTIFICHE_10MIN})"
            _salva_stato(stato)
            return False, f"🛡️ Tetto 10 min raggiunto ({MAX_NOTIFICHE_10MIN}). Invio sospeso 5 min."

        # Riserva per trade prioritari
        if len(c_1min) >= SOGLIA_RISERVA_TRADING and not prioritario:
            return False, f"🛡️ Quota 1 min quasi satura ({len(c_1min)}/{MAX_NOTIFICHE_1MIN}). Notifica non prioritaria soppressa."

        if len(c_1min) >= MAX_NOTIFICHE_1MIN:
            stato["circuit_open_until"] = now + 60
            stato["circuit_reason"] = f"Raggiunto tetto 1 min ({MAX_NOTIFICHE_1MIN})"
            _salva_stato(stato)
            return False, f"🛡️ Tetto 1 min raggiunto ({MAX_NOTIFICHE_1MIN}). Invio sospeso 1 min."

        # 5. Registra preventivamente timestamp per race condition
        cronologia.append(now)
        stato["cronologia_ts"] = cronologia
        if chiave_dedup:
            chiavi_dedup[chiave_dedup] = now
        chiavi_dedup[f"{titolo.strip()}|{messaggio.strip()}"] = now
        # Pulisci chiavi vecchie
        stato["chiavi_dedup"] = {k: v for k, v in chiavi_dedup.items() if (now - v) < 86400}
        _salva_stato(stato)

    # 6. Preparazione ed esecuzione HTTP POST
    try:
        orario = now_it().strftime("%H:%M:%S")
        body = f"[{orario}] {messaggio}"
        titolo_completo = f"[{prefisso_conto}] {titolo}" if prefisso_conto else titolo
        headers = {
            "Title": titolo_completo.encode('utf-8'),
            "Tags": tags
        }
        res = requests.post(f"https://ntfy.sh/{topic}", data=body.encode('utf-8'), headers=headers, timeout=5)

        if res.status_code == 200:
            return True, "Inviata con successo"
        elif res.status_code == 429:
            with _LOCK_LOCALE:
                stato = _carica_stato()
                stato["circuit_open_until"] = time.time() + DURATA_BLOCCO_429_SEC
                stato["circuit_reason"] = "HTTP 429 Too Many Requests da ntfy.sh"
                _salva_stato(stato)
            logger.warning(f"🚨 [CIRCUIT BREAKER] Ricevuto HTTP 429 da ntfy.sh! Notifiche congelate per {DURATA_BLOCCO_429_SEC//60} min.")
            return False, "HTTP 429 Too Many Requests"
        else:
            return False, f"HTTP Error {res.status_code}"

    except Exception as e:
        err_str = str(e)
        # Se errore di rete / connection refused / timeout
        with _LOCK_LOCALE:
            stato = _carica_stato()
            stato["circuit_open_until"] = time.time() + DURATA_BLOCCO_RETE_SEC
            stato["circuit_reason"] = f"Errore di connessione: {err_str[:40]}"
            _salva_stato(stato)
        logger.warning(f"⚠️ [CIRCUIT BREAKER] Errore connessione ntfy ({err_str[:50]}). Circuit breaker aperto per {DURATA_BLOCCO_RETE_SEC//60} min.")
        return False, f"Errore connessione: {err_str}"
