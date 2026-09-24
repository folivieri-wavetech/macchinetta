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

logger = logging.getLogger("HyperGoldEngine")

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
CANDLE_SECONDS = 30     # 30 Secondi per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi (27.5 min)
STATE_FILE = "hyper_gold_state.json"

# Parametri Strategia: Hyper 30S S&R Puro KJ55 (Posizione unica 10c + Trailing Stop 3p)
CORE_CONTRACTS = 10              # Size ingresso a mercato unico: 10 contratti
TS_STEP_PIPS = 3.0               # Step Trailing Stop discreto: ogni 3 pip di gain lo stop sale/scende di 3 pip
PARACADUTE_KJ_PIPS = 3.0         # Paracadute KJ Intracandela: Stop emergenza live a KJ +- 3 pip
PULLBACK_MAX_DIST_KJ_PIPS = 3.0  # Distanza max da KJ per consentire rientro pullback: <= 3.0 pip
CANDELA_SEGNALE_OFFSET_PIPS = 2.0 # Offset candela segnale di protezione

# Parametri legacy per retrocompatibilità
WARMUP_BARS_TK = 55
PARTIAL_CLOSE_CONTRACTS = 0
RUNNER_CONTRACTS = 10
PARTIAL_TP_PIPS = 0.0
CORE_TS_TRIGGER_PIPS = 3.0
CORE_TS_LOCK_PIPS = 0.0
CORE_TS_DISTANCE_PIPS = 3.0
TK_FILTER_PIPS = 0.0
CORE_REENTRY_KJ_DIST_PIPS = 3.0
INC_CONTRACTS = 0
MAX_INCREMENTS = 0
INC_TP_PIPS = 3.0
DEFAULT_SCALINI_PLAN_30S = []

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
    Dalle 00:00 il feed riapre: Lightstreamer si connette per aggiornare le candele e ricalcolare la KJ55."""
    if dt is None:
        dt = now_it()
    t = dt.time()
    t_start = datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0)
    return t >= t_start

def is_gold_trading_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True se l'operatività/apertura ordini è congelata (dalle 22:44 alle 00:15).
    Alle 22:44 le posizioni vengono chiuse a FLAT automaticamente prima della chiusura del feed delle 22:45.
    Dalle 00:00 alle 00:15 le candele si aggiornano e KJ55 viene calcolata, ma non si aprono ordini."""
    if dt is None:
        dt = now_it()
    t = dt.time()
    t_start = datetime.time(GOLD_TRADE_SUSPEND_START_HOUR, GOLD_TRADE_SUSPEND_START_MIN, 0)
    t_end = datetime.time(GOLD_TRADE_SUSPEND_END_HOUR, GOLD_TRADE_SUSPEND_END_MIN, 0)
    return t >= t_start or t < t_end

def is_gold_market_suspended(dt: datetime.datetime = None) -> bool:
    """Alias retrocompatibile per lo stato operatività congelata"""
    return is_gold_trading_suspended(dt)

class HyperGoldEngine:
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

        # Tracciamento barra corrente da 30s
        self.curr_boundary = None
        self.curr_open = None
        self.curr_high = None
        self.curr_low = None
        self.curr_close = None
        self.curr_bar_start_t = None

        # Storico barre concluse (ultime 500)
        self.candles = []
        self.kj55 = None
        self.tk144 = None

        # Portafoglio e Trading
        self.initial_balance = 10000.0
        self.balance = 10000.0
        self.point_value = 1.0   # 1 EUR per punto/pip per contratto
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False
        self.use_core_trailing = True   # Trailing Stop Core attivo di default (+10 pip trigger, +6 pip lock, 4 pip trail)

        # Configurazione Scalini 30S: Core + Scalini Opzione 2 (Default: Core 4c + [3c@2p, 2c@3p, 2c@4p, 1c@5p])
        self.core_size = CORE_CONTRACTS     # Size Core iniziale: 4
        self.scalini_plan = [dict(x) for x in DEFAULT_SCALINI_PLAN_30S]

        # Posizione Core aperta: None o {"direction": "LONG"/"SHORT", "open_price": float, "contracts": 4, "open_time": str}
        self.position = None

        # Scalini aperti: lista di {"id": int, "direction": str, "open_price": float, "contracts": int, "tp_price": float, "step_idx": int, "tp_dist_pips": float, "open_time": str}
        self.increments = []
        self.inc_tp_pips = INC_TP_PIPS

        # Candela Segnale KJ: Stop confermato su rottura Massimo/Minimo
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_ref_price = None

        # Macchina a Stati Ciclo 30S (1 Trade Primario + Max 1 Rientro Pullback)
        self.cycle_direction = None    # "LONG" / "SHORT" / None
        self.cycle_phase = "IDLE"      # "IDLE", "PRIMARY_OPEN", "PULLBACK_ARMED", "PULLBACK_OPEN", "CYCLE_DONE"

        # Storico eseguiti e stato ultimo ciclo TS
        self.trades = []
        self.last_ts_cycle = None

        # Flag controllo esecuzione ordini reali IG (evita collisioni e ordini multipli)
        self.entry_in_progress = False
        self.closing_in_progress = False
        self.partial_closing_in_progress = False

        # 1. Carica stato persistito
        self.load_state()

        # 2. Se non abbiamo abbastanza barre 30s (meno di 55), scarica subito candele M1 da IG REST e convertile a 30s
        if len(self.candles) < WARMUP_BARS_KJ:
            self._fetch_historical_30s_bars_from_ig()

        # 3. Avvia thread di streaming Lightstreamer in background
        self.stream_thread = threading.Thread(target=self._run_streaming_loop, daemon=True)
        self.stream_thread.start()

    def _fetch_historical_30s_bars_from_ig(self):
        """Scarica barre M1 storiche da IG REST e le converte in barre da 30s per avere subito la KJ55"""
        try:
            user, pwd, api_key = self._get_ig_credentials()
            if not user or not pwd or not api_key:
                return

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

            url_px = f"https://demo-api.ig.com/gateway/deal/prices/{EPIC_GOLD}?resolution=MINUTE&max=180&pageSize=0"
            h_px = {
                "X-IG-API-KEY": api_key,
                "CST": cst,
                "X-SECURITY-TOKEN": xst,
                "Version": "3"
            }
            r_px = requests.get(url_px, headers=h_px, timeout=15)
            if r_px.status_code == 200:
                prices = r_px.json().get("prices", [])
                with self.lock:
                    loaded = []
                    for p in prices:
                        try:
                            st_time = p.get("snapshotTime", "")
                            try:
                                dt_u = datetime.datetime.strptime(st_time, "%Y/%m/%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                                t_str = dt_u.astimezone(TZ_ITALIA).strftime("%H:%M:%S")
                            except Exception:
                                t_str = st_time.split(" ")[1] if " " in st_time else st_time
                            op = round((p["openPrice"]["bid"] + p["openPrice"]["ask"]) / 2.0, 2)
                            hi = round((p["highPrice"]["bid"] + p["highPrice"]["ask"]) / 2.0, 2)
                            lo = round((p["lowPrice"]["bid"] + p["lowPrice"]["ask"]) / 2.0, 2)
                            cl = round((p["closePrice"]["bid"] + p["closePrice"]["ask"]) / 2.0, 2)

                            mid1 = round((op + cl) / 2.0, 2)
                            hi1 = max(op, mid1)
                            lo1 = min(op, mid1)
                            loaded.append({"time": t_str, "open": op, "high": hi1, "low": lo1, "close": mid1})

                            hi2 = max(mid1, cl, hi)
                            lo2 = min(mid1, cl, lo)
                            loaded.append({"time": t_str, "open": mid1, "high": hi2, "low": lo2, "close": cl})
                        except Exception:
                            continue

                    if loaded:
                        self.candles = loaded[-500:]
                        self._recalculate_indicators()
                        self.save_state()
        except Exception:
            pass

    def _recalculate_indicators(self):
        """Calcola KJ55 (Livello S&R Puro) in base allo storico candele a 30s disponibili"""
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
        self.tk144 = None

    def _get_state_file(self):
        if getattr(self, "account_dir", None):
            return os.path.join(self.account_dir, STATE_FILE)
        return STATE_FILE

    def load_state(self):
        st_file = self._get_state_file()
        if not os.path.exists(st_file):
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
            self.candles = d.get("candles", [])
            self.last_ts_cycle = d.get("last_ts_cycle")
            self.core_size = int(d.get("core_size", CORE_CONTRACTS))
            self.scalini_plan = d.get("scalini_plan", [dict(x) for x in DEFAULT_SCALINI_PLAN_30S])
            self.signal_candle_active = bool(d.get("signal_candle_active", False))
            self.signal_stop_price = d.get("signal_stop_price")
            self.signal_ref_price = d.get("signal_ref_price")
            self.cycle_direction = d.get("cycle_direction")
            self.cycle_phase = d.get("cycle_phase", "IDLE")
            self._recalculate_indicators()

    def save_state(self):
        st_file = self._get_state_file()
        with self.lock:
            d = {
                "balance": self.balance,
                "trading_enabled": self.trading_enabled,
                "use_core_trailing": True,
                "core_size": getattr(self, "core_size", CORE_CONTRACTS),
                "scalini_plan": getattr(self, "scalini_plan", [dict(x) for x in DEFAULT_SCALINI_PLAN_30S]),
                "position": self.position,
                "increments": self.increments,
                "inc_tp_pips": self.inc_tp_pips,
                "signal_candle_active": getattr(self, "signal_candle_active", False),
                "signal_stop_price": getattr(self, "signal_stop_price", None),
                "signal_ref_price": getattr(self, "signal_ref_price", None),
                "cycle_direction": getattr(self, "cycle_direction", None),
                "cycle_phase": getattr(self, "cycle_phase", "IDLE"),
                "trades": self.trades[-100:],
                "candles": self.candles[-500:],
                "last_ts_cycle": self.last_ts_cycle
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
            self.last_ts_cycle = None
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

    def update_scalini_plan(self, core_size: int, plan: list):
        """Aggiorna il piano scalini a piramide (es. Opzione 2)"""
        with self.lock:
            self.core_size = max(1, int(core_size))
            self.scalini_plan = list(plan)
            self.save_state()

    def update_scalini_config(self, core_size: int, num_scalini: int, scalino_size: int, step_pips: float = 2.0):
        """Metodo retrocompatibile: genera scalini equidistanti"""
        with self.lock:
            self.core_size = max(1, int(core_size))
            self.scalini_plan = [
                {"step": i, "contracts": max(1, int(scalino_size)), "tp_pips": round(i * float(step_pips), 2)}
                for i in range(1, max(1, int(num_scalini)) + 1)
            ]
            self.save_state()

    def set_trading(self, enabled: bool):
        with self.lock:
            self.trading_enabled = enabled
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            if enabled:
                order_mgr.send_notification("🚀 AVVIO HYPER 30S: Spot Gold", "[Spot Gold] Scalping Hyper 30S attivato.", "rocket")
            else:
                order_mgr.send_notification("⏹️ STOP HYPER 30S: Spot Gold", "[Spot Gold] Scalping Hyper 30S disattivato dall'utente.", "stop_button")
                # Quando l'utente preme STOP TRADING, chiude immediatamente tutte le posizioni aperte a FLAT
                if self.position or self.increments:
                    exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                    t_str = now_it().strftime("%H:%M:%S")
                    self._close_all_to_flat(exec_px, t_str, reason="🛑 STOP TRADING Manuale Utente ➔ Chiusura immediata di tutte le posizioni a FLAT")
            self.save_state()

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

    def _run_streaming_loop(self):
        while self.running:
            try:
                # Durante la chiusura effettiva del feed Gold (22:45 - 00:00) NON effettuiamo chiamate API né login.
                # Dalle 00:00 in poi lo streaming è attivo per aggiornare le candele e ricalcolare la Kijun 55!
                if is_gold_feed_suspended():
                    with self.lock:
                        self.ls_connected = False
                    time.sleep(20)
                    continue

                user, pwd, api_key = self._get_ig_credentials()
                if not user or not pwd or not api_key:
                    time.sleep(5)
                    continue

                # 1. Login REST IG per sessione Lightstreamer
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

                # 2. Connessione client Lightstreamer
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
        """Gestisce il Trailing Stop a gradini discreti di 3 pip sulla posizione da 10 contratti:
        - Gain < 3.0 pip: Nessun Trailing attivo (protezione affidata al Paracadute KJ +-3 pip).
        - Gain >= 3.0 pip (k=1): Stop a Break-Even (open_price, profit locked = +0 pip).
        - Gain >= 6.0 pip (k=2): Stop a +3.0 pip di profitto garantito (+30.00 €).
        - Gain >= 9.0 pip (k=3): Stop a +6.0 pip di profitto garantito (+60.00 €).
        - In generale per k = int(peak_gain // 3.0): profit locked = (k - 1) * 3.0 pip.
        Quando il prezzo tocca o oltrepassa lo stop: chiude immediatamente a FLAT."""
        if not self.position or not getattr(self, "use_core_trailing", True):
            return

        pos = self.position
        direction = pos["direction"]
        open_px = pos["open_price"]

        if direction == "LONG":
            profit_pips = round(current_price - open_px, 2)
        else:
            profit_pips = round(open_px - current_price, 2)

        peak_gain = pos.get("peak_gain_pips", 0.0)
        if profit_pips > peak_gain:
            pos["peak_gain_pips"] = profit_pips
            peak_gain = profit_pips

        k = int(peak_gain // TS_STEP_PIPS)
        if k >= 1:
            profit_locked = (k - 1) * TS_STEP_PIPS
            if direction == "LONG":
                target_ts_px = round(open_px + profit_locked, 2)
                curr_ts_px = pos.get("ts_price")
                if curr_ts_px is None or target_ts_px > curr_ts_px:
                    pos["ts_price"] = target_ts_px
                    pos["ts_active"] = True
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 TRAILING STOP LONG ➔ {target_ts_px:.2f} (Lock +{profit_locked:.0f}p)",
                        "open_price": open_px,
                        "close_price": current_price,
                        "contracts": pos.get("contracts", CORE_CONTRACTS),
                        "pnl": round(profit_pips * pos.get("contracts", CORE_CONTRACTS) * self.point_value, 2),
                        "balance": round(self.balance, 2),
                        "reason": f"Picco +{peak_gain:.1f}p @ {current_price:.2f} ➔ Stop aggiornato a {target_ts_px:.2f} (Lock +{profit_locked:.0f}p)"
                    })
                    self.save_state()
                    order_mgr = HyperOrderManager.get_instance(self.account_dir)
                    order_mgr.send_notification(
                        "🎯 TRAILING STOP 30S: Spot Gold",
                        f"[Spot Gold] Trailing Stop LONG aggiornato a {target_ts_px:.2f} € (Lock +{profit_locked:.0f}p, Prezzo: {current_price:.2f} €)",
                        "dart"
                    )
            else:  # SHORT
                target_ts_px = round(open_px - profit_locked, 2)
                curr_ts_px = pos.get("ts_price")
                if curr_ts_px is None or target_ts_px < curr_ts_px:
                    pos["ts_price"] = target_ts_px
                    pos["ts_active"] = True
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 TRAILING STOP SHORT ➔ {target_ts_px:.2f} (Lock +{profit_locked:.0f}p)",
                        "open_price": open_px,
                        "close_price": current_price,
                        "contracts": pos.get("contracts", CORE_CONTRACTS),
                        "pnl": round(profit_pips * pos.get("contracts", CORE_CONTRACTS) * self.point_value, 2),
                        "balance": round(self.balance, 2),
                        "reason": f"Picco +{peak_gain:.1f}p @ {current_price:.2f} ➔ Stop aggiornato a {target_ts_px:.2f} (Lock +{profit_locked:.0f}p)"
                    })
                    self.save_state()
                    order_mgr = HyperOrderManager.get_instance(self.account_dir)
                    order_mgr.send_notification(
                        "🎯 TRAILING STOP 30S: Spot Gold",
                        f"[Spot Gold] Trailing Stop SHORT aggiornato a {target_ts_px:.2f} € (Lock +{profit_locked:.0f}p, Prezzo: {current_price:.2f} €)",
                        "dart"
                    )

        # Verifica tocco dello stop
        if pos.get("ts_active", False) and pos.get("ts_price") is not None:
            ts_px = pos["ts_price"]
            hit = False
            if direction == "LONG" and current_price <= ts_px:
                hit = True
            elif direction == "SHORT" and current_price >= ts_px:
                hit = True

            if hit:
                self._close_cycle_trailing_hit(current_price, time_str)

    def _execute_entry_sequence(self, direction: str, exec_price: float, time_str: str, label: str = None):
        """Esegue l'apertura a mercato reale su IG di UN UNICO ordine da 10 contratti
        (Hyper 30S: 10c S&R Puro KJ55) con esecuzione uniforme."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            total_sz = CORE_CONTRACTS  # 10 contratti
            lbl = label or f"Hyper 30S ({total_sz}c)"

            res = order_mgr.open_market_deal(
                direction=direction,
                size=total_sz,
                limit_level=None,
                label=lbl
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
                        "contracts": total_sz,
                        "initial_contracts": total_sz,
                        "open_time": res.get("time") or time_str,
                        "ts_active": False,
                        "ts_price": None,
                        "peak_gain_pips": 0.0,
                        "label": lbl
                    }
                    self.increments = []
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 OPEN REAL IG {direction} ({total_sz}c)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": total_sz,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"{lbl} {direction} @ {real_open:.2f} € (Deal ID: {deal_id})"
                    })
                    self.save_state()
                    is_pullback = "Pullback" in lbl
                    tag_ico = "arrows_counterclockwise" if is_pullback else "rocket"
                    titolo_ntfy = f"🔄 OPEN PULLBACK 30S: Spot Gold" if is_pullback else f"🚀 OPEN HYPER 30S: Spot Gold"
                    msg_ntfy = f"[Spot Gold] {lbl} {direction} a {real_open:.2f} €"
                    order_mgr.send_notification(titolo_ntfy, msg_ntfy, tag_ico)
        except Exception as e:
            logger.error(f"Eccezione durante esecuzione ordine IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_close_all_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude a mercato reale la posizione aperta su IG (10 contratti)."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            with self.lock:
                pos_to_close = dict(self.position) if self.position else None
                incs_to_close = [dict(i) for i in self.increments]
                self.position = None
                self.increments = []
                self.save_state()

            # 1. Chiudi la posizione a mercato su IG
            if pos_to_close and pos_to_close.get("deal_id"):
                deal_c = pos_to_close["deal_id"]
                c_lbl = pos_to_close.get("label") or f"Hyper 30S ({pos_to_close.get('contracts', 10)}c)"
                res_c = order_mgr.close_market_deal(
                    deal_id=deal_c,
                    direction_open=pos_to_close["direction"],
                    size=pos_to_close["contracts"],
                    label=c_lbl,
                    reason_note=reason
                )
                prof_c = float(res_c.get("profit") or 0.0)
                cl_c = float(res_c.get("close_level") or exec_price)
                order_mgr.record_closed_trade(
                    tf="30S",
                    direction=pos_to_close["direction"],
                    contracts=pos_to_close["contracts"],
                    open_price=pos_to_close["open_price"],
                    close_price=cl_c,
                    pnl_eur=prof_c,
                    deal_id=deal_c,
                    reason=reason,
                    time_open=pos_to_close.get("open_time", time_str),
                    label=c_lbl
                )
                with self.lock:
                    self.balance += prof_c
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"CLOSE {pos_to_close['direction']} ({prof_c:+.2f} €)",
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
                    tit_cl = "🎯 TS HIT 30S: Spot Gold"
                elif is_rev:
                    tag_cl = "warning"
                    tit_cl = "🛑 REVERSAL 30S: Spot Gold"
                else:
                    tag_cl = "octagonal_sign"
                    tit_cl = "🛑 CHIUSURA FLAT 30S: Spot Gold"
                msg_cl = f"[Spot Gold] {c_lbl} {pos_to_close['direction']} chiuso a {cl_c:.2f} € [PnL: {prof_c:+.2f} €] - Motivo: {reason}"
                order_mgr.send_notification(tit_cl, msg_cl, tag_cl)

            # 2. Chiudi gli scalini residui (se presenti da sessioni precedenti)
            for inc in incs_to_close:
                deal_i = inc.get("deal_id")
                if deal_i:
                    res_i = order_mgr.close_market_deal(
                        deal_id=deal_i,
                        direction_open=inc["direction"],
                        size=inc["contracts"],
                        label=f"Chiusura Scalino #{inc.get('step_idx')}",
                        reason_note=reason
                    )
                    prof_i = float(res_i.get("profit") or 0.0)
                    cl_i = float(res_i.get("close_level") or exec_price)
                    order_mgr.record_closed_trade(
                        tf="30S",
                        direction=inc["direction"],
                        contracts=inc["contracts"],
                        open_price=inc["open_price"],
                        close_price=cl_i,
                        pnl_eur=prof_i,
                        deal_id=deal_i,
                        reason=reason,
                        time_open=inc.get("open_time", time_str),
                        label=f"Scalino #{inc.get('step_idx')}"
                    )
                    with self.lock:
                        self.balance += prof_i
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"CLOSE SCALINO #{inc.get('step_idx')} ({prof_i:+.2f} €)",
                            "open_price": inc["open_price"],
                            "close_price": cl_i,
                            "contracts": inc["contracts"],
                            "pnl": prof_i,
                            "balance": round(self.balance, 2),
                            "reason": reason
                        })
                    time.sleep(1.0)

            with self.lock:
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura posizioni flat IG: {e}")
        finally:
            with self.lock:
                self.closing_in_progress = False

    def _close_cycle_trailing_hit(self, current_price: float, time_str: str):
        """Chiusura completa a FLAT all'entrata del Trailing Stop:
        - Se era il trade Primario (PRIMARY_OPEN): arma il rientro Pullback (PULLBACK_ARMED).
        - Se era già il rientro (PULLBACK_OPEN): conclude il ciclo (CYCLE_DONE)."""
        if not self.position or getattr(self, "closing_in_progress", False):
            return
        with self.lock:
            if self.cycle_phase == "PRIMARY_OPEN":
                self.cycle_phase = "PULLBACK_ARMED"
            elif self.cycle_phase == "PULLBACK_OPEN":
                self.cycle_phase = "CYCLE_DONE"
            self.save_state()

        self.closing_in_progress = True
        threading.Thread(
            target=self._execute_close_all_flat,
            args=(current_price, time_str, f"Trailing Stop 3p toccato @ {current_price:.2f}"),
            daemon=True
        ).start()

    def _check_increments_tp(self, current_price: float, time_str: str):
        """Controlla se qualcuno degli scalini attivi ha toccato il proprio Take Profit scalettato"""
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
                    target=self._execute_close_scalino,
                    args=(inc, current_price, time_str),
                    daemon=True
                ).start()

    def _check_paracadute_kj(self, mid: float, time_str: str):
        """Paracadute KJ Intracandela (Tick-by-Tick):
        Se durante la candela 30s il prezzo sfonda la Kijun 55 oltre il paracadute (3 pip),
        chiude immediatamente all'istante l'intera posizione da 10c a FLAT e conclude il ciclo."""
        if not self.position or self.kj55 is None:
            return

        pos_dir = self.position["direction"]
        if pos_dir == "LONG":
            threshold = round(self.kj55 - PARACADUTE_KJ_PIPS, 2)
            if mid <= threshold:
                with self.lock:
                    self.cycle_phase = "CYCLE_DONE"
                    self.save_state()
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ Intracandela: Mid live {mid:.2f} <= (KJ {self.kj55:.2f} - {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )
        elif pos_dir == "SHORT":
            threshold = round(self.kj55 + PARACADUTE_KJ_PIPS, 2)
            if mid >= threshold:
                with self.lock:
                    self.cycle_phase = "CYCLE_DONE"
                    self.save_state()
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ Intracandela: Mid live {mid:.2f} >= (KJ {self.kj55:.2f} + {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )

    def _check_candela_segnale_stop(self, mid: float, time_str: str):
        """Verifica Stop Conferma Candela Segnale KJ (Tick-by-Tick):
        Se una candela 30s ha chiuso oltre KJ attivando la Candela Segnale,
        ed il prezzo live rompe il livello confermato (Minimo - 2p per LONG, Massimo + 2p per SHORT),
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
                # 1. Verifica Trailing Stop per la posizione 10c (ogni 3 pip di gain -> 3 pip di stop)
                if self.trading_enabled and self.position and getattr(self, "use_core_trailing", True):
                    self._check_core_trailing_stop(mid, time_str)

                # 2. Verifica Take Profit per eventuali incrementi residui
                if self.trading_enabled and self.increments:
                    self._check_increments_tp(mid, time_str)

                # 3. Paracadute KJ Intracandela (3 pip): Chiusura istantanea di sicurezza a FLAT
                if self.trading_enabled and self.position and self.kj55 is not None:
                    self._check_paracadute_kj(mid, time_str)

                # 4. Stop Conferma Candela Segnale KJ (2 pip): Chiusura a rottura confermata
                if self.trading_enabled and self.position and self.signal_candle_active:
                    self._check_candela_segnale_stop(mid, time_str)

            # Inizializzazione prima barra 30s
            if self.curr_boundary is None:
                self.curr_boundary = boundary
                self.curr_open = mid
                self.curr_high = mid
                self.curr_low = mid
                self.curr_close = mid
                self.curr_bar_start_t = now_t
                return

            if boundary == self.curr_boundary:
                # Barra 30s in formazione
                if mid > self.curr_high: self.curr_high = mid
                if mid < self.curr_low: self.curr_low = mid
                self.curr_close = mid
            else:
                # Chiusura barra 30s
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

                # Ricalcolo KJ55 (Livello S&R Puro)
                self._recalculate_indicators()

                # Apertura nuova barra 30s
                new_open = mid
                self.curr_boundary = boundary
                self.curr_open = new_open
                self.curr_high = new_open
                self.curr_low = new_open
                self.curr_close = new_open
                self.curr_bar_start_t = now_t

                self.save_state()

                # Strategia S&R Puro KJ55 (1 Primario + 1 Rientro Pullback): solo se il mercato NON è sospeso
                if self.trading_enabled and not market_suspended and self.kj55 is not None:
                    self._evaluate_sr_strategy(closed_candle, self.kj55, new_open, time_str)

    def _evaluate_sr_strategy(self, closed_candle: dict, kj: float, exec_price: float, time_str: str):
        prev_close = closed_candle["close"]
        prev_open = closed_candle["open"]

        # =============================================================
        # 1. RILEVAMENTO TAGLIO (CROSSOVER) FRESCO DELLA KIJUN 55
        # =============================================================
        # Candela precedente nello storico
        prev_bar_close = self.candles[-2]["close"] if len(self.candles) >= 2 else prev_open

        taglio_kj_long = (prev_close > kj) and (prev_open <= kj or prev_bar_close <= kj)
        taglio_kj_short = (prev_close < kj) and (prev_open >= kj or prev_bar_close >= kj)

        # =============================================================
        # 2. GESTIONE POSIZIONE ESISTENTE: CONTROLLO INVERSIONE O SEGNALE
        # =============================================================
        if self.position:
            pos_dir = self.position["direction"]
            # Se la barra chiude oltre la Kijun in senso opposto -> chiusura immediata e ciclo terminato
            if pos_dir == "LONG" and prev_close < kj:
                with self.lock:
                    self.cycle_phase = "CYCLE_DONE"
                self._close_all_to_flat(exec_price, time_str, reason=f"Inversione S&R: Close {prev_close:.2f} < KJ55 {kj:.2f} ➔ FLAT")
                return

            elif pos_dir == "SHORT" and prev_close > kj:
                with self.lock:
                    self.cycle_phase = "CYCLE_DONE"
                self._close_all_to_flat(exec_price, time_str, reason=f"Inversione S&R: Close {prev_close:.2f} > KJ55 {kj:.2f} ➔ FLAT")
                return

            # Candela Segnale KJ protettiva
            if pos_dir == "LONG":
                if prev_close > kj:
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None
                else:
                    stop_livello = round(closed_candle["low"] - CANDELA_SEGNALE_OFFSET_PIPS, 2)
                    if not self.signal_candle_active or self.signal_stop_price is None or stop_livello < self.signal_stop_price:
                        self.signal_candle_active = True
                        self.signal_stop_price = stop_livello
                        self.signal_ref_price = closed_candle["low"]
                    self.save_state()

            elif pos_dir == "SHORT":
                if prev_close < kj:
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None
                else:
                    stop_livello = round(closed_candle["high"] + CANDELA_SEGNALE_OFFSET_PIPS, 2)
                    if not self.signal_candle_active or self.signal_stop_price is None or stop_livello > self.signal_stop_price:
                        self.signal_candle_active = True
                        self.signal_stop_price = stop_livello
                        self.signal_ref_price = closed_candle["high"]
                    self.save_state()

        # =============================================================
        # 3. GESTIONE INGRESSI QUANDO FLAT (PRIMARIO O PULLBACK)
        # =============================================================
        else:
            # A) TRADE PRIMARIO: Scatta al taglio fresco della KJ55
            if taglio_kj_long:
                if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                    self.entry_in_progress = True
                    self.cycle_direction = "LONG"
                    self.cycle_phase = "PRIMARY_OPEN"
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None
                    self.save_state()
                    threading.Thread(
                        target=self._execute_entry_sequence,
                        args=("LONG", exec_price, time_str, "Hyper 30S (10c: Primario)"),
                        daemon=True
                    ).start()

            elif taglio_kj_short:
                if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                    self.entry_in_progress = True
                    self.cycle_direction = "SHORT"
                    self.cycle_phase = "PRIMARY_OPEN"
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None
                    self.save_state()
                    threading.Thread(
                        target=self._execute_entry_sequence,
                        args=("SHORT", exec_price, time_str, "Hyper 30S (10c: Primario)"),
                        daemon=True
                    ).start()

            # B) TRADE DI RIENTRO PULLBACK (Max 1 rientro per ciclo):
            # Scatta se il Primario è uscito in TS, siamo ancora dalla parte giusta della KJ,
            # il prezzo è entro 3 pip da KJ55 e c'è una candela di rimbalzo/conferma.
            elif self.cycle_phase == "PULLBACK_ARMED":
                if self.cycle_direction == "LONG":
                    if prev_close <= kj:
                        # Ha perso la Kijun: ciclo concluso
                        self.cycle_phase = "CYCLE_DONE"
                        self.save_state()
                    else:
                        dist_kj = round(prev_close - kj, 2)
                        # Candela verde di rimbalzo (close >= open) e distanza da KJ <= 3.0 pip
                        if dist_kj <= PULLBACK_MAX_DIST_KJ_PIPS and prev_close >= prev_open:
                            if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                                self.entry_in_progress = True
                                self.cycle_phase = "PULLBACK_OPEN"
                                self.signal_candle_active = False
                                self.signal_stop_price = None
                                self.signal_ref_price = None
                                self.save_state()
                                threading.Thread(
                                    target=self._execute_entry_sequence,
                                    args=("LONG", exec_price, time_str, "Hyper 30S (10c: Rientro Pullback)"),
                                    daemon=True
                                ).start()

                elif self.cycle_direction == "SHORT":
                    if prev_close >= kj:
                        # Ha perso la Kijun: ciclo concluso
                        self.cycle_phase = "CYCLE_DONE"
                        self.save_state()
                    else:
                        dist_kj = round(kj - prev_close, 2)
                        # Candela rossa di rimbalzo (close <= open) e distanza da KJ <= 3.0 pip
                        if dist_kj <= PULLBACK_MAX_DIST_KJ_PIPS and prev_close <= prev_open:
                            if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                                self.entry_in_progress = True
                                self.cycle_phase = "PULLBACK_OPEN"
                                self.signal_candle_active = False
                                self.signal_stop_price = None
                                self.signal_ref_price = None
                                self.save_state()
                                threading.Thread(
                                    target=self._execute_entry_sequence,
                                    args=("SHORT", exec_price, time_str, "Hyper 30S (10c: Rientro Pullback)"),
                                    daemon=True
                                ).start()

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
                c += self.position.get("contracts", getattr(self, "core_size", CORE_CONTRACTS))
            for inc in self.increments:
                c += inc.get("contracts", getattr(self, "scalino_size", 1))
            return c
