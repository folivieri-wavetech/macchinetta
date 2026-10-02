import os
import time
import json
import logging
import threading
import datetime
import requests

try:
    from zoneinfo import ZoneInfo
    TZ_ITALIA = ZoneInfo("Europe/Rome")
except Exception:
    from datetime import timezone, timedelta
    TZ_ITALIA = timezone(timedelta(hours=2))

def now_it():
    return datetime.datetime.now(TZ_ITALIA)

logger = logging.getLogger("HyperOrderManager")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [HYPER_ORDER] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
GOLD_CURRENCY = "EUR"

class HyperOrderManager:
    _instances = {}
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, account_dir: str = "DANY_DEMO"):
        with cls._lock:
            if not account_dir:
                account_dir = "DANY_DEMO"
            if account_dir not in cls._instances:
                cls._instances[account_dir] = cls(account_dir)
            return cls._instances[account_dir]

    def __init__(self, account_dir: str):
        self.account_dir = account_dir
        self.lock = threading.RLock()
        self.last_request_time = 0.0
        self.min_order_interval_sec = 1.5  # Minimo 1.5 secondi di sicurezza tra ordini successivi verso IG

        # Credenziali e sessione IG
        self.is_real = "_REALE" in account_dir.upper()
        self.base_url = "https://api.ig.com/gateway/deal" if self.is_real else "https://demo-api.ig.com/gateway/deal"
        self.cst = None
        self.xst = None
        self.api_key = None
        self.session_time = 0.0

        # Micro-cache posizioni per prevenire HTTP 403 (Rate Limit / Allowance Overflow)
        self._positions_cache = None
        self._positions_cache_time = 0.0

        # File storico eseguiti per questo conto
        self.history_file = os.path.join(self.account_dir, "hyper_trades_history.json")
        if not os.path.exists(self.account_dir):
            try:
                os.makedirs(self.account_dir, exist_ok=True)
            except Exception:
                pass

        # Inizializza sessione IG
        self._ensure_session()

    def _get_credentials_from_env(self):
        user, pwd, api_key = None, None, None
        candidates = [
            os.path.join(self.account_dir, ".env"),
            os.path.join("DANY_DEMO", ".env"),
            os.path.join("FIORDOK_DEMO", ".env"),
            ".env"
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("IG_USERNAME="): user = line.split("=", 1)[1].strip()
                            elif line.startswith("IG_PASSWORD="): pwd = line.split("=", 1)[1].strip()
                            elif line.startswith("IG_API_KEY="): api_key = line.split("=", 1)[1].strip()
                    if user and pwd and api_key:
                        break
                except Exception:
                    pass
        return user, pwd, api_key

    def _get_ntfy_topic(self) -> str:
        """Recupera il topic NTFY dalle variabili d'ambiente (Kubernetes Secret) o dai file .env."""
        topic = os.environ.get("NTFY_TOPIC")
        if topic:
            return topic.strip()
        candidates = [
            os.path.join(self.account_dir, ".env"),
            os.path.join("DANY_DEMO", ".env"),
            os.path.join("FIORDOK_DEMO", ".env"),
            os.path.join("BONGIOLO_DEMO", ".env"),
            ".env"
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("NTFY_TOPIC="):
                                t = line.split("=", 1)[1].strip().strip('"').strip("'")
                                if t:
                                    return t
                except Exception:
                    pass
        return None

    def send_notification(self, titolo: str, messaggio: str, tags: str = "rotating_light", cooldown_identico_sec: int = 60, max_notifiche_minuto: int = 20):
        """Invia notifica push su ntfy.sh con Circuit Breaker e Rate Limiter integrati."""
        topic = self._get_ntfy_topic()
        if not topic:
            return

        try:
            from Sistema.notifiche_manager import invia_notifica as invia_notifica_centralizzata
            ok, dett = invia_notifica_centralizzata(
                topic=topic,
                titolo=titolo,
                messaggio=messaggio,
                tags=tags,
                prioritario=True,
                prefisso_conto=self.account_dir,
                cooldown_dedup_sec=cooldown_identico_sec
            )
            if not ok and "Sospensione attiva" in dett:
                logger.warning(f"🛡️ [CIRCUIT BREAKER HYPER] {dett}")
            return
        except Exception:
            pass

        # Fallback locale
        now = time.time()
        if not hasattr(self, "_registro_notifiche"):
            self._registro_notifiche = {}
            self._finestra_notifiche = []

        chiave = (str(titolo).strip(), str(messaggio).strip())
        if (now - self._registro_notifiche.get(chiave, 0)) < cooldown_identico_sec:
            return

        self._finestra_notifiche = [t for t in self._finestra_notifiche if (now - t) < 60]
        if len(self._finestra_notifiche) >= max_notifiche_minuto:
            logger.warning(f"🛡️ [ANTI-FLOOD HYPER] Limite notifiche raggiunto. Soppressa: {titolo}")
            return

        self._registro_notifiche[chiave] = now
        self._finestra_notifiche.append(now)

        try:
            orario = now_it().strftime("%H:%M:%S")
            headers = {"Title": f"[{self.account_dir}] {titolo}".encode('utf-8'), "Tags": tags}
            requests.post(f"https://ntfy.sh/{topic}", data=f"[{orario}] {messaggio}".encode('utf-8'), headers=headers, timeout=5)
        except Exception as e:
            logger.warning(f"⚠️ Errore invio notifica Push NTFY: {e}")

    def _ensure_session(self) -> bool:
        """Verifica o rinnova la sessione REST IG (CST e X-SECURITY-TOKEN)."""
        now = time.time()
        # Se abbiamo token validi da meno di 10 minuti, riutilizzali
        if self.cst and self.xst and self.api_key and (now - self.session_time) < 600:
            return True

        # Tentativo di lettura da token_ig.json salvato da Motore
        tok_file = os.path.join(self.account_dir, "token_ig.json")
        user, pwd, api_key = self._get_credentials_from_env()
        self.api_key = api_key

        if os.path.exists(tok_file):
            try:
                with open(tok_file, "r", encoding="utf-8") as f:
                    tok_d = json.load(f)
                    cst_test = tok_d.get("CST")
                    xst_test = tok_d.get("X-SECURITY-TOKEN")
                    if cst_test and xst_test and self.api_key:
                        # Test rapido validità token
                        h_test = {
                            "X-IG-API-KEY": self.api_key,
                            "CST": cst_test,
                            "X-SECURITY-TOKEN": xst_test,
                            "Version": "1"
                        }
                        r_test = requests.get(f"{self.base_url}/accounts", headers=h_test, timeout=6)
                        if r_test.status_code == 200:
                            self.cst = cst_test
                            self.xst = xst_test
                            self.session_time = now
                            return True
            except Exception:
                pass

        # Login esplicito tramite session endpoint
        if not user or not pwd or not self.api_key:
            logger.error(f"Impossibile effettuare login IG per {self.account_dir}: credenziali mancanti in .env")
            return False

        try:
            url_sess = f"{self.base_url}/session"
            h_login = {
                "X-IG-API-KEY": self.api_key,
                "Version": "2",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            body = {"identifier": user, "password": pwd}
            r = requests.post(url_sess, headers=h_login, json=body, timeout=10)
            if r.status_code == 200:
                self.cst = r.headers.get("CST")
                self.xst = r.headers.get("X-SECURITY-TOKEN")
                self.session_time = now
                logger.info(f"✅ Sessione IG rinnovata con successo per {self.account_dir}")

                # Salva token_ig.json per allineamento
                try:
                    with open(tok_file, "w", encoding="utf-8") as f:
                        json.dump({"CST": self.cst, "X-SECURITY-TOKEN": self.xst}, f)
                except Exception:
                    pass
                return True
            else:
                logger.error(f"Errore Login IG {self.account_dir}: HTTP {r.status_code} - {r.text}")
                return False
        except Exception as e:
            logger.error(f"Eccezione Login IG {self.account_dir}: {e}")
            return False

    def _throttle(self):
        """Garantisce un intervallo minimo di sicurezza di 1.5 secondi tra chiamate operative consecutive a IG."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_order_interval_sec:
            time.sleep(self.min_order_interval_sec - elapsed)
        self.last_request_time = time.time()

    def _get_headers(self, version="2"):
        return {
            "X-IG-API-KEY": self.api_key,
            "CST": self.cst,
            "X-SECURITY-TOKEN": self.xst,
            "Version": str(version),
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json; charset=UTF-8"
        }

    def verify_deal_confirm(self, deal_ref: str, max_attempts: int = 8):
        """Verifica la conferma dell'ordine tramite /confirms/{dealReference} con pause rilassate."""
        if not deal_ref:
            return False, {}

        h = self._get_headers(version="1")
        for attempt in range(1, max_attempts + 1):
            time.sleep(1.5)  # Pausa precauzionale per consentire a IG di finalizzare l'eseguito senza stress
            try:
                r = requests.get(f"{self.base_url}/confirms/{deal_ref}", headers=h, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    status = data.get("dealStatus")
                    if status == "ACCEPTED":
                        return True, data
                    elif status == "REJECTED":
                        reason = data.get("reason", "UNKNOWN_REJECT")
                        logger.warning(f"❌ Deal {deal_ref} RIFIUTATO da IG: {reason}")
                        return False, data
                elif r.status_code == 401:
                    # Token scaduto, prova a rinnovare e riprova
                    self._ensure_session()
                    h = self._get_headers(version="1")
            except Exception as e:
                logger.warning(f"Verifica conferma deal {deal_ref} tentativo {attempt}: {e}")
        return False, {"reason": "TIMEOUT_CONFERMA"}

    def open_market_deal(self, direction: str, size: float, limit_level: float = None, stop_level: float = None, label: str = "Core", epic: str = None, currency: str = None) -> dict:
        """Apre un ordine a mercato su IG (Gold, US500, ecc.) con rispetto delle tempistiche IG e ritorno dei dati effettivi."""
        with self.lock:
            self._throttle()
            if not self._ensure_session():
                return {"success": False, "reason": "ERRORE_SESSIONE_IG"}

            target_epic = epic or EPIC_GOLD
            target_curr = currency or GOLD_CURRENCY
            dir_str = "BUY" if direction.upper() in ("BUY", "LONG") else "SELL"
            size_val = int(size) if float(size).is_integer() else float(size)
            size_str = str(size_val)

            payload = {
                "epic": target_epic,
                "expiry": "-",
                "direction": dir_str,
                "size": size_str,
                "orderType": "MARKET",
                "timeInForce": "EXECUTE_AND_ELIMINATE",
                "guaranteedStop": False,
                "forceOpen": True,
                "currencyCode": target_curr
            }

            if limit_level is not None:
                payload["limitLevel"] = f"{float(limit_level):.2f}"
            if stop_level is not None:
                payload["stopLevel"] = f"{float(stop_level):.2f}"

            logger.info(f"📤 Invio ordine a mercato IG ({label}): {dir_str} {size_str} contratti su {target_epic} (TP: {limit_level}, SL: {stop_level})")

            try:
                h = self._get_headers(version="2")
                r = requests.post(f"{self.base_url}/positions/otc", headers=h, json=payload, timeout=10)
                if r.status_code == 401:
                    # Rinnova sessione e ritenta una volta
                    self._ensure_session()
                    h = self._get_headers(version="2")
                    r = requests.post(f"{self.base_url}/positions/otc", headers=h, json=payload, timeout=10)

                if r.status_code == 200:
                    deal_ref = r.json().get("dealReference")
                    if deal_ref:
                        ok, conf_data = self.verify_deal_confirm(deal_ref)
                        if ok:
                            self._positions_cache_time = 0.0
                            deal_id = conf_data.get("dealId")
                            exec_lvl = float(conf_data.get("level") or 0.0)
                            logger.info(f"✅ Ordine IG ({label}) ESEGUITO! Deal ID: {deal_id}, Livello: {exec_lvl:.2f} €")
                            return {
                                "success": True,
                                "deal_id": deal_id,
                                "deal_reference": deal_ref,
                                "level": exec_lvl,
                                "direction": dir_str,
                                "size": size_val,
                                "label": label,
                                "time": now_it().strftime("%Y-%m-%d %H:%M:%S")
                            }
                        else:
                            reason = conf_data.get("reason", "UNKNOWN_REJECT")
                            # Se rifiutato per TP/SL troppo vicini (ATTACHED_ORDER_LEVEL_ERROR), ritenta subito senza TP/SL
                            if ("ATTACHED" in str(reason).upper() or "LEVEL_ERROR" in str(reason).upper()) and (limit_level or stop_level):
                                logger.warning(f"🔄 TP/SL agganciato rifiutato ({reason}). Ritento apertura pulita senza TP/SL...")
                                payload.pop("limitLevel", None)
                                payload.pop("stopLevel", None)
                                self._throttle()
                                r_retry = requests.post(f"{self.base_url}/positions/otc", headers=h, json=payload, timeout=10)
                                if r_retry.status_code == 200:
                                    dref2 = r_retry.json().get("dealReference")
                                    ok2, conf2 = self.verify_deal_confirm(dref2)
                                    if ok2:
                                        self._positions_cache_time = 0.0
                                        deal_id2 = conf2.get("dealId")
                                        exec_lvl2 = float(conf2.get("level") or 0.0)
                                        return {
                                            "success": True,
                                            "deal_id": deal_id2,
                                            "deal_reference": dref2,
                                            "level": exec_lvl2,
                                            "direction": dir_str,
                                            "size": size_val,
                                            "label": label,
                                            "time": now_it().strftime("%Y-%m-%d %H:%M:%S")
                                        }
                            self.send_notification(f"⚠️ RIFIUTO ORDINE: {label}", f"Ordine {dir_str} {size_str}c su {target_epic} rifiutato da IG: {reason}", "warning")
                            return {"success": False, "reason": reason}
                    else:
                        self.send_notification(f"⚠️ ERRORE ORDINE: {label}", f"Nessun Deal Reference da IG per {label}", "warning")
                        return {"success": False, "reason": "NO_DEAL_REFERENCE"}
                else:
                    err_msg = r.text
                    logger.error(f"❌ Errore apertura posizione IG ({label}): HTTP {r.status_code} - {err_msg}")
                    self.send_notification(f"⚠️ ERRORE IG: {label}", f"HTTP {r.status_code}: {err_msg[:100]}", "warning")
                    return {"success": False, "reason": f"HTTP_{r.status_code}: {err_msg}"}
            except Exception as e:
                logger.error(f"❌ Eccezione apertura posizione IG ({label}): {e}")
                self.send_notification(f"⚠️ ECCEZIONE IG: {label}", f"Errore apertura: {str(e)[:100]}", "warning")
                return {"success": False, "reason": str(e)}

    def is_deal_open(self, deal_id: str) -> bool:
        """Verifica se un dealId è effettivamente ancora aperto su IG."""
        if not deal_id:
            return False
        positions = self.get_open_positions()
        if positions is None:
            # Chiamata IG fallita (403, timeout, rete): per prudenza non consideriamo la posizione chiusa
            logger.warning(f"⚠️ [ANTI-HEDGING] Impossibile verificare deal {deal_id} su IG (errore API). Trattato prudenzialmente come APERTO.")
            return True
        return any(p.get("position", {}).get("dealId") == deal_id for p in positions)

    def get_open_positions(self, epic: str = None, force_refresh: bool = False):
        """Restituisce la lista reale delle posizioni aperte su IG dal vivo, opzionalmente filtrate per epic o strumento.
        Usa una micro-cache di 2.0 secondi per evitare di saturare la quota API di IG (HTTP 403 Allowance Overflow).
        Ritorna None se la chiamata HTTP/API fallisce (per evitare falsi FLAT e conseguente hedging), altrimenti la lista."""
        now = time.time()
        if not force_refresh and self._positions_cache is not None and (now - self._positions_cache_time) < 2.0:
            positions = self._positions_cache
        else:
            try:
                h = self._get_headers(version="2")
                r = requests.get(f"{self.base_url}/positions", headers=h, timeout=6)
                if r.status_code == 200:
                    positions = r.json().get("positions", [])
                    self._positions_cache = positions
                    self._positions_cache_time = now
                else:
                    logger.warning(f"⚠️ get_open_positions fallita (HTTP {r.status_code}): {r.text[:120]}")
                    return None
            except Exception as e:
                logger.warning(f"⚠️ Errore get_open_positions: {e}")
                return None

        if epic:
            ep_u = str(epic).upper()
            filtered = []
            for p in positions:
                p_epic = str(p.get("market", {}).get("epic", "")).upper()
                p_name = str(p.get("market", {}).get("instrumentName", "")).upper()
                if ep_u in p_epic or p_epic in ep_u or ("GOLD" in ep_u and "GOLD" in p_name) or ("US500" in ep_u and "US 500" in p_name) or ("SPTRD" in ep_u and "SPTRD" in p_epic):
                    filtered.append(p)
            return filtered
        return positions

    def close_market_deal(self, deal_id: str, direction_open: str, size: float, label: str = "Chiusura", reason_note: str = "") -> dict:
        """Chiude a mercato una posizione aperta su IG tramite DELETE /positions/otc con verifica conferma."""
        if not deal_id:
            return {"success": False, "reason": "MISSING_DEAL_ID"}

        with self.lock:
            self._throttle()
            if not self._ensure_session():
                self.send_notification(f"⚠️ ERRORE SESSIONE: {label}", "Sessione IG non valida durante chiusura", "warning")
                return {"success": False, "reason": "ERRORE_SESSIONE_IG"}

            # Direzione opposta a quella di apertura
            dir_close = "SELL" if direction_open.upper() in ("BUY", "LONG") else "BUY"
            size_val = int(size) if float(size).is_integer() else float(size)
            size_str = str(size_val)

            payload = {
                "dealId": deal_id,
                "direction": dir_close,
                "size": size_str,
                "orderType": "MARKET"
            }

            h = self._get_headers(version="1")
            h["_method"] = "DELETE"

            logger.info(f"📤 Invio richiesta chiusura IG ({label}): Deal {deal_id} ({dir_close} {size_str}c) - Motivo: {reason_note}")

            try:
                r = requests.post(f"{self.base_url}/positions/otc", headers=h, json=payload, timeout=10)
                if r.status_code == 401:
                    self._ensure_session()
                    h = self._get_headers(version="1")
                    h["_method"] = "DELETE"
                    r = requests.post(f"{self.base_url}/positions/otc", headers=h, json=payload, timeout=10)

                if r.status_code == 200:
                    deal_ref = r.json().get("dealReference")
                    if deal_ref:
                        ok, conf_data = self.verify_deal_confirm(deal_ref)
                        if ok:
                            self._positions_cache_time = 0.0
                            close_lvl = float(conf_data.get("level") or 0.0)
                            profit = float(conf_data.get("profit") or 0.0)
                            logger.info(f"✅ Chiusura IG completata per {deal_id}! Livello: {close_lvl:.2f} €, P&L: {profit:+.2f} €")
                            return {
                                "success": True,
                                "deal_id": deal_id,
                                "close_level": close_lvl,
                                "profit": profit,
                                "label": label,
                                "reason": reason_note,
                                "time": now_it().strftime("%Y-%m-%d %H:%M:%S")
                            }
                        else:
                            rej_reason = conf_data.get("reason", "UNKNOWN_REJECT")
                            rej_upper = str(rej_reason).upper()
                            # Se la posizione non esiste più, è già stata chiusa (es. per TP già toccato)
                            if any(k in rej_upper for k in ("POSITION_NOT_FOUND", "ALREADY_CLOSED", "NOT_AVAILABLE", "ORDER_NOT_FOUND")):
                                logger.info(f"ℹ️ Posizione IG {deal_id} già chiusa su IG ({rej_reason}).")
                                return {"success": True, "deal_id": deal_id, "close_level": 0.0, "profit": 0.0, "already_closed": True}

                            # Verifica immediata su IG: se non è più tra le posizioni aperte, è già stata chiusa dal TP nativo
                            if not self.is_deal_open(deal_id):
                                logger.info(f"ℹ️ Posizione IG {deal_id} non più aperta su IG (già eseguita da TP/SL nativo IG). Nessun allarme.")
                                return {"success": True, "deal_id": deal_id, "close_level": 0.0, "profit": 0.0, "already_closed": True}

                            self.send_notification(f"⚠️ RIFIUTO CHIUSURA: {label}", f"Posizione ({dir_close} {size_str}c) rifiutata: {rej_reason}", "warning")
                            return {"success": False, "reason": rej_reason}
                    else:
                        return {"success": False, "reason": "NO_DEAL_REFERENCE"}
                else:
                    err_txt = r.text
                    err_upper = err_txt.upper()
                    if any(k in err_upper for k in ("POSITION_NOT_FOUND", "DEAL-NOT-FOUND", "ALREADY_CLOSED", "NOT_AVAILABLE")):
                        logger.info(f"ℹ️ Posizione IG {deal_id} già chiusa precedentemente.")
                        return {"success": True, "deal_id": deal_id, "already_closed": True}
                    if not self.is_deal_open(deal_id):
                        logger.info(f"ℹ️ Posizione IG {deal_id} non più aperta su IG (già chiusa da TP/SL).")
                        return {"success": True, "deal_id": deal_id, "already_closed": True}
                    logger.error(f"❌ Errore chiusura IG {deal_id}: HTTP {r.status_code} - {err_txt}")
                    self.send_notification(f"⚠️ ERRORE CHIUSURA: {label}", f"HTTP {r.status_code}: {err_txt[:100]}", "warning")
                    return {"success": False, "reason": f"HTTP_{r.status_code}: {err_txt}"}
            except Exception as e:
                logger.error(f"❌ Eccezione chiusura IG {deal_id}: {e}")
                if not self.is_deal_open(deal_id):
                    logger.info(f"ℹ️ Posizione IG {deal_id} non più aperta dopo eccezione (già chiusa).")
                    return {"success": True, "deal_id": deal_id, "already_closed": True}
                self.send_notification(f"⚠️ ECCEZIONE CHIUSURA: {label}", f"Errore chiusura: {str(e)[:100]}", "warning")
    def remove_limit_order(self, deal_id: str, label: str = "Rimozione TP") -> bool:
        """Invia una richiesta PUT a IG per rimuovere il Limit Order (Take Profit) da una posizione aperta,
        trasformando il deal in posizione a corsa libera con Trailing Stop."""
        if not deal_id:
            return False
        with self.lock:
            self._throttle()
            if not self._ensure_session():
                logger.warning(f"⚠️ Impossibile rimuovere TP per {deal_id}: sessione IG non valida.")
                return False
            url = f"{self.base_url}/positions/otc/{deal_id}"
            payload = {
                "limitLevel": None,
                "trailingStop": False
            }
            h = self._get_headers(version="2")
            try:
                r = requests.put(url, headers=h, json=payload, timeout=10)
                if r.status_code == 401:
                    self._ensure_session()
                    h = self._get_headers(version="2")
                    r = requests.put(url, headers=h, json=payload, timeout=10)
                if r.status_code == 200:
                    logger.info(f"🚀 [IG TP RIMOSSO] Deal {deal_id} ({label}): Take Profit eliminato su IG con successo! Posizione libera per Trailing Stop.")
                    return True
                else:
                    logger.warning(f"⚠️ [IG TP INFO] Rimozione TP per {deal_id} non riuscita (HTTP {r.status_code}): {r.text[:120]}")
                    return False
            except Exception as e:
                logger.error(f"❌ Eccezione remove_limit_order {deal_id}: {e}")
                return False

    def set_limit_order(self, deal_id: str, limit_level: float, label: str = "Imposta TP") -> bool:
        """Invia una richiesta PUT a IG per impostare/ripristinare il Limit Order (Take Profit) su una posizione aperta."""
        if not deal_id or limit_level is None:
            return False
        with self.lock:
            self._throttle()
            if not self._ensure_session():
                logger.warning(f"⚠️ Impossibile impostare TP per {deal_id}: sessione IG non valida.")
                return False
            url = f"{self.base_url}/positions/otc/{deal_id}"
            payload = {
                "limitLevel": round(float(limit_level), 2),
                "trailingStop": False
            }
            h = self._get_headers(version="2")
            try:
                r = requests.put(url, headers=h, json=payload, timeout=10)
                if r.status_code == 401:
                    self._ensure_session()
                    h = self._get_headers(version="2")
                    r = requests.put(url, headers=h, json=payload, timeout=10)
                if r.status_code == 200:
                    logger.info(f"🎯 [IG TP IMPOSTATO] Deal {deal_id} ({label}): Take Profit fissato su IG a {limit_level:.2f} con successo!")
                    return True
                else:
                    logger.warning(f"⚠️ [IG TP INFO] Impostazione TP per {deal_id} non riuscita (HTTP {r.status_code}): {r.text[:120]}")
                    return False
            except Exception as e:
                logger.error(f"❌ Eccezione set_limit_order {deal_id}: {e}")
                return False

    def set_stop_loss_order(self, deal_id: str, stop_level: float, label: str = "Aggiorna SL", limit_level: float = None) -> bool:
        """Invia una richiesta PUT a IG per aggiornare lo Stop Loss su una posizione aperta (Breakeven o Trailing Stop)."""
        if not deal_id or stop_level is None:
            return False
        with self.lock:
            self._throttle()
            if not self._ensure_session():
                logger.warning(f"⚠️ Impossibile aggiornare SL per {deal_id}: sessione IG non valida.")
                return False
            url = f"{self.base_url}/positions/otc/{deal_id}"
            payload = {
                "stopLevel": round(float(stop_level), 2),
                "trailingStop": False
            }
            if limit_level is not None:
                payload["limitLevel"] = round(float(limit_level), 2)
            h = self._get_headers(version="2")
            try:
                r = requests.put(url, headers=h, json=payload, timeout=10)
                if r.status_code == 401:
                    self._ensure_session()
                    h = self._get_headers(version="2")
                    r = requests.put(url, headers=h, json=payload, timeout=10)
                if r.status_code == 200:
                    logger.info(f"🛡️ [IG SL AGGIORNATO] Deal {deal_id} ({label}): Stop Loss fissato su IG a {stop_level:.2f} con successo!")
                    return True
                else:
                    logger.warning(f"⚠️ [IG SL INFO] Aggiornamento SL per {deal_id} non riuscito (HTTP {r.status_code}): {r.text[:120]}")
                    return False
            except Exception as e:
                logger.error(f"❌ Eccezione set_stop_loss_order {deal_id}: {e}")
                return False

    def record_closed_trade(self, tf: str, direction: str, contracts: float, open_price: float, close_price: float, pnl_eur: float, deal_id: str, reason: str, time_open: str = "", label: str = "", epic: str = ""):
        """Salva in modo persistente l'operazione conclusa in hyper_trades_history.json."""
        with self.lock:
            try:
                now_str = now_it().strftime("%Y-%m-%d %H:%M:%S")
                ep_upper = (epic or "").upper()
                lbl_upper = (label or "").upper()
                rsn_upper = (reason or "").upper()

                # Identificazione 100% deterministica tramite EPIC (e fallback solo su label/reason se epic assente)
                # ZERO confronti di prezzo.
                if any(k in ep_upper for k in ("CFEGOLD", "CFDGOLD", "GOLD")) or "GOLD" in lbl_upper or "ORO" in lbl_upper:
                    target_epic = epic or EPIC_GOLD
                elif "SPTRD" in ep_upper or "US500" in ep_upper or "SPX" in ep_upper or "US500" in lbl_upper or "US500" in rsn_upper:
                    target_epic = epic or "IX.D.SPTRD.IBE.IP"
                else:
                    target_epic = epic or EPIC_GOLD

                trade_item = {
                    "id": str(int(time.time() * 1000)),
                    "time_open": time_open or now_str,
                    "time_close": now_str,
                    "tf": tf,
                    "epic": target_epic,
                    "direction": direction,
                    "contracts": contracts,
                    "open_price": round(open_price, 2) if open_price else 0.0,
                    "close_price": round(close_price, 2) if close_price else 0.0,
                    "pips": round((close_price - open_price) if direction == "LONG" else (open_price - close_price), 2) if (open_price and close_price) else 0.0,
                    "pnl_eur": round(pnl_eur, 2),
                    "deal_id": deal_id or "--",
                    "label": label or tf,
                    "reason": reason or "Chiusura a mercato"
                }

                history = self.get_trades_history()
                if deal_id and deal_id != "--":
                    history = [h for h in history if h.get("deal_id") != deal_id]
                history.insert(0, trade_item)
                # Mantieni ultimi 1000 trade
                history = history[:1000]

                with open(self.history_file, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2)
            except Exception as e:
                logger.error(f"Errore salvataggio trade history in {self.history_file}: {e}")

    def _reconcile_from_engines_state(self, current_history: list) -> tuple[list, bool]:
        """Riconciliazione automatica trasparente (Self-Healing):
        Se un trade con esito CLOSE è presente nello stato locale di un motore M5
        (hyper_gold_m5_state.json o hyper_us500_m5_state.json) ma non è in hyper_trades_history.json,
        viene importato istantaneamente con attribuzione certa dello strumento."""
        import re
        modified = False
        known_deals = set()
        known_daily_pnl = set()
        for t in current_history:
            d_id = t.get("deal_id")
            if d_id and d_id != "--":
                known_deals.add(d_id)
            tc = str(t.get("time_close", ""))
            day_str = tc[:10]
            ep = str(t.get("epic", "")).upper()
            ep_key = "US500" if ("SPTRD" in ep or "US500" in ep) else "GOLD"
            pnl_val = round(float(t.get("pnl_eur", 0.0) or 0.0), 2)
            known_daily_pnl.add((ep_key, day_str, pnl_val))

        now_str = now_it().strftime("%Y-%m-%d %H:%M:%S")
        today_date = now_str[:10]

        # 1. Controllo Spot Gold M5
        gold_state_file = os.path.join(self.account_dir, "hyper_gold_m5_state.json")
        if os.path.exists(gold_state_file):
            try:
                with open(gold_state_file, "r", encoding="utf-8") as gf:
                    g_data = json.load(gf)
                    for t in g_data.get("trades", []):
                        act = str(t.get("action", ""))
                        if "CLOSE" in act:
                            rsn = str(t.get("reason", ""))
                            # Cerca eventuale Deal ID
                            m_deal = re.search(r"Deal\s+([A-Z0-9]+)", rsn) or re.search(r"\b(DIAAA[A-Z0-9]+)\b", rsn)
                            deal_id = m_deal.group(1) if m_deal else "--"
                            if deal_id != "--" and deal_id in known_deals:
                                continue

                            pnl_eur = float(t.get("pnl") or 0.0)
                            pnl_key = round(pnl_eur, 2)
                            time_val = str(t.get("time", ""))
                            time_close = f"{today_date} {time_val}" if (len(time_val) <= 8 and ":" in time_val) else (time_val or now_str)
                            day_key = time_close[:10]

                            if deal_id == "--" and ("GOLD", day_key, pnl_key) in known_daily_pnl:
                                continue

                            direction = "LONG" if "LONG" in act else ("SHORT" if "SHORT" in act else "LONG")
                            open_px = float(t.get("open_price") or 0.0)
                            close_px = float(t.get("close_price") or 0.0)
                            contracts = float(t.get("contracts") or 5.0)

                            # Modalità incremento o core
                            lbl = "Spot Gold 5M"
                            if "INC" in act:
                                mode = "RUNNER" if "RUNNER" in act else "BANCOMAT"
                                lbl = f"Inc {mode} Spot Gold 5M"
                            elif "CORE" in act:
                                lbl = "Core Spot Gold 5M"

                            trade_recovered = {
                                "id": str(int(time.time() * 1000)),
                                "time_open": time_close,
                                "time_close": time_close,
                                "tf": "5M",
                                "epic": EPIC_GOLD,
                                "direction": direction,
                                "contracts": contracts,
                                "open_price": round(open_px, 2),
                                "close_price": round(close_px, 2),
                                "pips": round((close_px - open_px) if direction == "LONG" else (open_px - close_px), 2) if (open_px and close_px) else 0.0,
                                "pnl_eur": round(pnl_eur, 2),
                                "deal_id": deal_id,
                                "label": lbl,
                                "reason": rsn or "Chiusura riconciliata da motore Spot Gold"
                            }
                            current_history.insert(0, trade_recovered)
                            if deal_id != "--":
                                known_deals.add(deal_id)
                            known_daily_pnl.add(("GOLD", day_key, pnl_key))
                            modified = True
            except Exception as e_g:
                logger.warning(f"Errore auto-riconciliazione Gold: {e_g}")

        # 2. Controllo US500 M5
        us500_state_file = os.path.join(self.account_dir, "hyper_us500_m5_state.json")
        if os.path.exists(us500_state_file):
            try:
                with open(us500_state_file, "r", encoding="utf-8") as uf:
                    u_data = json.load(uf)
                    for t in u_data.get("trades", []):
                        act = str(t.get("action", ""))
                        if "CLOSE" in act:
                            rsn = str(t.get("reason", ""))
                            m_deal = re.search(r"Deal\s+([A-Z0-9]+)", rsn) or re.search(r"\b(DIAAA[A-Z0-9]+)\b", rsn)
                            deal_id = m_deal.group(1) if m_deal else "--"
                            if deal_id != "--" and deal_id in known_deals:
                                continue

                            pnl_eur = float(t.get("pnl") or 0.0)
                            pnl_key = round(pnl_eur, 2)
                            time_val = str(t.get("time", ""))
                            time_close = f"{today_date} {time_val}" if (len(time_val) <= 8 and ":" in time_val) else (time_val or now_str)
                            day_key = time_close[:10]

                            if deal_id == "--" and ("US500", day_key, pnl_key) in known_daily_pnl:
                                continue

                            direction = "LONG" if "LONG" in act else ("SHORT" if "SHORT" in act else "LONG")
                            open_px = float(t.get("open_price") or 0.0)
                            close_px = float(t.get("close_price") or 0.0)
                            contracts = float(t.get("contracts") or 5.0)

                            lbl = "US500 5M"
                            if "INC" in act:
                                mode = "RUNNER" if "RUNNER" in act else "BANCOMAT"
                                lbl = f"Inc {mode} US500 5M"
                            elif "CORE" in act:
                                lbl = "Core US500 5M"

                            trade_recovered = {
                                "id": str(int(time.time() * 1000)),
                                "time_open": time_close,
                                "time_close": time_close,
                                "tf": "5M",
                                "epic": "IX.D.SPTRD.IBE.IP",
                                "direction": direction,
                                "contracts": contracts,
                                "open_price": round(open_px, 2),
                                "close_price": round(close_px, 2),
                                "pips": round((close_px - open_px) if direction == "LONG" else (open_px - close_px), 2) if (open_px and close_px) else 0.0,
                                "pnl_eur": round(pnl_eur, 2),
                                "deal_id": deal_id,
                                "label": lbl,
                                "reason": rsn or "Chiusura riconciliata da motore US500"
                            }
                            current_history.insert(0, trade_recovered)
                            if deal_id != "--":
                                known_deals.add(deal_id)
                            known_daily_pnl.add(("US500", day_key, pnl_key))
                            modified = True
            except Exception as e_u:
                logger.warning(f"Errore auto-riconciliazione US500: {e_u}")

        return current_history, modified

    def get_trades_history(self, tf: str = None, epic: str = None) -> list:
        """Restituisce la lista dei trade conclusi registrati, opzionalmente filtrati per TF ed Epic."""
        data = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = []
            except Exception:
                data = []

        # Deduplica preliminare e rigorosa
        # Prima raccogliamo tutti i deal_id noti per scartare eventuali cloni senza deal_id
        known_valid_deals = {t.get("deal_id") for t in data if isinstance(t, dict) and t.get("deal_id") and t.get("deal_id") != "--"}
        known_deals_pnl = {
            ("US500" if ("SPTRD" in str(t.get("epic", "")).upper() or "US500" in str(t.get("label", "")).upper()) else "GOLD",
             str(t.get("time_close", ""))[:10],
             round(float(t.get("pnl_eur", 0.0) or 0.0), 2))
            for t in data if isinstance(t, dict) and t.get("deal_id") and t.get("deal_id") != "--"
        }

        dedup_seen = set()
        clean_data = []
        for t in data:
            if isinstance(t, dict):
                d_id = t.get("deal_id")
                ep = str(t.get("epic", "")).upper()
                ep_key = "US500" if ("SPTRD" in ep or "US500" in str(t.get("label", "")).upper()) else "GOLD"
                pnl_v = round(float(t.get("pnl_eur", 0.0) or 0.0), 2)
                day_k = str(t.get("time_close", ""))[:10]

                # Se è un record senza deal_id ma ne esiste già uno ufficiale con deal_id con stesso pnl, scartalo
                if (not d_id or d_id == "--") and (ep_key, day_k, pnl_v) in known_deals_pnl:
                    continue

                if d_id and d_id != "--":
                    sig = ("DEAL", d_id)
                else:
                    sig = (ep_key, day_k, pnl_v)

                if sig not in dedup_seen:
                    dedup_seen.add(sig)
                    clean_data.append(t)
        data = clean_data

        # Auto-riconciliazione con i motori live per non perdere mai alcuna chiusura
        try:
            data, was_mod = self._reconcile_from_engines_state(data)
            if was_mod or len(data) != len(clean_data):
                with open(self.history_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        except Exception:
            pass

        try:
            res = []
            import re
            for t in data:
                if isinstance(t, dict):
                    ep = str(t.get("epic", "")).upper()
                    lbl = str(t.get("label", "")).upper()
                    rsn = str(t.get("reason", "")).upper()

                    # Identificazione deterministica basata ESCLUSIVAMENTE sull'EPIC (e label come fallback)
                    # ZERO confronti di prezzo.
                    if "SPTRD" in ep or "US500" in ep or "SPX" in ep or ("US500" in lbl and "GOLD" not in ep and "GOLD" not in lbl):
                        t["epic"] = "IX.D.SPTRD.IBE.IP"
                        if "US500" not in lbl:
                            t["label"] = f"{t.get('label', '')} US500".strip()
                    elif any(k in ep for k in ("CFEGOLD", "CFDGOLD", "GOLD")) or "GOLD" in lbl or "ORO" in lbl:
                        t["epic"] = EPIC_GOLD
                        if "US500" in t.get("label", ""):
                            t["label"] = t["label"].replace("US500", "Spot Gold").replace("  ", " ").strip()

                    reason_str = str(t.get("reason", "") or "")
                    if reason_str:
                        reason_str = reason_str.replace("Paracadute KJ Intracandela", "Paracadute KJ")
                        reason_str = reason_str.replace(
                            "Rollover Notturno Gold (22:44 - 00:15) ➔ Chiusura automatica anticipata di sicurezza a FLAT",
                            "Rollover Gold (22:44 - 00:15) ➔ Chiusura automatica, stato FLAT."
                        )
                        reason_str = reason_str.replace("Candela Segnale KJ Confermata:", "Candela Segnale KJ :")
                        reason_str = re.sub(r"\s*\((?:Minimo|Massimo)\s*[-+]\s*\d+p\)", "", reason_str)
                        t["reason"] = reason_str
                    res.append(t)
            if tf:
                res = [t for t in res if t.get("tf") == tf]
            if epic:
                ep_filter = epic.upper()
                if "SPTRD" in ep_filter or "US500" in ep_filter:
                    res = [t for t in res if "SPTRD" in str(t.get("epic", "")).upper() or "US500" in str(t.get("label", "")).upper()]
                elif any(k in ep_filter for k in ("CFEGOLD", "CFDGOLD", "GOLD")):
                    res = [t for t in res if any(k in str(t.get("epic", "")).upper() for k in ("CFEGOLD", "CFDGOLD", "GOLD")) or "GOLD" in str(t.get("label", "")).upper()]
                else:
                    res = [t for t in res if str(t.get("epic", "")).upper() == ep_filter]
            return res
        except Exception:
            return []

    def clear_trades_history(self, tf: str = None, epic: str = None):
        """Azzera lo storico eseguiti (per un singolo TF o globale, con filtro per strumento opzionale)."""
        with self.lock:
            all_t = self.get_trades_history()
            if tf or epic:
                def _should_keep(t):
                    if tf and t.get("tf") != tf:
                        return True
                    if epic:
                        is_us500_t = ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper())
                        target_is_us = ("SPTRD" in epic.upper() or "US500" in epic.upper())
                        if is_us500_t != target_is_us:
                            return True
                    return False
                kept = [t for t in all_t if _should_keep(t)]
                try:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump(kept, f, indent=2)
                except Exception:
                    pass
            else:
                try:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        json.dump([], f)
                except Exception:
                    pass

def invia_notifica_hyper(account_dir: str, titolo: str, messaggio: str, tags: str = "rotating_light"):
    """Helper globale per invio notifiche push Hyper."""
    try:
        mgr = HyperOrderManager.get_instance(account_dir)
        mgr.send_notification(titolo, messaggio, tags=tags)
    except Exception as e:
        logger.warning(f"Errore helper invia_notifica_hyper: {e}")

