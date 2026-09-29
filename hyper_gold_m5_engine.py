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
CANDLE_SECONDS = 600    # 10 Minuti (M10) per barra
WARMUP_BARS_KJ = 55     # Kijun 55 periodi (55 barre M10 = 550 min = ~9.1 ore)
WARMUP_BARS_TK = 55     # Retrocompatibilità
STATE_FILE = "hyper_gold_m5_state.json"

def aggregate_candles_to_10m(candles):
    """Aggrega una lista di candele a 10 Minuti (600s boundary) da candele 5M o 10M esistenti"""
    if not candles:
        return []
    buckets = {}
    for c in candles:
        b_target = int(c["boundary"] // CANDLE_SECONDS) * CANDLE_SECONDS
        if b_target not in buckets:
            buckets[b_target] = []
        buckets[b_target].append(c)

    aggregated = []
    for b_target in sorted(buckets.keys()):
        group = buckets[b_target]
        op = group[0]["open"]
        hi = max(x["high"] for x in group)
        lo = min(x["low"] for x in group)
        cl = group[-1]["close"]
        t_str = datetime.datetime.fromtimestamp(b_target, TZ_ITALIA).strftime("%H:%M:%S")
        aggregated.append({
            "boundary": b_target,
            "time": t_str,
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl
        })
    return aggregated

# Parametri Strategia: S&R Puro KJ55 a Doppia Velocità (Core + Incrementi Bancomat/Runner + Trailing Stop M5)
CORE_CONTRACTS = 5          # Size iniziale Core: 5 contratti
CORE_TS_TRIGGER_PIPS = 10.0 # Attivazione Trailing Stop Core: a +10 pip di guadagno
CORE_TS_LOCK_PIPS = 6.0     # Lock profit iniziale Core: +6 pip garantiti (+30.00 €)
CORE_TS_STEP_PIPS = 2.0     # Avanzamento a scatti Core: di 2 in 2 pip
INC_CONTRACTS = 5           # Incrementi: 5 contratti ciascuno (pari alla size Core)
MAX_INCREMENTS = 3          # Max 3 incrementi complessivi a mercato (totale max 20c con Core)

# Regime 1: "Bancomat" (Distanza da KJ <= 10 pip)
BANCOMAT_MAX_DIST_KJ = 10.0 # Soglia max per regime Bancomat: <= 10 pip da KJ
INC_TP_PIPS = 5.0           # TP incrementi Bancomat: 5 pip (+25.00 € a incremento)

# Regime 2: "Runner / Piramidazione di Trend" (Distanza da KJ > 10 pip)
RUNNER_THRESHOLD_KJ_DIST = 10.0 # Soglia spartiacque Bancomat (<= 10p) vs Runner (> 10p)
MAX_RUNNER_INCREMENTS = 3       # Max 3 incrementi Runner contemporanei
MIN_DIST_RUNNER_PIPS = 4.0      # Distanza minima di progressione a gradini tra incrementi Runner (>= 4 pip)
RUNNER_TS_TRIGGER_PIPS = 5.0    # Runner TS: a +5 pip dal prezzo di carico blocca a Pareggio (Breakeven +1p)
RUNNER_TS_STEP_PIPS = 4.0       # Runner TS: insegue a 4 pip di distanza dal picco massimo favorevole

# Protezioni di sicurezza
PARACADUTE_KJ_PIPS = 6.0       # Paracadute KJ Intracandela: Stop emergenza live a KJ +- 6 pip
CANDELA_SEGNALE_OFFSET_PIPS = 3.0 # Candela Segnale M5: Stop confermato su rottura Massimo/Minimo +- 3 pip
CORE_MIN_KJ_DIST_PIPS = 2.0    # Minima distanza Prezzo - KJ per ingresso Core M5: >= 2 pip (stacco da KJ)
CORE_MAX_KJ_DIST_PIPS = 6.0    # Massima distanza Prezzo - KJ per ingresso Core M5: <= 6 pip (coerente con Paracadute)
KJ_TOLERANCE_PIPS = 5.0
MIN_DIST_INCR_PIPS = 4.0

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
    """Restituisce True durante la chiusura reale del feed dati Gold (nessun tick disponibile):
    - Weekend: da venerdì sera ore 22:45 fino alla domenica sera ore 21:58.
    - Notturno feriale (Lun-Gio): dalle 22:45 alle 23:59:59 (dalle 00:00 il feed riapre per candele M5)."""
    if dt is None:
        dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    # Weekend: da venerdì 22:45 a domenica 21:58
    if wd == 4 and t >= datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    # Notturno feriale Lun-Gio (22:45 - 23:59:59)
    if wd in (0, 1, 2, 3) and t >= datetime.time(GOLD_FEED_SUSPEND_START_HOUR, GOLD_FEED_SUSPEND_START_MIN, 0):
        return True
    return False

def is_gold_rollover_window(dt: datetime.datetime = None) -> bool:
    """Restituisce True SOLO nella finestra operativa utile di chiusura anticipata a FLAT (22:44:00 - 22:44:55),
    sia il venerdì prima del freeze del weekend sia nelle notti feriali Lun-Gio prima del rollover.
    Evita di inviare ordini a mercati chiusi durante il weekend o dopo le 22:45."""
    if dt is None:
        dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    t_start = datetime.time(GOLD_TRADE_SUSPEND_START_HOUR, GOLD_TRADE_SUSPEND_START_MIN, 0) # 22:44:00
    t_end = datetime.time(22, 44, 55)
    # Venerdì sera: 22:44:00 - 22:44:55
    if wd == 4 and t_start <= t <= t_end:
        return True
    # Lun-Gio notte: 22:44:00 - 22:44:55
    if wd in (0, 1, 2, 3) and t_start <= t <= t_end:
        return True
    return False

def is_gold_trading_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True se l'operatività/apertura ordini è congelata a FLAT:
    - Notte feriale per rollover (22:44 - 00:15)
    - Weekend: dal venerdì sera alle 22:44 fino alla domenica sera alle 21:58."""
    if dt is None:
        dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    # Weekend: venerdì sera dalle 22:44 fino alla domenica sera alle 21:58
    if wd == 4 and t >= datetime.time(22, 44, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    # Rollover infrasettimanale (Lun-Gio notte)
    t_start = datetime.time(GOLD_TRADE_SUSPEND_START_HOUR, GOLD_TRADE_SUSPEND_START_MIN, 0)
    t_end = datetime.time(GOLD_TRADE_SUSPEND_END_HOUR, GOLD_TRADE_SUSPEND_END_MIN, 0)
    return t >= t_start or t < t_end

def is_gold_entry_suspended(dt: datetime.datetime = None) -> bool:
    """Restituisce True se l'apertura di nuove posizioni (Core e Incrementi M5) è sospesa:
    1. Venerdì sera dalle 22:14:00 in poi e per tutto il weekend fino alla riapertura di domenica sera (21:58),
       lasciando 30 minuti di respiro (fino alle 22:44) alle posizioni a mercato per svilupparsi e chiudersi fisiologicamente.
    2. Durante il normale congelamento notturno di trading (22:44 - 00:15)."""
    if dt is None:
        dt = now_it()
    wd = dt.weekday()
    t = dt.time()
    # Blocco ingressi pre-weekend (Venerdì dalle 22:14, Sabato, Domenica fino alle 21:58)
    if wd == 4 and t >= datetime.time(22, 14, 0):
        return True
    if wd == 5:
        return True
    if wd == 6 and t < datetime.time(21, 58, 0):
        return True
    return is_gold_trading_suspended(dt)

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

        # Tracciamento Regime e Taglio KJ (Opzione B: Ingresso su Taglio Puro, no pullback)
        self.last_regime = None
        self.regime_traded = True

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

        # 4. Avvia watchdog indipendente per chiusura proattiva rollover / pre-weekend alle 22:44 (non dipende da Lightstreamer)
        self.watchdog_thread = threading.Thread(target=self._run_rollover_watchdog, daemon=True)
        self.watchdog_thread.start()

        # 5. Avvia riconciliazione asincrona posizioni con IG (ripulisce deal già chiusi a server spento)
        threading.Thread(target=self._reconcile_open_positions_with_ig, daemon=True).start()

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
        """Caricamento e aggregazione a 10M da cache/stato locale (ZERO chiamate IG REST)"""
        with self.lock:
            if len(self.candles) >= WARMUP_BARS_KJ:
                self.candles = aggregate_candles_to_10m(self.candles)[-500:]
                self._recalculate_indicators()
                self.save_state()
                return

        central_file = "candele_Spot_Gold_M5.json"
        candidates = [central_file, STATE_FILE]
        if getattr(self, "account_dir", None):
            candidates.append(os.path.join(self.account_dir, STATE_FILE))
            candidates.append(os.path.join("/data", self.account_dir, STATE_FILE))
        candidates.extend([
            os.path.join("DANY_DEMO", STATE_FILE),
            os.path.join("FIORDOK_DEMO", STATE_FILE),
            os.path.join("BONGIOLO_DEMO", STATE_FILE),
            os.path.join("/data", "DANY_DEMO", STATE_FILE),
            os.path.join("/data", "FIORDOK_DEMO", STATE_FILE),
            "candele_Spot_Gold_HOUR.json"
        ])

        for fpath in candidates:
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    c_list = d if isinstance(d, list) else d.get("candles", [])
                    if len(c_list) >= 55:
                        with self.lock:
                            self.candles = aggregate_candles_to_10m(c_list)[-500:]
                            self._recalculate_indicators()
                            self.save_state()
                        print(f"✅ [HYPER GOLD 10M] Caricate {len(self.candles)} barre 10M aggregate da file locale {fpath} (ZERO chiamate IG).")
                        return
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
            # Salvaguardia weekend: se il server riparte nel weekend (da venerdì 23:05 a domenica 21:58), forza DA AVVIARE
            _now = now_it()
            _wd = _now.weekday()
            _t = _now.time()
            if (_wd == 4 and _t >= datetime.time(23, 5)) or (_wd == 5) or (_wd == 6 and _t < datetime.time(21, 58)):
                if self.trading_enabled:
                    self.trading_enabled = False
                    logger.info("🛑 [WEEKEND SAFEGUARD] Spot Gold: weekend in corso, trading forzato a DA AVVIARE.")
            self.use_core_trailing = True
            self.position = d.get("position")
            self.increments = d.get("increments", [])
            self.inc_tp_pips = float(d.get("inc_tp_pips", INC_TP_PIPS))
            self.trades = d.get("trades", [])
            self.last_ts_cycle = d.get("last_ts_cycle")
            self.last_regime = d.get("last_regime", None)
            self.regime_traded = bool(d.get("regime_traded", True))
            raw_c = d.get("candles", [])
            self.candles = aggregate_candles_to_10m(raw_c) if raw_c else []
            if self.candles and self.candles[-1].get("boundary", 0) > (time.time() + 600):
                self.candles = []
            self.signal_candle_active = bool(d.get("signal_candle_active", False))
            self.signal_stop_price = d.get("signal_stop_price")
            self.signal_ref_price = d.get("signal_ref_price")
            if not self.position:
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None
            self._recalculate_indicators()

    def _reconcile_open_positions_with_ig(self):
        """Verifica all'avvio che le posizioni/incrementi registrati esistano ancora realmente su IG.
        Se un deal è già stato chiuso (es. per TP o chiusura manuale a server spento), lo ripulisce dallo stato."""
        try:
            time.sleep(3.0) # Attendi connessione sessione
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            changed = False
            with self.lock:
                if self.position and self.position.get("deal_id"):
                    deal_c = self.position["deal_id"]
                    if not order_mgr.is_deal_open(deal_c):
                        logger.info(f"ℹ️ [RECONCILE GOLD] Posizione Core {deal_c} non più presente su IG. Stato locale allineato a FLAT.")
                        self.position = None
                        self.signal_candle_active = False
                        self.signal_stop_price = None
                        self.signal_ref_price = None
                        changed = True

                valid_incs = []
                for inc in self.increments:
                    deal_i = inc.get("deal_id")
                    if deal_i and not order_mgr.is_deal_open(deal_i):
                        logger.info(f"ℹ️ [RECONCILE GOLD] Incremento {deal_i} non più presente su IG. Rimosso dallo stato locale.")
                        changed = True
                    else:
                        valid_incs.append(inc)
                self.increments = valid_incs

                if changed:
                    self.save_state()
        except Exception as e:
            logger.warning(f"Errore riconciliazione posizioni Gold con IG all'avvio: {e}")

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
                "last_regime": getattr(self, "last_regime", None),
                "regime_traded": getattr(self, "regime_traded", True),
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
            if not enabled:
                # Quando l'utente preme STOP TRADING, chiude immediatamente tutte le posizioni aperte a FLAT
                if self.position or self.increments:
                    exec_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                    t_str = now_it().strftime("%H:%M:%S")
                    self._close_all_to_flat(exec_px, t_str, reason="🛑 STOP TRADING Manuale Utente ➔ Chiusura immediata di tutte le posizioni a FLAT")
            self.save_state()

    def manual_entry_core(self, direction: str) -> dict:
        """Avvio manuale discrezionale della posizione Core 10M (5 contratti)."""
        norm_dir = "LONG" if direction.upper() in ("LONG", "BUY") else "SHORT"
        with self.lock:
            if not self.trading_enabled:
                return {"success": False, "error": "Motore non avviato (trading disabilitato)"}
            if self.position is not None or len(self.increments) > 0:
                return {"success": False, "error": "Posizione già aperta (strumento non FLAT)"}
            if getattr(self, "entry_in_progress", False):
                return {"success": False, "error": "Operazione di ingresso già in corso"}

            self.entry_in_progress = True
            self.regime_traded = True
            self.signal_candle_active = False
            self.signal_stop_price = None
            self.signal_ref_price = None
            self.save_state()

        exec_price = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
        time_str = now_it().strftime("%H:%M:%S")

        threading.Thread(
            target=self._execute_entry_core,
            args=(norm_dir, exec_price, time_str),
            daemon=True
        ).start()
        return {"success": True, "message": f"Avvio Core {norm_dir} inviato a mercato"}

    def _run_rollover_watchdog(self):
        """Watchdog temporale indipendente: garantisce la chiusura automatica a FLAT
        nella finestra utile (22:44:00 - 22:44:55) prima del freeze del feed e del weekend,
        anche in assenza di tick live da Lightstreamer, e disattiva il trading al venerdì sera (23:05)."""
        last_friday_disarmed_date = None
        while self.running:
            try:
                time.sleep(2)
                now = now_it()
                wd = now.weekday()
                t = now.time()
                today_str = now.strftime("%Y-%m-%d")

                # 1. Chiusura proattiva a FLAT a 22:44 (rollover e pre-weekend)
                if is_gold_rollover_window(now):
                    with self.lock:
                        has_pos = (self.position is not None or len(self.increments) > 0)
                        mid_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                    if has_pos and not getattr(self, "closing_in_progress", False):
                        t_str = now.strftime("%H:%M:%S")
                        self._close_all_to_flat(mid_px, t_str, reason="Rollover Gold (22:44 - 00:15) ➔ Chiusura automatica, stato FLAT.")

                # 2. Venerdì sera alle 23:05: Disattivazione automatica per il weekend (stato 'DA AVVIARE')
                if wd == 4 and t >= datetime.time(23, 5):
                    if last_friday_disarmed_date != today_str:
                        last_friday_disarmed_date = today_str
                        if self.trading_enabled:
                            with self.lock:
                                self.trading_enabled = False
                                self.save_state()
                            logger.info(f"🛑 [WEEKEND SHUTDOWN] Venerdì ore {t.strftime('%H:%M:%S')}: Trading Spot Gold disattivato automaticamente per il weekend. Stato impostato su DA AVVIARE.")
                            try:
                                order_mgr.send_notification(
                                    "🛑 SPOT GOLD 10M: WEEKEND SHUTDOWN",
                                    f"Chiusura weekend ({t.strftime('%H:%M:%S')}). Motore Spot Gold 10M disattivato e reimpostato su DA AVVIARE.",
                                    "pause_button"
                                )
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Errore watchdog rollover Gold: {e}")

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
                        except Exception as e:
                            logger.error(f"Errore _process_tick Gold M5: {e}")

                sub = LightstreamerSubscription(
                    mode="DISTINCT",
                    items=[f"CHART:{EPIC_GOLD}:TICK"],
                    fields=["BID", "OFR", "UTM"]
                )
                sub.addlistener(on_tick)
                ls_client.subscribe(sub)

                while self.running and self.ls_connected:
                    time.sleep(2)
                    # Controllo proattivo chiusura Rollover solo nella finestra utile (22:44:00 - 22:44:55)
                    if is_gold_rollover_window():
                        with self.lock:
                            has_pos = (self.position is not None or len(self.increments) > 0)
                            mid_px = self.live_mid if self.live_mid is not None else (self.candles[-1]["close"] if self.candles else 0.0)
                        if has_pos and not getattr(self, "closing_in_progress", False):
                            t_str = now_it().strftime("%H:%M:%S")
                            self._close_all_to_flat(mid_px, t_str, reason="Rollover Gold (22:44 - 00:15) ➔ Chiusura automatica, stato FLAT.")
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

                # Verifica tocco Trailing Stop
                if current_price >= pos["ts_price"]:
                    self._close_cycle_trailing_hit(current_price, time_str)

    def _execute_entry_core(self, direction: str, exec_price: float, time_str: str):
        """Esegue l'apertura a mercato reale su IG della Core 10M (5 contratti)."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            res = order_mgr.open_market_deal(
                direction=direction,
                size=CORE_CONTRACTS,
                limit_level=None,
                label="Core 10M"
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
                        "action": f"🚀 OPEN REAL IG {direction} ({CORE_CONTRACTS}c Core 10M)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": CORE_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Ingresso IG Reale {direction} @ {real_open:.2f} € (Deal ID Core: {deal_id})"
                    })
                    self.save_state()
                    order_mgr.send_notification(
                        "🚀 OPEN CORE 10M: Spot Gold",
                        f"[Spot Gold] Core {direction} {CORE_CONTRACTS}c a {real_open:.2f} €",
                        "rocket"
                    )
        except Exception as e:
            logger.error(f"Errore apertura Core 10M IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_entry_increment(self, direction: str, exec_price: float, time_str: str, mode: str = "BANCOMAT"):
        """Esegue l'apertura a mercato reale su IG di un incremento 10M (5 contratti):
        - Se mode='BANCOMAT': imposta TP a +5p
        - Se mode='RUNNER': nessun TP fisso, profitto corre con Trailing Stop Virtuale"""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            if mode == "BANCOMAT":
                tp_px = round(exec_price + self.inc_tp_pips if direction == "LONG" else exec_price - self.inc_tp_pips, 2)
                limit_lvl = tp_px
                lbl_order = f"Inc. Bancomat Spot Gold 10M #{len(self.increments)+1}"
            else:
                tp_px = None
                limit_lvl = None
                lbl_order = f"Inc. Runner Spot Gold 10M #{len(self.increments)+1}"

            res = order_mgr.open_market_deal(
                direction=direction,
                size=INC_CONTRACTS,
                limit_level=limit_lvl,
                label=lbl_order
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
                        "mode": mode,
                        "peak_price": real_open,
                        "ts_active": False,
                        "ts_price": None,
                        "open_time": res.get("time") or time_str
                    }
                    self.increments.append(new_inc)
                    tot_c = CORE_CONTRACTS + sum(i["contracts"] for i in self.increments)
                    tp_desc = f"TP: {tp_px:.2f} €" if tp_px else "Runner No-TP (TS attivo)"
                    self.trades.insert(0, {
                        "time": time_str,
                        "action": f"➕ OPEN INC {mode} {direction} (+{INC_CONTRACTS}c, Tot: {tot_c}c)",
                        "open_price": real_open,
                        "close_price": None,
                        "contracts": INC_CONTRACTS,
                        "pnl": 0.0,
                        "balance": round(self.balance, 2),
                        "reason": f"Incremento {mode} 10M IG @ {real_open:.2f} € ({tp_desc}, Deal ID: {deal_id})"
                    })
                    self.save_state()
                    order_mgr.send_notification(
                        f"➕ INCREMENTO {mode} 10M: Spot Gold",
                        f"[Spot Gold] Incremento {mode} #{len(self.increments)} {direction} {INC_CONTRACTS}c a {real_open:.2f} € ({tp_desc}, Tot: {tot_c}c)",
                        "heavy_plus_sign"
                    )
        except Exception as e:
            logger.error(f"Errore apertura incremento 10M IG: {e}")
        finally:
            with self.lock:
                self.entry_in_progress = False

    def _execute_close_increment(self, inc: dict, current_price: float, time_str: str, reason: str = None):
        """Chiude a mercato reale un singolo incremento M5 (per TP Bancomat, Trailing Stop Runner, o Incasso Sicurezza)."""
        try:
            order_mgr = HyperOrderManager.get_instance(self.account_dir)
            deal_id = inc.get("deal_id")
            mode = inc.get("mode", "BANCOMAT")
            if reason is None:
                reason = f"TP Incremento (+{self.inc_tp_pips:.1f}p)"

            res = order_mgr.close_market_deal(
                deal_id=deal_id,
                direction_open=inc["direction"],
                size=inc["contracts"],
                label=f"Chiusura Inc {mode} Spot Gold 10M",
                reason_note=reason
            )
            profit = float(res.get("profit") or 0.0)
            close_px = float(res.get("close_level") or current_price)
            if profit == 0.0 and res.get("already_closed") and inc.get("tp_price"):
                profit = round(abs(inc["open_price"] - inc["tp_price"]) * inc["contracts"] * self.point_value, 2)
                close_px = inc["tp_price"]

            with self.lock:
                self.increments = [i for i in self.increments if i.get("deal_id") != deal_id and i.get("id") != inc.get("id")]
                self.balance += profit

                order_mgr.record_closed_trade(
                    tf="10M",
                    direction=inc["direction"],
                    contracts=inc["contracts"],
                    open_price=inc["open_price"],
                    close_price=close_px,
                    pnl_eur=profit,
                    deal_id=deal_id,
                    reason=reason,
                    time_open=inc.get("open_time", time_str),
                    label=f"Inc {mode} 10M"
                )

                self.trades.insert(0, {
                    "time": time_str,
                    "action": f"🎯 CLOSE INC {mode} {inc['direction']} ({profit:+.2f} €)",
                    "open_price": inc["open_price"],
                    "close_price": close_px,
                    "contracts": inc["contracts"],
                    "pnl": profit,
                    "balance": round(self.balance, 2),
                    "reason": f"Chiusura IG Deal {deal_id}: {reason} @ {close_px:.2f}"
                })
                self.save_state()
                order_mgr.send_notification(
                    f"🎯 CHIUSURA INC {mode} 10M: Spot Gold",
                    f"[Spot Gold] Close Incr {mode} {inc['direction']} ({inc['contracts']}c) a {close_px:.2f} [PnL: {profit:+.2f} €] - Motivo: {reason}",
                    "dart"
                )
        except Exception as e:
            logger.error(f"Errore chiusura incremento 10M IG: {e}")

    def _execute_close_all_flat(self, exec_price: float, time_str: str, reason: str):
        """Chiude a mercato reale tutte le posizioni aperte su IG (Core + Incrementi 10M)."""
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
                    label="Chiusura Core Spot Gold 10M Flat",
                    reason_note=reason
                )
                if not res_c.get("success") and not res_c.get("already_closed"):
                    logger.warning(f"❌ Chiusura Core {deal_c} non riuscita su IG ({res_c.get('reason')}). Posizione mantenuta attiva.")
                    with self.lock:
                        self.position = pos_to_close
                        self.save_state()
                else:
                    prof_c = float(res_c.get("profit") or 0.0)
                    cl_c = float(res_c.get("close_level") or exec_price)
                    order_mgr.record_closed_trade(
                        tf="10M",
                        direction=pos_to_close["direction"],
                        contracts=pos_to_close["contracts"],
                        open_price=pos_to_close["open_price"],
                        close_price=cl_c,
                        pnl_eur=prof_c,
                        deal_id=deal_c,
                        reason=reason,
                        time_open=pos_to_close.get("open_time", time_str),
                        label="Core 10M"
                    )
                    with self.lock:
                        self.balance += prof_c
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"CLOSE CORE 10M {pos_to_close['direction']} ({prof_c:+.2f} €)",
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
                        tit_cl = "🎯 TS HIT 10M: Spot Gold"
                    elif is_rev:
                        tag_cl = "warning"
                        tit_cl = "🛑 REVERSAL 10M: Spot Gold"
                    else:
                        tag_cl = "octagonal_sign"
                        tit_cl = "🛑 CHIUSURA FLAT 10M: Spot Gold"
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
                        label="Chiusura Inc Spot Gold 10M Flat",
                        reason_note=reason
                    )
                    if not res_i.get("success") and not res_i.get("already_closed"):
                        logger.warning(f"❌ Chiusura Inc {deal_i} non riuscita su IG ({res_i.get('reason')}). Incremento mantenuto attivo.")
                        with self.lock:
                            self.increments.append(inc)
                            self.save_state()
                        continue
                    prof_i = float(res_i.get("profit") or 0.0)
                    cl_i = float(res_i.get("close_level") or exec_price)
                    order_mgr.record_closed_trade(
                        tf="10M",
                        direction=inc["direction"],
                        contracts=inc["contracts"],
                        open_price=inc["open_price"],
                        close_price=cl_i,
                        pnl_eur=prof_i,
                        deal_id=deal_i,
                        reason=reason,
                        time_open=inc.get("open_time", time_str),
                        label="Incremento 10M"
                    )
                    with self.lock:
                        self.balance += prof_i
                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"CLOSE INC 10M {inc['direction']} ({prof_i:+.2f} €)",
                            "open_price": inc["open_price"],
                            "close_price": cl_i,
                            "contracts": inc["contracts"],
                            "pnl": prof_i,
                            "balance": round(self.balance, 2),
                            "reason": reason
                        })
                    order_mgr.send_notification(
                        "🛑 CHIUSURA FLAT INC 10M: Spot Gold",
                        f"[Spot Gold] Incremento {inc['direction']} ({inc['contracts']}c) chiuso a {cl_i:.2f} € [PnL: {prof_i:+.2f} €]",
                        "octagonal_sign"
                    )
                    # Pausa prudenziale tra incrementi
                    time.sleep(1.5)

            with self.lock:
                self.save_state()
        except Exception as e:
            logger.error(f"Errore chiusura posizioni flat 10M IG: {e}")
        finally:
            with self.lock:
                self.closing_in_progress = False

    def _close_cycle_trailing_hit(self, current_price: float, time_str: str):
        """Chiusura completa a FLAT all'entrata del Trailing Stop su 10M"""
        if not self.position or getattr(self, "closing_in_progress", False):
            return
        self.closing_in_progress = True
        threading.Thread(
            target=self._execute_close_all_flat,
            args=(current_price, time_str, f"TS Spot Gold 10M @ {current_price:.2f}"),
            daemon=True
        ).start()

    def _check_increments_management(self, current_price: float, time_str: str):
        """Controlla tick-by-tick:
        - Take Profit (+5 pip) per incrementi BANCOMAT
        - Trailing Stop Virtuale (Trigger +5p, Lock BE, Trailing 4p) per incrementi RUNNER"""
        for inc in list(self.increments):
            if inc.get("closing"):
                continue

            mode = inc.get("mode", "BANCOMAT")
            direction = inc["direction"]
            open_px = inc["open_price"]

            # 1. Regime BANCOMAT: controllo TP fisso a +5p
            if mode == "BANCOMAT" or inc.get("tp_price") is not None:
                tp_val = inc.get("tp_price")
                hit_tp = False
                if direction == "LONG" and tp_val and current_price >= tp_val:
                    hit_tp = True
                elif direction == "SHORT" and tp_val and current_price <= tp_val:
                    hit_tp = True

                if hit_tp:
                    inc["closing"] = True
                    threading.Thread(
                        target=self._execute_close_increment,
                        args=(inc, current_price, time_str, f"TP Bancomat (+{self.inc_tp_pips:.1f}p)"),
                        daemon=True
                    ).start()

            # 2. Regime RUNNER: Trailing Stop Virtuale dinamico (Trigger +5p -> Lock BE +1p -> Trailing 4p)
            elif mode == "RUNNER":
                # Aggiorna picco massimo favorevole
                if direction == "LONG":
                    if current_price > inc.get("peak_price", open_px):
                        inc["peak_price"] = current_price
                    gain_pips = current_price - open_px
                else:
                    if current_price < inc.get("peak_price", open_px):
                        inc["peak_price"] = current_price
                    gain_pips = open_px - current_price

                # Attivazione Trailing / Breakeven Lock a +5 pip
                if gain_pips >= RUNNER_TS_TRIGGER_PIPS:
                    if not inc.get("ts_active"):
                        inc["ts_active"] = True
                        inc["ts_price"] = round(open_px + 1.0 if direction == "LONG" else open_px - 1.0, 2)
                        logger.info(f"[{time_str}] 🔒 [RUNNER BE LOCKED] Inc #{inc.get('id')} locked a {inc['ts_price']:.2f}")
                    else:
                        # Insegue a RUNNER_TS_STEP_PIPS (4p) dal picco massimo
                        if direction == "LONG":
                            cand_ts = round(inc["peak_price"] - RUNNER_TS_STEP_PIPS, 2)
                            if cand_ts > inc["ts_price"]:
                                inc["ts_price"] = cand_ts
                        else:
                            cand_ts = round(inc["peak_price"] + RUNNER_TS_STEP_PIPS, 2)
                            if cand_ts < inc["ts_price"]:
                                inc["ts_price"] = cand_ts

                # Verifica se prezzo tocca il Trailing Stop
                if inc.get("ts_active") and inc.get("ts_price") is not None:
                    hit_ts = False
                    if direction == "LONG" and current_price <= inc["ts_price"]:
                        hit_ts = True
                    elif direction == "SHORT" and current_price >= inc["ts_price"]:
                        hit_ts = True

                    if hit_ts:
                        inc["closing"] = True
                        pnl_pips = round(current_price - open_px if direction == "LONG" else open_px - current_price, 2)
                        threading.Thread(
                            target=self._execute_close_increment,
                            args=(inc, current_price, time_str, f"TS Runner Inc ({pnl_pips:+.2f}p)"),
                            daemon=True
                        ).start()

    def _check_runner_harvesting(self, current_price: float, time_str: str):
        """Soluzione 1 (Incasso di Sicurezza):
        Se ci sono incrementi Runner aperti e la distanza Prezzo - KJ scende <= 10 pip
        (la Kijun è salita e ha raggiunto il prezzo che si è fermato/ha lateralizzato),
        chiude istantaneamente a mercato tutti i Runner incassando il profitto e lasciando la sola Core."""
        runner_incs = [i for i in self.increments if i.get("mode") == "RUNNER" and not i.get("closing")]
        if not runner_incs or self.kj55 is None:
            return

        dist_kj = abs(current_price - self.kj55)
        if dist_kj <= RUNNER_THRESHOLD_KJ_DIST:
            logger.info(f"[{time_str}] 🎯 [INCASSO SICUREZZA RUNNER] Distanza KJ ridotta a {dist_kj:.2f}p (<= {RUNNER_THRESHOLD_KJ_DIST:.1f}p). Incasso {len(runner_incs)} Runner!")
            for inc in runner_incs:
                inc["closing"] = True
                pnl_pips = round(current_price - inc["open_price"] if inc["direction"] == "LONG" else inc["open_price"] - current_price, 2)
                threading.Thread(
                    target=self._execute_close_increment,
                    args=(inc, current_price, time_str, f"Incasso Sicurezza Runner (dist KJ {dist_kj:.1f}p <= {RUNNER_THRESHOLD_KJ_DIST:.0f}p, PnL: {pnl_pips:+.1f}p)"),
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
                    reason=f"Paracadute KJ: Mid live {mid:.2f} <= (KJ {self.kj55:.2f} - {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
                )
        elif pos_dir == "SHORT":
            threshold = round(self.kj55 + PARACADUTE_KJ_PIPS, 2)
            if mid >= threshold:
                self._close_all_to_flat(
                    mid,
                    time_str,
                    reason=f"Paracadute KJ: Mid live {mid:.2f} >= (KJ {self.kj55:.2f} + {PARACADUTE_KJ_PIPS:.0f}p = {threshold:.2f}) ➔ FLAT"
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
                    reason=f"Candela Segnale KJ : Mid live {mid:.2f} <= Stop {stop_val:.2f} ➔ FLAT"
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
                    reason=f"Candela Segnale KJ : Mid live {mid:.2f} >= Stop {stop_val:.2f} ➔ FLAT"
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

            # Verifica finestra utile di chiusura rollover/pre-weekend Gold (22:44:00 - 22:44:55)
            if is_gold_rollover_window():
                if self.position or self.increments:
                    self._close_all_to_flat(mid, time_str, reason="Rollover Gold (22:44 - 00:15) ➔ Chiusura automatica, stato FLAT.")
            elif not is_gold_market_suspended():
                # 1. Verifica Trailing Stop per la Core (Attivo di default: Trigger +10p, Lock +6p, Step 2p)
                if self.trading_enabled and self.position and getattr(self, "use_core_trailing", True):
                    self._check_core_trailing_stop(mid, time_str)

                # 2. Gestione Incrementi: Bancomat (TP +5p), Runner (Trailing Stop Virtuale) e Incasso Sicurezza (<= 10p da KJ)
                if self.trading_enabled and self.increments:
                    self._check_increments_management(mid, time_str)
                    if self.position and self.kj55 is not None:
                        self._check_runner_harvesting(mid, time_str)

                # 3. Paracadute KJ Intracandela (6 pip): Chiusura istantanea di sicurezza a FLAT
                if self.trading_enabled and self.position and self.kj55 is not None:
                    self._check_paracadute_kj(mid, time_str)

                # 4. Stop Conferma Candela Segnale KJ (5 pip): Chiusura a rottura confermata
                if self.trading_enabled and self.position and self.signal_candle_active:
                    self._check_candela_segnale_stop(mid, time_str)

            # Inizializzazione prima barra M10
            if self.curr_boundary is None:
                self.curr_boundary = boundary
                self.curr_open = mid
                self.curr_high = mid
                self.curr_low = mid
                self.curr_close = mid
                self.curr_bar_start_t = now_t
                # Se il motore parte a più di 60s dall'inizio del boundary M10, la prima barra è parziale
                self.curr_bar_is_partial = (now_t - boundary) > 60
                if self.curr_bar_is_partial:
                    logger.info(f"⏳ [CANDELA M10 PARZIALE AVVIATA] Spot Gold: motore avviato a metà barra (trascorsi {int(now_t - boundary)}s). La prima barra sarà di solo allineamento.")
                return

            if boundary == self.curr_boundary:
                # Barra M10 corrente in formazione
                if mid > self.curr_high: self.curr_high = mid
                if mid < self.curr_low: self.curr_low = mid
                self.curr_close = mid
            else:
                # Chiusura barra M10
                closed_candle = {
                    "boundary": self.curr_boundary,
                    "time": datetime.datetime.fromtimestamp(self.curr_boundary, TZ_ITALIA).strftime("%H:%M:%S"),
                    "open": self.curr_open,
                    "high": self.curr_high,
                    "low": self.curr_low,
                    "close": self.curr_close
                }
                was_partial = getattr(self, "curr_bar_is_partial", False)
                self.curr_bar_is_partial = False

                self.candles.append(closed_candle)
                if len(self.candles) > 500:
                    self.candles = self.candles[-500:]

                # Ricalcola KJ55 e TK144
                self._recalculate_indicators()

                # Apertura nuova candela M10
                new_open = mid
                self.curr_boundary = boundary
                self.curr_open = new_open
                self.curr_high = new_open
                self.curr_low = new_open
                self.curr_close = new_open
                self.curr_bar_start_t = now_t

                self.save_state()

                market_suspended = is_gold_market_suspended()
                if was_partial:
                    logger.info(f"⏳ [PRIMA BARRA PARZIALE CONCLUSA] Spot Gold @ {time_str}: Kijun ricalcolata ({self.kj55}). Operatività attiva dalla prima candela interamente formata.")
                elif self.trading_enabled and not market_suspended and self.kj55 is not None:
                    self._evaluate_pure_sr_strategy(closed_candle, self.kj55, new_open, time_str)

    def _update_increments_dynamic_mode(self, dist_kj: float, exec_price: float, time_str: str):
        """A fine candela M10, valuta dinamicamente gli incrementi già aperti in base alla distanza da KJ:
        1. Se dist_kj > 10 pip: i Bancomat vengono promossi a RUNNER (rimozione TP su IG a broker e attivazione Trailing)
        2. Se dist_kj <= 10 pip: i Runner vengono incassati a mercato per sicurezza (Incasso Sicurezza)"""
        with self.lock:
            active_incs = [i for i in self.increments if not i.get("closing")]
            if not active_incs:
                return

            order_mgr = HyperOrderManager.get_instance(self.account_dir)

            # Caso 1: Distanza > 10 pip -> Trend allunga, promuovi Bancomat a Runner
            if dist_kj > RUNNER_THRESHOLD_KJ_DIST:
                for inc in active_incs:
                    if inc.get("mode") == "BANCOMAT" and inc.get("tp_price") is not None:
                        deal_id = inc.get("deal_id")
                        old_tp = inc.get("tp_price")
                        inc["mode"] = "RUNNER"
                        inc["tp_price"] = None
                        inc["ts_active"] = False
                        inc["ts_price"] = None
                        inc["peak_price"] = exec_price

                        logger.info(f"[{time_str}] 🚀 [PROMOZIONE RUNNER] Deal {deal_id} convertito in RUNNER (dist KJ {dist_kj:.1f}p > 10p). Rimozione TP {old_tp:.2f} su IG.")
                        if deal_id:
                            threading.Thread(target=order_mgr.remove_limit_order, args=(deal_id, "Promozione Runner Spot Gold"), daemon=True).start()

                        self.trades.insert(0, {
                            "time": time_str,
                            "action": f"🚀 PROMOZIONE RUNNER GOLD {inc['direction']}",
                            "open_price": inc["open_price"],
                            "close_price": None,
                            "contracts": inc["contracts"],
                            "pnl": 0.0,
                            "balance": round(self.balance, 2),
                            "reason": f"Distanza KJ {dist_kj:.1f}p > 10p: Take Profit ({old_tp:.2f}) rimosso a broker IG, attivo Trailing Stop"
                        })
                        self.save_state()
                        order_mgr.send_notification(
                            "🚀 PROMOZIONE RUNNER 10M: Spot Gold",
                            f"[Spot Gold] Incremento #{inc.get('id')} {inc['direction']} convertito in RUNNER! Distanza KJ {dist_kj:.1f}p > 10p: Take Profit rimosso a broker IG, attivo Trailing Stop.",
                            "rocket"
                        )

            # Caso 2: Distanza <= 10 pip -> Ritracciamento verso KJ, incasso immediato di sicurezza per tutti i Runner
            else:
                has_runners = any(i.get("mode") == "RUNNER" for i in active_incs)
                if has_runners:
                    logger.info(f"[{time_str}] 🎯 [INCASSO SICUREZZA RUNNER A FINE CANDELA] Distanza KJ {dist_kj:.1f}p <= 10p. Esecuzione incasso Runner.")
                    self._check_runner_harvesting(exec_price, time_str)

    def _evaluate_pure_sr_strategy(self, closed_candle: dict, kj: float, exec_price: float, time_str: str):
        prev_close = closed_candle["close"]
        prev_open = closed_candle["open"]
        entry_allowed = not is_gold_entry_suspended()

        # Determinazione del regime della candela appena chiusa
        if prev_close > kj:
            current_regime = "LONG"
        elif prev_close < kj:
            current_regime = "SHORT"
        else:
            current_regime = self.last_regime

        # Rilevamento Taglio (Cross) KJ55
        if self.last_regime is not None and current_regime is not None and current_regime != self.last_regime:
            logger.info(f"⚡ [TAGLIO KJ 10M] Spot Gold: cambio regime da {self.last_regime} a {current_regime} (Close={prev_close:.2f}, KJ={kj:.2f})")
            self.last_regime = current_regime
            self.regime_traded = False
            self.save_state()
        elif self.last_regime is None and current_regime is not None:
            # BLINDATURA DI SICUREZZA ALL'AVVIO:
            # All'avvio senza stato pregresso, aggancia il regime attuale ma forza SEMPRE regime_traded = True.
            # Non azzarda mai ingressi a freddo su trend preesistenti. Si opera SOLO su tagli confermati in diretta.
            self.last_regime = current_regime
            self.regime_traded = True
            logger.info(f"🔄 [BOOTSTRAP KJ 10M] Spot Gold: regime iniziale agganciato a {current_regime}. In attesa del prossimo taglio in tempo reale per operare.")
            self.save_state()

        # AGGIORNAMENTO DINAMICO INCREMENTI A FINE CANDELA (OPZIONE 1):
        # - Se dist_kj > 10 pip: promuovi i Bancomat a RUNNER (rimozione TP su IG a broker e attivo Trailing Stop)
        # - Se dist_kj <= 10 pip: incasso di sicurezza a mercato per tutti i Runner
        dist_kj_candle = abs(prev_close - kj)
        self._update_increments_dynamic_mode(dist_kj_candle, exec_price, time_str)

        # =============================================================
        # 1. MERCATO SOPRA KJ55 (BULLISH)
        # =============================================================
        if current_regime == "LONG":
            if self.position is None:
                if not self.regime_traded:
                    if not entry_allowed:
                        print(f"[{time_str}] ⏸️ [PRE-WEEKEND CUTOFF] Venerdì >= 22:14: Apertura Core LONG sospesa prima del weekend.")
                        return
                    dist_kj = round(exec_price - kj, 2)
                    if dist_kj >= CORE_MIN_KJ_DIST_PIPS:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            self.regime_traded = True
                            self.signal_candle_active = False
                            self.signal_stop_price = None
                            self.signal_ref_price = None
                            self.save_state()
                            threading.Thread(
                                target=self._execute_entry_core,
                                args=("LONG", exec_price, time_str),
                                daemon=True
                            ).start()
                    else:
                        print(f"[{time_str}] ⏸️ [TAGLIO LONG] Distacco Prezzo-KJ insufficiente ({dist_kj:.2f}p < min {CORE_MIN_KJ_DIST_PIPS:.1f}p). Attendo conferma.")
                else:
                    print(f"[{time_str}] ⏸️ [ATTESA TAGLIO LONG] Mercato sopra KJ {kj:.2f} ma trend già avviato (nessun taglio). In attesa del prossimo taglio da sotto a sopra.")
            elif self.position and self.position["direction"] == "LONG":
                # Core già LONG: azzera eventuale Candela Segnale e valuta incremento
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None

                # Assioma Granitico: Incremento SEMPRE e SOLO su ritracciamento (candela chiusa ROSSA)
                is_retracement = prev_close < prev_open
                if not entry_allowed and is_retracement:
                    print(f"[{time_str}] ⏸️ [PRE-WEEKEND CUTOFF] Venerdì >= 22:14: Apertura Incremento LONG sospesa prima del weekend.")
                elif is_retracement and not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                    dist_kj = abs(exec_price - kj)
                    active_incs = [i for i in self.increments if not i.get("closing")]
                    tot_incs = len(active_incs)

                    if tot_incs < MAX_INCREMENTS:
                        # 1. Regime BANCOMAT (distanza da KJ <= 10.0 pip): max 1 incremento con TP rapido a +5p
                        if dist_kj <= BANCOMAT_MAX_DIST_KJ:
                            has_bancomat = any(i.get("mode", "BANCOMAT") == "BANCOMAT" for i in active_incs)
                            troppo_vicino = any(abs(exec_price - i["open_price"]) < (MIN_DIST_INCR_PIPS - 1e-7) for i in active_incs)
                            if not has_bancomat and not troppo_vicino:
                                self.entry_in_progress = True
                                threading.Thread(
                                    target=self._execute_entry_increment,
                                    args=("LONG", exec_price, time_str, "BANCOMAT"),
                                    daemon=True
                                ).start()

                        # 2. Regime RUNNER (distanza da KJ > 10.0 pip): piramidazione di trend, max 3 runner contemporanei con Trailing Stop
                        else:
                            runner_incs = [i for i in active_incs if i.get("mode") == "RUNNER"]
                            troppo_vicino_runner = any(abs(exec_price - i["open_price"]) < (MIN_DIST_RUNNER_PIPS - 1e-7) for i in active_incs)
                            if len(runner_incs) < MAX_RUNNER_INCREMENTS and not troppo_vicino_runner:
                                self.entry_in_progress = True
                                threading.Thread(
                                    target=self._execute_entry_increment,
                                    args=("LONG", exec_price, time_str, "RUNNER"),
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
        elif current_regime == "SHORT":
            if self.position is None:
                if not self.regime_traded:
                    if not entry_allowed:
                        print(f"[{time_str}] ⏸️ [PRE-WEEKEND CUTOFF] Venerdì >= 22:14: Apertura Core SHORT sospesa prima del weekend.")
                        return
                    dist_kj = round(kj - exec_price, 2)
                    if dist_kj >= CORE_MIN_KJ_DIST_PIPS:
                        if not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                            self.entry_in_progress = True
                            self.regime_traded = True
                            self.signal_candle_active = False
                            self.signal_stop_price = None
                            self.signal_ref_price = None
                            self.save_state()
                            threading.Thread(
                                target=self._execute_entry_core,
                                args=("SHORT", exec_price, time_str),
                                daemon=True
                            ).start()
                    else:
                        print(f"[{time_str}] ⏸️ [TAGLIO SHORT] Distacco Prezzo-KJ insufficiente ({dist_kj:.2f}p < min {CORE_MIN_KJ_DIST_PIPS:.1f}p). Attendo conferma.")
                else:
                    print(f"[{time_str}] ⏸️ [ATTESA TAGLIO SHORT] Mercato sotto KJ {kj:.2f} ma trend già avviato (nessun taglio). In attesa del prossimo taglio da sopra a sotto.")
            elif self.position and self.position["direction"] == "SHORT":
                # Core già SHORT: azzera eventuale Candela Segnale e valuta incremento
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_ref_price = None

                # Assioma Granitico: Incremento SEMPRE e SOLO su ritracciamento (candela chiusa VERDE)
                is_retracement = prev_close > prev_open
                if not entry_allowed and is_retracement:
                    print(f"[{time_str}] ⏸️ [PRE-WEEKEND CUTOFF] Venerdì >= 22:14: Apertura Incremento SHORT sospesa prima del weekend.")
                elif is_retracement and not getattr(self, "entry_in_progress", False) and not getattr(self, "closing_in_progress", False):
                    dist_kj = abs(exec_price - kj)
                    active_incs = [i for i in self.increments if not i.get("closing")]
                    tot_incs = len(active_incs)

                    if tot_incs < MAX_INCREMENTS:
                        # 1. Regime BANCOMAT (distanza da KJ <= 10.0 pip): max 1 incremento con TP rapido a +5p
                        if dist_kj <= BANCOMAT_MAX_DIST_KJ:
                            has_bancomat = any(i.get("mode", "BANCOMAT") == "BANCOMAT" for i in active_incs)
                            troppo_vicino = any(abs(exec_price - i["open_price"]) < (MIN_DIST_INCR_PIPS - 1e-7) for i in active_incs)
                            if not has_bancomat and not troppo_vicino:
                                self.entry_in_progress = True
                                threading.Thread(
                                    target=self._execute_entry_increment,
                                    args=("SHORT", exec_price, time_str, "BANCOMAT"),
                                    daemon=True
                                ).start()

                        # 2. Regime RUNNER (distanza da KJ > 10.0 pip): piramidazione di trend, max 3 runner contemporanei con Trailing Stop
                        else:
                            runner_incs = [i for i in active_incs if i.get("mode") == "RUNNER"]
                            troppo_vicino_runner = any(abs(exec_price - i["open_price"]) < (MIN_DIST_RUNNER_PIPS - 1e-7) for i in active_incs)
                            if len(runner_incs) < MAX_RUNNER_INCREMENTS and not troppo_vicino_runner:
                                self.entry_in_progress = True
                                threading.Thread(
                                    target=self._execute_entry_increment,
                                    args=("SHORT", exec_price, time_str, "RUNNER"),
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
