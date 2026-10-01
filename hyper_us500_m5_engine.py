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

logger = logging.getLogger("HyperUS500M5Engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [HYPER_US500_M5] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_US500 = "IX.D.SPTRD.IBE.IP"
CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra
STATE_FILE = "hyper_us500_m5_state.json"

# Parametri Operativi Apex Swing M5 per US 500
CORE_CONTRACTS = 6          # Totale 6 contratti (3 Bancomat + 3 Runner)
BANCOMAT_CONTRACTS = 3      # 3 contratti Bancomat (TP1 rapido a R:R 1:1 o 4 pt)
RUNNER_CONTRACTS = 3        # 3 contratti Runner (Trailing Stop strutturale sui minimi/massimi crescenti)

TP1_DEFAULT_PTS = 4.0       # Take Profit Bancomat fisso: +4.0 pt (+24.00 € con 3 contratti)
SL_BUFFER_PTS = 1.0         # Cuscinetto oltre il pivot strutturale: 1.0 pt
SL_MIN_PTS = 2.0            # Stop Loss minimo di protezione: 2.0 pt
SL_MAX_PTS = 6.0            # Stop Loss massimo invalicabile (cap di sicurezza): 6.0 pt
BE_EXTRA_LOCK_PTS = 0.5     # Lock sopra il breakeven a protezione spread (+0.5 pt)

# Costanti di compatibilità per UI dashboard (hyper_tab)
INC_CONTRACTS = 3
MAX_INCREMENTS = 3

# Orari Sospensione US 500
def is_us500_feed_suspended(dt: datetime.datetime = None) -> bool:
    if dt is None: dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(23, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58):
        return True
    if wd in (0, 1, 2, 3) and datetime.time(22, 15) <= t < datetime.time(22, 30):
        return True
    return False

def is_us500_trading_suspended(dt: datetime.datetime = None) -> bool:
    if dt is None: dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(22, 44, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    if wd in (0, 1, 2, 3) and datetime.time(22, 15) <= t < datetime.time(22, 30):
        return True
    t_start = datetime.time(22, 44, 0)
    t_end = datetime.time(0, 15, 0)
    return t >= t_start or t < t_end

def is_us500_entry_suspended(dt: datetime.datetime = None) -> bool:
    if dt is None: dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(22, 14, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    return is_us500_trading_suspended(dt)

# ==============================================================================
# ALGORITMI PRICE ACTION & INDICATORI APEX SWING M5 PER US 500
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
        return 3.0  # Fallback per US 500 (3.0 pt)
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

class HyperUS500M5Engine:
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
        self.epic = EPIC_US500
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

        # Semaforo a 4 Lucette (Stato Real-Time)
        self.traffic_light = {
            "l1_structure": {"status": False, "dir": "NEUTRAL", "desc": "Analisi Swings in corso..."},
            "l2_trigger": {"status": False, "dir": "NEUTRAL", "desc": "In attesa di breakout..."},
            "l3_volatility": {"status": False, "desc": "Calcolo volatilità..."},
            "l4_momentum": {"status": False, "dir": "NEUTRAL", "desc": "Calcolo EMA Flow..."},
            "direction": "NEUTRAL",
            "all_green": False,
            "last_pivot_high": None,
            "last_pivot_low": None,
            "atr": 3.0,
            "ema8": None,
            "ema21": None
        }

        # Portafoglio e Trading
        self.initial_balance = 10000.0
        self.balance = 10000.0
        self.point_value = 1.0   # 1 EUR per punto su US 500
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False

        # Posizione Aperta (Bancomat + Runner)
        self.position = None

        # Retrocompatibilità interfaccia dashboard
        self.increments = []
        self.trades = []
        self.last_ts_cycle = None
        self.entry_in_progress = False
        self.closing_in_progress = False

        # 1. Carica stato persistente
        self.load_state()

        # 2. Sincronizzazione candele M5 da cache locale all'avvio
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
                    self.trades = d.get("trades", [])
                    if "candles" in d and isinstance(d["candles"], list):
                        self.candles = d["candles"][-500:]
                    if "traffic_light" in d:
                        self.traffic_light.update(d["traffic_light"])
            except Exception as e:
                logger.warning(f"Errore caricamento stato {st_file}: {e}")

    def save_state(self):
        st_file = self._get_state_file()
        with self.lock:
            d = {
                "balance": self.balance,
                "trading_enabled": self.trading_enabled,
                "position": self.position,
                "increments": [],
                "traffic_light": self.traffic_light,
                "trades": self.trades[-100:],
                "candles": self.candles[-500:]
            }
            for _ in range(5):
                try:
                    with open(st_file, "w", encoding="utf-8") as f:
                        json.dump(d, f, indent=2, ensure_ascii=False)
                        f.flush()
                    break
                except Exception:
                    time.sleep(0.05)

    def _load_initial_m5_candles(self):
        candidates = [
            f"candele_US_500_Cash_MINUTE_5.json",
            os.path.join(self.account_dir or "", "candele_US_500_Cash_MINUTE_5.json"),
            os.path.join("Logs_e_Cache", "candele_US_500_Cash_MINUTE_5.json")
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
                                logger.info(f"Caricate {len(self.candles)} candele M5 iniziali per US 500.")
                                self._evaluate_traffic_lights(now_it().strftime("%H:%M:%S"))
                                return
                except Exception:
                    pass

    def set_trading(self, enabled: bool):
        with self.lock:
            self.trading_enabled = enabled
            logger.info(f"🚦 [COMANDO UTENTE] Trading Hyper US500 M5 impostato a: {'🟢 AVVIATO' if enabled else '🔴 STOP'}")
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
    # MOTORE DI VALUTAZIONE: LE 4 LUCETTE (SEMAFORO APEX PER US 500)
    # ==============================================================================

    def _evaluate_traffic_lights(self, time_str: str):
        if len(self.candles) < 20:
            return

        recent_candles = self.candles[-35:]
        closes = [c["close"] for c in recent_candles]
        curr_c = recent_candles[-1]

        # 1. Calcolo Indicatori
        atr = calculate_atr(recent_candles, period=14)
        ema8 = calculate_ema(closes, period=8)
        ema21 = calculate_ema(closes, period=21)
        prev_ema8 = calculate_ema(closes[:-1], period=8)

        # 2. Calcolo Swings Strutturali
        high_pivots, low_pivots = find_swings(recent_candles, left=2, right=1)
        last_ph = high_pivots[-1]["price"] if high_pivots else None
        prev_ph = high_pivots[-2]["price"] if len(high_pivots) >= 2 else None
        last_pl = low_pivots[-1]["price"] if low_pivots else None
        prev_pl = low_pivots[-2]["price"] if len(low_pivots) >= 2 else None

        # -------------------------------------------------------------
        # LUCETTA 1: STRUTTURA DI MERCATO (HH/HL vs LH/LL)
        # -------------------------------------------------------------
        l1_long = False
        l1_short = False
        l1_desc = "Struttura laterale / Neutra"

        if last_ph and prev_ph and last_pl and prev_pl:
            if last_ph > prev_ph and last_pl > prev_pl:
                l1_long = True
                l1_desc = f"Rialzista: HH {last_ph:.1f} > {prev_ph:.1f} | HL {last_pl:.1f} > {prev_pl:.1f}"
            elif last_ph < prev_ph and last_pl < prev_pl:
                l1_short = True
                l1_desc = f"Ribassista: LH {last_ph:.1f} < {prev_ph:.1f} | LL {last_pl:.1f} < {prev_pl:.1f}"
            elif last_ph > prev_ph:
                l1_long = True
                l1_desc = f"Setup HH {last_ph:.1f} > {prev_ph:.1f} (Pressione Bull)"
            elif last_pl < prev_pl:
                l1_short = True
                l1_desc = f"Setup LL {last_pl:.1f} < {prev_pl:.1f} (Pressione Bear)"

        # -------------------------------------------------------------
        # LUCETTA 2: TRIGGER / BREAKOUT CON BODY DOMINANCE
        # -------------------------------------------------------------
        l2_long = False
        l2_short = False
        l2_desc = "In attesa di rottura o candela d'impulso"

        live_px = self.live_mid or curr_c["close"]
        body = abs(curr_c["close"] - curr_c["open"])
        c_range = max(curr_c["high"] - curr_c["low"], 0.01)
        body_ratio = body / c_range

        if last_ph and (live_px > last_ph or (curr_c["close"] > curr_c["open"] and body_ratio >= 0.50 and l1_long)):
            l2_long = True
            l2_desc = f"Breakout/Impulso Long: {live_px:.1f} sopra Pivot {last_ph:.1f} (Body {int(body_ratio*100)}%)"

        if last_pl and (live_px < last_pl or (curr_c["close"] < curr_c["open"] and body_ratio >= 0.50 and l1_short)):
            l2_short = True
            l2_desc = f"Breakdown/Impulso Short: {live_px:.1f} sotto Pivot {last_pl:.1f} (Body {int(body_ratio*100)}%)"

        # -------------------------------------------------------------
        # LUCETTA 3: VOLATILITY GATE (ANTI-TRITACARNE)
        # -------------------------------------------------------------
        l3_ok = False
        recent_max_range = max(c["high"] - c["low"] for c in recent_candles[-2:])
        min_required_range = max(atr * 0.50, 1.0)

        if recent_max_range >= min_required_range:
            l3_ok = True
            l3_desc = f"Volatilità Attiva: Range {recent_max_range:.1f}pt >= soglia {min_required_range:.1f}pt (ATR: {atr:.1f}pt)"
        else:
            l3_desc = f"Fase Compressa: Range {recent_max_range:.1f}pt < soglia {min_required_range:.1f}pt (Stand-by)"

        # -------------------------------------------------------------
        # LUCETTA 4: MOMENTUM & FLOW (EMA 8 / EMA 21)
        # -------------------------------------------------------------
        l4_long = False
        l4_short = False
        l4_desc = "Medie piatte o incrociate"

        if ema8 is not None and ema21 is not None and prev_ema8 is not None:
            if ema8 > ema21:
                l4_long = True
                l4_desc = f"Flusso Rialzista: EMA8 ({ema8:.1f}) > EMA21 ({ema21:.1f})"
            elif ema8 < ema21:
                l4_short = True
                l4_desc = f"Flusso Ribassista: EMA8 ({ema8:.1f}) < EMA21 ({ema21:.1f})"

        all_green_long = l1_long and l2_long and l3_ok and l4_long
        all_green_short = l1_short and l2_short and l3_ok and l4_short

        detected_dir = "LONG" if all_green_long else ("SHORT" if all_green_short else "NEUTRAL")
        all_green = all_green_long or all_green_short

        self.traffic_light = {
            "l1_structure": {"status": l1_long or l1_short, "dir": "LONG" if l1_long else ("SHORT" if l1_short else "NEUTRAL"), "desc": l1_desc},
            "l2_trigger": {"status": l2_long or l2_short, "dir": "LONG" if l2_long else ("SHORT" if l2_short else "NEUTRAL"), "desc": l2_desc},
            "l3_volatility": {"status": l3_ok, "desc": l3_desc},
            "l4_momentum": {"status": l4_long or l4_short, "dir": "LONG" if l4_long else ("SHORT" if l4_short else "NEUTRAL"), "desc": l4_desc},
            "direction": detected_dir,
            "all_green": all_green,
            "last_pivot_high": last_ph,
            "last_pivot_low": last_pl,
            "atr": round(atr, 1),
            "ema8": round(ema8, 2) if ema8 else None,
            "ema21": round(ema21, 2) if ema21 else None
        }

        # Controllo ingresso automatico
        if self.trading_enabled and self.position is None and not self.entry_in_progress:
            if not is_us500_entry_suspended():
                if all_green_long:
                    self._trigger_entry("LONG", live_px, time_str, last_pl, last_ph)
                elif all_green_short:
                    self._trigger_entry("SHORT", live_px, time_str, last_ph, last_pl)

    def _trigger_entry(self, direction: str, live_px: float, time_str: str, pivot_sl: float, pivot_opp: float):
        self.entry_in_progress = True
        logger.info(f"[{time_str}] 🚀 [SEMAFORO VERDE US500 4/4] Innesco ingresso {direction} a {live_px:.2f}!")

        if direction == "LONG":
            sl_raw = (pivot_sl - SL_BUFFER_PTS) if pivot_sl else (live_px - 3.0)
            sl_dist = live_px - sl_raw
            sl_dist = max(SL_MIN_PTS, min(sl_dist, SL_MAX_PTS))
            final_sl = round(live_px - sl_dist, 2)
            final_tp1 = round(live_px + TP1_DEFAULT_PTS, 2)
        else:
            sl_raw = (pivot_sl + SL_BUFFER_PTS) if pivot_sl else (live_px + 3.0)
            sl_dist = sl_raw - live_px
            sl_dist = max(SL_MIN_PTS, min(sl_dist, SL_MAX_PTS))
            final_sl = round(live_px + sl_dist, 2)
            final_tp1 = round(live_px - TP1_DEFAULT_PTS, 2)

        threading.Thread(
            target=self._execute_apex_entry,
            args=(direction, live_px, final_sl, final_tp1, time_str),
            daemon=True
        ).start()

    def _execute_apex_entry(self, direction: str, exec_price: float, sl_price: float, tp1_price: float, time_str: str):
        order_mgr = HyperOrderManager.get_instance(self.account_dir)
        try:
            logger.info(f"[{time_str}] 📤 Invio a IG: {direction} {CORE_CONTRACTS} contratti US500 (3c Bancomat TP {tp1_price:.2f} + 3c Runner SL {sl_price:.2f})")

            res_banc = order_mgr.open_market_deal(
                direction=direction,
                size=BANCOMAT_CONTRACTS,
                limit_level=tp1_price,
                stop_level=sl_price,
                label=f"Apex Bancomat US 500 ({direction})",
                epic=EPIC_US500
            )

            res_run = order_mgr.open_market_deal(
                direction=direction,
                size=RUNNER_CONTRACTS,
                limit_level=None,
                stop_level=sl_price,
                label=f"Apex Runner US 500 ({direction})",
                epic=EPIC_US500
            )

            deal_id_banc = res_banc.get("deal_id") if res_banc.get("success") else None
            deal_id_run = res_run.get("deal_id") if res_run.get("success") else None
            real_open_px = res_banc.get("level") or res_run.get("level") or exec_price

            with self.lock:
                self.position = {
                    "direction": direction,
                    "open_price": real_open_px,
                    "contracts": CORE_CONTRACTS,
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
                f"🚀 APEX US500 INGRESSO: {direction}",
                f"Aperto {direction} {CORE_CONTRACTS}c a {real_open_px:.2f} | SL: {sl_price:.2f} | TP1: {tp1_price:.2f}",
                "rocket"
            )

        except Exception as e:
            logger.error(f"Errore durante esecuzione ingresso Apex US500: {e}")
            with self.lock:
                self.entry_in_progress = False
                self.save_state()

    def _manage_open_position(self, current_price: float, time_str: str):
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

        # 1. Stop Loss Iniziale Globale
        if not tp1_hit:
            hit_sl = (current_price <= sl_px) if direction == "LONG" else (current_price >= sl_px)
            if hit_sl:
                logger.info(f"[{time_str}] 🛑 [STOP LOSS COLPITO] US500 {current_price:.2f} ha toccato SL {sl_px:.2f}!")
                self._close_all_to_flat(current_price, time_str, reason=f"Stop Loss Strutturale ({sl_px:.2f})")
                return

        # 2. Hit TP1 Bancomat + Spostamento a Breakeven
        if not tp1_hit:
            hit_tp1 = (current_price >= tp1_px) if direction == "LONG" else (current_price <= tp1_px)
            if hit_tp1:
                logger.info(f"[{time_str}] 🎯 [TP1 BANCOMAT US500] Prezzo {current_price:.2f} >= TP1 {tp1_px:.2f}!")
                self.position["tp1_hit"] = True

                be_sl = round(open_px + BE_EXTRA_LOCK_PTS if direction == "LONG" else open_px - BE_EXTRA_LOCK_PTS, 2)
                self.position["runner_sl"] = be_sl
                self.position["contracts"] = RUNNER_CONTRACTS
                self.save_state()

                if deal_banc:
                    threading.Thread(
                        target=order_mgr.close_market_deal,
                        args=(deal_banc, direction, BANCOMAT_CONTRACTS, "TP1 Bancomat US500", "Hit TP1"),
                        daemon=True
                    ).start()

                if deal_run:
                    threading.Thread(
                        target=order_mgr.set_stop_loss_order,
                        args=(deal_run, be_sl, "Runner US500 Breakeven"),
                        daemon=True
                    ).start()

                order_mgr.send_notification(
                    "🎯 TP1 BANCOMAT US500 INCASSATO!",
                    f"Incassati +{TP1_DEFAULT_PTS:.1f} pt! Runner spostato a BREAKEVEN ({be_sl:.2f}).",
                    "moneybag"
                )
                return

        # 3. Trailing Stop Strutturale sul Runner
        if tp1_hit:
            hit_runner_sl = (current_price <= runner_sl) if direction == "LONG" else (current_price >= runner_sl)
            if hit_runner_sl:
                logger.info(f"[{time_str}] 🏁 [RUNNER TRAILING HIT] US500 {current_price:.2f} ha toccato Trailing SL {runner_sl:.2f}!")
                self._close_all_to_flat(current_price, time_str, reason=f"Trailing Stop Runner ({runner_sl:.2f})")
                return

            last_pl = self.traffic_light.get("last_pivot_low")
            last_ph = self.traffic_light.get("last_pivot_high")

            if direction == "LONG" and last_pl:
                new_sl = round(last_pl - SL_BUFFER_PTS, 2)
                if new_sl > runner_sl:
                    logger.info(f"[{time_str}] 📈 [TRAILING RUNNER ALZATO] Nuovo HL {last_pl:.2f}. Trailing SL alzato a {new_sl:.2f}")
                    self.position["runner_sl"] = new_sl
                    self.save_state()
                    if deal_run:
                        threading.Thread(target=order_mgr.set_stop_loss_order, args=(deal_run, new_sl, "Trailing HL"), daemon=True).start()

            elif direction == "SHORT" and last_ph:
                new_sl = round(last_ph + SL_BUFFER_PTS, 2)
                if new_sl < runner_sl:
                    logger.info(f"[{time_str}] 📉 [TRAILING RUNNER ABBASSATO] Nuovo LH {last_ph:.2f}. Trailing SL abbassato a {new_sl:.2f}")
                    self.position["runner_sl"] = new_sl
                    self.save_state()
                    if deal_run:
                        threading.Thread(target=order_mgr.set_stop_loss_order, args=(deal_run, new_sl, "Trailing LH"), daemon=True).start()

    def _close_all_to_flat(self, exec_price: float, time_str: str, reason: str):
        with self.lock:
            if not self.position or self.closing_in_progress:
                return
            self.closing_in_progress = True

        pos = self.position
        direction = pos["direction"]
        open_px = pos["open_price"]
        contracts = pos.get("contracts", CORE_CONTRACTS)
        deal_run = pos.get("deal_id_runner")
        deal_banc = pos.get("deal_id_bancomat")
        order_mgr = HyperOrderManager.get_instance(self.account_dir)

        pnl_pts = (exec_price - open_px) if direction == "LONG" else (open_px - exec_price)
        total_pnl = round(pnl_pts * self.point_value * contracts, 2)

        logger.info(f"[{time_str}] 🛑 CHIUSURA FLAT US500: {direction} {contracts}c a {exec_price:.2f} | PnL: {total_pnl:+.2f} € | Motivo: {reason}")

        for deal_id, sz in [(deal_banc, BANCOMAT_CONTRACTS), (deal_run, RUNNER_CONTRACTS)]:
            if deal_id:
                threading.Thread(
                    target=order_mgr.close_market_deal,
                    args=(deal_id, direction, sz, f"Chiusura FLAT {reason}", reason),
                    daemon=True
                ).start()

        with self.lock:
            self.balance = round(self.balance + total_pnl, 2)
            self.trades.append({
                "time_open": pos["open_time"],
                "time_close": time_str,
                "direction": direction,
                "open_price": open_px,
                "close_price": exec_price,
                "contracts": contracts,
                "pnl_eur": total_pnl,
                "reason": reason,
                "tf": "5M"
            })
            self.position = None
            self.closing_in_progress = False
            self.save_state()

        order_mgr.send_notification(
            f"🏁 APEX US500 CHIUSURA: {total_pnl:+.2f} €",
            f"Trade chiuso: {total_pnl:+.2f} € a {exec_price:.2f} ({reason})",
            "white_check_mark" if total_pnl >= 0 else "x"
        )

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

            if self.curr_boundary != boundary:
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

            self._evaluate_traffic_lights(time_str)
            self._manage_open_position(mid, time_str)

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
                if is_us500_feed_suspended():
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
                            logger.error(f"Errore _process_tick US500 M5: {e}")

                sub = LightstreamerSubscription(
                    mode="DISTINCT",
                    items=[f"CHART:{EPIC_US500}:TICK"],
                    fields=["BID", "OFR", "UTM"]
                )
                sub.addlistener(on_tick)
                ls_client.subscribe(sub)
                logger.info(f"✅ Sottoscrizione Lightstreamer M5 attiva su CHART:{EPIC_US500}:TICK")

                while self.running and self.ls_connected:
                    time.sleep(2)

            except Exception as e:
                logger.warning(f"Errore connessione Lightstreamer US500: {e}")
                with self.lock:
                    self.ls_connected = False
                time.sleep(5)

    def _run_rollover_watchdog(self):
        while self.running:
            try:
                now_t = now_it()
                if is_us500_trading_suspended(now_t):
                    if self.position:
                        exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                        self._close_all_to_flat(exec_px, now_t.strftime("%H:%M:%S"), reason="🌙 Chiusura Freeze Notturno US500")
            except Exception:
                pass
            time.sleep(10)

    def manual_entry_core(self, direction: str) -> dict:
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
