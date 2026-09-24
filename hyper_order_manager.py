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

    def send_notification(self, titolo: str, messaggio: str, tags: str = "rotating_light"):
        """Invia notifica push su ntfy.sh usando il topic configurato per questo conto."""
        topic = self._get_ntfy_topic()
        if not topic:
            return
        try:
            orario = now_it().strftime("%H:%M:%S")
            messaggio_con_orario = f"[{orario}] {messaggio}"
            headers = {
                "Title": f"[{self.account_dir}] {titolo}".encode('utf-8'),
                "Tags": tags
            }
            requests.post(
                f"https://ntfy.sh/{topic}",
                data=messaggio_con_orario.encode('utf-8'),
                headers=headers,
                timeout=5
            )
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
        try:
            h = self._get_headers(version="2")
            r = requests.get(f"{self.base_url}/positions", headers=h, timeout=6)
            if r.status_code == 200:
                positions = r.json().get("positions", [])
                return any(p.get("position", {}).get("dealId") == deal_id for p in positions)
        except Exception:
            pass
        return False

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
                return {"success": False, "reason": str(e)}

    def record_closed_trade(self, tf: str, direction: str, contracts: float, open_price: float, close_price: float, pnl_eur: float, deal_id: str, reason: str, time_open: str = "", label: str = "", epic: str = ""):
        """Salva in modo persistente l'operazione conclusa in hyper_trades_history.json."""
        with self.lock:
            now_str = now_it().strftime("%Y-%m-%d %H:%M:%S")
            target_epic = epic or ("IX.D.SPTRD.IBE.IP" if "US500" in (label or "").upper() else EPIC_GOLD)
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
            history.insert(0, trade_item)
            # Mantieni ultimi 1000 trade
            history = history[:1000]

            try:
                with open(self.history_file, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2)
            except Exception as e:
                logger.error(f"Errore salvataggio trade history in {self.history_file}: {e}")

    def get_trades_history(self, tf: str = None, epic: str = None) -> list:
        """Restituisce la lista dei trade conclusi registrati, opzionalmente filtrati per TF ed Epic."""
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    return []
                res = data
                if tf:
                    res = [t for t in res if t.get("tf") == tf]
                if epic:
                    if "SPTRD" in epic.upper() or "US500" in epic.upper():
                        res = [t for t in res if ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper())]
                    else:
                        res = [t for t in res if not ("SPTRD" in t.get("epic", "").upper() or "US500" in t.get("label", "").upper())]
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

