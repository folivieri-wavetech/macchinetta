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

logger = logging.getLogger("HyperUS500Engine")

# Disabilita controllo revoca Windows su Lightstreamer Demo (evita timeout WinError 10060)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

EPIC_US500 = "IX.D.SPTRD.IBE.IP"
CANDLE_SECONDS = 30     # 30 Secondi per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi (27.5 min)
STATE_FILE = "hyper_us500_state.json"

# Parametri Strategia: Hyper 30S S&R Puro KJ55 (Posizione unica 8c + Trailing Stop 5p)
CORE_CONTRACTS = 8               # Size ingresso a mercato unico: 8 contratti
TS_STEP_PIPS = 5.0               # Step Trailing Stop discreto: ogni 5 punti di gain lo stop sale/scende di 5 punti
PARACADUTE_KJ_PIPS = 5.0         # Paracadute KJ Intracandela: Stop emergenza live a KJ +- 5 punti
PULLBACK_MAX_DIST_KJ_PIPS = 5.0  # Distanza max da KJ per consentire rientro pullback: <= 5.0 punti
CANDELA_SEGNALE_OFFSET_PIPS = 3.0 # Offset candela segnale di protezione

# Parametri legacy per retrocompatibilità
WARMUP_BARS_TK = 55
PARTIAL_CLOSE_CONTRACTS = 0
RUNNER_CONTRACTS = 8
PARTIAL_TP_PIPS = 0.0
CORE_TS_TRIGGER_PIPS = 5.0
CORE_TS_LOCK_PIPS = 0.0
CORE_TS_DISTANCE_PIPS = 5.0
TK_FILTER_PIPS = 0.0
CORE_REENTRY_KJ_DIST_PIPS = 5.0
INC_CONTRACTS = 0
MAX_INCREMENTS = 0
INC_TP_PIPS = 5.0
DEFAULT_SCALINI_PLAN_30S = []

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

class HyperUS500Engine:
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
        self.point_value = 1.0   # 1 EUR per punto per contratto
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False
        self.use_core_trailing = True

        self.core_size = CORE_CONTRACTS
        self.scalini_plan = [dict(x) for x in DEFAULT_SCALINI_PLAN_30S]
        self.position = None
        self.increments = []
        self.inc_tp_pips = INC_TP_PIPS

        # Candela Segnale KJ
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_ref_price = None

        # Macchina a Stati Ciclo 30S (1 Trade Primario + Max 1 Rientro Pullback)
        self.cycle_direction = None    # "LONG" / "SHORT" / None
        self.cycle_phase = "IDLE"      # "IDLE", "PRIMARY_OPEN", "PULLBACK_ARMED", "PULLBACK_OPEN", "CYCLE_DONE"

        # Storico eseguiti e stato ultimo ciclo TS
        self.trades = []
        self.last_ts_cycle = None

        self.closing_in_progress = False
        self.entry_in_progress = False

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

            url_px = f"https://demo-api.ig.com/gateway/deal/prices/{EPIC_US500}?resolution=MINUTE&max=180&pageSize=0"
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
            self.cycle_direction = d.get("cycle_direction")
            self.cycle_phase = d.get("cycle_phase", "IDLE")
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
                "cycle_direction": getattr(self, "cycle_direction", None),
                "cycle_phase": getattr(self, "cycle_phase", "IDLE"),
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
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            if enabled:
                order_mgr.send_notification("🚀 AVVIO HYPER 30S: US 500 Cash", "[US 500] Scalping Hyper 30S attivato.", "rocket")
            else:
                order_mgr.send_notification("⏹️ STOP HYPER 30S: US 500 Cash", "[US 500] Scalping Hyper 30S disattivato dall'utente.", "stop_button")
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
                        except Exception:
                            pass

                sub = LightstreamerSubscription(
                    mode="DISTINCT",
                    items=[f"CHART:{EPIC_US500}:TICK"],
                    fields=["BID", "OFR", "UTM"]
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
                            self._close_all_to_flat(mid_px, t_str, reason="Pausa / Weekend US500 ➔ Chiusura automatica di sicurezza a FLAT")
                    if self.last_tick_time and (time.time() - self.last_tick_time) > 40:
                        break

            except Exception:
                pass
            finally:
                with self.lock:
                    self.ls_connected = False
                time.sleep(5)

    def _check_core_trailing_stop(self, current_price: float, time_str: str):
        """Gestisce il Trailing Stop a gradini discreti di 5 punti sulla posizione da 8 contratti."""
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
                target_stop = round(open_px + profit_locked, 2)
                cur_stop = pos.get("ts_price")
                if cur_stop is None or target_stop > cur_stop:
                    pos["ts_price"] = target_stop
                    pos["ts_active"] = True
                    pos["ts_locked_pips"] = profit_locked
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 TRAILING STOP STEP US500 {direction}",
                        "open_price": open_px,
                        "close_price": current_price,
                        "contracts": pos["contracts"],
                        "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                        "balance": round(self.balance, 2),
                        "reason": f"Peak +{peak_gain:.1f}p (k={k}) ➔ Stop Lock a {target_stop:.2f} (+{profit_locked:.1f}p)"
                    })
                    self.save_state()
                    order_mgr = HyperOrderManager.get_instance(self.account_dir)
                    order_mgr.send_notification(
                        "🎯 TRAILING STOP 30S: US 500 Cash",
                        f"[US 500] Trailing Stop LONG aggiornato a {target_stop:.2f} pt (Lock +{profit_locked:.1f}pt, Prezzo: {current_price:.2f} pt)",
                        "dart"
                    )

                if current_price <= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

            else: # SHORT
                target_stop = round(open_px - profit_locked, 2)
                cur_stop = pos.get("ts_price")
                if cur_stop is None or target_stop < cur_stop:
                    pos["ts_price"] = target_stop
                    pos["ts_active"] = True
                    pos["ts_locked_pips"] = profit_locked
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🚀 TRAILING STOP STEP US500 {direction}",
                        "open_price": open_px,
                        "close_price": current_price,
                        "contracts": pos["contracts"],
                        "pnl": round(profit_pips * pos["contracts"] * self.point_value, 2),
                        "balance": round(self.balance, 2),
                        "reason": f"Peak +{peak_gain:.1f}p (k={k}) ➔ Stop Lock a {target_stop:.2f} (+{profit_locked:.1f}p)"
                    })
                    self.save_state()
                    order_mgr = HyperOrderManager.get_instance(self.account_dir)
                    order_mgr.send_notification(
                        "🎯 TRAILING STOP 30S: US 500 Cash",
                        f"[US 500] Trailing Stop SHORT aggiornato a {target_stop:.2f} pt (Lock +{profit_locked:.1f}pt, Prezzo: {current_price:.2f} pt)",
                        "dart"
                    )

                if current_price >= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

    def _execute_entry_core(self, direction: str, exec_price: float, time_str: str):
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            contracts = CORE_CONTRACTS
            res = order_mgr.open_market_deal(
                direction=direction,
                size=contracts,
                limit_level=None,
                label=f"US500 30S {self.cycle_phase}",
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
                        "contracts": contracts,
                        "open_time": res.get("time") or time_str,
                        "ts_active": False,
                        "ts_price": None,
                        "ts_locked_pips": 0.0,
                        "peak_gain_pips": 0.0,
                        "phase": self.cycle_phase
                    }
                    action_label = "🚀 OPEN REAL IG US500" if self.cycle_phase == "PRIMARY_OPEN" else "🔄 OPEN PULLBACK US500"
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"{action_label} {direction} ({contracts}c 30S)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": contracts,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Ingresso IG Reale {direction} @ {real_open:.2f} (Fase: {self.cycle_phase}, Deal ID: {deal_id})"
                    })
                    self.save_state()
                    is_pullback = (self.cycle_phase == "PULLBACK_OPEN")
                    tag_ico = "arrows_counterclockwise" if is_pullback else "rocket"
                    titolo_ntfy = "🔄 OPEN PULLBACK 30S: US 500 Cash" if is_pullback else "🚀 OPEN HYPER 30S: US 500 Cash"
                    msg_ntfy = f"[US 500] {direction} {contracts}c a {real_open:.2f} pt (Deal ID: {deal_id}, Fase: {self.cycle_phase})"
                    order_mgr.send_notification(titolo_ntfy, msg_ntfy, tag_ico)
        except Exception as e:
            logger.error(f"Errore apertura Core US500 IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

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
                    label="US500 30S Flat",
                    reason_note=reason
                )
                profit = float(res.get("profit") or 0.0)
                close_px = float(res.get("close_level") or exec_price)
                with self.lock:
                    self.balance += profit
                    order_mgr.record_closed_trade(
                        tf="30S",
                        direction=pos_to_close["direction"],
                        contracts=pos_to_close["contracts"],
                        open_price=pos_to_close["open_price"],
                        close_price=close_px,
                        pnl_eur=profit,
                        deal_id=deal_id,
                        reason=reason,
                        time_open=pos_to_close.get("open_time", time_str),
                        label="US500 30S Flat"
                    )
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"🏁 CLOSE US500 {pos_to_close['direction']} ({profit:+.2f} €)",
                        "open_price": pos_to_close["open_price"],
                        "close_price": close_px,
                        "contracts": pos_to_close["contracts"],
                        "pnl": profit,
                        "balance": round(self.balance, 2),
                        "reason": reason
                    })
                is_ts = "Trailing" in reason or "TS" in reason
                is_rev = "Reversal" in reason or "Inversione" in reason or "taglio" in reason.lower()
                if is_ts:
                    tag_cl = "dart"
                    tit_cl = "🎯 TS HIT 30S: US 500 Cash"
                elif is_rev:
                    tag_cl = "warning"
                    tit_cl = "🛑 REVERSAL 30S: US 500 Cash"
                else:
                    tag_cl = "octagonal_sign"
                    tit_cl = "🛑 CHIUSURA FLAT 30S: US 500 Cash"
                msg_cl = f"[US 500] Posizione {pos_to_close['direction']} ({pos_to_close['contracts']}c) chiusa a {close_px:.2f} pt [PnL: {profit:+.2f} €] - Motivo: {reason}"
                order_mgr.send_notification(tit_cl, msg_cl, tag_cl)

            for inc in incs_to_close:
                if inc.get("deal_id"):
                    res_i = order_mgr.close_market_deal(
                        deal_id=inc["deal_id"],
                        direction_open=inc["direction"],
                        size=inc["contracts"],
                        label="Chiusura Flat Residuo US500",
                        reason_note=reason
                    )
                    prof_i = float(res_i.get("profit") or 0.0)
                    close_i = float(res_i.get("close_level") or exec_price)
                    with self.lock:
                        self.balance += prof_i
                        order_mgr.record_closed_trade(
                            tf="30S",
                            direction=inc["direction"],
                            contracts=inc["contracts"],
                            open_price=inc["open_price"],
                            close_price=close_i,
                            pnl_eur=prof_i,
                            deal_id=inc["deal_id"],
                            reason=reason,
                            time_open=inc.get("open_time", time_str),
                            label="Residuo US500"
                        )
                    time.sleep(1.5)

            with self.lock:
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura posizioni flat US500 IG: {e}")
        finally:
            with self.lock:
                self.closing_in_progress = False

    def _close_cycle_trailing_hit(self, current_price: float, time_str: str):
        if not self.position or getattr(self, "closing_in_progress", False):
            return
        self.closing_in_progress = True
        with self.lock:
            if self.cycle_phase == "PRIMARY_OPEN":
                self.cycle_phase = "PULLBACK_ARMED"
            elif self.cycle_phase == "PULLBACK_OPEN":
                self.cycle_phase = "CYCLE_DONE"
            self.save_state()

        threading.Thread(
            target=self._execute_close_all_flat,
            args=(current_price, time_str, f"Trailing Stop US500 preso @ {current_price:.2f} ➔ FLAT (Fase: {self.cycle_phase})"),
            daemon=True
        ).start()

    def _check_paracadute_kj(self, mid: float, time_str: str):
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
                    reason=f"🪂 Paracadute KJ US500: Mid {mid:.2f} <= (KJ {self.kj55:.2f} - {PARACADUTE_KJ_PIPS:.1f}p = {threshold:.2f}) ➔ FLAT"
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
                    reason=f"🪂 Paracadute KJ US500: Mid {mid:.2f} >= (KJ {self.kj55:.2f} + {PARACADUTE_KJ_PIPS:.1f}p = {threshold:.2f}) ➔ FLAT"
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
                with self.lock:
                    self.cycle_phase = "CYCLE_DONE"
                    self.save_state()
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
                with self.lock:
                    self.cycle_phase = "CYCLE_DONE"
                    self.save_state()
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

        prev_bar_close = None
        if len(self.candles) >= 2:
            prev_bar_close = self.candles[-2]["close"]

        taglio_fresco_long = (prev_close > kj) and (prev_open <= kj or (prev_bar_close is not None and prev_bar_close <= kj))
        taglio_fresco_short = (prev_close < kj) and (prev_open >= kj or (prev_bar_close is not None and prev_bar_close >= kj))

        # A) RESET CICLO SU TAGLIO FRESCO OPPOSTO O NUOVO
        if taglio_fresco_long and self.cycle_direction != "LONG":
            self.cycle_direction = "LONG"
            self.cycle_phase = "IDLE"
            self.signal_candle_active = False
            self.signal_stop_price = None

        elif taglio_fresco_short and self.cycle_direction != "SHORT":
            self.cycle_direction = "SHORT"
            self.cycle_phase = "IDLE"
            self.signal_candle_active = False
            self.signal_stop_price = None

        # B) MACCHINA A STATI DEL CICLO US500
        if self.position is None:
            # 1. TRADE PRIMARIO SU TAGLIO FRESCO
            if self.cycle_phase == "IDLE":
                if self.cycle_direction == "LONG" and prev_close > kj and taglio_fresco_long:
                    if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                        self.entry_in_progress = True
                        self.cycle_phase = "PRIMARY_OPEN"
                        self.save_state()
                        threading.Thread(
                            target=self._execute_entry_core,
                            args=("LONG", exec_price, time_str),
                            daemon=True
                        ).start()

                elif self.cycle_direction == "SHORT" and prev_close < kj and taglio_fresco_short:
                    if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                        self.entry_in_progress = True
                        self.cycle_phase = "PRIMARY_OPEN"
                        self.save_state()
                        threading.Thread(
                            target=self._execute_entry_core,
                            args=("SHORT", exec_price, time_str),
                            daemon=True
                        ).start()

            # 2. RIENTRO PULLBACK (MAX 1 PER CICLO)
            elif self.cycle_phase == "PULLBACK_ARMED":
                if self.cycle_direction == "LONG" and prev_close > kj:
                    dist_kj = round(prev_close - kj, 2)
                    is_green_rebound = (prev_close >= prev_open)
                    if dist_kj <= PULLBACK_MAX_DIST_KJ_PIPS and is_green_rebound:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            self.cycle_phase = "PULLBACK_OPEN"
                            self.save_state()
                            threading.Thread(
                                target=self._execute_entry_core,
                                args=("LONG", exec_price, time_str),
                                daemon=True
                            ).start()

                elif self.cycle_direction == "SHORT" and prev_close < kj:
                    dist_kj = round(kj - prev_close, 2)
                    is_red_rebound = (prev_close <= prev_open)
                    if dist_kj <= PULLBACK_MAX_DIST_KJ_PIPS and is_red_rebound:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            self.cycle_phase = "PULLBACK_OPEN"
                            self.save_state()
                            threading.Thread(
                                target=self._execute_entry_core,
                                args=("SHORT", exec_price, time_str),
                                daemon=True
                            ).start()

        # C) PROTEZIONE CANDELA SEGNALE SE LA POSIZIONE È APERTA ED IL PREZZO CHIUDE DALLA PARTE OPPOSTA
        elif self.position:
            pos_dir = self.position["direction"]
            if pos_dir == "LONG" and prev_close <= kj:
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

            elif pos_dir == "SHORT" and prev_close >= kj:
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

            elif (pos_dir == "LONG" and prev_close > kj) or (pos_dir == "SHORT" and prev_close < kj):
                if self.signal_candle_active:
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_ref_price = None
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
