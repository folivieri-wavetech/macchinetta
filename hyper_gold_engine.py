import os
import sys
import ssl
import time
import json
import threading
import datetime
import requests
import logging
from hyper_order_manager import HyperOrderManager

logger = logging.getLogger("HyperGoldEngine")

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
CANDLE_SECONDS = 30     # 30 Secondi per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi
WARMUP_BARS_TK = 144    # Tenkan/Macro 144 periodi
STATE_FILE = "hyper_gold_state.json"
ENV_PATH = os.path.join("FIORDOK_DEMO", ".env")

# Parametri Strategia: Core + Incrementi + Trailing Stop
CORE_CONTRACTS = 2          # Size Core Runner: 2 contratti (Trailing Stop a +10 pip)
CORE_TS_TRIGGER_PIPS = 10.0 # Attivazione Trailing Stop: a +10 pip di guadagno
CORE_TS_LOCK_PIPS = 6.0     # Lock profit iniziale: +6 pip garantiti subito (+12.00 €)
CORE_TS_DISTANCE_PIPS = 4.0 # Distanza trailing: 4 pip continui dal picco massimo/minimo
INC_CONTRACTS = 1           # Incrementi: 1 contratto ciascuno
MAX_INCREMENTS = 8          # 8 scalini x 1c = 8 contratti (Totale 10 con core)
INC_TP_PIPS = 2.0           # TP incrementi su 30S: a partire da 2 pip
KJ_TOLERANCE_PIPS = 2.0     # Tolleranza di 2 pip su rottura Kijun 55
MAX_INC_KJ_DISTANCE_PIPS = 5.0 # Max distanza da KJ per consentire incrementi: <= 5 pip
MIN_DIST_INCR_PIPS = 1.0       # Distanza minima tra incrementi: 1 pip
PARACADUTE_KJ_PIPS = 2.0       # Paracadute KJ Intracandela: Stop emergenza live a KJ +- 2 pip
CANDELA_SEGNALE_OFFSET_PIPS = 2.0 # Candela Segnale: Stop confermato su rottura Massimo/Minimo +- 2 pip
TK_FILTER_PIPS = 3.0              # Filtro Macro TK 144: Conferma cambio direzione a TK +- 3 pip
CORE_REENTRY_KJ_DIST_PIPS = 3.0   # Max distanza da KJ per ingresso/rientro Core 30S: <= 3 pip

# Modello Fast Scalping 30S (Totale 10 Contratti: 4c @ 2p + 4c @ 3p + Core Runner 2c [TS a +10p])
DEFAULT_SCALINI_PLAN_30S = [
    {"step": 1, "contracts": 4, "tp_pips": 2.0},
    {"step": 2, "contracts": 4, "tp_pips": 3.0},
]

# Orari Sospensione Gold:
# 1. Chiusura Feed IG Spot Gold (Nessun tick disponibile dalle 22:45 alle 00:00)
GOLD_FEED_SUSPEND_START_HOUR = 22
GOLD_FEED_SUSPEND_START_MIN = 45

# 2. Congelamento Operatività / Ordini (Dalle 22:45 alle 00:15 per spread/stabilizzazione)
GOLD_TRADE_SUSPEND_START_HOUR = 22
GOLD_TRADE_SUSPEND_START_MIN = 45
GOLD_TRADE_SUSPEND_END_HOUR = 0
GOLD_TRADE_SUSPEND_END_MIN = 15

def is_gold_feed_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True SOLO durante la chiusura reale del feed dati Gold (22:45 - 00:00).
    Dalle 00:00 il feed riapre: Lightstreamer si connette per aggiornare le candele e ricalcolare la KJ55."""
    if dt is None:
        dt = datetime.datetime.now()
    t = dt.time()
    t_start = datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0)
    return t >= t_start

def is_gold_trading_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True se l'operatività/apertura ordini è congelata (dalle 22:45 alle 00:15).
    Dalle 00:00 alle 00:15 le candele si aggiornano e KJ55 viene calcolata, ma non si aprono ordini."""
    if dt is None:
        dt = datetime.datetime.now()
    t = dt.time()
    t_start = datetime.time(GOLD_TRADE_SUSPEND_START_HOUR, GOLD_TRADE_SUSPEND_START_MIN, 0)
    t_end = datetime.time(GOLD_TRADE_SUSPEND_END_HOUR, GOLD_TRADE_SUSPEND_END_MIN, 0)
    return t >= t_start or t < t_end

def is_gold_market_suspended(dt: datetime.datetime = None) -> bool:
    """Alias retrocompatibile per lo stato operatività congelata"""
    return is_gold_trading_suspended(dt)

class HyperGoldEngine:
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls, account_dir: str = None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(account_dir=account_dir)
            elif account_dir:
                cls._instance.account_dir = account_dir
            return cls._instance

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

        # Storico eseguiti e stato ultimo ciclo TS
        self.trades = []
        self.last_ts_cycle = None

        # Flag controllo esecuzione ordini reali IG (evita collisioni e ordini multipli)
        self.entry_in_progress = False
        self.closing_in_progress = False

        # 1. Carica stato persistito
        self.load_state()

        # 2. Se non abbiamo abbastanza barre 30s (meno di 144), scarica subito candele M1 da IG REST e convertile a 30s
        if len(self.candles) < WARMUP_BARS_TK:
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
        """Calcola KJ55 e TK144 in base allo storico candele a 30s disponibili"""
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

        if n >= WARMUP_BARS_TK:
            sub_tk = self.candles[-WARMUP_BARS_TK:]
            max_h_tk = max(c["high"] for c in sub_tk)
            min_l_tk = min(c["low"] for c in sub_tk)
            self.tk144 = round((max_h_tk + min_l_tk) / 2.0, 2)
            if self.candles:
                self.candles[-1]["tk144"] = self.tk144
        else:
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
            if not enabled:
                # Quando l'utente preme STOP TRADING, chiude immediatamente tutte le posizioni aperte a FLAT
                if self.position or self.increments:
                    exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                    t_str = datetime.datetime.now().strftime("%H:%M:%S")
                    self._close_all_to_flat(exec_px, t_str, reason="🛑 STOP TRADING Manuale Utente ➔ Chiusura immediata di tutte le posizioni a FLAT")
            self.save_state()

    def _get_ig_credentials(self):
        user, pwd, api_key = None, None, None
        candidates = []
        if getattr(self, "account_dir", None):
            candidates.append(os.path.join(self.account_dir, ".env"))
        candidates.append(ENV_PATH)
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
                    ask_s = vals.get("OFFER")
                    # Orario locale italiano (Roma UTC+2/UTC+1) per storico ed eseguiti
                    t_str = datetime.datetime.now().strftime("%H:%M:%S")
                    if bid_s and ask_s:
                        try:
                            b = float(bid_s)
                            a = float(ask_s)
                            self._process_tick(b, a, t_str)
                        except Exception:
                            pass

                sub = LightstreamerSubscription(
                    mode="MERGE",
                    items=[f"MARKET:{EPIC_GOLD}"],
                    fields=["BID", "OFFER", "HIGH", "LOW", "UPDATE_TIME"]
                )
                sub.addlistener(on_tick)
                ls_client.subscribe(sub)

                while self.running and self.ls_connected:
                    time.sleep(2)
                    if self.last_tick_time and (time.time() - self.last_tick_time) > 40:
                        break

            except Exception:
                pass
            finally:
                with self.lock:
                    self.ls_connected = False
                time.sleep(5)

    def _check_core_trailing_stop(self, current_price: float, time_str: str):
        """Gestisce il Trailing Stop sulla posizione Core:
        1. A +10 pip attiva il TS e piazza il lock a +7 pip garantiti.
        2. Segue il prezzo a 3 pip dal picco massimo (Long) o minimo (Short).
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
                pos["ts_distance"] = CORE_TS_DISTANCE_PIPS
                if direction == "LONG":
                    pos["ts_price"] = round(open_px + CORE_TS_LOCK_PIPS, 2)
                else:
                    pos["ts_price"] = round(open_px - CORE_TS_LOCK_PIPS, 2)

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🚀 TRAILING ATTIVATO {direction}",
                    "open_price": open_px,
                    "close_price": current_price,
                    "contracts": pos["contracts"],
                    "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                    "balance": round(self.balance, 2),
                    "reason": f"Raggiunti +{profit_pips:.1f} pip @ {current_price:.2f} ➔ Lock +{CORE_TS_LOCK_PIPS:.1f} pip @ {pos['ts_price']:.2f}, Trail {CORE_TS_DISTANCE_PIPS:.1f} pip (dinamico +1p ogni 10p)"
                })
                self.save_state()

        # 2. Aggiornamento dinamico del Trailing e verifica tocco
        if pos.get("ts_active", False):
            peak_px = pos.get("peak_price", current_price)

            if direction == "LONG":
                # Nuovo picco massimo
                if current_price > peak_px:
                    pos["peak_price"] = current_price
                    peak_px = current_price

                # Calcolo distanza dinamica: +1 pip ogni 10 pip oltre il trigger (+10 pip)
                # Es. 10-19.9p: 4p | 20-29.9p: 5p | 30-39.9p: 6p ...
                peak_gain = max(0.0, peak_px - open_px)
                extra_dist = max(0, int((peak_gain - CORE_TS_TRIGGER_PIPS) // 10.0))
                current_ts_dist = CORE_TS_DISTANCE_PIPS + float(extra_dist)
                pos["ts_distance"] = current_ts_dist

                new_ts = round(peak_px - current_ts_dist, 2)
                if new_ts > pos.get("ts_price", 0.0):
                    pos["ts_price"] = new_ts

                # Verifica tocco Trailing Stop
                if current_price <= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

            else: # SHORT
                # Nuovo picco minimo
                if current_price < peak_px:
                    pos["peak_price"] = current_price
                    peak_px = current_price

                # Calcolo distanza dinamica: +1 pip ogni 10 pip oltre il trigger (+10 pip)
                # Es. 10-19.9p: 4p | 20-29.9p: 5p | 30-39.9p: 6p ...
                peak_gain = max(0.0, open_px - peak_px)
                extra_dist = max(0, int((peak_gain - CORE_TS_TRIGGER_PIPS) // 10.0))
                current_ts_dist = CORE_TS_DISTANCE_PIPS + float(extra_dist)
                pos["ts_distance"] = current_ts_dist

                new_ts = round(peak_px + current_ts_dist, 2)
                if new_ts < pos.get("ts_price", 999999.0):
                    pos["ts_price"] = new_ts

                # Verifica tocco Trailing Stop
                if current_price >= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

    def _execute_entry_sequence(self, direction: str, exec_price: float, time_str: str):
        """Esegue l'apertura a mercato reale su IG dei 3 blocchi (Scalino 1, Scalino 2, Core Runner)
        in un thread separato senza bloccare il flusso Lightstreamer, rispettando il pacing di sicurezza."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            plan = getattr(self, "scalini_plan", DEFAULT_SCALINI_PLAN_30S)
            c_sz = getattr(self, "core_size", CORE_CONTRACTS)

            # 1. Apertura blocchi scalini a mercato
            for it in plan:
                st_idx = it["step"]
                st_sz = it["contracts"]
                st_tp_dist = it["tp_pips"]
                tp_px = round(exec_price + st_tp_dist if direction == "LONG" else exec_price - st_tp_dist, 2)

                res = order_mgr.open_market_deal(
                    direction=direction,
                    size=st_sz,
                    limit_level=tp_px,
                    label=f"Scalino #{st_idx} (30S)"
                )
                if res.get("success"):
                    deal_id = res.get("deal_id")
                    real_open = float(res.get("level") or exec_price)
                    with self.lock:
                        self.increments.append({
                            "id": int(time.time() * 1000) + st_idx,
                            "deal_id": deal_id,
                            "deal_reference": res.get("deal_reference"),
                            "direction": direction,
                            "open_price": real_open,
                            "contracts": st_sz,
                            "tp_price": tp_px,
                            "tp_dist_pips": st_tp_dist,
                            "step_idx": st_idx,
                            "open_time": res.get("time") or time_str
                        })
                        self.save_state()

            # 2. Apertura blocco Core Runner
            res_core = order_mgr.open_market_deal(
                direction=direction,
                size=c_sz,
                limit_level=None,
                label="Core Runner (30S)"
            )
            if res_core.get("success"):
                deal_id_c = res_core.get("deal_id")
                real_open_c = float(res_core.get("level") or exec_price)
                with self.lock:
                    self.position = {
                        "deal_id": deal_id_c,
                        "deal_reference": res_core.get("deal_reference"),
                        "direction": direction,
                        "open_price": real_open_c,
                        "contracts": c_sz,
                        "open_time": res_core.get("time") or time_str,
                        "ts_active": False,
                        "ts_price": None,
                        "peak_price": real_open_c
                    }
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 OPEN REAL IG {direction} ({c_sz}c Core + Scalini)",
                        "open_price": real_open_c,
                        "close_price": None,
                        "contracts": c_sz,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Ingresso IG Reale {direction} @ {real_open_c:.2f} € (Deal ID Core: {deal_id_c})"
                    })
                    self.save_state()
        except Exception as e:
            logger.error(f"Eccezione durante esecuzione ordine IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_close_scalino(self, inc: dict, current_price: float, time_str: str):
        """Chiude a mercato reale un singolo scalino quando tocca il Take Profit."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            deal_id = inc.get("deal_id")
            res = order_mgr.close_market_deal(
                deal_id=deal_id,
                direction_open=inc["direction"],
                size=inc["contracts"],
                label=f"TP Scalino #{inc.get('step_idx')}",
                reason_note=f"Raggiunto TP a +{inc.get('tp_dist_pips', 0):.1f}p @ {current_price:.2f}"
            )
            profit = float(res.get("profit") or 0.0)
            close_px = float(res.get("close_level") or current_price)

            with self.lock:
                # Rimuovi l'incremento chiuso
                self.increments = [i for i in self.increments if i.get("deal_id") != deal_id and i.get("id") != inc.get("id")]
                self.balance += profit

                # Registra trade nello storico di Sintesi
                order_mgr.record_closed_trade(
                    tf="30S",
                    direction=inc["direction"],
                    contracts=inc["contracts"],
                    open_price=inc["open_price"],
                    close_price=close_px,
                    pnl_eur=profit,
                    deal_id=deal_id,
                    reason=f"TP Scalino #{inc.get('step_idx')} (+{inc.get('tp_dist_pips', 0):.1f}p)",
                    time_open=inc.get("open_time", time_str),
                    label=f"Scalino #{inc.get('step_idx')}"
                )

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🎯 TP SCALINO #{inc.get('step_idx')} {inc['direction']} (+{profit:+.2f} €)",
                    "open_price": inc["open_price"],
                    "close_price": close_px,
                    "contracts": inc["contracts"],
                    "pnl": profit,
                    "balance": round(self.balance, 2),
                    "reason": f"Chiusura IG Deal {deal_id}: TP raggiunto @ {close_px:.2f}"
                })
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura scalino IG: {e}")

    def _execute_close_all_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude a mercato reale tutte le posizioni aperte su IG (Core + Scalini)."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            with self.lock:
                pos_to_close = dict(self.position) if self.position else None
                incs_to_close = [dict(i) for i in self.increments]
                self.position = None
                self.increments = []
                self.save_state()

            # 1. Chiudi la Core se presente
            if pos_to_close and pos_to_close.get("deal_id"):
                deal_c = pos_to_close["deal_id"]
                res_c = order_mgr.close_market_deal(
                    deal_id=deal_c,
                    direction_open=pos_to_close["direction"],
                    size=pos_to_close["contracts"],
                    label="Chiusura Core Flat",
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
                    label="Core Runner"
                )
                with self.lock:
                    self.balance += prof_c
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"CLOSE CORE {pos_to_close['direction']} ({prof_c:+.2f} €)",
                        "open_price": pos_to_close["open_price"],
                        "close_price": cl_c,
                        "contracts": pos_to_close["contracts"],
                        "pnl": prof_c,
                        "balance": round(self.balance, 2),
                        "reason": reason
                    })

            # 2. Chiudi gli scalini residui
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

            with self.lock:
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura posizioni flat IG: {e}")
        finally:
            with self.lock:
                self.closing_in_progress = False

    def _close_cycle_trailing_hit(self, current_price: float, time_str: str):
        """Chiusura completa a FLAT all'entrata del Trailing Stop"""
        if not self.position or getattr(self, "closing_in_progress", False):
            return
        self.closing_in_progress = True
        threading.Thread(
            target=self._execute_close_all_flat,
            args=(current_price, time_str, f"Trailing Stop toccato @ {current_price:.2f}"),
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

            # Verifica sospensione notturna Gold (22:45 - 00:15)
            market_suspended = is_gold_market_suspended()

            if market_suspended:
                # Se è scattata l'ora di sospensione con posizioni ancora aperte, le chiudiamo a FLAT di sicurezza
                if self.position or self.increments:
                    self._close_all_to_flat(mid, time_str, reason="Sospensione Notturna Gold (22:45 - 00:15) ➔ Chiusura automatica di sicurezza a FLAT")
            else:
                # 1. Verifica Trailing Stop per la Core (Attivo di default: Trigger +10p, Lock +6p, Trail 4p)
                if self.trading_enabled and self.position and getattr(self, "use_core_trailing", True):
                    self._check_core_trailing_stop(mid, time_str)

                # 2. Verifica Take Profit (2 pip) per gli incrementi aperti (Bancomat continuo)
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
                    "time": datetime.datetime.fromtimestamp(self.curr_boundary).strftime("%H:%M:%S"),
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

                # Strategia Unidirezionale TK144 + Trigger KJ55: solo se il mercato NON è sospeso
                if self.trading_enabled and not market_suspended and self.kj55 is not None and self.tk144 is not None:
                    self._evaluate_unidirectional_strategy(closed_candle, self.kj55, self.tk144, new_open, time_str)

    def _evaluate_unidirectional_strategy(self, closed_candle: dict, kj: float, tk: float, exec_price: float, time_str: str):
        prev_close = closed_candle["close"]
        prev_open = closed_candle["open"]

        tk_bullish_threshold = round(tk + TK_FILTER_PIPS, 2)
        tk_bearish_threshold = round(tk - TK_FILTER_PIPS, 2)

        # =============================================================
        # 1. CONTROLLO INVERSIONE MACRO SU POSIZIONI ESISTENTI (FILTRO 3 PIP)
        # =============================================================
        if self.position and self.position["direction"] == "SHORT" and prev_close > tk_bullish_threshold:
            self._close_all_to_flat(exec_price, time_str, reason=f"Inversione Macro: Close {prev_close:.2f} > (TK144 {tk:.2f} + {TK_FILTER_PIPS:.0f}p = {tk_bullish_threshold:.2f})")

        elif self.position and self.position["direction"] == "LONG" and prev_close < tk_bearish_threshold:
            self._close_all_to_flat(exec_price, time_str, reason=f"Inversione Macro: Close {prev_close:.2f} < (TK144 {tk:.2f} - {TK_FILTER_PIPS:.0f}p = {tk_bearish_threshold:.2f})")

        # =============================================================
        # 2. GESTIONE OPERATIVA SECONDO IL REGIME
        # =============================================================
        # A) REGIME BULLISH (Close > TK144 + 3 pip) o POSIZIONE LONG RESIDUA (non ancora invertita)
        if prev_close > tk_bullish_threshold or (self.position and self.position["direction"] == "LONG"):
            if prev_close > kj:
                if self.position is None and prev_close > tk_bullish_threshold:
                    # Verifica condizione rientro Core LONG:
                    # Solo se il prezzo è riavvicinato a KJ (pullback entro CORE_REENTRY_KJ_DIST_PIPS, 3 pip su 30S)
                    dist_kj = abs(exec_price - kj)
                    if dist_kj <= CORE_REENTRY_KJ_DIST_PIPS:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            self.signal_candle_active = False
                            self.signal_stop_price = None
                            self.signal_ref_price = None
                            threading.Thread(
                                target=self._execute_entry_sequence,
                                args=("LONG", exec_price, time_str),
                                daemon=True
                            ).start()
                elif self.position and self.position["direction"] == "LONG":
                    # Core già LONG: azzera eventuale Candela Segnale. Nessun incremento successivo (già tutti aperti alla partenza)
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None

            else:
                # prev_close <= kj in Regime Bullish: Candela Segnale se siamo LONG!
                # Non chiude subito all'Open: imposta stop confermato su Minimo - 3 pip
                if self.position and self.position["direction"] == "LONG":
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

        # B) REGIME BEARISH (Close < TK144 - 3 pip) o POSIZIONE SHORT RESIDUA (non ancora invertita)
        elif prev_close < tk_bearish_threshold or (self.position and self.position["direction"] == "SHORT"):
            if prev_close < kj:
                if self.position is None and prev_close < tk_bearish_threshold:
                    # Verifica condizione rientro Core SHORT:
                    # Solo se il prezzo è riavvicinato a KJ (pullback entro CORE_REENTRY_KJ_DIST_PIPS, 3 pip su 30S)
                    dist_kj = abs(exec_price - kj)
                    if dist_kj <= CORE_REENTRY_KJ_DIST_PIPS:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            self.signal_candle_active = False
                            self.signal_stop_price = None
                            self.signal_ref_price = None
                            threading.Thread(
                                target=self._execute_entry_sequence,
                                args=("SHORT", exec_price, time_str),
                                daemon=True
                            ).start()
                elif self.position and self.position["direction"] == "SHORT":
                    # Core già SHORT: azzera eventuale Candela Segnale. Nessun incremento successivo
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None

            else:
                # prev_close >= kj in Regime Bearish: Candela Segnale se siamo SHORT!
                # Non chiude subito all'Open: imposta stop confermato su Massimo + 3 pip
                if self.position and self.position["direction"] == "SHORT":
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
