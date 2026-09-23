import os
import sys
import ssl
import time
import json
import threading
import datetime
import requests
import logging
from hyper_order_manager import HyperOrderManager, TZ_ITALIA, now_it

logger = logging.getLogger("HyperGoldM5Engine")

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi (55 barre M5 = 275 min = ~4.5 ore)
WARMUP_BARS_TK = 55     # Retrocompatibilità
STATE_FILE = "hyper_gold_m5_state.json"

# Parametri Strategia: S&R Puro KJ55 (Core + Incrementi Pullback + Trailing Stop M5)
CORE_CONTRACTS = 5          # Size iniziale Core: 5 contratti
CORE_TS_TRIGGER_PIPS = 10.0 # Attivazione Trailing Stop: a +10 pip di guadagno
CORE_TS_LOCK_PIPS = 6.0     # Lock profit iniziale: +6 pip garantiti (+30.00 €)
CORE_TS_STEP_PIPS = 2.0     # Avanzamento a scatti: di 2 in 2 pip
INC_CONTRACTS = 3           # Incrementi: 3 contratti ciascuno
MAX_INCREMENTS = 5          # Max 5 incrementi x 3c = 15 contratti (Totale max 20 con core)
INC_TP_PIPS = 5.0           # TP incrementi su M5: 5 pip (+15.00 € a incremento)
KJ_TOLERANCE_PIPS = 5.0     # Tolleranza di 5 pip su Kijun 55
MAX_INC_KJ_DISTANCE_PIPS = 5.0 # Max distanza da KJ per consentire incrementi: <= 5 pip
MIN_DIST_INCR_PIPS = 5.0       # Distanza minima tra incrementi consecutivi su M5: >= 5 pip
PARACADUTE_KJ_PIPS = 6.0       # Paracadute KJ Intracandela: Stop emergenza live a KJ +- 6 pip
CANDELA_SEGNALE_OFFSET_PIPS = 3.0 # Candela Segnale M5: Stop confermato su rottura Massimo/Minimo +- 3 pip
CORE_MIN_KJ_DIST_PIPS = 2.0    # Minima distanza Prezzo - KJ per ingresso Core M5: >= 2 pip (stacco da KJ)
CORE_MAX_KJ_DIST_PIPS = 6.0    # Massima distanza Prezzo - KJ per ingresso Core M5: <= 6 pip (coerente con Paracadute)

# Parametri legacy per retrocompatibilità
KJ_TK_MIN_FORBICE_PIPS = 0.0
TK_FILTER_PIPS = 0.0
CORE_REENTRY_KJ_DIST_PIPS = 2.0

# Orari Sospensione Gold:
# 1. Chiusura Feed IG Spot Gold (Nessun tick disponibile dalle 22:45 alle 00:00)
GOLD_FEED_SUSPEND_START_HOUR = 22
GOLD_FEED_SUSPEND_START_MIN = 45

# 2. Congelamento Operatività / Ordini (Dalle 22:44 alle 00:15 per rollover e spread)
GOLD_TRADE_SUSPEND_START_HOUR = 22
GOLD_TRADE_SUSPEND_START_MIN = 44
GOLD_TRADE_SUSPEND_END_HOUR = 0
GOLD_TRADE_SUSPEND_END_MIN = 15

def is_gold_feed_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True SOLO durante la chiusura reale del feed dati Gold (22:45 - 00:00).
    Dalle 00:00 il feed riapre: Lightstreamer si connette per aggiornare le candele e ricalcolare KJ55 e TK144."""
    if dt is None:
        dt = now_it()
    t = dt.time()
    t_start = datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0)
    return t >= t_start

def is_gold_trading_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True se l'operatività/apertura ordini è congelata (dalle 22:44 alle 00:15).
    Alle 22:44 le posizioni vengono chiuse a FLAT automaticamente prima della chiusura del feed delle 22:45.
    Dalle 00:00 alle 00:15 le candele si aggiornano e KJ55/TK144 vengono calcolate, ma non si aprono ordini."""
    if dt is None:
        dt = now_it()
    t = dt.time()
    t_start = datetime.time(GOLD_TRADE_SUSPEND_START_HOUR, GOLD_TRADE_SUSPEND_START_MIN, 0)
    t_end = datetime.time(GOLD_TRADE_SUSPEND_END_HOUR, GOLD_TRADE_SUSPEND_END_MIN, 0)
    return t >= t_start or t < t_end

def is_gold_market_suspended(dt: datetime.datetime = None) -> bool:
    """Alias retrocompatibile per lo stato operatività congelata"""
    return is_gold_trading_suspended(dt)

class HyperGoldM5Engine:
    _instances = {}
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, account_dir: str = None):
        key = account_dir or "DEFAULT"
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(account_dir=account_dir)
            return cls._instances[key]

    def __init__(self, account_dir: str = None):
        self.account_dir = account_dir
        self.lock = threading.RLock()
        self.running = True
        self.ls_connected = False
        self.last_tick_time = None
        self.total_ticks = 0

        # Prezzi live
        self.live_bid = None
        self.live_ask = None
        self.live_mid = None
        self.live_time_str = "--:--:--"

        # Tracciamento barra corrente M5 (300s)
        self.curr_boundary = None
        self.curr_open = None
        self.curr_high = None
        self.curr_low = None
        self.curr_close = None
        self.curr_bar_start_t = None

        # Storico barre concluse M5 (ultime 500)
        self.candles = []
        self.kj55 = None
        self.tk233 = None
        self.tk144 = None  # Retrocompatibilità (punta a tk233)

        # Portafoglio e Trading
        self.initial_balance = 10000.0
        self.balance = 10000.0
        self.point_value = 1.0   # 1 EUR per punto/pip per contratto
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False
        self.use_core_trailing = True   # Trailing Stop Core attivo di default (+10 pip trigger, +6 pip lock, step 2p)

        # Posizione Core: None (FLAT) o {"direction": "LONG"/"SHORT", "open_price": float, "contracts": 5, "tp_price": float, "open_time": str}
        self.position = None

        # Incrementi aperti: lista di {"id": int, "direction": str, "open_price": float, "contracts": 3, "tp_price": float, "open_time": str}
        self.increments = []
        self.inc_tp_pips = INC_TP_PIPS

        # Candela Segnale KJ: Stop confermato su rottura Massimo/Minimo
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_ref_price = None

        # Storico eseguiti e stato ultimo ciclo TS
        self.trades = []
        self.last_ts_cycle = None

        # Flag controllo esecuzione ordini reali IG (evita collisioni e ordini multipli)
        self.entry_in_progress = False
        self.closing_in_progress = False

        # 1. Carica eventuale stato persistito
        self.load_state()

        # 2. Sincronizzazione candele M5 contigue direttamente da IG REST all'avvio (elimina buchi da riavvii)
        self._fetch_historical_m5_bars_from_ig()

        # 3. Avvia thread di streaming Lightstreamer in background
        self.stream_thread = threading.Thread(target=self._run_streaming_loop, daemon=True)
        self.stream_thread.start()

    def _get_ig_credentials(self):
        user, pwd, api_key = None, None, None
        candidates = []
        if getattr(self, "account_dir", None):
            candidates.append(os.path.join(self.account_dir, ".env"))
        candidates.append(".env")
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("IG_USERNAME="): user = line.split("=", 1)[1]
                            elif line.startswith("IG_PASSWORD="): pwd = line.split("=", 1)[1]
                            elif line.startswith("IG_API_KEY="): api_key = line.split("=", 1)[1]
                    if user and pwd and api_key:
                        break
                except Exception:
                    pass
        return user, pwd, api_key

    def _fetch_historical_m5_bars_from_ig(self):
        """Singola chiamata REST una tantum per scaricare le barre M5 storiche contigue con cache centralizzata condivisa"""
        # 1. Verifica se esiste già una cache centralizzata recente (meno di 5 minuti)
        central_file = "candele_Spot_Gold_M5.json"
        if os.path.exists(central_file):
            try:
                mtime = os.path.getmtime(central_file)
                if (time.time() - mtime) < 300: # Meno di 5 minuti
                    with open(central_file, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    if isinstance(cached, list) and len(cached) >= WARMUP_BARS_KJ:
                        if cached[-1].get("boundary", 0) <= (time.time() + 600):
                            with self.lock:
                                self.candles = cached[-500:]
                                self._recalculate_indicators()
                                self.save_state()
                            return
            except Exception:
                pass

        try:
            # Preferisce credenziali DANY_DEMO per risparmiare quote o usa il conto corrente
            user, pwd, api_key = None, None, None
            for p in ["DANY_DEMO/.env", "/data/DANY_DEMO/.env"]:
                if os.path.exists(p):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("IG_USERNAME="): user = line.split("=", 1)[1]
                                elif line.startswith("IG_PASSWORD="): pwd = line.split("=", 1)[1]
                                elif line.startswith("IG_API_KEY="): api_key = line.split("=", 1)[1]
                        if user and pwd and api_key: break
                    except Exception: pass
            if not user or not pwd or not api_key:
                user, pwd, api_key = self._get_ig_credentials()
            if not user or not pwd or not api_key:
                return

            # Login REST IG per sessione
            url_session = "https://demo-api.ig.com/gateway/deal/session"
            h_session = {
                "X-IG-API-KEY": api_key,
                "Version": "2",
                "Accept": "application/json; charset=UTF-8",
                "Content-Type": "application/json; charset=UTF-8"
            }
            payload = {"identifier": user, "password": pwd}
            r_sess = requests.post(url_session, headers=h_session, json=payload, timeout=10)
            if r_sess.status_code != 200:
                return

            cst = r_sess.headers.get("CST")
            xst = r_sess.headers.get("X-SECURITY-TOKEN")

            # Recupera fino a 250 barre storiche M5 in UNA SOLA chiamata REST condivisa
            url_px = f"https://demo-api.ig.com/gateway/deal/prices/{EPIC_GOLD}?resolution=MINUTE_5&max=250&pageSize=0"
            h_px = {
                "X-IG-API-KEY": api_key,
                "CST": cst,
                "X-SECURITY-TOKEN": xst,
                "Version": "3"
            }
            r_px = requests.get(url_px, headers=h_px, timeout=15)
            if r_px.status_code == 200:
                d = r_px.json()
                raw_prices = d.get("prices", [])
                with self.lock:
                    loaded_candles = []
                    for p in raw_prices:
                        try:
                            st_time_utc = p.get("snapshotTimeUTC")
                            st_time = p.get("snapshotTime", "")
                            if st_time_utc:
                                try:
                                    dt_u = datetime.datetime.fromisoformat(st_time_utc).replace(tzinfo=datetime.timezone.utc)
                                except Exception:
                                    dt_u = datetime.datetime.strptime(st_time_utc, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                                dt_it = dt_u.astimezone(TZ_ITALIA)
                                t_str = dt_it.strftime("%H:%M:%S")
                                boundary = int(dt_u.timestamp() // CANDLE_SECONDS) * CANDLE_SECONDS
                            else:
                                dt_it = datetime.datetime.strptime(st_time, "%Y/%m/%d %H:%M:%S").replace(tzinfo=TZ_ITALIA)
                                t_str = dt_it.strftime("%H:%M:%S")
                                boundary = int(dt_it.timestamp() // CANDLE_SECONDS) * CANDLE_SECONDS

                            op = round((p["openPrice"]["bid"] + p["openPrice"]["ask"]) / 2.0, 2)
                            hi = round((p["highPrice"]["bid"] + p["highPrice"]["ask"]) / 2.0, 2)
                            lo = round((p["lowPrice"]["bid"] + p["lowPrice"]["ask"]) / 2.0, 2)
                            cl = round((p["closePrice"]["bid"] + p["closePrice"]["ask"]) / 2.0, 2)
                            loaded_candles.append({
                                "boundary": boundary,
                                "time": t_str,
                                "open": op,
                                "high": hi,
                                "low": lo,
                                "close": cl
                            })
                        except Exception:
                            pass

                    if loaded_candles:
                        self.candles = loaded_candles[-500:]
                        self._recalculate_indicators()
                        self.save_state()

                        # Salva centralmente per condividere con tutti gli altri account
                        try:
                            with open(central_file, "w", encoding="utf-8") as f:
                                json.dump(self.candles, f, indent=2)
                        except Exception:
                            pass

                        # Sincronizza istantaneamente su FIORDOK_DEMO, DANY_DEMO, BONGIOLO_DEMO
                        for acc in ["FIORDOK_DEMO", "DANY_DEMO", "BONGIOLO_DEMO"]:
                            try:
                                p_acc = os.path.join(acc, STATE_FILE)
                                if os.path.exists(acc) and os.path.exists(p_acc):
                                    with open(p_acc, "r", encoding="utf-8") as f_r:
                                        d_acc = json.load(f_r)
                                    d_acc["candles"] = self.candles
                                    with open(p_acc, "w", encoding="utf-8") as f_w:
                                        json.dump(d_acc, f_w, indent=2)
                            except Exception:
                                pass
        except Exception:
            pass

    def _recalculate_indicators(self):
        """Calcola KJ55 (Supporto & Resistenza Puro) in base allo storico candele M5 disponibile"""
        n = len(self.candles)
        if n >= WARMUP_BARS_KJ:
            sub_kj = self.candles[-WARMUP_BARS_KJ:]
            max_h_kj = max(c["high"] for c in sub_kj)
            min_l_kj = min(c["low"] for c in sub_kj)
            self.kj55 = round((max_h_kj + min_l_kj) / 2.0, 2)
            if self.candles:
                self.candles[-1]["kj55"] = self.kj55
        else:
            self.kj55 = None

        self.tk233 = None
        self.tk144 = None

    def _get_state_file(self):
        if getattr(self, "account_dir", None):
            return os.path.join(self.account_dir, STATE_FILE)
        return STATE_FILE

    def load_state(self):
        st_file = self._get_state_file()
        if not os.path.exists(st_file):
            legacy_file = st_file.replace("hyper_gold_m5_state.json", "hyper_gold_m1_state.json")
            if os.path.exists(legacy_file):
                st_file = legacy_file
            else:
                return
        d = None
        for _ in range(5):
            try:
                with open(st_file, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                if not text.strip():
                    return
                try:
                    d = json.loads(text)
                except Exception:
                    # Decodifica il primo blocco JSON valido se ci sono dati residui
                    d, _ = json.JSONDecoder().raw_decode(text)
                if d and isinstance(d, dict):
                    break
            except Exception:
                time.sleep(0.05)

        if not d or not isinstance(d, dict):
            return

        with self.lock:
            self.balance = float(d.get("balance", 10000.0))
            self.trading_enabled = bool(d.get("trading_enabled", False))
            self.use_core_trailing = True
            self.position = d.get("position")
            self.increments = d.get("increments", [])
            self.inc_tp_pips = float(d.get("inc_tp_pips", INC_TP_PIPS))
            self.trades = d.get("trades", [])
            self.last_ts_cycle = d.get("last_ts_cycle")
            self.candles = d.get("candles", [])
            if self.candles and self.candles[-1].get("boundary", 0) > (time.time() + 600):
                self.candles = []
            self.signal_candle_active = bool(d.get("signal_candle_active", False))
            self.signal_stop_price = d.get("signal_stop_price")
            self.signal_ref_price = d.get("signal_ref_price")
            self._recalculate_indicators()

    def save_state(self):
        st_file = self._get_state_file()
        with self.lock:
            d = {
                "balance": self.balance,
                "trading_enabled": self.trading_enabled,
                "use_core_trailing": True,
                "position": self.position,
                "increments": self.increments,
                "inc_tp_pips": self.inc_tp_pips,
                "signal_candle_active": getattr(self, "signal_candle_active", False),
                "signal_stop_price": getattr(self, "signal_stop_price", None),
                "signal_ref_price": getattr(self, "signal_ref_price", None),
                "trades": self.trades[-100:],
                "last_ts_cycle": self.last_ts_cycle,
                "candles": self.candles[-500:]
            }
            # Scrittura diretta con truncate e retry per compatibilità Windows
            for _ in range(5):
                try:
                    with open(st_file, "w", encoding="utf-8") as f:
                        json.dump(d, f, indent=2, ensure_ascii=False)
                        f.flush()
                    break
                except Exception:
                    time.sleep(0.05)

    def reset_portfolio(self):
        with self.lock:
            self.balance = self.initial_balance
            self.position = None
            self.increments = []
            self.trades = []
            self.save_state()

    def clear_session_trades(self):
        with self.lock:
            self.trades = []
            self.last_ts_cycle = None
            self.save_state()

    def set_use_core_trailing(self, enabled: bool):
        with self.lock:
            self.use_core_trailing = enabled
            self.save_state()

    def set_trading(self, enabled: bool):
        with self.lock:
            self.trading_enabled = enabled
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            if enabled:
                order_mgr.send_notification("🚀 AVVIO HYPER 5M: Spot Gold", "[Spot Gold] Scalping Hyper 5M attivato.", "rocket")
            else:
                order_mgr.send_notification("⏹️ STOP HYPER 5M: Spot Gold", "[Spot Gold] Scalping Hyper 5M disattivato dall'utente.", "stop_button")
                # Quando l'utente preme STOP TRADING, chiude immediatamente tutte le posizioni aperte a FLAT
                if self.position or self.increments:
                    exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                    t_str = now_it().strftime("%H:%M:%S")
                    self._close_all_to_flat(exec_px, t_str, reason="🛑 STOP TRADING Manuale Utente ➔ Chiusura immediata di tutte le posizioni a FLAT")
            self.save_state()

    def _run_streaming_loop(self):
        while self.running:
            try:
                # Durante la chiusura effettiva del feed Gold (22:45 - 00:00) NON effettuiamo chiamate API né login.
                # Dalle 00:00 in poi lo streaming è attivo per aggiornare le candele e ricalcolare KJ55 e TK144!
                if is_gold_feed_suspended():
                    with self.lock:
                        self.ls_connected = False
                    time.sleep(20)
                    continue

                user, pwd, api_key = self._get_ig_credentials()
                if not user or not pwd or not api_key:
                    time.sleep(5)
                    continue

                url_session = "https://demo-api.ig.com/gateway/deal/session"
                h_session = {
                    "X-IG-API-KEY": api_key,
                    "Version": "2",
                    "Accept": "application/json; charset=UTF-8",
                    "Content-Type": "application/json; charset=UTF-8"
                }
                payload = {"identifier": user, "password": pwd}
                r = requests.post(url_session, headers=h_session, json=payload, timeout=10)
                if r.status_code != 200:
                    time.sleep(10)
                    continue

                cst = r.headers.get("CST")
                xst = r.headers.get("X-SECURITY-TOKEN")
                d_resp = r.json()
                endpoint = d_resp.get("lightstreamerEndpoint")
                account_id = d_resp.get("currentAccountId")

                from lightstreamer_client import LightstreamerClient, LightstreamerSubscription
                ls_client = LightstreamerClient(account_id, f"CST-{cst}|XST-{xst}", endpoint)
                ls_client.connect()
                with self.lock:
                    self.ls_connected = True

                def on_tick(item_update):
                    vals = item_update.get("values", {})
                    bid_s = vals.get("BID")
                    ask_s = vals.get("OFR") or vals.get("OFFER")
                    # Orario locale italiano (Roma UTC+2/UTC+1) per storico ed eseguiti
                    t_str = now_it().strftime("%H:%M:%S")
                    if bid_s and ask_s:
                        try:
                            b = float(bid_s)
                            a = float(ask_s)
                            self._process_tick(b, a, t_str)
                        except Exception:
                            pass

                sub = LightstreamerSubscription(
                    mode="DISTINCT",
                    items=[f"CHART:{EPIC_GOLD}:TICK"],
                    fields=["BID", "OFR", "UTM"]
                )
                sub.addlistener(on_tick)
                ls_client.subscribe(sub)

                while self.running and self.ls_connected:
                    time.sleep(2)
                    # Controllo proattivo chiusura Rollover alle 22:44 (1 min prima del freeze del feed)
                    if is_gold_market_suspended():
                        with self.lock:
                            has_pos = (self.position is not None or len(self.increments) > 0)
                            mid_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                        if has_pos:
                            t_str = now_it().strftime("%H:%M:%S")
                            self._close_all_to_flat(mid_px, t_str, reason="Rollover Notturno Gold (22:44 - 00:15) ➔ Chiusura automatica anticipata di sicurezza a FLAT")
                    if self.last_tick_time and (time.time() - self.last_tick_time) > 40:
                        break

            except Exception:
                pass
            finally:
                with self.lock:
                    self.ls_connected = False
                time.sleep(5)

    def _check_core_trailing_stop(self, current_price: float, time_str: str):
        """Gestisce il Trailing Stop sulla posizione Core M5:
        1. A +10 pip attiva il TS e piazza il lock a +6 pip garantiti (+30.00 €).
        2. Segue il prezzo a scatti di 2 in 2 pip:
           - A +12 pip: TS scatta a +8 pip garantiti (+40.00 €)
           - A +14 pip: TS scatta a +10 pip garantiti (+50.00 €)
           - A +16 pip: TS scatta a +12 pip garantiti (+60.00 €)
        3. Quando il prezzo tocca il TS: chiude Core + tutti gli incrementi a FLAT,
           imposta automaticamente trading_enabled = False (STOP TRADING) e salva il ciclo."""
        if not self.position:
            return

        pos = self.position
        direction = pos["direction"]
        open_px = pos["open_price"]

        # Calcolo pips attuali
        if direction == "LONG":
            profit_pips = round(current_price - open_px, 2)
        else:
            profit_pips = round(open_px - current_price, 2)

        # 1. Attivazione Trailing Stop al raggiungimento di +10 pip
        if not pos.get("ts_active", False):
            if profit_pips >= CORE_TS_TRIGGER_PIPS:
                pos["ts_active"] = True
                pos["peak_price"] = current_price
                steps = int((profit_pips - CORE_TS_TRIGGER_PIPS) // CORE_TS_STEP_PIPS)
                locked_pips = CORE_TS_LOCK_PIPS + (steps * CORE_TS_STEP_PIPS)
                if direction == "LONG":
                    pos["ts_price"] = round(open_px + locked_pips, 2)
                else:
                    pos["ts_price"] = round(open_px - locked_pips, 2)

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🚀 TRAILING ATTIVATO {direction}",
                    "open_price": open_px,
                    "close_price": current_price,
                    "contracts": pos["contracts"],
                    "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                    "balance": round(self.balance, 2),
                    "reason": f"Raggiunti +{profit_pips:.1f} pip @ {current_price:.2f} ➔ Lock +{locked_pips:.1f} pip @ {pos['ts_price']:.2f} (Step 2 pip)"
                })
                self.save_state()

        # 2. Aggiornamento dinamico del Trailing (scatti di 2 in 2) e verifica tocco
        if pos.get("ts_active", False):
            peak_px = pos.get("peak_price", current_price)

            if direction == "LONG":
                # Nuovo picco massimo
                if current_price > peak_px:
                    pos["peak_price"] = current_price
                    steps = int((profit_pips - CORE_TS_TRIGGER_PIPS) // CORE_TS_STEP_PIPS)
                    locked_pips = CORE_TS_LOCK_PIPS + (steps * CORE_TS_STEP_PIPS)
                    new_ts = round(open_px + locked_pips, 2)
                    if new_ts > pos["ts_price"]:
                        pos["ts_price"] = new_ts
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"📈 TS STEP UP (+{locked_pips:.1f} pip)",
                            "open_price": open_px,
                            "close_price": current_price,
                            "contracts": pos["contracts"],
                            "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                            "balance": round(self.balance, 2),
                            "reason": f"Nuovo picco {current_price:.2f} (+{profit_pips:.1f} pip) ➔ TS sale a {new_ts:.2f} (+{locked_pips:.1f} pip garantiti)"
                        })
                        self.save_state()
                        order_mgr = HyperOrderManager.get_instance(self.account_dir)
                        order_mgr.send_notification(
                            "🎯 TRAILING STOP 5M: Spot Gold",
                            f"[Spot Gold] Core Trailing Stop LONG aggiornato a {new_ts:.2f} € (Lock +{locked_pips:.1f}p, Prezzo: {current_price:.2f} €)",
                            "dart"
                        )

                # Verifica tocco Trailing Stop
                if current_price <= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

            else: # SHORT
                # Nuovo picco minimo
                if current_price < peak_px:
                    pos["peak_price"] = current_price
                    steps = int((profit_pips - CORE_TS_TRIGGER_PIPS) // CORE_TS_STEP_PIPS)
                    locked_pips = CORE_TS_LOCK_PIPS + (steps * CORE_TS_STEP_PIPS)
                    new_ts = round(open_px - locked_pips, 2)
                    if new_ts < pos["ts_price"]:
                        pos["ts_price"] = new_ts
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"📉 TS STEP DOWN (+{locked_pips:.1f} pip)",
                            "open_price": open_px,
                            "close_price": current_price,
                            "contracts": pos["contracts"],
                            "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                            "balance": round(self.balance, 2),
                            "reason": f"Nuovo picco {current_price:.2f} (+{profit_pips:.1f} pip) ➔ TS scende a {new_ts:.2f} (+{locked_pips:.1f} pip garantiti)"
                        })
                        self.save_state()
                        order_mgr = HyperOrderManager.get_instance(self.account_dir)
                        order_mgr.send_notification(
                            "🎯 TRAILING STOP 5M: Spot Gold",
                            f"[Spot Gold] Core Trailing Stop SHORT aggiornato a {new_ts:.2f} € (Lock +{locked_pips:.1f}p, Prezzo: {current_price:.2f} €)",
                            "dart"
                        )

                # Verifica tocco Trailing Stop
                if current_price >= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

    def _execute_entry_core(self, direction: str, exec_price: float, time_str: str):
        """Esegue l'apertura a mercato reale su IG della Core M5 (5 contratti)."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            res = order_mgr.open_market_deal(
                direction=direction,
                size=CORE_CONTRACTS,
                limit_level=None,
                label="Core M5"
            )
            if res.get("success"):
                deal_id = res.get("deal_id")
                real_open = float(res.get("level") or exec_price)
                with self.lock:
                    self.position = {
                        "deal_id": deal_id,
                        "deal_reference": res.get("deal_reference"),
                        "direction": direction,
                        "open_price": real_open,
                        "contracts": CORE_CONTRACTS,
                        "open_time": res.get("time") or time_str,
                        "ts_active": False,
                        "ts_price": None,
                        "peak_price": real_open
                    }
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 OPEN REAL IG {direction} ({CORE_CONTRACTS}c Core M5)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": CORE_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Ingresso IG Reale {direction} @ {real_open:.2f} € (Deal ID Core: {deal_id})"
                    })
                    self.save_state()
                    order_mgr.send_notification(
                        "🚀 OPEN CORE 5M: Spot Gold",
                        f"[Spot Gold] Core {direction} {CORE_CONTRACTS}c a {real_open:.2f} € (Deal ID: {deal_id})",
                        "rocket"
                    )
        except Exception as e:
            logger.error(f"Errore apertura Core M5 IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_entry_increment(self, direction: str, exec_price: float, time_str: str):
        """Esegue l'apertura a mercato reale su IG di un incremento M5 (3 contratti) con TP +5p."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            tp_px = round(exec_price + self.inc_tp_pips if direction == "LONG" else exec_price - self.inc_tp_pips, 2)
            res = order_mgr.open_market_deal(
                direction=direction,
                size=INC_CONTRACTS,
                limit_level=tp_px,
                label=f"Incremento M5 #{len(self.increments)+1}"
            )
            if res.get("success"):
                deal_id = res.get("deal_id")
                real_open = float(res.get("level") or exec_price)
                with self.lock:
                    new_inc = {
                        "id": int(time.time() * 1000),
                        "deal_id": deal_id,
                        "deal_reference": res.get("deal_reference"),
                        "direction": direction,
                        "open_price": real_open,
                        "contracts": INC_CONTRACTS,
                        "tp_price": tp_px,
                        "open_time": res.get("time") or time_str
                    }
                    self.increments.append(new_inc)
                    tot_c = CORE_CONTRACTS + sum(i["contracts"] for i in self.increments)
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"➕ OPEN REAL IG INC {direction} (+{INC_CONTRACTS}c, Tot: {tot_c}c)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": INC_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Incremento M5 IG @ {real_open:.2f} € (TP: {tp_px:.2f}, Deal ID: {deal_id})"
                    })
                    self.save_state()
                    order_mgr.send_notification(
                        "➕ INCREMENTO 5M: Spot Gold",
                        f"[Spot Gold] Incremento #{len(self.increments)} {direction} {INC_CONTRACTS}c a {real_open:.2f} € (TP: {tp_px:.2f} €, Tot: {tot_c}c)",
                        "heavy_plus_sign"
                    )
        except Exception as e:
            logger.error(f"Errore apertura incremento M5 IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_close_increment(self, inc: dict, current_price: float, time_str: str):
        """Chiude a mercato reale un singolo incremento M5 quando tocca il Take Profit."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            deal_id = inc.get("deal_id")
            res = order_mgr.close_market_deal(
                deal_id=deal_id,
                direction_open=inc["direction"],
                size=inc["contracts"],
                label="TP Incremento M5",
                reason_note=f"Raggiunto TP a +{self.inc_tp_pips:.1f}p @ {current_price:.2f}"
            )
            profit = float(res.get("profit") or 0.0)
            close_px = float(res.get("close_level") or current_price)

            with self.lock:
                self.increments = [i for i in self.increments if i.get("deal_id") != deal_id and i.get("id") != inc.get("id")]
                self.balance += profit

                order_mgr.record_closed_trade(
                    tf="5M",
                    direction=inc["direction"],
                    contracts=inc["contracts"],
                    open_price=inc["open_price"],
                    close_price=close_px,
                    pnl_eur=profit,
                    deal_id=deal_id,
                    reason=f"TP Incremento (+{self.inc_tp_pips:.1f}p)",
                    time_open=inc.get("open_time", time_str),
                    label="Incremento M5"
                )

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🎯 TP INC {inc['direction']} (+{profit:+.2f} €)",
                    "open_price": inc["open_price"],
                    "close_price": close_px,
                    "contracts": inc["contracts"],
                    "pnl": profit,
                    "balance": round(self.balance, 2),
                    "reason": f"Chiusura IG Deal {deal_id}: TP raggiunto @ {close_px:.2f}"
                })
                self.save_state()
                order_mgr.send_notification(
                    "🎯 TP INCREMENTO 5M: Spot Gold",
                    f"[Spot Gold] Incremento {inc['direction']} ({inc['contracts']}c) a target a {close_px:.2f} € [PnL: {profit:+.2f} €]",
                    "dart"
                )
        except Exception as e:
            logger.error(f"Errore chiusura incremento M5 IG: {e}")

    def _execute_close_all_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude a mercato reale tutte le posizioni aperte su IG (Core + Incrementi M5)."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            with self.lock:
                pos_to_close = dict(self.position) if self.position else None
                incs_to_close = [dict(i) for i in self.increments]
                self.position = None
                self.increments = []
                self.save_state()

            # 1. Chiudi Core se presente
            if pos_to_close and pos_to_close.get("deal_id"):
                deal_c = pos_to_close["deal_id"]
                res_c = order_mgr.close_market_deal(
                    deal_id=deal_c,
                    direction_open=pos_to_close["direction"],
                    size=pos_to_close["contracts"],
                    label="Chiusura Core M5 Flat",
                    reason_note=reason
                )
                prof_c = float(res_c.get("profit") or 0.0)
                cl_c = float(res_c.get("close_level") or exec_price)
                order_mgr.record_closed_trade(
                    tf="5M",
                    direction=pos_to_close["direction"],
                    contracts=pos_to_close["contracts"],
                    open_price=pos_to_close["open_price"],
                    close_price=cl_c,
                    pnl_eur=prof_c,
                    deal_id=deal_c,
                    reason=reason,
                    time_open=pos_to_close.get("open_time", time_str),
                    label="Core M5"
                )
                with self.lock:
                    self.balance += prof_c
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"CLOSE CORE M5 {pos_to_close['direction']} ({prof_c:+.2f} €)",
                        "open_price": pos_to_close["open_price"],
                        "close_price": cl_c,
                        "contracts": pos_to_close["contracts"],
                        "pnl": prof_c,
                        "balance": round(self.balance, 2),
                        "reason": reason
                    })
                is_ts = "Trailing" in reason or "TS" in reason
                is_rev = "Reversal" in reason or "Inversione" in reason or "taglio" in reason.lower()
                if is_ts:
                    tag_cl = "dart"
                    tit_cl = "🎯 TS HIT 5M: Spot Gold"
                elif is_rev:
                    tag_cl = "warning"
                    tit_cl = "🛑 REVERSAL 5M: Spot Gold"
                else:
                    tag_cl = "octagonal_sign"
                    tit_cl = "🛑 CHIUSURA FLAT 5M: Spot Gold"
                msg_cl = f"[Spot Gold] Core {pos_to_close['direction']} ({pos_to_close['contracts']}c) chiusa a {cl_c:.2f} € [PnL: {prof_c:+.2f} €] - Motivo: {reason}"
                order_mgr.send_notification(tit_cl, msg_cl, tag_cl)
                # Pausa prima degli incrementi
                time.sleep(1.5)

            # 2. Chiudi incrementi residui
            for inc in incs_to_close:
                deal_i = inc.get("deal_id")
                if deal_i:
                    res_i = order_mgr.close_market_deal(
                        deal_id=deal_i,
                        direction_open=inc["direction"],
                        size=inc["contracts"],
                        label="Chiusura Inc M5 Flat",
                        reason_note=reason
                    )
                    prof_i = float(res_i.get("profit") or 0.0)
                    cl_i = float(res_i.get("close_level") or exec_price)
                    order_mgr.record_closed_trade(
                        tf="5M",
                        direction=inc["direction"],
                        contracts=inc["contracts"],
                        open_price=inc["open_price"],
                        close_price=cl_i,
                        pnl_eur=prof_i,
                        deal_id=deal_i,
                        reason=reason,
                        time_open=inc.get("open_time", time_str),
                        label="Incremento M5"
                    )
                    with self.lock:
                        self.balance += prof_i
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"CLOSE INC M5 {inc['direction']} ({prof_i:+.2f} €)",
                            "open_price": inc["open_price"],
                            "close_price": cl_i,
                            "contracts": inc["contracts"],
                            "pnl": prof_i,
                            "balance": round(self.balance, 2),
                            "reason": reason
                        })
                    order_mgr.send_notification(
                        "🛑 CHIUSURA FLAT INC 5M: Spot Gold",
                        f"[Spot Gold] Incremento {inc['direction']} ({inc['contracts']}c) chiuso a {cl_i:.2f} € [PnL: {prof_i:+.2f} €]",
                        "octagonal_sign"
                    )
                    # Pausa prudenziale tra incrementi
                    time.sleep(1.5)

            with self.lock:
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura posizioni flat M5 IG: {e}")
        finally:
            with self.lock:
                self.closing_in_progress = False

    def _close_cycle_trailing_hit(self, current_price: float, time_str: str):
        """Chiusura completa a FLAT all'entrata del Trailing Stop su M5"""
        if not self.position or getattr(self, "closing_in_progress", False):
            return
        self.closing_in_progress = True
        threading.Thread(
            target=self._execute_close_all_flat,
            args=(current_price, time_str, f"Trailing Stop toccato @ {current_price:.2f}"),
            daemon=True
        ).start()

    def _check_increments_tp(self, current_price: float, time_str: str):
        """Controlla Take Profit (+5 pip) per gli incrementi aperti su M5"""
        for inc in list(self.increments):
            if inc.get("closing"):
                continue
            hit_tp = False
            if inc["direction"] == "LONG" and current_price >= inc["tp_price"]:
                hit_tp = True
            elif inc["direction"] == "SHORT" and current_price <= inc["tp_price"]:
                hit_tp = True

            if hit_tp:
                inc["closing"] = True
                threading.Thread(
                    target=self._execute_close_increment,
                    args=(inc, current_price, time_str),
                    daemon=True
                ).start()

    def _check_paracadute_kj(self, mid: float, time_str: str):
        """Paracadute KJ Intracandela (Tick-by-Tick):
        Se durante la candela M5 il prezzo sfonda la Kijun 55 oltre il paracadute (6 pip),
        chiude immediatamente all'istante la Core e tutti gli incrementi a FLAT."""
        if not self.position or self.kj55 is None:
            return

        pos_dir = self.position["direction"]
        if pos_dir == "LONG":
            threshold = round(self.kj55 - PARACADUTE_KJ_PIPS, 2)
            if mid <= threshold:
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ Intracandela: Mid live {mid:.2f} <= (KJ {self.kj55:.2f} - {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )
        elif pos_dir == "SHORT":
            threshold = round(self.kj55 + PARACADUTE_KJ_PIPS, 2)
            if mid >= threshold:
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ Intracandela: Mid live {mid:.2f} >= (KJ {self.kj55:.2f} + {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )

    def _check_candela_segnale_stop(self, mid: float, time_str: str):
        """Verifica Stop Conferma Candela Segnale KJ (Tick-by-Tick):
        Se una candela M5 precedente ha chiuso oltre KJ attivando la Candela Segnale,
        ed il prezzo live rompe il livello confermato (Minimo - 5p per LONG, Massimo + 5p per SHORT),
        chiude immediatamente all'istante la Core e tutti gli incrementi a FLAT."""
        if not self.position or not self.signal_candle_active or self.signal_stop_price is None:
            return

        pos_dir = self.position["direction"]
        if pos_dir == "LONG":
            if mid <= self.signal_stop_price:
                stop_val = self.signal_stop_price
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Candela Segnale KJ Confermata: Mid live {mid:.2f} <= Stop {stop_val:.2f} (Minimo - {CANDELA_SEGNALE_OFFSET_PIPS:.0f}p) ➔ FLAT"
                )
        elif pos_dir == "SHORT":
            if mid >= self.signal_stop_price:
                stop_val = self.signal_stop_price
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Candela Segnale KJ Confermata: Mid live {mid:.2f} >= Stop {stop_val:.2f} (Massimo + {CANDELA_SEGNALE_OFFSET_PIPS:.0f}p) ➔ FLAT"
                )

    def _process_tick(self, bid: float, ask: float, time_str: str):
        now_t = time.time()
        mid = round((bid + ask) / 2.0, 2)
        boundary = int(now_t // CANDLE_SECONDS) * CANDLE_SECONDS

        with self.lock:
            self.total_ticks += 1
            self.last_tick_time = now_t
            self.live_bid = bid
            self.live_ask = ask
            self.live_mid = mid
            self.live_time_str = time_str

            # Verifica sospensione notturna / rollover Gold (22:44 - 00:15)
            market_suspended = is_gold_market_suspended()

            if market_suspended:
                # Se è scattata l'ora di sospensione (22:44) con posizioni ancora aperte, le chiudiamo a FLAT di sicurezza
                if self.position or self.increments:
                    self._close_all_to_flat(mid, time_str, reason="Rollover Notturno Gold (22:44 - 00:15) ➔ Chiusura automatica anticipata di sicurezza a FLAT")
            else:
                # 1. Verifica Trailing Stop per la Core (Attivo di default: Trigger +10p, Lock +6p, Step 2p)
                if self.trading_enabled and self.position and getattr(self, "use_core_trailing", True):
                    self._check_core_trailing_stop(mid, time_str)

                # 2. Verifica Take Profit (5 pip) per gli incrementi aperti (Bancomat continuo)
                if self.trading_enabled and self.increments:
                    self._check_increments_tp(mid, time_str)

                # 3. Paracadute KJ Intracandela (6 pip): Chiusura istantanea di sicurezza a FLAT
                if self.trading_enabled and self.position and self.kj55 is not None:
                    self._check_paracadute_kj(mid, time_str)

                # 4. Stop Conferma Candela Segnale KJ (5 pip): Chiusura a rottura confermata
                if self.trading_enabled and self.position and self.signal_candle_active:
                    self._check_candela_segnale_stop(mid, time_str)

            # Inizializzazione prima barra M5
            if self.curr_boundary is None:
                self.curr_boundary = boundary
                self.curr_open = mid
                self.curr_high = mid
                self.curr_low = mid
                self.curr_close = mid
                self.curr_bar_start_t = now_t
                return

            if boundary == self.curr_boundary:
                # Barra M5 corrente in formazione
                if mid > self.curr_high: self.curr_high = mid
                if mid < self.curr_low: self.curr_low = mid
                self.curr_close = mid
            else:
                # Chiusura barra M5 (300s)
                closed_candle = {
                    "boundary": self.curr_boundary,
                    "time": datetime.datetime.fromtimestamp(self.curr_boundary, TZ_ITALIA).strftime("%H:%M:%S"),
                    "open": self.curr_open,
                    "high": self.curr_high,
                    "low": self.curr_low,
                    "close": self.curr_close
                }
                self.candles.append(closed_candle)
                if len(self.candles) > 500:
                    self.candles = self.candles[-500:]

                # Ricalcola KJ55 e TK144
                self._recalculate_indicators()

                # Apertura nuova candela M5
                new_open = mid
                self.curr_boundary = boundary
                self.curr_open = new_open
                self.curr_high = new_open
                self.curr_low = new_open
                self.curr_close = new_open
                self.curr_bar_start_t = now_t

                self.save_state()

                # Strategia S&R Puro KJ55: solo se il mercato NON è sospeso
                if self.trading_enabled and not market_suspended and self.kj55 is not None:
                    self._evaluate_pure_sr_strategy(closed_candle, self.kj55, new_open, time_str)

    def _evaluate_pure_sr_strategy(self, closed_candle: dict, kj: float, exec_price: float, time_str: str):
        prev_close = closed_candle["close"]
        prev_open = closed_candle["open"]

        # =============================================================
        # 1. MERCATO SOPRA KJ55 (BULLISH)
        # =============================================================
        if prev_close > kj:
            if self.position is None:
                # Ingresso Core LONG: solo se il prezzo attuale stacca sopra KJ tra 2.0 e 6.0 pip
                dist_kj = round(exec_price - kj, 2)
                if CORE_MIN_KJ_DIST_PIPS <= dist_kj <= CORE_MAX_KJ_DIST_PIPS:
                    if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                        self.entry_in_progress = True
                        self.signal_candle_active = False
                        self.signal_stop_price = None
                        self.signal_ref_price = None
                        threading.Thread(
                            target=self._execute_entry_core,
                            args=("LONG", exec_price, time_str),
                            daemon=True
                        ).start()
                elif dist_kj > CORE_MAX_KJ_DIST_PIPS:
                    print(f"[{time_str}] ⏸️ [CORE SKIP LONG] Prezzo {exec_price:.2f} troppo distante da KJ {kj:.2f} ({dist_kj:.2f}p > max {CORE_MAX_KJ_DIST_PIPS:.1f}p). Attendo rientro/pullback.")
            elif self.position and self.position["direction"] == "LONG":
                # Core già LONG: azzera eventuale Candela Segnale e valuta incremento su pullback
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None
                dist_kj = abs(exec_price - kj)
                troppo_vicino = any(abs(exec_price - inc["open_price"]) < (MIN_DIST_INCR_PIPS - 1e-7) for inc in self.increments)
                if prev_close < prev_open and dist_kj <= MAX_INC_KJ_DISTANCE_PIPS and not troppo_vicino:
                    if len(self.increments) < MAX_INCREMENTS:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            threading.Thread(
                                target=self._execute_entry_increment,
                                args=("LONG", exec_price, time_str),
                                daemon=True
                            ).start()
            elif self.position and self.position["direction"] == "SHORT":
                # Chiusura candela sopra KJ mentre siamo SHORT: Candela Segnale rialzista!
                stop_livello = round(closed_candle["high"] + CANDELA_SEGNALE_OFFSET_PIPS, 2)
                if self.signal_candle_active and self.signal_stop_price is not None:
                    if stop_livello > self.signal_stop_price:
                        self.signal_stop_price = stop_livello
                        self.signal_ref_price = closed_candle["high"]
                else:
                    self.signal_candle_active = True
                    self.signal_stop_price = stop_livello
                    self.signal_ref_price = closed_candle["high"]
                self.save_state()

        # =============================================================
        # 2. MERCATO SOTTO KJ55 (BEARISH)
        # =============================================================
        elif prev_close < kj:
            if self.position is None:
                # Ingresso Core SHORT: solo se il prezzo attuale stacca sotto KJ tra 2.0 e 6.0 pip
                dist_kj = round(kj - exec_price, 2)
                if CORE_MIN_KJ_DIST_PIPS <= dist_kj <= CORE_MAX_KJ_DIST_PIPS:
                    if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                        self.entry_in_progress = True
                        self.signal_candle_active = False
                        self.signal_stop_price = None
                        self.signal_ref_price = None
                        threading.Thread(
                            target=self._execute_entry_core,
                            args=("SHORT", exec_price, time_str),
                            daemon=True
                        ).start()
                elif dist_kj > CORE_MAX_KJ_DIST_PIPS:
                    print(f"[{time_str}] ⏸️ [CORE SKIP SHORT] Prezzo {exec_price:.2f} troppo distante da KJ {kj:.2f} ({dist_kj:.2f}p > max {CORE_MAX_KJ_DIST_PIPS:.1f}p). Attendo rientro/pullback.")
            elif self.position and self.position["direction"] == "SHORT":
                # Core già SHORT: azzera eventuale Candela Segnale e valuta incremento su pullback
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None
                dist_kj = abs(exec_price - kj)
                troppo_vicino = any(abs(exec_price - inc["open_price"]) < (MIN_DIST_INCR_PIPS - 1e-7) for inc in self.increments)
                if prev_close > prev_open and dist_kj <= MAX_INC_KJ_DISTANCE_PIPS and not troppo_vicino:
                    if len(self.increments) < MAX_INCREMENTS:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            threading.Thread(
                                target=self._execute_entry_increment,
                                args=("SHORT", exec_price, time_str),
                                daemon=True
                            ).start()
            elif self.position and self.position["direction"] == "LONG":
                # Chiusura candela sotto KJ mentre siamo LONG: Candela Segnale ribassista!
                stop_livello = round(closed_candle["low"] - CANDELA_SEGNALE_OFFSET_PIPS, 2)
                if self.signal_candle_active and self.signal_stop_price is not None:
                    if stop_livello < self.signal_stop_price:
                        self.signal_stop_price = stop_livello
                        self.signal_ref_price = closed_candle["low"]
                else:
                    self.signal_candle_active = True
                    self.signal_stop_price = stop_livello
                    self.signal_ref_price = closed_candle["low"]
                self.save_state()

    def _evaluate_unidirectional_strategy(self, closed_candle: dict, kj: float, tk: float, exec_price: float, time_str: str):
        """Metodo di compatibilità legacy"""
        self._evaluate_pure_sr_strategy(closed_candle, kj, exec_price, time_str)

    def _close_all_to_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude la Core e tutti gli incrementi tornando a FLAT su IG tramite chiamate a mercato reali"""
        if getattr(self, "closing_in_progress", False):
            return
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_ref_price = None
        if self.position or self.increments:
            self.closing_in_progress = True
            threading.Thread(
                target=self._execute_close_all_flat,
                args=(exec_price, time_str, reason),
                daemon=True
            ).start()

    def get_floating_pnl(self):
        with self.lock:
            if self.live_mid is None:
                return 0.0
            tot = 0.0
            if self.position:
                if self.position["direction"] == "LONG":
                    tot += (self.live_mid - self.position["open_price"]) * self.position["contracts"] * self.point_value
                else:
                    tot += (self.position["open_price"] - self.live_mid) * self.position["contracts"] * self.point_value

            for inc in self.increments:
                if inc["direction"] == "LONG":
                    tot += (self.live_mid - inc["open_price"]) * inc["contracts"] * self.point_value
                else:
                    tot += (inc["open_price"] - self.live_mid) * inc["contracts"] * self.point_value

            return round(tot, 2)

    def get_total_contracts(self):
        with self.lock:
            c = 0
            if self.position:
                c += self.position.get("contracts", CORE_CONTRACTS)
            for inc in self.increments:
                c += inc.get("contracts", INC_CONTRACTS)
            return c

# Alias di retrocompatibilità
HyperGoldM1Engine = HyperGoldM5Engine
