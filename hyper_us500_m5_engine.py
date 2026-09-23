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

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_US500 = "IX.D.SPTRD.IBE.IP"
CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi (55 barre M5 = 275 min = ~4.5 ore)
WARMUP_BARS_TK = 55     # Retrocompatibilità
STATE_FILE = "hyper_us500_m5_state.json"

# Parametri Strategia: S&R Puro KJ55 (Core 4c + Incrementi Pullback 2c + Trailing Stop M5 - Max 8c)
CORE_CONTRACTS = 4          # Size iniziale Core: 4 contratti
CORE_TS_TRIGGER_PIPS = 15.0 # Attivazione Trailing Stop: a +15 punti di guadagno
CORE_TS_LOCK_PIPS = 10.0    # Lock profit iniziale: +10 punti garantiti (+40.00 €)
CORE_TS_STEP_PIPS = 4.0     # Avanzamento a scatti: di 4 in 4 punti
INC_CONTRACTS = 2           # Incrementi: 2 contratti ciascuno
MAX_INCREMENTS = 2          # Max 2 incrementi x 2c = 4 contratti (Totale max 8c con core)
INC_TP_PIPS = 10.0          # TP incrementi su M5: 10 punti (+20.00 € a incremento)
KJ_TOLERANCE_PIPS = 10.0    # Tolleranza su Kijun 55
MAX_INC_KJ_DISTANCE_PIPS = 10.0 # Max distanza da KJ per consentire incrementi: <= 10 punti
MIN_DIST_INCR_PIPS = 10.0       # Distanza minima tra incrementi consecutivi: >= 10 punti
PARACADUTE_KJ_PIPS = 10.0       # Paracadute KJ Intracandela: Stop emergenza live a KJ +- 10 punti
CANDELA_SEGNALE_OFFSET_PIPS = 5.0 # Candela Segnale M5: Stop confermato su rottura Massimo/Minimo +- 5 punti
CORE_MIN_KJ_DIST_PIPS = 3.0     # Minima distanza Prezzo - KJ per ingresso Core M5: >= 3 punti (stacco da KJ)

# Parametri legacy per retrocompatibilità
KJ_TK_MIN_FORBICE_PIPS = 0.0
TK_FILTER_PIPS = 0.0
CORE_REENTRY_KJ_DIST_PIPS = 3.0

def is_us500_feed_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True durante la chiusura weekend o pausa tecnica CME (22:15 - 22:30)."""
    if dt is None:
        dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    if wd == 4 and t >= datetime.time(23, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(23, 0):
        return True
    if datetime.time(22, 15) <= t < datetime.time(22, 30):
        return True
    return False

def is_us500_trading_suspended(dt: datetime.datetime = None) -> bool:
    return is_us500_feed_suspended(dt)

def is_us500_market_suspended(dt: datetime.datetime = None) -> bool:
    return is_us500_trading_suspended(dt)

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

        # Storico barre concluse (ultime 500)
        self.candles = []
        self.kj55 = None
        self.tk233 = None
        self.tk144 = None

        # Portafoglio e Trading
        self.initial_balance = 10000.0
        self.balance = 10000.0
        self.point_value = 1.0   # 1 EUR per punto per contratto
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False
        self.use_core_trailing = True

        self.position = None
        self.increments = []
        self.inc_tp_pips = INC_TP_PIPS

        # Candela Segnale KJ
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_ref_price = None

        self.trades = []
        self.last_ts_cycle = None

        self.closing_in_progress = False
        self.entry_in_progress = False

        # 1. Carica stato persistito
        self.load_state()

        # 2. Sincronizzazione candele M5 da IG REST
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
        central_file = "candele_Spot_US500_M5.json"
        if os.path.exists(central_file):
            try:
                mtime = os.path.getmtime(central_file)
                if (time.time() - mtime) < 300:
                    with open(central_file, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    if isinstance(cached, list) and len(cached) >= WARMUP_BARS_KJ:
                        with self.lock:
                            self.candles = cached[-500:]
                            self._recalculate_indicators()
                            self.save_state()
                        return
            except Exception:
                pass

        try:
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

            url_px = f"https://demo-api.ig.com/gateway/deal/prices/{EPIC_US500}?resolution=MINUTE_5&max=250&pageSize=0"
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
                            st_time = p.get("snapshotTime", "")
                            try:
                                dt_u = datetime.datetime.strptime(st_time, "%Y/%m/%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                                t_str = dt_u.astimezone(TZ_ITALIA).strftime("%H:%M:%S")
                                boundary = int(dt_u.timestamp() // CANDLE_SECONDS) * CANDLE_SECONDS
                            except Exception:
                                t_str = st_time.split(" ")[1] if " " in st_time else st_time
                                boundary = int(time.time() // CANDLE_SECONDS) * CANDLE_SECONDS

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
                            continue

                    if loaded_candles:
                        self.candles = loaded_candles[-500:]
                        self._recalculate_indicators()
                        self.save_state()

                        try:
                            with open(central_file, "w", encoding="utf-8") as f:
                                json.dump(self.candles, f, indent=2)
                        except Exception:
                            pass
        except Exception:
            pass

    def _recalculate_indicators(self):
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
            self.trades = d.get("trades", [])
            self.candles = d.get("candles", [])
            self.last_ts_cycle = d.get("last_ts_cycle")
            self.signal_candle_active = bool(d.get("signal_candle_active", False))
            self.signal_stop_price = d.get("signal_stop_price")
            self.signal_ref_price = d.get("signal_ref_price")
            self._recalculate_indicators()

    def save_state(self):
        st_file = self._get_state_file()
        with self.lock:
            data = {
                "balance": self.balance,
                "trading_enabled": self.trading_enabled,
                "use_core_trailing": self.use_core_trailing,
                "position": self.position,
                "increments": self.increments,
                "signal_candle_active": getattr(self, "signal_candle_active", False),
                "signal_stop_price": getattr(self, "signal_stop_price", None),
                "signal_ref_price": getattr(self, "signal_ref_price", None),
                "trades": self.trades[-100:],
                "candles": self.candles[-500:],
                "last_ts_cycle": self.last_ts_cycle
            }
        try:
            tmp = st_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if os.path.exists(st_file):
                try:
                    os.replace(tmp, st_file)
                except Exception:
                    with open(st_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    if os.path.exists(tmp): os.remove(tmp)
            else:
                os.replace(tmp, st_file)
        except Exception:
            pass

    def set_trading(self, enabled: bool):
        with self.lock:
            self.trading_enabled = enabled
            if not enabled:
                if self.position or self.increments:
                    exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                    t_str = now_it().strftime("%H:%M:%S")
                    self._close_all_to_flat(exec_px, t_str, reason="🛑 STOP TRADING Manuale Utente ➔ Chiusura immediata di tutte le posizioni a FLAT")
            self.save_state()

    def _run_streaming_loop(self):
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
                    ask_s = vals.get("OFFER")
                    t_str = now_it().strftime("%H:%M:%S")
                    if bid_s and ask_s:
                        try:
                            b = float(bid_s)
                            a = float(ask_s)
                            self._process_tick(b, a, t_str)
                        except Exception:
                            pass

                sub = LightstreamerSubscription(
                    mode="MERGE",
                    items=[f"MARKET:{EPIC_US500}"],
                    fields=["BID", "OFFER", "HIGH", "LOW", "UPDATE_TIME"]
                )
                sub.addlistener(on_tick)
                ls_client.subscribe(sub)

                while self.running and self.ls_connected:
                    time.sleep(2)
                    if is_us500_market_suspended():
                        with self.lock:
                            has_pos = (self.position is not None or len(self.increments) > 0)
                            mid_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                        if has_pos:
                            t_str = now_it().strftime("%H:%M:%S")
                            self._close_all_to_flat(mid_px, t_str, reason="Pausa / Weekend US500 ➔ Chiusura automatica anticipata di sicurezza a FLAT")
                    if self.last_tick_time and (time.time() - self.last_tick_time) > 40:
                        break

            except Exception:
                pass
            finally:
                with self.lock:
                    self.ls_connected = False
                time.sleep(5)

    def _check_core_trailing_stop(self, current_price: float, time_str: str):
        if not self.position or not getattr(self, "use_core_trailing", True):
            return

        pos = self.position
        direction = pos["direction"]
        open_px = pos["open_price"]

        if direction == "LONG":
            profit_pips = round(current_price - open_px, 2)
        else:
            profit_pips = round(open_px - current_price, 2)

        if not pos.get("ts_active", False):
            if profit_pips >= CORE_TS_TRIGGER_PIPS:
                pos["ts_active"] = True
                pos["peak_price"] = current_price
                if direction == "LONG":
                    pos["ts_price"] = round(open_px + CORE_TS_LOCK_PIPS, 2)
                else:
                    pos["ts_price"] = round(open_px - CORE_TS_LOCK_PIPS, 2)

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🚀 TRAILING ATTIVATO US500 M5 {direction}",
                    "open_price": open_px,
                    "close_price": current_price,
                    "contracts": pos["contracts"],
                    "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                    "balance": round(self.balance, 2),
                    "reason": f"Raggiunti +{profit_pips:.1f}p @ {current_price:.2f} ➔ Lock Profit +{CORE_TS_LOCK_PIPS:.1f}p @ {pos['ts_price']:.2f}"
                })
                self.save_state()

        if pos.get("ts_active", False):
            peak_px = pos.get("peak_price", current_price)
            if direction == "LONG":
                if current_price > peak_px:
                    delta = current_price - peak_px
                    if delta >= CORE_TS_STEP_PIPS:
                        steps = int(delta // CORE_TS_STEP_PIPS)
                        pos["peak_price"] = round(peak_px + steps * CORE_TS_STEP_PIPS, 2)
                        pos["ts_price"] = round(pos["ts_price"] + steps * CORE_TS_STEP_PIPS, 2)
                        self.save_state()

                if current_price <= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

            else: # SHORT
                if current_price < peak_px:
                    delta = peak_px - current_price
                    if delta >= CORE_TS_STEP_PIPS:
                        steps = int(delta // CORE_TS_STEP_PIPS)
                        pos["peak_price"] = round(peak_px - steps * CORE_TS_STEP_PIPS, 2)
                        pos["ts_price"] = round(pos["ts_price"] - steps * CORE_TS_STEP_PIPS, 2)
                        self.save_state()

                if current_price >= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

    def _execute_entry_core(self, direction: str, exec_price: float, time_str: str):
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            res = order_mgr.open_market_deal(
                direction=direction,
                size=CORE_CONTRACTS,
                limit_level=None,
                label="Core US500 M5",
                epic=EPIC_US500
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
                        "action": f"🚀 OPEN REAL IG US500 {direction} ({CORE_CONTRACTS}c Core M5)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": CORE_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Ingresso IG Reale US500 {direction} @ {real_open:.2f} (Deal ID Core: {deal_id})"
                    })
                    self.save_state()
        except Exception as e:
            logger.error(f"Errore apertura Core US500 M5 IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_entry_increment(self, direction: str, exec_price: float, time_str: str):
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            tp_px = round(exec_price + self.inc_tp_pips if direction == "LONG" else exec_price - self.inc_tp_pips, 2)
            res = order_mgr.open_market_deal(
                direction=direction,
                size=INC_CONTRACTS,
                limit_level=tp_px,
                label=f"Incremento US500 M5 #{len(self.increments)+1}",
                epic=EPIC_US500
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
                        "action": f"➕ OPEN REAL IG INC US500 {direction} (+{INC_CONTRACTS}c, Tot: {tot_c}c)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": INC_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Incremento US500 M5 @ {real_open:.2f} (TP: {tp_px:.2f}, Deal ID: {deal_id})"
                    })
                    self.save_state()
        except Exception as e:
            logger.error(f"Errore apertura incremento US500 M5 IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_close_increment(self, inc: dict, current_price: float, time_str: str):
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            deal_id = inc.get("deal_id")
            res = order_mgr.close_market_deal(
                deal_id=deal_id,
                direction_open=inc["direction"],
                size=inc["contracts"],
                label="TP Incremento US500 M5",
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
                    reason=f"TP Incremento US500 (+{self.inc_tp_pips:.1f}p)",
                    time_open=inc.get("open_time", time_str),
                    label="Incremento US500 M5"
                )

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🎯 TP INC US500 {inc['direction']} (+{profit:+.2f} €)",
                    "open_price": inc["open_price"],
                    "close_price": close_px,
                    "contracts": inc["contracts"],
                    "pnl": profit,
                    "balance": round(self.balance, 2),
                    "reason": f"Chiusura Deal US500 {deal_id}: TP raggiunto @ {close_px:.2f}"
                })
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura incremento US500 M5 IG: {e}")

    def _execute_close_all_flat(self, exec_price: float, time_str: str, reason: str):
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            with self.lock:
                pos_to_close = dict(self.position) if self.position else None
                incs_to_close = [dict(i) for i in self.increments]
                self.position = None
                self.increments = []
                self.save_state()

            if pos_to_close and pos_to_close.get("deal_id"):
                deal_id = pos_to_close["deal_id"]
                res = order_mgr.close_market_deal(
                    deal_id=deal_id,
                    direction_open=pos_to_close["direction"],
                    size=pos_to_close["contracts"],
                    label="Chiusura Flat US500 Core",
                    reason_note=reason
                )
                profit = float(res.get("profit") or 0.0)
                close_px = float(res.get("close_level") or exec_price)
                with self.lock:
                    self.balance += profit
                    order_mgr.record_closed_trade(
                        tf="5M",
                        direction=pos_to_close["direction"],
                        contracts=pos_to_close["contracts"],
                        open_price=pos_to_close["open_price"],
                        close_price=close_px,
                        pnl_eur=profit,
                        deal_id=deal_id,
                        reason=reason,
                        time_open=pos_to_close.get("open_time", time_str),
                        label="Core US500 M5"
                    )
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🏁 CLOSE REAL IG US500 {pos_to_close['direction']} ({profit:+.2f} €)",
                        "open_price": pos_to_close["open_price"],
                        "close_price": close_px,
                        "contracts": pos_to_close["contracts"],
                        "pnl": profit,
                        "balance": round(self.balance, 2),
                        "reason": reason
                    })

            for inc in incs_to_close:
                if inc.get("deal_id"):
                    res_i = order_mgr.close_market_deal(
                        deal_id=inc["deal_id"],
                        direction_open=inc["direction"],
                        size=inc["contracts"],
                        label="Chiusura Flat Residuo US500 M5",
                        reason_note=reason
                    )
                    prof_i = float(res_i.get("profit") or 0.0)
                    close_i = float(res_i.get("close_level") or exec_price)
                    with self.lock:
                        self.balance += prof_i
                        order_mgr.record_closed_trade(
                            tf="5M",
                            direction=inc["direction"],
                            contracts=inc["contracts"],
                            open_price=inc["open_price"],
                            close_price=close_i,
                            pnl_eur=prof_i,
                            deal_id=inc["deal_id"],
                            reason=reason,
                            time_open=inc.get("open_time", time_str),
                            label="Incremento US500 M5"
                        )
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"🏁 CLOSE REAL INC US500 {inc['direction']} ({prof_i:+.2f} €)",
                            "open_price": inc["open_price"],
                            "close_price": close_i,
                            "contracts": inc["contracts"],
                            "pnl": prof_i,
                            "balance": round(self.balance, 2),
                            "reason": reason
                        })
                    time.sleep(1.5)

            with self.lock:
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura posizioni flat US500 M5 IG: {e}")
        finally:
            with self.lock:
                self.closing_in_progress = False

    def _close_cycle_trailing_hit(self, current_price: float, time_str: str):
        if not self.position or getattr(self, "closing_in_progress", False):
            return
        self.closing_in_progress = True
        threading.Thread(
            target=self._execute_close_all_flat,
            args=(current_price, time_str, f"Trailing Stop US500 M5 toccato @ {current_price:.2f}"),
            daemon=True
        ).start()

    def _check_increments_tp(self, current_price: float, time_str: str):
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
        if not self.position or self.kj55 is None:
            return

        pos_dir = self.position["direction"]
        if pos_dir == "LONG":
            threshold = round(self.kj55 - PARACADUTE_KJ_PIPS, 2)
            if mid <= threshold:
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ US500: Mid {mid:.2f} <= (KJ {self.kj55:.2f} - {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )
        elif pos_dir == "SHORT":
            threshold = round(self.kj55 + PARACADUTE_KJ_PIPS, 2)
            if mid >= threshold:
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ US500: Mid {mid:.2f} >= (KJ {self.kj55:.2f} + {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )

    def _check_candela_segnale_stop(self, mid: float, time_str: str):
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
                    reason=f"Candela Segnale KJ US500: Mid {mid:.2f} <= Stop {stop_val:.2f} ➔ FLAT"
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
                    reason=f"Candela Segnale KJ US500: Mid {mid:.2f} >= Stop {stop_val:.2f} ➔ FLAT"
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

            market_suspended = is_us500_market_suspended()

            if market_suspended:
                if self.position or self.increments:
                    self._close_all_to_flat(mid, time_str, reason="Pausa / Weekend US500 ➔ Chiusura automatica anticipata di sicurezza a FLAT")
            else:
                if self.trading_enabled and self.position and getattr(self, "use_core_trailing", True):
                    self._check_core_trailing_stop(mid, time_str)

                if self.trading_enabled and self.increments:
                    self._check_increments_tp(mid, time_str)

                if self.trading_enabled and self.position and self.kj55 is not None:
                    self._check_paracadute_kj(mid, time_str)

                if self.trading_enabled and self.position and self.signal_candle_active:
                    self._check_candela_segnale_stop(mid, time_str)

            if self.curr_boundary is None:
                self.curr_boundary = boundary
                self.curr_open = mid
                self.curr_high = mid
                self.curr_low = mid
                self.curr_close = mid
                self.curr_bar_start_t = now_t
                return

            if boundary == self.curr_boundary:
                if mid > self.curr_high: self.curr_high = mid
                if mid < self.curr_low: self.curr_low = mid
                self.curr_close = mid
            else:
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

                self._recalculate_indicators()

                new_open = mid
                self.curr_boundary = boundary
                self.curr_open = new_open
                self.curr_high = new_open
                self.curr_low = new_open
                self.curr_close = new_open
                self.curr_bar_start_t = now_t

                self.save_state()

                if self.trading_enabled and not market_suspended and self.kj55 is not None:
                    self._evaluate_pure_sr_strategy(closed_candle, self.kj55, new_open, time_str)

    def _evaluate_pure_sr_strategy(self, closed_candle: dict, kj: float, exec_price: float, time_str: str):
        prev_close = closed_candle["close"]
        prev_open = closed_candle["open"]

        if prev_close > kj:
            if self.position is None:
                dist_kj = round(exec_price - kj, 2)
                if dist_kj >= CORE_MIN_KJ_DIST_PIPS:
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
            elif self.position and self.position["direction"] == "LONG":
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

        elif prev_close < kj:
            if self.position is None:
                dist_kj = round(kj - exec_price, 2)
                if dist_kj >= CORE_MIN_KJ_DIST_PIPS:
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
            elif self.position and self.position["direction"] == "SHORT":
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

    def _close_all_to_flat(self, exec_price: float, time_str: str, reason: str):
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
