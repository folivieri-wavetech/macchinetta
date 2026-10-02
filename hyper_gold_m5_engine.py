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
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [HYPER_GOLD_M5] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra
STATE_FILE = "hyper_gold_m5_state.json"

# Parametri Operativi Apex Swing M5
CORE_CONTRACTS = 10         # Totale 10 contratti (5 Bancomat + 5 Runner)
BANCOMAT_CONTRACTS = 5      # 5 contratti Bancomat (TP1 rapido a R:R 1:1 o 20 pip)
RUNNER_CONTRACTS = 5        # 5 contratti Runner (Trailing Stop strutturale sui minimi/massimi crescenti)

TP1_DEFAULT_PIPS = 5.0      # Take Profit Bancomat rapido M5: +5 pip (+25.00 € con 5 contratti)
RUNNER_MAX_GIVEBACK_PIPS = 7.0  # Trailing dal massimo/minimo battuto: max 7 pip di escursione
CANDLE_BUFFER_PIPS = 2.0        # Cuscinetto sotto/sopra la candela M5 precedente
SL_BUFFER_PIPS = 3.0        # Cuscinetto oltre il pivot strutturale: 3 pip
SL_MIN_PIPS = 10.0          # Stop Loss minimo di protezione: 10 pip
SL_MAX_PIPS = 35.0          # Stop Loss massimo invalicabile (cap di sicurezza): 35 pip
BE_EXTRA_LOCK_PIPS = 1.0    # Lock sopra il breakeven a protezione spread (+1 pip)

# Costanti di compatibilità per UI dashboard (hyper_tab)
WARMUP_BARS_KJ = 55
WARMUP_BARS_TK = 21
CORE_TS_TRIGGER_PIPS = 10.0
INC_CONTRACTS = 5           # 5 contratti per ciascun incremento Speed (Speed 1, Speed 2)
MAX_SPEED_INCREMENTS = 2    # Massimo 2 incrementi Speed attivi (totale massimo 20 contratti su Gold)
MAX_INCREMENTS = 2
SPEED_TP_PIPS = 4.0         # Take Profit rapido per incrementi Speed (+4.0 pip = +20.00 € su 5c)
INC_TP_PIPS = 4.0
CANDELA_SEGNALE_OFFSET_PIPS = 5.0
TK_FILTER_PIPS = 50.0

# Orari Sospensione Gold:
GOLD_FEED_SUSPEND_START_HOUR = 23
GOLD_FEED_SUSPEND_START_MIN = 0
GOLD_TRADE_SUSPEND_START_HOUR = 22
GOLD_TRADE_SUSPEND_START_MIN = 44
GOLD_TRADE_SUSPEND_END_HOUR = 0
GOLD_TRADE_SUSPEND_END_MIN = 15

def is_gold_feed_suspended(dt: datetime.datetime = None) -> bool:
    if dt is None: dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    if wd in (0, 1, 2, 3) and t >= datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0):
        return True
    return False

def is_gold_trading_suspended(dt: datetime.datetime = None) -> bool:
    if dt is None: dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(22, 44, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    t_start = datetime.time(GOLD_TRADE_SUSPEND_START_HOUR, GOLD_TRADE_SUSPEND_START_MIN, 0)
    t_end = datetime.time(GOLD_TRADE_SUSPEND_END_HOUR, GOLD_TRADE_SUSPEND_END_MIN, 0)
    return t >= t_start or t < t_end

def is_gold_entry_suspended(dt: datetime.datetime = None) -> bool:
    if dt is None: dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(22, 14, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    return is_gold_trading_suspended(dt)

# ==============================================================================
# ALGORITMI PRICE ACTION & INDICATORI APEX SWING M5
# ==============================================================================

def calculate_ema(values, period):
    if not values or len(values) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1.0 - k)
    return ema

def calculate_atr(candles, period=14):
    if not candles or len(candles) < period + 1:
        return 15.0  # Fallback ragionevole per Gold M5 (15 pip)
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return sum(trs[-period:]) / float(period)

def find_swings(candles, left=2, right=1):
    """Individua i Pivot High e Pivot Low sulle candele M5."""
    high_pivots = []
    low_pivots = []
    n = len(candles)
    for i in range(left, n - right):
        h = candles[i]["high"]
        l = candles[i]["low"]
        is_high = all(candles[i - j]["high"] <= h for j in range(1, left + 1)) and all(candles[i + j]["high"] <= h for j in range(1, right + 1))
        is_low = all(candles[i - j]["low"] >= l for j in range(1, left + 1)) and all(candles[i + j]["low"] >= l for j in range(1, right + 1))
        if is_high:
            high_pivots.append({"index": i, "time": candles[i].get("time", ""), "price": h})
        if is_low:
            low_pivots.append({"index": i, "time": candles[i].get("time", ""), "price": l})
    return high_pivots, low_pivots

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
        self.epic = EPIC_GOLD
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

        # Storico barre concluse M5
        self.candles = []

        # Semaforo a 3 Lucette (Stato Real-Time: Struttura, Trigger, Spinta EMA)
        self.traffic_light = {
            "l1_structure": {"status": False, "dir": "NEUTRAL", "desc": "Analisi Swings in corso..."},
            "l2_trigger": {"status": False, "dir": "NEUTRAL", "desc": "In attesa di breakout..."},
            "l3_momentum": {"status": False, "dir": "NEUTRAL", "desc": "Calcolo Spinta & Flow EMA..."},
            "direction": "NEUTRAL",
            "all_green": False,
            "last_pivot_high": None,
            "last_pivot_low": None,
            "atr": 15.0,
            "ema8": None,
            "ema21": None
        }

        # Portafoglio e Trading
        self.initial_balance = 10000.0
        self.balance = 10000.0
        self.point_value = 1.0   # 1 EUR per pip su Gold
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False

        # Posizione Aperta (Bancomat + Runner)
        # Formato: {"direction": "LONG"/"SHORT", "open_price": float, "contracts": 6,
        #           "deal_id_bancomat": str, "deal_id_runner": str, "tp1_price": float,
        #           "sl_price": float, "open_time": str, "tp1_hit": bool, "runner_sl": float}
        self.position = None

        # Retrocompatibilità interfaccia dashboard
        self.increments = []
        self.trades = []
        self.last_ts_cycle = None
        self.entry_in_progress = False
        self.closing_in_progress = False

        # 1. Carica stato persistente
        self.load_state()

        # 2. Sincronizzazione candele M5 da IG REST o cache locale all'avvio
        self._load_initial_m5_candles()

        # 3. Avvia thread di streaming Lightstreamer in background
        self.stream_thread = threading.Thread(target=self._run_streaming_loop, daemon=True)
        self.stream_thread.start()

        # 4. Avvia watchdog rollover
        self.watchdog_thread = threading.Thread(target=self._run_rollover_watchdog, daemon=True)
        self.watchdog_thread.start()

    def _get_state_file(self):
        if self.account_dir:
            return os.path.join(self.account_dir, STATE_FILE)
        return STATE_FILE

    def load_state(self):
        st_file = self._get_state_file()
        if os.path.exists(st_file):
            try:
                with open(st_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self.balance = float(d.get("balance", self.initial_balance))
                    self.trading_enabled = bool(d.get("trading_enabled", False))
                    self.position = d.get("position")
                    self.increments = d.get("increments", [])
                    self.trades = d.get("trades", [])
                    if "candles" in d and isinstance(d["candles"], list):
                        self.candles = d["candles"][-500:]
                    if "traffic_light" in d:
                        self.traffic_light.update(d["traffic_light"])
                    self._last_disk_mtime = os.path.getmtime(st_file)
            except Exception as e:
                logger.warning(f"Errore caricamento stato {st_file}: {e}")

    def sync_state_from_disk_if_needed(self):
        """Ricarica istantaneamente la posizione se il file di stato su disco è stato modificato esternamente."""
        st_file = self._get_state_file()
        if os.path.exists(st_file):
            try:
                mtime = os.path.getmtime(st_file)
                if getattr(self, "_last_disk_mtime", 0.0) < mtime:
                    self._last_disk_mtime = mtime
                    with open(st_file, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    with self.lock:
                        self.position = d.get("position")
                        self.increments = d.get("increments", [])
                        self.trading_enabled = bool(d.get("trading_enabled", self.trading_enabled))
            except Exception:
                pass

    def reconcile_with_ig_deals(self):
        """Verifica se i deal registrati in posizione sono ancora realmente aperti su IG. Se chiusi, resetta a FLAT."""
        with self.lock:
            if not self.position or self.closing_in_progress:
                return
            deal_run = self.position.get("deal_id_runner")
            deal_banc = self.position.get("deal_id_bancomat")
            tp1_hit = self.position.get("tp1_hit", False)
            active_incs = list(self.increments)

        order_mgr = HyperOrderManager.get_instance(self.account_dir)
        run_open = order_mgr.is_deal_open(deal_run) if deal_run else False
        banc_open = order_mgr.is_deal_open(deal_banc) if (deal_banc and not tp1_hit) else False

        # Verifica deal incrementi
        surviving_incs = []
        for inc in active_incs:
            d_id = inc.get("deal_id")
            if d_id and order_mgr.is_deal_open(d_id):
                surviving_incs.append(inc)
            else:
                logger.info(f"ℹ️ [RECONCILE IG SPOT GOLD] Deal incremento {inc.get('label')} ({d_id}) non aperto su IG. Rimosso.")

        with self.lock:
            self.increments = surviving_incs

        if not run_open and not banc_open and not surviving_incs:
            logger.info(f"ℹ️ [RECONCILE IG SPOT GOLD] I deal {deal_banc} e {deal_run} non risultano più aperti su IG. Reset immediato a FLAT.")
            with self.lock:
                self.position = None
                self.increments = []
                self.save_state()
        elif len(surviving_incs) != len(active_incs):
            with self.lock:
                self.save_state()

    def save_state(self):
        st_file = self._get_state_file()
        with self.lock:
            d = {
                "balance": self.balance,
                "trading_enabled": self.trading_enabled,
                "position": self.position,
                "increments": self.increments,
                "traffic_light": self.traffic_light,
                "trades": self.trades[-100:],
                "candles": self.candles[-500:]
            }
            for _ in range(5):
                try:
                    with open(st_file, "w", encoding="utf-8") as f:
                        json.dump(d, f, indent=2, ensure_ascii=False)
                        f.flush()
                    self._last_disk_mtime = os.path.getmtime(st_file)
                    break
                except Exception:
                    time.sleep(0.05)

    @property
    def semaforo(self):
        """Espone lo stato del semaforo per la Dashboard e moduli esterni."""
        with self.lock:
            tl = getattr(self, "traffic_light", {})
            return {
                "L1_structure": tl.get("l1_structure", {}).get("status", False),
                "L2_trigger": tl.get("l2_trigger", {}).get("status", False),
                "L3_momentum": tl.get("l3_momentum", {}).get("status", False),
                "L3_volatility": True,  # Retrocompatibilità
                "L4_momentum": tl.get("l3_momentum", {}).get("status", False),  # Retrocompatibilità
                "bias": tl.get("direction", "NEUTRAL"),
                "all_green": tl.get("all_green", False),
                "desc_l1": tl.get("l1_structure", {}).get("desc", ""),
                "desc_l2": tl.get("l2_trigger", {}).get("desc", ""),
                "desc_l3": tl.get("l3_momentum", {}).get("desc", "")
            }

    def _load_initial_m5_candles(self):
        """Carica storico M5 locale."""
        candidates = [
            f"candele_Spot_Gold_MINUTE_5.json",
            os.path.join(self.account_dir or "", "candele_Spot_Gold_MINUTE_5.json"),
            os.path.join("Logs_e_Cache", "candele_Spot_Gold_MINUTE_5.json")
        ]
        for p in candidates:
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list) and len(data) >= 20:
                            conv = []
                            for c in data:
                                o = c.get("openPrice", {}).get("bid") or c.get("open")
                                h = c.get("highPrice", {}).get("bid") or c.get("high")
                                l = c.get("lowPrice", {}).get("bid") or c.get("low")
                                cl = c.get("closePrice", {}).get("bid") or c.get("close")
                                t_s = c.get("snapshotTime", "")[11:19]
                                if all(x is not None for x in (o, h, l, cl)):
                                    conv.append({"time": t_s, "open": float(o), "high": float(h), "low": float(l), "close": float(cl)})
                            if conv:
                                self.candles = conv[-500:]
                                logger.info(f"Caricate {len(self.candles)} candele M5 iniziali per Spot Gold.")
                                self._evaluate_traffic_lights(now_it().strftime("%H:%M:%S"))
                                return
                except Exception:
                    pass

    def set_trading(self, enabled: bool):
        with self.lock:
            self.trading_enabled = enabled
            logger.info(f"🚦 [COMANDO UTENTE] Trading Hyper M5 impostato a: {'🟢 AVVIATO' if enabled else '🔴 STOP'}")
            if not enabled and self.position:
                exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                t_str = now_it().strftime("%H:%M:%S")
                self._close_all_to_flat(exec_px, t_str, reason="🛑 STOP TRADING Manuale Utente ➔ Chiusura a FLAT")
            self.save_state()

    def reset_portfolio(self):
        with self.lock:
            self.balance = self.initial_balance
            self.position = None
            self.trades = []
            self.save_state()

    def clear_session_trades(self):
        with self.lock:
            self.trades = []
            self.save_state()

    # ==============================================================================
    # MOTORE DI VALUTAZIONE: LE 4 LUCETTE (SEMAFORO APEX)
    # ==============================================================================

    def _evaluate_traffic_lights(self, time_str: str, on_candle_close: bool = False):
        """Valuta in tempo reale le 3 Lucette di Confluenza su M5 (L1 Struttura, L2 Breakout, L3 Spinta EMA)."""
        if len(self.candles) < 20:
            return

        recent_candles = self.candles[-35:]
        closes = [c["close"] for c in recent_candles]
        curr_c = recent_candles[-1]
        prev_c = recent_candles[-2] if len(recent_candles) >= 2 else curr_c

        # 1. Calcolo Indicatori di Supporto
        atr = calculate_atr(recent_candles, period=14)
        ema8 = calculate_ema(closes, period=8)
        ema21 = calculate_ema(closes, period=21)
        prev_ema8 = calculate_ema(closes[:-1], period=8)

        # 2. Calcolo Swings Strutturali (Williams Fractals)
        high_pivots, low_pivots = find_swings(recent_candles, left=2, right=1)
        last_ph = high_pivots[-1]["price"] if high_pivots else None
        prev_ph = high_pivots[-2]["price"] if len(high_pivots) >= 2 else None
        last_pl = low_pivots[-1]["price"] if low_pivots else None
        prev_pl = low_pivots[-2]["price"] if len(low_pivots) >= 2 else None

        live_px = self.live_mid or curr_c["close"]
        body = abs(curr_c["close"] - curr_c["open"])
        c_range = max(curr_c["high"] - curr_c["low"], 0.01)
        body_ratio = body / c_range

        # -------------------------------------------------------------
        # LUCETTA 1: STRUTTURA DI MERCATO (Swings Classici O Micro-Trend 2+ Candele Direzionali)
        # -------------------------------------------------------------
        l1_long = False
        l1_short = False
        l1_desc = "Struttura laterale / Neutra"

        # A) Analisi Swings Frattali (con protezione contro la trappola del vecchio massimo/minimo)
        if last_ph and prev_ph and last_pl and prev_pl:
            if last_ph > prev_ph and last_pl > prev_pl and (ema21 is None or live_px >= ema21):
                l1_long = True
                l1_desc = f"Rialzista: HH {last_ph:.1f} > {prev_ph:.1f} | HL {last_pl:.1f} > {prev_pl:.1f}"
            elif last_ph < prev_ph and last_pl < prev_pl and (ema21 is None or live_px <= ema21):
                l1_short = True
                l1_desc = f"Ribassista: LH {last_ph:.1f} < {prev_ph:.1f} | LL {last_pl:.1f} < {prev_pl:.1f}"
            elif last_pl < prev_pl and (ema8 is None or live_px <= ema8):
                l1_short = True
                l1_desc = f"Setup LL {last_pl:.1f} < {prev_pl:.1f} (Pressione Bear)"
            elif last_ph > prev_ph and (ema8 is None or live_px >= ema8):
                l1_long = True
                l1_desc = f"Setup HH {last_ph:.1f} > {prev_ph:.1f} (Pressione Bull)"

        # B) Micro-Trend da Sequenza Direzionale (2 o più candele consecutive a favore sotto/sopra EMA)
        c_red_2 = (curr_c["close"] < curr_c["open"]) and (prev_c["close"] < prev_c["open"]) and (curr_c["close"] <= prev_c["close"])
        c_green_2 = (curr_c["close"] > curr_c["open"]) and (prev_c["close"] > prev_c["open"]) and (curr_c["close"] >= prev_c["close"])

        if c_red_2 and (ema8 is None or live_px <= ema8):
            l1_short = True
            l1_long = False
            l1_desc = f"Trend Impulso Short: 2+ candele rosse sotto EMA ({live_px:.1f})"
        elif c_green_2 and (ema8 is None or live_px >= ema8):
            l1_long = True
            l1_short = False
            l1_desc = f"Trend Impulso Long: 2+ candele verdi sopra EMA ({live_px:.1f})"

        # -------------------------------------------------------------
        # LUCETTA 2: TRIGGER / BREAKOUT
        # -------------------------------------------------------------
        l2_long = False
        l2_short = False
        l2_desc = "In attesa di rottura o candela d'impulso"

        # SHORT: Breakout sotto minimo precedente, breakdown Pivot Low, o candela rossa decisa (Body >= 40%)
        break_low_prev = bool(live_px < prev_c["low"])
        is_red_impulse = (curr_c["close"] < curr_c["open"] and body_ratio >= 0.40)
        break_pivot_low = bool(last_pl and live_px < last_pl)

        if (break_pivot_low or break_low_prev or is_red_impulse) and (live_px < curr_c["open"]):
            l2_short = True
            if break_low_prev:
                l2_desc = f"Breakout M5: {live_px:.1f} < Minimo Prec {prev_c['low']:.1f}"
            elif break_pivot_low:
                l2_desc = f"Breakdown Pivot: {live_px:.1f} < Pivot {last_pl:.1f}"
            else:
                l2_desc = f"Impulso Rosso: Body {int(body_ratio*100)}%"

        # LONG: Breakout sopra massimo precedente, breakout Pivot High, o candela verde decisa (Body >= 40%)
        break_high_prev = bool(live_px > prev_c["high"])
        is_green_impulse = (curr_c["close"] > curr_c["open"] and body_ratio >= 0.40)
        break_pivot_high = bool(last_ph and live_px > last_ph)

        if (break_pivot_high or break_high_prev or is_green_impulse) and (live_px > curr_c["open"]):
            l2_long = True
            if break_high_prev:
                l2_desc = f"Breakout M5: {live_px:.1f} > Massimo Prec {prev_c['high']:.1f}"
            elif break_pivot_high:
                l2_desc = f"Breakout Pivot: {live_px:.1f} > Pivot {last_ph:.1f}"
            else:
                l2_desc = f"Impulso Verde: Body {int(body_ratio*100)}%"

        # -------------------------------------------------------------
        # LUCETTA 3: SPINTA & FLOW EMA (MOMENTUM CANDELA)
        # -------------------------------------------------------------
        l3_long = False
        l3_short = False
        l3_desc = "Flusso in consolidamento"

        # SHORT: Prezzo sotto EMA8 e candela corrente che spinge verso il basso (o EMA8 discendente)
        if ema8 is not None:
            if live_px < ema8 and (live_px <= curr_c["open"] or (prev_ema8 and ema8 < prev_ema8)):
                l3_short = True
                l3_desc = f"Spinta Ribassista: {live_px:.1f} < EMA8 ({ema8:.1f})"
            elif live_px > ema8 and (live_px >= curr_c["open"] or (prev_ema8 and ema8 > prev_ema8)):
                l3_long = True
                l3_desc = f"Spinta Rialzista: {live_px:.1f} > EMA8 ({ema8:.1f})"

        # SINTESI DELLE CONFLUENZE A 3 LUCETTE (3/3 PRONTO)
        all_green_long = l1_long and l2_long and l3_long
        all_green_short = l1_short and l2_short and l3_short

        detected_dir = "LONG" if all_green_long else ("SHORT" if all_green_short else "NEUTRAL")
        all_green = all_green_long or all_green_short

        self.traffic_light = {
            "l1_structure": {"status": l1_long or l1_short, "dir": "LONG" if l1_long else ("SHORT" if l1_short else "NEUTRAL"), "desc": l1_desc},
            "l2_trigger": {"status": l2_long or l2_short, "dir": "LONG" if l2_long else ("SHORT" if l2_short else "NEUTRAL"), "desc": l2_desc},
            "l3_momentum": {"status": l3_long or l3_short, "dir": "LONG" if l3_long else ("SHORT" if l3_short else "NEUTRAL"), "desc": l3_desc},
            "direction": detected_dir,
            "all_green": all_green,
            "last_pivot_high": last_ph,
            "last_pivot_low": last_pl,
            "atr": round(atr, 1),
            "ema8": round(ema8, 2) if ema8 else None,
            "ema21": round(ema21, 2) if ema21 else None
        }

        # INGRESSO AUTOMATICO: CONSENTITO SOLO A CHIUSURA CANDELA CONFERMATA (ALL'INIZIO DELLA NUOVA BARRA M5)
        # Mai a metà candela o appena il bot si connette!
        if on_candle_close and self.trading_enabled and not self.entry_in_progress:
            if not is_gold_entry_suspended():
                if self.position is None:
                    if all_green_long:
                        self._trigger_entry("LONG", live_px, time_str, last_pl, last_ph)
                    elif all_green_short:
                        self._trigger_entry("SHORT", live_px, time_str, last_ph, last_pl)
                elif not self.closing_in_progress:
                    # Innesco Incrementi Speed 1 e Speed 2 se il trend M5 riaccende 3/3 luci verdi
                    self._check_speed_increment_entry(live_px, time_str, all_green_long, all_green_short)

    def _trigger_entry(self, direction: str, live_px: float, time_str: str, pivot_sl: float, pivot_opp: float):
        """Innesca l'ingresso a mercato quando tutte le 4 luci sono verdi."""
        self.entry_in_progress = True
        logger.info(f"[{time_str}] 🚀 [SEMAFORO VERDE 4/4] Innesco ingresso {direction} a {live_px:.2f}!")

        # Calcolo Stop Loss Strutturale Adattivo (ancorato alla candela d'impulso recente o al pivot)
        if direction == "LONG":
            swing_sl = min(c["low"] for c in self.candles[-3:]) if len(self.candles) >= 3 else live_px - 20.0
            ref_sl = min(pivot_sl, swing_sl) if pivot_sl else swing_sl
            sl_raw = ref_sl - SL_BUFFER_PIPS
            sl_dist = live_px - sl_raw
            sl_dist = max(SL_MIN_PIPS, min(sl_dist, SL_MAX_PIPS))
            final_sl = round(live_px - sl_dist, 2)
            final_tp1 = round(live_px + TP1_DEFAULT_PIPS, 2)
        else:
            swing_sl = max(c["high"] for c in self.candles[-3:]) if len(self.candles) >= 3 else live_px + 20.0
            ref_sl = min(pivot_sl, swing_sl) if pivot_sl else swing_sl
            sl_raw = ref_sl + SL_BUFFER_PIPS
            sl_dist = sl_raw - live_px
            sl_dist = max(SL_MIN_PIPS, min(sl_dist, SL_MAX_PIPS))
            final_sl = round(live_px + sl_dist, 2)
            final_tp1 = round(live_px - TP1_DEFAULT_PIPS, 2)

        threading.Thread(
            target=self._execute_apex_entry,
            args=(direction, live_px, final_sl, final_tp1, time_str),
            daemon=True
        ).start()

    def _execute_apex_entry(self, direction: str, exec_price: float, sl_price: float, tp1_price: float, time_str: str):
        """Apre a mercato la posizione divisa in 5c Bancomat + 5c Runner."""
        order_mgr = HyperOrderManager.get_instance(self.account_dir)
        try:
            logger.info(f"[{time_str}] 📤 Invio a IG: {direction} {CORE_CONTRACTS} contratti (5c Bancomat TP {tp1_price:.2f} + 5c Runner SL {sl_price:.2f})")

            # 1. Apertura Bancomat (5 contratti con TP1 nativo su IG)
            res_banc = order_mgr.open_market_deal(
                direction=direction,
                size=BANCOMAT_CONTRACTS,
                limit_level=tp1_price,
                stop_level=sl_price,
                label=f"Apex Bancomat Spot Gold ({direction})",
                epic=EPIC_GOLD
            )

            # 2. Apertura Runner (5 contratti con Stop Loss protettivo su IG)
            res_run = order_mgr.open_market_deal(
                direction=direction,
                size=RUNNER_CONTRACTS,
                limit_level=None,
                stop_level=sl_price,
                label=f"Apex Runner Spot Gold ({direction})",
                epic=EPIC_GOLD
            )

            deal_id_banc = res_banc.get("deal_id") if res_banc.get("success") else None
            deal_id_run = res_run.get("deal_id") if res_run.get("success") else None
            real_open_px = res_banc.get("level") or res_run.get("level") or exec_price

            with self.lock:
                self.position = {
                    "direction": direction,
                    "open_price": real_open_px,
                    "contracts": CORE_CONTRACTS,
                    "bancomat_contracts": BANCOMAT_CONTRACTS,
                    "runner_contracts": RUNNER_CONTRACTS,
                    "deal_id_bancomat": deal_id_banc,
                    "deal_id_runner": deal_id_run,
                    "tp1_price": tp1_price,
                    "sl_price": sl_price,
                    "runner_sl": sl_price,
                    "tp1_hit": False,
                    "open_time": time_str
                }
                self.entry_in_progress = False
                self.save_state()

            order_mgr.send_notification(
                f"🚀 APEX M5 INGRESSO: {direction}",
                f"Aperto {direction} {CORE_CONTRACTS}c a {real_open_px:.2f} | SL: {sl_price:.2f} | TP1: {tp1_price:.2f}",
                "rocket"
            )
            logger.info(f"[{time_str}] ✅ Posizione {direction} registrata: Deal Banc={deal_id_banc}, Deal Run={deal_id_run}")

        except Exception as e:
            logger.error(f"Errore durante esecuzione ingresso Apex M5: {e}")
            with self.lock:
                self.entry_in_progress = False
                self.save_state()

    def _check_speed_increment_entry(self, live_px: float, time_str: str, all_green_long: bool, all_green_short: bool):
        """Verifica se innescare un incremento Speed 1 o Speed 2 a chiusura candela M5 con 3/3 luci verdi."""
        with self.lock:
            if not self.position or self.closing_in_progress:
                return
            if len(self.increments) >= MAX_SPEED_INCREMENTS:
                return
            pos = dict(self.position)
            curr_incs = list(self.increments)

        dir_pos = pos["direction"]
        # Verifica concordanza direzione semaforo 3/3
        matching_signal = (dir_pos == "LONG" and all_green_long) or (dir_pos == "SHORT" and all_green_short)
        if not matching_signal:
            return

        # Solo se trade già in profitto (Bancomat incassato o prezzo oltre BE)
        open_px = pos["open_price"]
        is_profitable = pos.get("tp1_hit", False) or ((live_px >= open_px + 2.0) if dir_pos == "LONG" else (live_px <= open_px - 2.0))
        if not is_profitable:
            return

        # Distanza minima di almeno 2 pip dall'ingresso o da altri incrementi attivi
        if abs(live_px - open_px) < 2.0:
            return
        for inc in curr_incs:
            if abs(live_px - inc.get("open_price", 0.0)) < 2.0:
                return

        label_num = 1 if len(curr_incs) == 0 else 2
        label = f"Speed {label_num}"

        # Target Take Profit rapido e Stop Loss alla base della candela M5 precedente
        if dir_pos == "LONG":
            tp_px = round(live_px + SPEED_TP_PIPS, 2)
            prev_low = self.candles[-1]["low"] if self.candles else live_px - 10.0
            sl_px = round(min(prev_low - CANDLE_BUFFER_PIPS, live_px - SL_MIN_PIPS), 2)
        else:
            tp_px = round(live_px - SPEED_TP_PIPS, 2)
            prev_high = self.candles[-1]["high"] if self.candles else live_px + 10.0
            sl_px = round(max(prev_high + CANDLE_BUFFER_PIPS, live_px + SL_MIN_PIPS), 2)

        threading.Thread(
            target=self._execute_speed_entry,
            args=(label, dir_pos, live_px, sl_px, tp_px, time_str),
            daemon=True
        ).start()

    def _execute_speed_entry(self, label: str, direction: str, exec_price: float, sl_price: float, tp_price: float, time_str: str):
        """Apre a mercato l'ordine di incremento Speed (5 contratti Spot Gold)."""
        order_mgr = HyperOrderManager.get_instance(self.account_dir)
        try:
            logger.info(f"[{time_str}] ⚡ [ACCELERAZIONE {label}] Invio a IG: {direction} {INC_CONTRACTS}c | TP: {tp_price:.2f} | SL: {sl_price:.2f}")
            res = order_mgr.open_market_deal(
                direction=direction,
                size=INC_CONTRACTS,
                limit_level=tp_price,
                stop_level=sl_price,
                label=f"Apex {label} Spot Gold ({direction})",
                epic=EPIC_GOLD
            )
            deal_id = res.get("deal_id") if res.get("success") else None
            real_open_px = res.get("level") or exec_price

            inc_entry = {
                "id": f"speed_{int(time.time()*1000)}",
                "label": f"⚡ {label}",
                "deal_id": deal_id,
                "direction": direction,
                "open_price": real_open_px,
                "contracts": INC_CONTRACTS,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "open_time": time_str
            }

            with self.lock:
                self.increments.append(inc_entry)
                self.save_state()

            order_mgr.send_notification(
                f"⚡ APEX M5: {label} APERTO",
                f"{direction} {INC_CONTRACTS}c a {real_open_px:.2f} | TP: {tp_price:.2f} | SL: {sl_price:.2f}",
                "zap"
            )
            logger.info(f"[{time_str}] ✅ {label} registrato con successo (Deal: {deal_id})")
        except Exception as e:
            logger.error(f"Errore durante apertura incremento {label}: {e}")

    # ==============================================================================
    # GESTIONE POSIZIONE APERTA (BANCOMAT, BREAKEVEN, RUNNER TRAILING, SPEED)
    # ==============================================================================

    def _manage_open_position(self, current_price: float, time_str: str, on_candle_close: bool = False):
        """Gestisce in continuo su ogni tick la posizione aperta."""
        if not self.position or self.closing_in_progress:
            return

        direction = self.position["direction"]
        open_px = self.position["open_price"]
        sl_px = self.position["sl_price"]
        tp1_px = self.position["tp1_price"]
        tp1_hit = self.position.get("tp1_hit", False)
        runner_sl = self.position.get("runner_sl", sl_px)
        deal_run = self.position.get("deal_id_runner")
        deal_banc = self.position.get("deal_id_bancomat")
        order_mgr = HyperOrderManager.get_instance(self.account_dir)

        # -------------------------------------------------------------
        # 0. VERIFICA INVERSIONE STRUTTURALE: 3 MASSIMI E 3 MINIMI DECRESCENTI (DOW THEORY)
        # -------------------------------------------------------------
        if on_candle_close and len(self.candles) >= 3:
            c1 = self.candles[-1]
            c2 = self.candles[-2]
            c3 = self.candles[-3]

            # LONG: 3 massimi decrescenti E 3 minimi decrescenti (Inversione ribassista conclamata)
            if direction == "LONG" and (c1["high"] < c2["high"] < c3["high"]) and (c1["low"] < c2["low"] < c3["low"]):
                logger.info(f"[{time_str}] ⚠️ [INVERSIONE RIBASSISTA M5] Rilevati 3 massimi e 3 minimi decrescenti ({c3['high']:.2f}>{c2['high']:.2f}>{c1['high']:.2f} e {c3['low']:.2f}>{c2['low']:.2f}>{c1['low']:.2f}). Chiusura anticipata!")
                self._close_all_to_flat(current_price, time_str, reason="Inversione Strutturale (3 Massimi e 3 Minimi Decrescenti M5)")
                return

            # SHORT: 3 minimi crescenti E 3 massimi crescenti (Inversione rialzista conclamata)
            elif direction == "SHORT" and (c1["low"] > c2["low"] > c3["low"]) and (c1["high"] > c2["high"] > c3["high"]):
                logger.info(f"[{time_str}] ⚠️ [INVERSIONE RIALZISTA M5] Rilevati 3 minimi e 3 massimi crescenti ({c3['low']:.2f}<{c2['low']:.2f}<{c1['low']:.2f} e {c3['high']:.2f}<{c2['high']:.2f}<{c1['high']:.2f}). Chiusura anticipata!")
                self._close_all_to_flat(current_price, time_str, reason="Inversione Strutturale (3 Minimi e 3 Massimi Crescenti M5)")
                return

        # -------------------------------------------------------------
        # 0B. GESTIONE AUTONOMA INCREMENTI SPEED (TP e SL)
        # -------------------------------------------------------------
        with self.lock:
            curr_incs = list(self.increments)

        for inc in curr_incs:
            inc_id = inc["id"]
            inc_deal = inc.get("deal_id")
            inc_dir = inc["direction"]
            inc_tp = inc["tp_price"]
            inc_sl = inc["sl_price"]
            inc_sz = inc.get("contracts", INC_CONTRACTS)
            inc_label = inc.get("label", "⚡ Speed")
            inc_open_t = inc.get("open_time", time_str)
            inc_open_p = inc.get("open_price", current_price)

            hit_inc_tp = (current_price >= inc_tp) if inc_dir == "LONG" else (current_price <= inc_tp)
            hit_inc_sl = (current_price <= inc_sl) if inc_dir == "LONG" else (current_price >= inc_sl)

            if hit_inc_tp or hit_inc_sl:
                reason_inc = "Hit TP Rapido" if hit_inc_tp else "Hit SL Protezione"
                close_px_inc = inc_tp if hit_inc_tp else inc_sl
                pts_inc = (close_px_inc - inc_open_p) if inc_dir == "LONG" else (inc_open_p - close_px_inc)
                est_pnl_inc = round(pts_inc * self.point_value * inc_sz, 2)

                def _close_inc_worker(d_id, d_dir, sz, o_px, cl_px, est_p, rsn, lbl, t_op, i_id):
                    act_p = est_p
                    act_cl = cl_px
                    if d_id:
                        res = order_mgr.close_market_deal(d_id, d_dir, sz, f"Chiusura {lbl} {rsn}", rsn)
                        if res.get("success") and float(res.get("profit") or 0.0) != 0.0:
                            act_p = float(res.get("profit"))
                        if res.get("close_level"):
                            act_cl = float(res.get("close_level"))
                    order_mgr.record_closed_trade(
                        tf="5M",
                        direction=d_dir,
                        contracts=sz,
                        open_price=o_px,
                        close_price=act_cl,
                        pnl_eur=act_p,
                        deal_id=d_id or "--",
                        reason=f"{lbl} ({rsn})",
                        time_open=t_op,
                        label=f"{lbl} Spot Gold",
                        epic=self.epic
                    )
                    with self.lock:
                        self.balance = round(self.balance + act_p, 2)
                        self.trades.insert(0, {
                            "time_open": t_op,
                            "time_close": now_it().strftime("%H:%M:%S"),
                            "direction": d_dir,
                            "open_price": o_px,
                            "close_price": act_cl,
                            "contracts": sz,
                            "pnl_eur": act_p,
                            "reason": f"{lbl} ({rsn})",
                            "tf": "5M"
                        })
                        self.increments = [i for i in self.increments if i.get("id") != i_id]
                        self.save_state()

                threading.Thread(
                    target=_close_inc_worker,
                    args=(inc_deal, inc_dir, inc_sz, inc_open_p, close_px_inc, est_pnl_inc, reason_inc, inc_label, inc_open_t, inc_id),
                    daemon=True
                ).start()

        # -------------------------------------------------------------
        # 1. VERIFICA STOP LOSS STRUTTURALE GLOBALE (Se non ancora preso TP1)
        # -------------------------------------------------------------
        if not tp1_hit:
            hit_sl = (current_price <= sl_px) if direction == "LONG" else (current_price >= sl_px)
            if hit_sl:
                logger.info(f"[{time_str}] 🛑 [STOP LOSS COLPITO] Prezzo {current_price:.2f} ha toccato SL {sl_px:.2f}!")
                self._close_all_to_flat(current_price, time_str, reason=f"Stop Loss Strutturale ({sl_px:.2f})")
                return

        # -------------------------------------------------------------
        # 2. VERIFICA HIT TP1 BANCOMAT (+ Spostamento a BREAKEVEN)
        # -------------------------------------------------------------
        if not tp1_hit:
            hit_tp1 = (current_price >= tp1_px) if direction == "LONG" else (current_price <= tp1_px)
            if hit_tp1:
                logger.info(f"[{time_str}] 🎯 [TP1 BANCOMAT RAGGIUNTO] Prezzo {current_price:.2f} >= TP1 {tp1_px:.2f}!")
                self.position["tp1_hit"] = True

                # Sposta lo Stop Loss del Runner a BREAKEVEN (+1 pip protetto)
                be_sl = round(open_px + BE_EXTRA_LOCK_PIPS if direction == "LONG" else open_px - BE_EXTRA_LOCK_PIPS, 2)
                self.position["runner_sl"] = be_sl
                self.position["contracts"] = RUNNER_CONTRACTS
                self.save_state()

                # Calcolo PnL stimato Bancomat
                banc_pts = (tp1_px - open_px) if direction == "LONG" else (open_px - tp1_px)
                est_banc_pnl = round(banc_pts * self.point_value * BANCOMAT_CONTRACTS, 2)
                open_t_str = self.position.get("open_time", time_str)

                def _close_bancomat_worker(d_id, d_dir, sz, o_px, t_px, est_pnl, t_op):
                    act_pnl = est_pnl
                    act_close_px = t_px
                    if d_id:
                        res = order_mgr.close_market_deal(d_id, d_dir, sz, "TP1 Bancomat Incassato", "Hit TP1")
                        if res.get("success") and float(res.get("profit") or 0.0) != 0.0:
                            act_pnl = float(res.get("profit"))
                        if res.get("close_level"):
                            act_close_px = float(res.get("close_level"))
                    order_mgr.record_closed_trade(
                        tf="5M",
                        direction=d_dir,
                        contracts=sz,
                        open_price=o_px,
                        close_price=act_close_px,
                        pnl_eur=act_pnl,
                        deal_id=d_id or "--",
                        reason="TP1 Bancomat Incassato",
                        time_open=t_op,
                        label="💰 Bancomat Spot Gold",
                        epic=self.epic
                    )
                    with self.lock:
                        self.balance = round(self.balance + act_pnl, 2)
                        self.trades.insert(0, {
                            "time_open": t_op,
                            "time_close": now_it().strftime("%H:%M:%S"),
                            "direction": d_dir,
                            "open_price": o_px,
                            "close_price": act_close_px,
                            "contracts": sz,
                            "pnl_eur": act_pnl,
                            "reason": "TP1 Bancomat Incassato",
                            "tf": "5M"
                        })
                        self.save_state()

                # Chiude Bancomat se ancora aperto su IG e registra profitto
                threading.Thread(
                    target=_close_bancomat_worker,
                    args=(deal_banc, direction, BANCOMAT_CONTRACTS, open_px, tp1_px, est_banc_pnl, open_t_str),
                    daemon=True
                ).start()

                # Aggiorna lo stop del runner su IG a Breakeven
                if deal_run:
                    threading.Thread(
                        target=order_mgr.set_stop_loss_order,
                        args=(deal_run, be_sl, "Runner a Breakeven"),
                        daemon=True
                    ).start()

                order_mgr.send_notification(
                    "🎯 TP1 BANCOMAT INCASSATO!",
                    f"Incassati +{TP1_DEFAULT_PIPS:.0f} pip! Runner spostato a BREAKEVEN ({be_sl:.2f}). Rischio ZERO!",
                    "moneybag"
                )
                return

        # -------------------------------------------------------------
        # 3. TRAILING STOP ADATTIVO SUL RUNNER (Dopo TP1)
        # -------------------------------------------------------------
        if tp1_hit:
            # 1. Aggiorna il massimo (o minimo per SHORT) battuto dal trade
            peak_px = self.position.get("peak_price", open_px)
            if direction == "LONG":
                if current_price > peak_px:
                    peak_px = current_price
                    self.position["peak_price"] = peak_px
            else:
                if current_price < peak_px:
                    peak_px = current_price
                    self.position["peak_price"] = peak_px

            # 2. Candidato Candela M5 precedente chiusa
            candela_sl = None
            if len(self.candles) >= 2:
                prev_c = self.candles[-2]
                if direction == "LONG":
                    candela_sl = round(prev_c["low"] - CANDLE_BUFFER_PIPS, 2)
                else:
                    candela_sl = round(prev_c["high"] + CANDLE_BUFFER_PIPS, 2)

            # 3. Candidato Pivot Frattale
            last_pl = self.traffic_light.get("last_pivot_low")
            last_ph = self.traffic_light.get("last_pivot_high")
            pivot_sl = None
            if direction == "LONG" and last_pl:
                pivot_sl = round(last_pl - SL_BUFFER_PIPS, 2)
            elif direction == "SHORT" and last_ph:
                pivot_sl = round(last_ph + SL_BUFFER_PIPS, 2)

            # 4. Candidato Chasing dal Picco (High Watermark Trailing: max 7 pip di ritracciamento)
            if direction == "LONG":
                peak_sl = round(peak_px - RUNNER_MAX_GIVEBACK_PIPS, 2)
                candidates = [runner_sl]
                if peak_sl: candidates.append(peak_sl)
                if candela_sl: candidates.append(candela_sl)
                if pivot_sl: candidates.append(pivot_sl)
                new_sl = max(candidates)
            else:
                peak_sl = round(peak_px + RUNNER_MAX_GIVEBACK_PIPS, 2)
                candidates = [runner_sl]
                if peak_sl: candidates.append(peak_sl)
                if candela_sl: candidates.append(candela_sl)
                if pivot_sl: candidates.append(pivot_sl)
                new_sl = min(candidates)

            # Se il nuovo SL si è alzato (per LONG) o abbassato (per SHORT), aggiorna
            should_update = (new_sl > runner_sl) if direction == "LONG" else (new_sl < runner_sl)
            if should_update:
                logger.info(f"[{time_str}] 📈 [TRAILING RUNNER ALZATO] Stop aggiornato da {runner_sl:.2f} a {new_sl:.2f} (Peak: {peak_px:.2f})")
                self.position["runner_sl"] = new_sl
                self.save_state()
                # Invia aggiornamento Stop Loss a IG se c'è variazione di almeno 1 pip
                last_ig_sl = self.position.get("last_ig_sl", 0.0)
                if deal_run and abs(new_sl - last_ig_sl) >= 1.0:
                    self.position["last_ig_sl"] = new_sl
                    threading.Thread(target=order_mgr.set_stop_loss_order, args=(deal_run, new_sl, "Trailing M5"), daemon=True).start()

            # 5. Verifica se il prezzo corrente ha toccato il Trailing Stop
            hit_runner_sl = (current_price <= self.position["runner_sl"]) if direction == "LONG" else (current_price >= self.position["runner_sl"])
            if hit_runner_sl:
                logger.info(f"[{time_str}] 🏁 [RUNNER TRAILING HIT] Prezzo {current_price:.2f} ha toccato Trailing SL {self.position['runner_sl']:.2f}!")
                self._close_all_to_flat(current_price, time_str, reason=f"Trailing Stop Runner ({self.position['runner_sl']:.2f})")
                return

    def _close_all_to_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude tutte le posizioni a mercato e torna a FLAT."""
        with self.lock:
            if not self.position or self.closing_in_progress:
                return
            self.closing_in_progress = True
            incs_to_close = list(self.increments)
            self.increments = []

        pos = self.position
        direction = pos["direction"]
        open_px = pos["open_price"]
        deal_run = pos.get("deal_id_runner")
        deal_banc = pos.get("deal_id_bancomat")
        is_tp1_hit = pos.get("tp1_hit", False)
        open_t_str = pos.get("open_time", time_str)
        order_mgr = HyperOrderManager.get_instance(self.account_dir)

        pnl_pts = (exec_price - open_px) if direction == "LONG" else (open_px - exec_price)
        pnl_run = round(pnl_pts * self.point_value * RUNNER_CONTRACTS, 2)
        pnl_banc = round(pnl_pts * self.point_value * BANCOMAT_CONTRACTS, 2) if not is_tp1_hit else 0.0
        total_pnl = pnl_run + pnl_banc

        logger.info(f"[{time_str}] 🛑 CHIUSURA A FLAT: {direction} a {exec_price:.2f} | Runner PnL: {pnl_run:+.2f} € | Motivo: {reason}")

        def _close_flat_worker():
            act_pnl_run = pnl_run
            act_cl_run = exec_price
            if deal_run:
                res_r = order_mgr.close_market_deal(deal_run, direction, RUNNER_CONTRACTS, f"Chiusura Runner {reason}", reason)
                if res_r.get("success") and float(res_r.get("profit") or 0.0) != 0.0:
                    act_pnl_run = float(res_r.get("profit"))
                if res_r.get("close_level"):
                    act_cl_run = float(res_r.get("close_level"))

            order_mgr.record_closed_trade(
                tf="5M",
                direction=direction,
                contracts=RUNNER_CONTRACTS,
                open_price=open_px,
                close_price=act_cl_run,
                pnl_eur=act_pnl_run,
                deal_id=deal_run or "--",
                reason=reason,
                time_open=open_t_str,
                label="🏃 Runner Spot Gold",
                epic=self.epic
            )

            # Se Bancomat non era ancora stato chiuso da TP1, chiudilo e registralo
            act_pnl_b = pnl_banc
            if not is_tp1_hit:
                act_cl_b = exec_price
                if deal_banc:
                    res_b = order_mgr.close_market_deal(deal_banc, direction, BANCOMAT_CONTRACTS, f"Chiusura Bancomat {reason}", reason)
                    if res_b.get("success") and float(res_b.get("profit") or 0.0) != 0.0:
                        act_pnl_b = float(res_b.get("profit"))
                    if res_b.get("close_level"):
                        act_cl_b = float(res_b.get("close_level"))
                order_mgr.record_closed_trade(
                    tf="5M",
                    direction=direction,
                    contracts=BANCOMAT_CONTRACTS,
                    open_price=open_px,
                    close_price=act_cl_b,
                    pnl_eur=act_pnl_b,
                    deal_id=deal_banc or "--",
                    reason=reason,
                    time_open=open_t_str,
                    label="💰 Bancomat Spot Gold",
                    epic=self.epic
                )

            # Chiude eventuali incrementi Speed ancora a mercato
            act_pnl_incs = 0.0
            for inc in incs_to_close:
                inc_deal = inc.get("deal_id")
                inc_lbl = inc.get("label", "⚡ Speed")
                inc_sz = inc.get("contracts", INC_CONTRACTS)
                inc_op = inc.get("open_price", open_px)
                inc_top = inc.get("open_time", open_t_str)
                inc_pts = (exec_price - inc_op) if direction == "LONG" else (inc_op - exec_price)
                act_pnl_inc = round(inc_pts * self.point_value * inc_sz, 2)
                act_cl_inc = exec_price
                if inc_deal:
                    res_i = order_mgr.close_market_deal(inc_deal, direction, inc_sz, f"Chiusura {inc_lbl} {reason}", reason)
                    if res_i.get("success") and float(res_i.get("profit") or 0.0) != 0.0:
                        act_pnl_inc = float(res_i.get("profit"))
                    if res_i.get("close_level"):
                        act_cl_inc = float(res_i.get("close_level"))
                order_mgr.record_closed_trade(
                    tf="5M",
                    direction=direction,
                    contracts=inc_sz,
                    open_price=inc_op,
                    close_price=act_cl_inc,
                    pnl_eur=act_pnl_inc,
                    deal_id=inc_deal or "--",
                    reason=reason,
                    time_open=inc_top,
                    label=f"{inc_lbl} Spot Gold",
                    epic=self.epic
                )
                act_pnl_incs += act_pnl_inc

            tot_incassato = act_pnl_run + (act_pnl_b if not is_tp1_hit else 0.0) + act_pnl_incs
            with self.lock:
                self.balance = round(self.balance + tot_incassato, 2)
                self.trades.insert(0, {
                    "time_open": open_t_str,
                    "time_close": now_it().strftime("%H:%M:%S"),
                    "direction": direction,
                    "open_price": open_px,
                    "close_price": act_cl_run,
                    "contracts": RUNNER_CONTRACTS,
                    "pnl_eur": act_pnl_run,
                    "reason": reason,
                    "tf": "5M"
                })
                self.position = None
                self.increments = []
                self.closing_in_progress = False
                self.save_state()

        threading.Thread(target=_close_flat_worker, daemon=True).start()

        order_mgr.send_notification(
            f"🏁 APEX M5 CHIUSURA: {total_pnl:+.2f} €",
            f"Trade chiuso: {total_pnl:+.2f} € a {exec_price:.2f} ({reason})",
            "white_check_mark" if total_pnl >= 0 else "x"
        )

    # ==============================================================================
    # GESTIONE STREAMING TICK & CANDLE BUILDER M5
    # ==============================================================================

    def _process_tick(self, bid: float, ask: float, time_str: str):
        with self.lock:
            self.live_bid = bid
            self.live_ask = ask
            self.live_mid = round((bid + ask) / 2.0, 2)
            self.live_time_str = time_str
            self.total_ticks += 1
            mid = self.live_mid

            now_epoch = int(time.time())
            boundary = (now_epoch // CANDLE_SECONDS) * CANDLE_SECONDS

            # Aggiornamento barra M5 corrente
            is_candle_close = False
            if self.curr_boundary != boundary:
                # Chiusura barra precedente (avvenuta al termine dei 5 minuti esatti)
                if self.curr_boundary is not None and self.curr_open is not None:
                    closed_bar = {
                        "time": self.curr_bar_start_t or time_str,
                        "open": self.curr_open,
                        "high": self.curr_high,
                        "low": self.curr_low,
                        "close": self.curr_close
                    }
                    self.candles.append(closed_bar)
                    if len(self.candles) > 500:
                        self.candles = self.candles[-500:]
                    is_candle_close = True

                # Nuova barra M5
                self.curr_boundary = boundary
                self.curr_open = mid
                self.curr_high = mid
                self.curr_low = mid
                self.curr_close = mid
                self.curr_bar_start_t = time_str
            else:
                self.curr_high = max(self.curr_high, mid)
                self.curr_low = min(self.curr_low, mid)
                self.curr_close = mid

            # 1. Valuta Semaforo a 3 Lucette (Ingresso automatico consentito ESCLUSIVAMENTE all'inizio della nuova candela)
            self._evaluate_traffic_lights(time_str, on_candle_close=is_candle_close)

            # 2. Gestisci Posizione Aperta (SL, TP1, Trailing, Uscita Anticipata) - sempre attivo tick-by-tick
            self._manage_open_position(mid, time_str, on_candle_close=is_candle_close)

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
                        return user, pwd, api_key
                except Exception:
                    pass
        user = os.getenv("IG_USERNAME")
        pwd = os.getenv("IG_PASSWORD")
        api_key = os.getenv("IG_API_KEY")
        return user, pwd, api_key

    def _run_streaming_loop(self):
        """Thread di ascolto streaming Lightstreamer IG."""
        while self.running:
            try:
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
                    t_str = now_it().strftime("%H:%M:%S")
                    if bid_s and ask_s:
                        try:
                            b = float(bid_s)
                            a = float(ask_s)
                            self._process_tick(b, a, t_str)
                        except Exception as e:
                            logger.error(f"Errore _process_tick Gold M5: {e}")

                sub = LightstreamerSubscription(
                    mode="DISTINCT",
                    items=[f"CHART:{EPIC_GOLD}:TICK"],
                    fields=["BID", "OFR", "UTM"]
                )
                sub.addlistener(on_tick)
                ls_client.subscribe(sub)
                logger.info(f"✅ Sottoscrizione Lightstreamer M5 attiva su CHART:{EPIC_GOLD}:TICK")

                while self.running and self.ls_connected:
                    time.sleep(2)

            except Exception as e:
                logger.warning(f"Errore connessione Lightstreamer Gold: {e}")
                with self.lock:
                    self.ls_connected = False
                time.sleep(5)

    def _run_rollover_watchdog(self):
        """Watchdog automatico per freeze rollover e weekend."""
        while self.running:
            try:
                now_t = now_it()
                if is_gold_trading_suspended(now_t):
                    if self.position:
                        exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                        self._close_all_to_flat(exec_px, now_t.strftime("%H:%M:%S"), reason="🌙 Chiusura Freeze Notturno / Rollover")
            except Exception:
                pass
            time.sleep(10)

    def manual_entry_core(self, direction: str) -> dict:
        """Forzatura ingresso manuale dell'utente."""
        norm_dir = "LONG" if direction.upper() in ("LONG", "BUY") else "SHORT"
        with self.lock:
            if self.position is not None:
                return {"success": False, "error": "Posizione già aperta a mercato"}
            live_px = self.live_mid or (self.candles[-1]["close"] if self.candles else 0.0)
            t_str = now_it().strftime("%H:%M:%S")
            last_ph = self.traffic_light.get("last_pivot_high")
            last_pl = self.traffic_light.get("last_pivot_low")
            self._trigger_entry(norm_dir, live_px, t_str, last_pl if norm_dir == "LONG" else last_ph, None)
            return {"success": True, "direction": norm_dir, "price": live_px}

    def get_floating_pnl(self):
        with self.lock:
            if not self.position or self.live_mid is None:
                return 0.0
            direction = self.position["direction"]
            open_px = self.position["open_price"]
            contracts = self.position.get("contracts", CORE_CONTRACTS)
            pnl_pts = (self.live_mid - open_px) if direction == "LONG" else (open_px - self.live_mid)
            return round(pnl_pts * self.point_value * contracts, 2)

    def get_total_contracts(self):
        with self.lock:
            return self.position.get("contracts", 0) if self.position else 0
