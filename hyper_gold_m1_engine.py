import os
import sys
import time
import json
import threading
import datetime
import requests

EPIC_GOLD = "CS.D.CFEGOLD.CBE.IP"
CANDLE_SECONDS = 300    # 5 Minuti (M5) per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi
WARMUP_BARS_TK = 144    # Tenkan/Macro 144 periodi
STATE_FILE = "hyper_gold_m1_state.json"
ENV_PATH = os.path.join("FIORDOK_DEMO", ".env")

# Parametri Strategia: Core + Incrementi (Size 20 totale)
CORE_CONTRACTS = 5      # Size iniziale Core: 5 contratti
CORE_TP_PIPS = 10.0     # Take Profit Core: 10 pip (chiude tutto a FLAT e resta pronto ad autorestart)
INC_CONTRACTS = 3       # Incrementi: 3 contratti ciascuno
MAX_INCREMENTS = 5      # Max 5 incrementi x 3c = 15 contratti (Totale max 20 con core)
INC_TP_PIPS = 4.0       # TP incrementi su M5: 4 pip
KJ_TOLERANCE_PIPS = 3.0 # Tolleranza di 3 pip prima di chiudere la posizione su uscita KJ55

class HyperGoldM1Engine:
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
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
        self.tk144 = None

        # Portafoglio e Trading
        self.initial_balance = 10000.0
        self.balance = 10000.0
        self.point_value = 1.0   # 1 EUR per punto/pip per contratto
        self.num_contracts = CORE_CONTRACTS
        self.trading_enabled = False

        # Posizione Core: None (FLAT) o {"direction": "LONG"/"SHORT", "open_price": float, "contracts": 5, "tp_price": float, "open_time": str}
        self.position = None

        # Incrementi aperti: lista di {"id": int, "direction": str, "open_price": float, "contracts": 3, "tp_price": float, "open_time": str}
        self.increments = []
        self.inc_tp_pips = INC_TP_PIPS

        # Storico eseguiti
        self.trades = []

        # 1. Carica eventuale stato persistito
        self.load_state()

        # 2. Se non abbiamo abbastanza candele storiche M5 (meno di 150), recupero rapido una tantum da IG REST
        if len(self.candles) < WARMUP_BARS_TK:
            self._fetch_historical_m5_bars_from_ig()

        # 3. Avvia thread di streaming Lightstreamer in background
        self.stream_thread = threading.Thread(target=self._run_streaming_loop, daemon=True)
        self.stream_thread.start()

    def _get_ig_credentials(self):
        user, pwd, api_key = None, None, None
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("IG_USERNAME="): user = line.split("=", 1)[1]
                    elif line.startswith("IG_PASSWORD="): pwd = line.split("=", 1)[1]
                    elif line.startswith("IG_API_KEY="): api_key = line.split("=", 1)[1]
        return user, pwd, api_key

    def _fetch_historical_m5_bars_from_ig(self):
        """Singola chiamata REST una tantum per scaricare 200 barre M5 storiche senza overflow"""
        try:
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

            # Recupera 200 barre storiche M5 in UNA SOLA chiamata REST
            url_px = f"https://demo-api.ig.com/gateway/deal/prices/{EPIC_GOLD}?resolution=MINUTE_5&max=200&pageSize=0"
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
                            t_str = st_time.split(" ")[1] if " " in st_time else st_time
                            op = round((p["openPrice"]["bid"] + p["openPrice"]["ask"]) / 2.0, 2)
                            hi = round((p["highPrice"]["bid"] + p["highPrice"]["ask"]) / 2.0, 2)
                            lo = round((p["lowPrice"]["bid"] + p["lowPrice"]["ask"]) / 2.0, 2)
                            cl = round((p["closePrice"]["bid"] + p["closePrice"]["ask"]) / 2.0, 2)
                            loaded_candles.append({
                                "boundary": 0,
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
        except Exception:
            pass

    def _recalculate_indicators(self):
        """Calcola KJ55 e TK144 in base allo storico candele M5 disponibile"""
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

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self.balance = float(d.get("balance", 10000.0))
                    self.trading_enabled = bool(d.get("trading_enabled", False))
                    self.position = d.get("position")
                    self.increments = d.get("increments", [])
                    self.inc_tp_pips = float(d.get("inc_tp_pips", INC_TP_PIPS))
                    self.trades = d.get("trades", [])
                    self.candles = d.get("candles", [])
                    self._recalculate_indicators()
            except Exception:
                pass

    def save_state(self):
        try:
            d = {
                "balance": self.balance,
                "trading_enabled": self.trading_enabled,
                "position": self.position,
                "increments": self.increments,
                "inc_tp_pips": self.inc_tp_pips,
                "trades": self.trades[-100:],
                "candles": self.candles[-500:]
            }
            tmp = f"{STATE_FILE}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def reset_portfolio(self):
        with self.lock:
            self.balance = self.initial_balance
            self.position = None
            self.increments = []
            self.trades = []
            self.save_state()

    def set_trading(self, enabled: bool):
        with self.lock:
            self.trading_enabled = enabled
            self.save_state()

    def _run_streaming_loop(self):
        while self.running:
            try:
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

    def _check_core_tp(self, current_price: float, time_str: str):
        """Controlla se la posizione Core ha raggiunto il Take Profit di 10 pip.
        In caso positivo: chiude TUTTE le posizioni (Core + incrementi), va a FLAT e resta in attesa automatica del prossimo segnale."""
        if not self.position:
            return

        pos = self.position
        hit_tp = False
        core_tp_price = pos.get("tp_price")
        if core_tp_price is None:
            if pos["direction"] == "LONG":
                core_tp_price = round(pos["open_price"] + CORE_TP_PIPS, 2)
            else:
                core_tp_price = round(pos["open_price"] - CORE_TP_PIPS, 2)
            pos["tp_price"] = core_tp_price

        if pos["direction"] == "LONG" and current_price >= core_tp_price:
            hit_tp = True
        elif pos["direction"] == "SHORT" and current_price <= core_tp_price:
            hit_tp = True

        if hit_tp:
            # 1. Chiudi Core con Take Profit (+10 pip * 5 contratti * 1 = +50 €)
            core_pnl = round(CORE_TP_PIPS * pos["contracts"] * self.point_value, 2)
            self.balance += core_pnl
            self.trades.insert(0, {
                "time": time_str,
                "action": f"🎯 TP CORE {pos['direction']} (+{CORE_TP_PIPS:.1f} pip)",
                "open_price": pos["open_price"],
                "close_price": core_tp_price,
                "contracts": pos["contracts"],
                "pnl": core_pnl,
                "balance": round(self.balance, 2),
                "reason": f"Raggiunto TP Core {CORE_TP_PIPS:.0f} pip @ {core_tp_price:.2f} ➔ FLAT E ATTESA AUTO SEGNALE"
            })
            self.position = None

            # 2. Chiudi tutti gli incrementi residui
            for inc in self.increments:
                if inc["direction"] == "LONG":
                    inc_pnl = round((current_price - inc["open_price"]) * inc["contracts"] * self.point_value, 2)
                else:
                    inc_pnl = round((inc["open_price"] - current_price) * inc["contracts"] * self.point_value, 2)
                self.balance += inc_pnl
                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"CLOSE INC {inc['direction']} (TP CORE TRIGGER)",
                    "open_price": inc["open_price"],
                    "close_price": current_price,
                    "contracts": inc["contracts"],
                    "pnl": inc_pnl,
                    "balance": round(self.balance, 2),
                    "reason": f"Chiusura a FLAT per TP Core raggiunto @ {core_tp_price:.2f}"
                })
            self.increments = []

            # Salvataggio: il trading_enabled RESTA TRUE, pronto al prossimo segnale in modo automatico!
            self.save_state()

    def _check_increments_tp(self, current_price: float, time_str: str):
        """Controlla Take Profit (+4 pip = +12.00 €) per gli incrementi aperti su M5"""
        remaining = []
        closed_any = False
        for inc in self.increments:
            hit_tp = False
            if inc["direction"] == "LONG" and current_price >= inc["tp_price"]:
                hit_tp = True
            elif inc["direction"] == "SHORT" and current_price <= inc["tp_price"]:
                hit_tp = True

            if hit_tp:
                pnl = round(self.inc_tp_pips * inc["contracts"] * self.point_value, 2)
                self.balance += pnl
                trade_log = {
                    "time": time_str,
                    "action": f"🎯 TP INC {inc['direction']} (+{self.inc_tp_pips:.1f} pip)",
                    "open_price": inc["open_price"],
                    "close_price": inc["tp_price"],
                    "contracts": inc["contracts"],
                    "pnl": pnl,
                    "balance": round(self.balance, 2),
                    "reason": f"Raggiunto TP {self.inc_tp_pips:.0f} pip @ {inc['tp_price']:.2f}"
                }
                self.trades.insert(0, trade_log)
                closed_any = True
            else:
                remaining.append(inc)

        if closed_any:
            self.increments = remaining
            self.save_state()

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

            # 1. Verifica Take Profit (10 pip) per la Core
            if self.trading_enabled and self.position:
                self._check_core_tp(mid, time_str)

            # 2. Verifica Take Profit (4 pip) per gli incrementi aperti
            if self.trading_enabled and self.increments:
                self._check_increments_tp(mid, time_str)

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
                    "time": datetime.datetime.fromtimestamp(self.curr_boundary).strftime("%H:%M:%S"),
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

                # Strategia Unidirezionale TK144 + Trigger KJ55
                if self.trading_enabled and self.kj55 is not None and self.tk144 is not None:
                    self._evaluate_unidirectional_strategy(closed_candle, self.kj55, self.tk144, new_open, time_str)

    def _evaluate_unidirectional_strategy(self, closed_candle: dict, kj: float, tk: float, exec_price: float, time_str: str):
        prev_close = closed_candle["close"]
        prev_open = closed_candle["open"]

        # =============================================================
        # 1. REGIME BULLISH: PREZZO > TK144 (SOLO TRADE LONG)
        # =============================================================
        if prev_close > tk:
            if self.position and self.position["direction"] == "SHORT":
                self._close_all_to_flat(exec_price, time_str, reason=f"Inversione Macro: Close {prev_close:.2f} > TK144 {tk:.2f}")

            if prev_close > kj:
                if self.position is None:
                    # Apri Core LONG (5 contratti)
                    self.position = {
                        "direction": "LONG",
                        "open_price": exec_price,
                        "tp_price": round(exec_price + CORE_TP_PIPS, 2),
                        "contracts": CORE_CONTRACTS,
                        "open_time": time_str
                    }
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": "OPEN CORE LONG",
                        "open_price": exec_price,
                        "close_price": None,
                        "contracts": CORE_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Prezzo > TK144 ({tk:.2f}) e Close > KJ ({kj:.2f}) | TP Core: {exec_price + CORE_TP_PIPS:.2f} (+10 pip)"
                    })
                    self.save_state()
                elif self.position["direction"] == "LONG":
                    # Core già LONG: incremento su barra contraria (rossa) da 3c con TP 4 pip
                    if prev_close < prev_open:
                        if len(self.increments) < MAX_INCREMENTS:
                            tp_p = round(exec_price + self.inc_tp_pips, 2)
                            new_inc = {
                                "id": int(time.time() * 1000),
                                "direction": "LONG",
                                "open_price": exec_price,
                                "contracts": INC_CONTRACTS,
                                "tp_price": tp_p,
                                "open_time": time_str
                            }
                            self.increments.append(new_inc)
                            tot_c = CORE_CONTRACTS + sum(i["contracts"] for i in self.increments)
                            self.trades.insert(0, {
                                "time": time_str,
                                "action": f"➕ OPEN INC LONG (+3 Contr., Tot: {tot_c})",
                                "open_price": exec_price,
                                "close_price": None,
                                "contracts": INC_CONTRACTS,
                                "pnl": 0.0,
                                "balance": round(self.balance, 2),
                                "reason": f"Barra M5 rossa (C:{prev_close:.2f} < O:{prev_open:.2f}) | TP: {tp_p:.2f} (+4 pip)"
                            })
                            self.save_state()

            elif prev_close < (kj - KJ_TOLERANCE_PIPS):
                # Uscita KJ55 in regime Bullish con tolleranza 3 pip: chiudi tutto a FLAT
                if self.position and self.position["direction"] == "LONG":
                    self._close_all_to_flat(exec_price, time_str, reason=f"Uscita KJ: Close {prev_close:.2f} < (KJ {kj:.2f} - {KJ_TOLERANCE_PIPS:.0f} pip = {kj - KJ_TOLERANCE_PIPS:.2f}) ➔ FLAT")

        # =============================================================
        # 2. REGIME BEARISH: PREZZO < TK144 (SOLO TRADE SHORT)
        # =============================================================
        elif prev_close < tk:
            if self.position and self.position["direction"] == "LONG":
                self._close_all_to_flat(exec_price, time_str, reason=f"Inversione Macro: Close {prev_close:.2f} < TK144 {tk:.2f}")

            if prev_close < kj:
                if self.position is None:
                    # Apri Core SHORT (5 contratti)
                    self.position = {
                        "direction": "SHORT",
                        "open_price": exec_price,
                        "tp_price": round(exec_price - CORE_TP_PIPS, 2),
                        "contracts": CORE_CONTRACTS,
                        "open_time": time_str
                    }
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": "OPEN CORE SHORT",
                        "open_price": exec_price,
                        "close_price": None,
                        "contracts": CORE_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Prezzo < TK144 ({tk:.2f}) e Close < KJ ({kj:.2f}) | TP Core: {exec_price - CORE_TP_PIPS:.2f} (+10 pip)"
                    })
                    self.save_state()
                elif self.position["direction"] == "SHORT":
                    # Core già SHORT: incremento su barra contraria (verde) da 3c con TP 4 pip
                    if prev_close > prev_open:
                        if len(self.increments) < MAX_INCREMENTS:
                            tp_p = round(exec_price - self.inc_tp_pips, 2)
                            new_inc = {
                                "id": int(time.time() * 1000),
                                "direction": "SHORT",
                                "open_price": exec_price,
                                "contracts": INC_CONTRACTS,
                                "tp_price": tp_p,
                                "open_time": time_str
                            }
                            self.increments.append(new_inc)
                            tot_c = CORE_CONTRACTS + sum(i["contracts"] for i in self.increments)
                            self.trades.insert(0, {
                                "time": time_str,
                                "action": f"➕ OPEN INC SHORT (+3 Contr., Tot: {tot_c})",
                                "open_price": exec_price,
                                "close_price": None,
                                "contracts": INC_CONTRACTS,
                                "pnl": 0.0,
                                "balance": round(self.balance, 2),
                                "reason": f"Barra M5 verde (C:{prev_close:.2f} > O:{prev_open:.2f}) | TP: {tp_p:.2f} (+4 pip)"
                            })
                            self.save_state()

            elif prev_close > (kj + KJ_TOLERANCE_PIPS):
                # Uscita KJ55 in regime Bearish con tolleranza 3 pip: chiudi tutto a FLAT
                if self.position and self.position["direction"] == "SHORT":
                    self._close_all_to_flat(exec_price, time_str, reason=f"Uscita KJ: Close {prev_close:.2f} > (KJ {kj:.2f} + {KJ_TOLERANCE_PIPS:.0f} pip = {kj + KJ_TOLERANCE_PIPS:.2f}) ➔ FLAT")

    def _close_all_to_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude la Core e tutti gli incrementi tornando a FLAT"""
        if self.position:
            p = self.position
            if p["direction"] == "LONG":
                pnl = round((exec_price - p["open_price"]) * p["contracts"] * self.point_value, 2)
            else:
                pnl = round((p["open_price"] - exec_price) * p["contracts"] * self.point_value, 2)

            self.balance += pnl
            self.trades.insert(0, {
                "time": time_str,
                "action": f"CLOSE CORE {p['direction']} (FLAT)",
                "open_price": p["open_price"],
                "close_price": exec_price,
                "contracts": p["contracts"],
                "pnl": pnl,
                "balance": round(self.balance, 2),
                "reason": reason
            })
            self.position = None

        for inc in self.increments:
            if inc["direction"] == "LONG":
                inc_pnl = round((exec_price - inc["open_price"]) * inc["contracts"] * self.point_value, 2)
            else:
                inc_pnl = round((inc["open_price"] - exec_price) * inc["contracts"] * self.point_value, 2)

            self.balance += inc_pnl
            self.trades.insert(0, {
                "time": time_str,
                "action": f"CLOSE INC {inc['direction']} (FLAT)",
                "open_price": inc["open_price"],
                "close_price": exec_price,
                "contracts": inc["contracts"],
                "pnl": inc_pnl,
                "balance": round(self.balance, 2),
                "reason": f"Uscita FLAT @ {exec_price:.2f}"
            })
        self.increments = []
        self.save_state()

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
