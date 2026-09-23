try:
    from macchinetta_trend.position_manager import PositionManager
except (ImportError, ModuleNotFoundError):
    try:
        from position_manager import PositionManager
    except (ImportError, ModuleNotFoundError):
        from .position_manager import PositionManager
from collections import deque

class Candle:
    def __init__(self, open_p, high_p, low_p, close_p):
        self.open = float(open_p)
        self.high = float(high_p)
        self.low = float(low_p)
        self.close = float(close_p)
        
    def is_red(self):
        return self.close < self.open
        
    def is_green(self):
        return self.close > self.open
        
    def body_size(self):
        return abs(self.open - self.close)


class CoreEngine:
    def __init__(self, config=None):
        self.config = config or {}
        self.pm = PositionManager()
        
        # Stato del motore
        self.is_running = False
        self.current_direction = "FLAT" # "LONG", "SHORT" o "FLAT"
        self.candles = []  # Storico delle candele
        self.retracement_start_price = None # Traccia da dove parte un ritracciamento per gli incrementi cumulativi
        self.active_signal = None
        self.signal_candles_elapsed = 0
        
        # Stato Indicatori calcolati all'ultima candela chiusa
        self.current_tk = None
        self.current_kj = None
        self.trailing_sl_incr = None # Trailing SL a 20 pip da Close per tutti gli incrementi (dist TK >= 20 pip)
        self.trailing_sl_core = None # Trailing SL a 40 pip da Close per la Core (dist KJ >= 40 pip)
        self.signal_candle_active = False # True se una candela ha chiuso oltre KJ senza prendere il paracadute
        self.signal_stop_price = None     # Livello di stop confermato Core (Minimo - 5p per LONG, Massimo + 5p per SHORT)
        self.signal_candle_tk_active = False # True se una candela ha chiuso oltre TK senza prendere il paracadute TK
        self.signal_stop_price_tk = None     # Livello di stop confermato Incrementi (Minimo - 5p per LONG, Massimo + 5p per SHORT)
        
    def reset(self):
        """Resetta lo stato della macchinetta."""
        self.is_running = False
        self.pm = PositionManager() # Reset completo della memoria trade
        self.retracement_start_price = None
        self.active_signal = None
        self.signal_candles_elapsed = 0
        self.trailing_sl_incr = None
        self.trailing_sl_core = None
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_candle_tk_active = False
        self.signal_stop_price_tk = None
        # NOTA: le candele (lo storico) NON vengono resettate perché servono agli indicatori!

    def seed_history(self, candles_list):
        """Popola lo storico iniziale prima dell'avvio."""
        self.candles = candles_list

    def start(self, current_price, direction="LONG"):
        """Inizializza la macchinetta entrando a mercato con la Core nella direzione specificata."""
        self.is_running = True
        self.current_direction = direction
        self.retracement_start_price = None
        self.signal_candle_active = False
        self.signal_stop_price = None
        self.signal_candle_tk_active = False
        self.signal_stop_price_tk = None
        pos = self.pm.open_core(current_price, self.config.get("size_i"), direction)
        print(f"START: Eseguita Core a Mercato {direction} a Prezzo={current_price}")
        return pos


    def _calculate_donchian(self, periods):
        """Calcola la mediana (Max+Min)/2 degli ultimi N periodi (candele)."""
        if not self.candles:
            return None
        recent_candles = self.candles[-periods:] if len(self.candles) >= periods else self.candles
        valid_candles = [c for c in recent_candles if 0 < c.high < 1e8 and 0 < c.low < 1e8]
        if not valid_candles:
            return None
        highest = max(c.high for c in valid_candles)
        lowest = min(c.low for c in valid_candles)
        return (highest + lowest) / 2.0

    def _get_core_trailing_pips(self):
        """Restituisce la distanza/offset in pip per il Trailing SL Core in base al Timeframe."""
        return None

    def _get_increment_tp_pips(self):
        """Restituisce il target Take Profit in pip per gli incrementi rispetto a Tenkan (TK ± 50 pip su tutti i TF)."""
        return self.config.get("increment_tp_tk_pips", 50)

    def _get_increment_rules(self):
        """
        Restituisce le soglie Break-Even, Trailing e Take Profit per singolo incremento:
        - Crude Oil (Oil - US Crude):
            be_pips = 90, be_offset = 5, tp_pips = 100, trail_dist = 30
        - Commodities e Indici (Spot Gold, US 500 Cash):
            be_pips = 40, be_offset = 2, tp_pips = 50, trail_dist = 15
        - Cross Forex:
            be_pips = 25, be_offset = 1, tp_pips = 40, trail_dist = 12
        """
        nome = str(self.config.get("nome", "") or self.config.get("symbol", "")).strip().lower()
        if "oil" in nome or "crude" in nome:
            be_pips = self.config.get("increment_be_pips", 90)
            be_offset = self.config.get("increment_be_offset", 5)
            tp_pips = self.config.get("increment_tp_pips", 100)
            trail_dist = self.config.get("increment_trail_pips", 30)
        elif any(c in nome for c in ["gold", "us 500", "us500", "sp500"]):
            be_pips = self.config.get("increment_be_pips", 40)
            be_offset = self.config.get("increment_be_offset", 2)
            tp_pips = self.config.get("increment_tp_pips", 50)
            trail_dist = self.config.get("increment_trail_pips", 15)
        else:
            be_pips = self.config.get("increment_be_pips", 25)
            be_offset = self.config.get("increment_be_offset", 1)
            tp_pips = self.config.get("increment_tp_pips", 40)
            trail_dist = self.config.get("increment_trail_pips", 12)
        return be_pips, be_offset, tp_pips, trail_dist

    def _get_tk_increment_filters(self):
        """Restituisce (tolleranza_tk, max_dist_tk, min_dist_incr, min_candle_body) in pip/punti."""
        nome = str(self.config.get("nome", "") or self.config.get("symbol", "")).strip().lower()
        if "oil" in nome or "crude" in nome:
            return 10, 40, 30, 5 # Per Oil: tolleranza 10p, zona TK 40p, dist tra incr 30p, body 5p
        return 5, 20, 10, 1 # Per Forex e altri: 5p, 20p, 10p, 1p

    def _get_max_kj_tk_threshold_pips(self):
        """Restituisce la soglia di forbice Kijun-Tenkan in pip per Timeframe: H1=30, H4=40, D1=50."""
        tf_val = str(self.config.get("timeframe", "HOUR")).upper()
        if "HOUR_4" in tf_val or "H4" in tf_val:
            return 40
        elif "DAY" in tf_val or "D1" in tf_val:
            return 50
        else:
            return 30 # Default H1 (HOUR)

    def on_candle_close(self, closed_candle, next_open_price=None):
        """
        Metodo da chiamare OGNI VOLTA che si chiude una candela sul TF stabilito.
        """
        self.candles.append(closed_candle)
        if len(self.candles) > 100:
            self.candles.pop(0)
            
        events = []
        
        self.current_tk = self._calculate_donchian(self.config.get("tk_periods"))
        self.current_kj = self._calculate_donchian(self.config.get("kj_periods"))
        
        if not self.is_running:
            return events
            
        if self.current_tk is None or self.current_kj is None:
            return events
        c_close = closed_candle.close
        exec_price = next_open_price if next_open_price is not None else c_close
        tk = self.current_tk
        kj = self.current_kj
        pip_val = self.config.get("pip_value") or 0.0001
        min_body = self.config.get("min_body", 5) or 5
        min_body_price = min_body * pip_val
        size_max = self.config.get("size_max") or self.config.get("size_f", 10)
        core_trailing_pips = self._get_core_trailing_pips()
        
        # ==========================================
        # LOGICA BI-DIREZIONALE (STOP & REVERSE)
        # ==========================================
        
        if self.current_direction == "LONG":
            # --- USCITE E REVERSAL LONG ---
            # 0. Trailing Stop Estensione Trend H1: Distanza Prezzo - Kijun >= tp_kj_threshold pip a chiusura candela
            tf_val = str(self.config.get("timeframe", "HOUR")).upper()
            is_h1 = ("HOUR" in tf_val or "H1" in tf_val) and not ("HOUR_4" in tf_val or "H4" in tf_val)
            dist_kj_pips = (c_close - kj) / pip_val
            nome_str = str(self.config.get("nome", "") or self.config.get("symbol", "")).upper()
            is_oil = ("OIL" in nome_str or "CRUDE" in nome_str)
            default_tp_h1 = 250 if is_oil else 100
            tp_kj_threshold = float(self.config.get("tp_kj_distance_h1") or default_tp_h1)
            trail_pips = 65 if is_oil else 30

            if is_h1 and dist_kj_pips >= tp_kj_threshold:
                # Si attiva / aggiorna il Trailing SL Core a trail_pips dalla chiusura (picco confermato)
                nuovo_sl = c_close - (trail_pips * pip_val)
                if self.trailing_sl_core is None:
                    self.trailing_sl_core = nuovo_sl
                    events.append({
                        "type": "trailing_core_updated",
                        "direction": "LONG",
                        "stop_level": nuovo_sl,
                        "trail_pips": trail_pips,
                        "dist_kj_pips": round(dist_kj_pips, 1),
                        "reason": f"Attivazione Trailing Core Estensione H1 (+{int(dist_kj_pips)}p >= {int(tp_kj_threshold)}p)"
                    })
                elif nuovo_sl > self.trailing_sl_core:
                    self.trailing_sl_core = nuovo_sl
                    events.append({
                        "type": "trailing_core_updated",
                        "direction": "LONG",
                        "stop_level": nuovo_sl,
                        "trail_pips": trail_pips,
                        "dist_kj_pips": round(dist_kj_pips, 1),
                        "reason": f"Rettifica Trailing Core Estensione H1 a {nuovo_sl:.5f}"
                    })

            # 1. Chiusura Trailing SL Core a fine candela se attivo
            if self.trailing_sl_core is not None and c_close < self.trailing_sl_core:
                self.trailing_sl_core = None
                self.trailing_sl_incr = None
                self.signal_candle_active = False
                self.signal_stop_price = None
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_below_trailing_sl_core", "new_direction": "FLAT", "price": exec_price})
                self.current_direction = "FLAT"
                self.retracement_start_price = None
            elif c_close < kj:
                # 2. Chiusura sotto Kijun: Candela Segnale! Non chiude subito all'Open, imposta stop confermato a Minimo - 5 pip
                stop_livello = closed_candle.low - (5 * pip_val)
                if self.signal_candle_active and self.signal_stop_price is not None:
                    self.signal_stop_price = min(self.signal_stop_price, stop_livello)
                else:
                    self.signal_candle_active = True
                    self.signal_stop_price = stop_livello
                events.append({
                    "type": "signal_candle_kj",
                    "direction": "LONG",
                    "stop_price": self.signal_stop_price,
                    "candle_low": closed_candle.low,
                    "kj": kj
                })
            else:
                # 3. c_close >= kj: prezzo rientrato sopra Kijun, eventuale Candela Segnale azzerata
                self.signal_candle_active = False
                self.signal_stop_price = None

            if self.current_direction == "LONG":
                # Aggiornamento Trailing SL Core da Close (se core_trailing_pips è attivo)

                if core_trailing_pips is not None:
                    dist_kj = c_close - kj
                    if dist_kj >= (core_trailing_pips * pip_val):
                        nuovo_sl_core = c_close - (core_trailing_pips * pip_val)
                        if self.trailing_sl_core is None:
                            self.trailing_sl_core = nuovo_sl_core
                        else:
                            self.trailing_sl_core = max(self.trailing_sl_core, nuovo_sl_core)

                # Gestione Stop Loss Incrementi: Candela Segnale TK (se forbice TK-KJ > soglia)
                max_forbice_pips = self._get_max_kj_tk_threshold_pips()
                dist_kj_tk_pips = abs(tk - kj) / pip_val
                proteggi_su_tk = dist_kj_tk_pips > (max_forbice_pips - 1e-7)

                if len(self.pm.increments) > 0:
                    if proteggi_su_tk and c_close < (tk - 5 * pip_val - 1e-7):
                        # Chiusura sotto Tenkan oltre tolleranza 5 pip con forbice ampia (> soglia): Candela Segnale TK! Imposta stop a Minimo - 5 pip
                        stop_livello_tk = closed_candle.low - (5 * pip_val)
                        if self.signal_candle_tk_active and self.signal_stop_price_tk is not None:
                            self.signal_stop_price_tk = min(self.signal_stop_price_tk, stop_livello_tk)
                        else:
                            self.signal_candle_tk_active = True
                            self.signal_stop_price_tk = stop_livello_tk
                        events.append({
                            "type": "signal_candle_tk",
                            "direction": "LONG",
                            "stop_price": self.signal_stop_price_tk,
                            "candle_low": closed_candle.low,
                            "tk": tk
                        })
                    else:
                        # c_close in zona TK o sopra, oppure forbice stretta (<= soglia, respiro verso KJ): eventuale Candela Segnale TK azzerata
                        self.signal_candle_tk_active = False
                        self.signal_stop_price_tk = None
                else:
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None

            has_cleared_increments_long = any(e.get("type") in ("increments_cleared", "reversal") for e in events)
            if self.current_direction == "LONG" and not has_cleared_increments_long:
                # Take Profit Incrementi Bancomat (+25p Forex / +50p Comm) valutato a fine candela
                be_pips, be_offset_pips, tp_pips, trail_dist_pips = self._get_increment_rules()
                tp_threshold = tp_pips * pip_val
                inc_to_close = [p for p in list(self.pm.increments) if (c_close - p.entry_price) >= (tp_threshold - 1e-7)]
                for inc in inc_to_close:
                    inc.close(exec_price)
                    if inc in self.pm.increments:
                        self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    diff_p = (c_close - inc.entry_price) / pip_val
                    gained_pips = int(round(diff_p)) if round(diff_p, 1).is_integer() else round(diff_p, 1)
                    events.append({
                        "type": "tp_increment",
                        "pnl": inc.pnl,
                        "price": exec_price,
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "direction": "LONG",
                        "tp_pips": gained_pips
                    })
                if inc_to_close:
                    self.retracement_start_price = None

                # --- INGRESSI INCREMENTO LONG ---
                tol_pips, max_tk_dist_pips, min_dist_pips, min_body_pips = self._get_tk_increment_filters()
                tolleranza_tk = tol_pips * pip_val
                max_dist_tk = max_tk_dist_pips * pip_val
                min_dist_incr = min_dist_pips * pip_val
                min_body = min_body_pips * pip_val

                if closed_candle.open > (tk - tolleranza_tk) and c_close >= (tk - tolleranza_tk - 1e-7) and (c_close - tk) <= (max_dist_tk + 1e-7):
                    # Candela rossa di almeno min_body pip
                    if (closed_candle.open - closed_candle.close) >= (min_body - 1e-7):
                        entry_price = exec_price
                        troppo_vicino = any(abs(entry_price - inc.entry_price) < (min_dist_incr - 1e-7) for inc in self.pm.increments)
                        if troppo_vicino:
                            self.retracement_start_price = None
                        else:
                            scala = int(self.config.get("scala", 1) or 1)
                            while self.pm.total_active_size() + scala > size_max and len(self.pm.increments) > 0:
                                best = self.pm.force_close_best_increment(entry_price)
                                if best:
                                    events.append({
                                        "type": "fifo_close", 
                                        "pnl": best.pnl, 
                                        "price": entry_price, 
                                        "ticket": best.ticket, 
                                        "size": best.size,
                                        "direction": "LONG"
                                    })
                                else:
                                    break
                            pos = self.pm.open_increment(entry_price, size=scala, direction="LONG")
                            events.append({"type": "increment_opened", "price": entry_price, "direction": "LONG", "position": pos})
                            self.retracement_start_price = None
                    else:
                        self.retracement_start_price = None # Ritracciamento interrotto da candela verde
                else:
                    self.retracement_start_price = None # Fuori dai paletti

        elif self.current_direction == "SHORT":
            # --- USCITE E REVERSAL SHORT ---
            # 0. Trailing Stop Estensione Trend H1: Distanza Kijun - Prezzo >= tp_kj_threshold pip a chiusura candela
            tf_val = str(self.config.get("timeframe", "HOUR")).upper()
            is_h1 = ("HOUR" in tf_val or "H1" in tf_val) and not ("HOUR_4" in tf_val or "H4" in tf_val)
            dist_kj_pips = (kj - c_close) / pip_val
            nome_str = str(self.config.get("nome", "") or self.config.get("symbol", "")).upper()
            is_oil = ("OIL" in nome_str or "CRUDE" in nome_str)
            default_tp_h1 = 250 if is_oil else 100
            tp_kj_threshold = float(self.config.get("tp_kj_distance_h1") or default_tp_h1)
            trail_pips = 65 if is_oil else 30

            if is_h1 and dist_kj_pips >= tp_kj_threshold:
                # Si attiva / aggiorna il Trailing SL Core a trail_pips dalla chiusura (picco confermato)
                nuovo_sl = c_close + (trail_pips * pip_val)
                if self.trailing_sl_core is None:
                    self.trailing_sl_core = nuovo_sl
                    events.append({
                        "type": "trailing_core_updated",
                        "direction": "SHORT",
                        "stop_level": nuovo_sl,
                        "trail_pips": trail_pips,
                        "dist_kj_pips": round(dist_kj_pips, 1),
                        "reason": f"Attivazione Trailing Core Estensione H1 (+{int(dist_kj_pips)}p >= {int(tp_kj_threshold)}p)"
                    })
                elif nuovo_sl < self.trailing_sl_core:
                    self.trailing_sl_core = nuovo_sl
                    events.append({
                        "type": "trailing_core_updated",
                        "direction": "SHORT",
                        "stop_level": nuovo_sl,
                        "trail_pips": trail_pips,
                        "dist_kj_pips": round(dist_kj_pips, 1),
                        "reason": f"Rettifica Trailing Core Estensione H1 a {nuovo_sl:.5f}"
                    })

            # 1. Chiusura Trailing SL Core a fine candela se attivo
            if self.trailing_sl_core is not None and c_close > self.trailing_sl_core:
                self.trailing_sl_core = None
                self.trailing_sl_incr = None
                self.signal_candle_active = False
                self.signal_stop_price = None
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_above_trailing_sl_core", "new_direction": "FLAT", "price": exec_price})
                self.current_direction = "FLAT"
                self.retracement_start_price = None
            elif c_close > kj:
                # 2. Chiusura sopra Kijun: Candela Segnale! Non chiude subito all'Open, imposta stop confermato a Massimo + 5 pip
                stop_livello = closed_candle.high + (5 * pip_val)
                if self.signal_candle_active and self.signal_stop_price is not None:
                    self.signal_stop_price = max(self.signal_stop_price, stop_livello)
                else:
                    self.signal_candle_active = True
                    self.signal_stop_price = stop_livello
                events.append({
                    "type": "signal_candle_kj",
                    "direction": "SHORT",
                    "stop_price": self.signal_stop_price,
                    "candle_high": closed_candle.high,
                    "kj": kj
                })
            else:
                # 3. c_close <= kj: prezzo rientrato sotto Kijun, eventuale Candela Segnale azzerata
                self.signal_candle_active = False
                self.signal_stop_price = None

            if self.current_direction == "SHORT":
                # Aggiornamento Trailing SL Core da Close (se core_trailing_pips è attivo)

                if core_trailing_pips is not None:
                    dist_kj = kj - c_close
                    if dist_kj >= (core_trailing_pips * pip_val):
                        nuovo_sl_core = c_close + (core_trailing_pips * pip_val)
                        if self.trailing_sl_core is None:
                            self.trailing_sl_core = nuovo_sl_core
                        else:
                            self.trailing_sl_core = min(self.trailing_sl_core, nuovo_sl_core)

                # Gestione Stop Loss Incrementi: Candela Segnale TK (se forbice TK-KJ > soglia)
                max_forbice_pips = self._get_max_kj_tk_threshold_pips()
                dist_kj_tk_pips = abs(tk - kj) / pip_val
                proteggi_su_tk = dist_kj_tk_pips > (max_forbice_pips - 1e-7)

                if len(self.pm.increments) > 0:
                    if proteggi_su_tk and c_close > (tk + 5 * pip_val + 1e-7):
                        # Chiusura sopra Tenkan oltre tolleranza 5 pip con forbice ampia (> soglia): Candela Segnale TK! Imposta stop a Massimo + 5 pip
                        stop_livello_tk = closed_candle.high + (5 * pip_val)
                        if self.signal_candle_tk_active and self.signal_stop_price_tk is not None:
                            self.signal_stop_price_tk = max(self.signal_stop_price_tk, stop_livello_tk)
                        else:
                            self.signal_candle_tk_active = True
                            self.signal_stop_price_tk = stop_livello_tk
                        events.append({
                            "type": "signal_candle_tk",
                            "direction": "SHORT",
                            "stop_price": self.signal_stop_price_tk,
                            "candle_high": closed_candle.high,
                            "tk": tk
                        })
                    else:
                        # c_close in zona TK o sotto, oppure forbice stretta (<= soglia, respiro verso KJ): eventuale Candela Segnale TK azzerata
                        self.signal_candle_tk_active = False
                        self.signal_stop_price_tk = None
                else:
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None

            has_cleared_increments_short = any(e.get("type") in ("increments_cleared", "reversal") for e in events)
            if self.current_direction == "SHORT" and not has_cleared_increments_short:
                # Take Profit Incrementi Bancomat (+25p Forex / +50p Comm) valutato a fine candela
                be_pips, be_offset_pips, tp_pips, trail_dist_pips = self._get_increment_rules()
                tp_threshold = tp_pips * pip_val
                inc_to_close = [p for p in list(self.pm.increments) if (p.entry_price - c_close) >= (tp_threshold - 1e-7)]
                for inc in inc_to_close:
                    inc.close(exec_price)
                    if inc in self.pm.increments:
                        self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    diff_p = (inc.entry_price - c_close) / pip_val
                    gained_pips = int(round(diff_p)) if round(diff_p, 1).is_integer() else round(diff_p, 1)
                    events.append({
                        "type": "tp_increment",
                        "pnl": inc.pnl,
                        "price": exec_price,
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "direction": "SHORT",
                        "tp_pips": gained_pips
                    })
                if inc_to_close:
                    self.retracement_start_price = None

                # --- INGRESSI INCREMENTO SHORT ---
                tol_pips, max_tk_dist_pips, min_dist_pips, min_body_pips = self._get_tk_increment_filters()
                tolleranza_tk = tol_pips * pip_val
                max_dist_tk = max_tk_dist_pips * pip_val
                min_dist_incr = min_dist_pips * pip_val
                min_body = min_body_pips * pip_val

                if closed_candle.open < (tk + tolleranza_tk) and c_close <= (tk + tolleranza_tk + 1e-7) and (tk - c_close) <= (max_dist_tk + 1e-7):
                    # Candela verde di almeno min_body pip
                    if (closed_candle.close - closed_candle.open) >= (min_body - 1e-7):
                        entry_price = exec_price
                        troppo_vicino = any(abs(entry_price - inc.entry_price) < (min_dist_incr - 1e-7) for inc in self.pm.increments)
                        if troppo_vicino:
                            self.retracement_start_price = None
                        else:
                            scala = int(self.config.get("scala", 1) or 1)
                            while self.pm.total_active_size() + scala > size_max and len(self.pm.increments) > 0:
                                best = self.pm.force_close_best_increment(entry_price)
                                if best:
                                    events.append({
                                        "type": "fifo_close", 
                                        "pnl": best.pnl, 
                                        "price": entry_price, 
                                        "ticket": best.ticket, 
                                        "size": best.size,
                                        "direction": "SHORT"
                                    })
                                else:
                                    break
                            pos = self.pm.open_increment(entry_price, size=scala, direction="SHORT")
                            events.append({"type": "increment_opened", "price": entry_price, "direction": "SHORT", "position": pos})
                            self.retracement_start_price = None
                    else:
                        self.retracement_start_price = None # Ritracciamento interrotto da candela rossa
                else:
                    self.retracement_start_price = None # Fuori dai paletti

        # --- VALUTAZIONE INGRESSO DA STATO FLAT (AUTO-RESTART) ---
        if self.current_direction == "FLAT":
            if not self.config.get("auto_restart", False):
                return events

            is_long_cond = c_close > kj and closed_candle.is_green()
            is_short_cond = c_close < kj and closed_candle.is_red()
            
            pip_val = self.config.get("pip_value") or 0.0001
            max_dist = (self.config.get("max_kj_distance") or 30.0) * pip_val
            max_delay = self.config.get("max_entry_delay") or 5
            
            if is_long_cond:
                if self.active_signal != "LONG":
                    self.active_signal = "LONG"
                    self.signal_candles_elapsed = 0
                self.signal_candles_elapsed += 1
                
                if abs(exec_price - kj) <= max_dist:
                    if self.signal_candles_elapsed <= max_delay:
                        self.start(exec_price, "LONG")
                        reason = "rottura_kj_candela_verde"
                        events.append({"type": "auto_start", "direction": "LONG", "price": exec_price, "reason": reason})
                        self.active_signal = None
                        self.signal_candles_elapsed = 0
            
            elif is_short_cond:
                if self.active_signal != "SHORT":
                    self.active_signal = "SHORT"
                    self.signal_candles_elapsed = 0
                self.signal_candles_elapsed += 1
                
                if abs(kj - exec_price) <= max_dist:
                    if self.signal_candles_elapsed <= max_delay:
                        self.start(exec_price, "SHORT")
                        reason = "rottura_kj_candela_rossa"
                        events.append({"type": "auto_start", "direction": "SHORT", "price": exec_price, "reason": reason})
                        self.active_signal = None
                        self.signal_candles_elapsed = 0
            
            else:
                # Se nessuna delle due condizioni base è vera, il segnale decade e si resetta tutto
                self.active_signal = None
                self.signal_candles_elapsed = 0

        return events

    def check_live_stops(self, current_price):
        """
        Valuta Stop Loss in tempo reale (intracandela):
        - Core: KJ +- 15 pip o Trailing SL Core o Candela Segnale Min/Max +- 5 pip
        - Incrementi Stop: Paracadute TK +- 15 pip o Candela Segnale TK Min/Max +- 5 pip
        (Nota: il Take Profit Incrementi TK ± 50 pip viene valutato a fine candela)
        """
        events = []
        if not self.is_running or self.current_direction == "FLAT":
            return events
        if self.current_tk is None or self.current_kj is None or current_price is None:
            return events
            
        tk = self.current_tk
        kj = self.current_kj
        pip_val = self.config.get("pip_value") or 0.0001
        max_forbice_pips = self._get_max_kj_tk_threshold_pips()
        dist_kj_tk_pips = abs(tk - kj) / pip_val
        proteggi_su_tk = dist_kj_tk_pips > (max_forbice_pips - 1e-7)
        
        # Soglie per gestione a 3 stadi singolo incremento
        be_pips, be_offset_pips, tp_pips, trail_dist_pips = self._get_increment_rules()
        be_threshold = be_pips * pip_val
        be_offset = be_offset_pips * pip_val
        tp_threshold = tp_pips * pip_val
        trail_dist = trail_dist_pips * pip_val

        nome_str = str(self.config.get("nome", "") or self.config.get("symbol", "")).strip().lower()
        sl_core_pips = 40 if ("oil" in nome_str or "crude" in nome_str) else 15

        if self.current_direction == "LONG":
            # 1. Stop Loss Core Intracandela (Paracadute): KJ - 15 pip (40p per Oil) o Trailing SL Core
            sl_core_base = kj - (sl_core_pips * pip_val)
            effective_sl_core = max(sl_core_base, self.trailing_sl_core) if self.trailing_sl_core is not None else sl_core_base
            if current_price <= (effective_sl_core + 1e-7):
                reason = "live_stop_trailing_core" if (self.trailing_sl_core is not None and effective_sl_core == self.trailing_sl_core) else "live_stop_kj"
                self.trailing_sl_core = None
                self.trailing_sl_incr = None
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_candle_tk_active = False
                self.signal_stop_price_tk = None
                events.extend(self.pm.close_all_increments(current_price))
                ev = self.pm.close_core(current_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": reason, "new_direction": "FLAT", "price": current_price})
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                return events

            # 2. Stop Conferma Candela Segnale Core (Minimo - 5 pip)
            if self.signal_candle_active and self.signal_stop_price is not None:
                if current_price <= (self.signal_stop_price + 1e-7):
                    self.trailing_sl_core = None
                    self.trailing_sl_incr = None
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    events.extend(self.pm.close_all_increments(current_price))
                    ev = self.pm.close_core(current_price)
                    if ev: events.append(ev)
                    events.append({"type": "reversal", "reason": "live_stop_kj_break_min", "new_direction": "FLAT", "price": current_price})
                    self.current_direction = "FLAT"
                    self.retracement_start_price = None
                    return events

            # 3. Stop Loss Incrementi Intracandela: Paracadute TK a TK - 15 pip solo se forbice ampia > soglia
            if len(self.pm.increments) > 0 and proteggi_su_tk:
                sl_incr_base = tk - (15 * pip_val)
                if current_price <= (sl_incr_base + 1e-7):
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_tk", "price": current_price})
                    self.retracement_start_price = None

            # 4. Stop Conferma Candela Segnale TK (Minimo - 5 pip) - attivo solo se forbice ampia
            if len(self.pm.increments) > 0 and proteggi_su_tk and self.signal_candle_tk_active and self.signal_stop_price_tk is not None:
                if current_price <= (self.signal_stop_price_tk + 1e-7):
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_tk_break_min", "price": current_price})
                    self.retracement_start_price = None

            # 5. Gestione a 3 Stadi Singolo Incremento (Break-Even, Trailing Stop e Take Profit Bancomat)
            for inc in list(self.pm.increments):
                gain = current_price - inc.entry_price
                if not hasattr(inc, 'highest_price') or inc.highest_price is None:
                    inc.highest_price = inc.entry_price
                inc.highest_price = max(inc.highest_price, current_price)

                # A. Take Profit Bancomat Immediato al Target (+25p Forex / +50p Comm)
                if gain >= (tp_threshold - 1e-7):
                    inc.close(current_price)
                    if inc in self.pm.increments:
                        self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    diff_p = gain / pip_val
                    gained_pips = int(round(diff_p)) if round(diff_p, 1).is_integer() else round(diff_p, 1)
                    events.append({
                        "type": "tp_increment",
                        "pnl": inc.pnl,
                        "price": current_price,
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "direction": "LONG",
                        "tp_pips": gained_pips
                    })
                    self.retracement_start_price = None
                    continue

                # B. Attivazione Break-Even (+15p Forex / +30p Comm)
                if gain >= (be_threshold - 1e-7):
                    be_level = inc.entry_price + be_offset
                    if not getattr(inc, 'be_active', False):
                        inc.be_active = True
                        inc.sl_price = be_level
                        events.append({
                            "type": "increment_be_activated",
                            "ticket": inc.ticket,
                            "size": inc.size,
                            "direction": "LONG",
                            "price": current_price,
                            "sl_price": be_level,
                            "be_pips": be_pips
                        })
                    # Trailing Stop progressivo sopra Break-Even
                    trail_level = inc.highest_price - trail_dist
                    if getattr(inc, 'sl_price', None) is not None:
                        inc.sl_price = max(inc.sl_price, trail_level)
                    else:
                        inc.sl_price = max(be_level, trail_level)

                # C. Esecuzione Stop / Break-Even dell'incremento
                if getattr(inc, 'sl_price', None) is not None and current_price <= (inc.sl_price + 1e-7):
                    inc.close(current_price)
                    if inc in self.pm.increments:
                        self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    is_pure_be = (inc.sl_price <= (inc.entry_price + be_offset + 1e-7))
                    reason_close = "be_increment" if is_pure_be else "trailing_increment"
                    events.append({
                        "type": "increment_closed",
                        "reason": reason_close,
                        "pnl": inc.pnl,
                        "price": current_price,
                        "direction": "LONG",
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "sl_price": inc.sl_price
                    })
                    self.retracement_start_price = None

        elif self.current_direction == "SHORT":
            # 1. Stop Loss Core Intracandela (Paracadute): KJ + 15 pip (40p per Oil) o Trailing SL Core
            sl_core_base = kj + (sl_core_pips * pip_val)
            effective_sl_core = min(sl_core_base, self.trailing_sl_core) if self.trailing_sl_core is not None else sl_core_base
            if current_price >= (effective_sl_core - 1e-7):
                reason = "live_stop_trailing_core" if (self.trailing_sl_core is not None and effective_sl_core == self.trailing_sl_core) else "live_stop_kj"
                self.trailing_sl_core = None
                self.trailing_sl_incr = None
                self.signal_candle_active = False
                self.signal_stop_price = None
                self.signal_candle_tk_active = False
                self.signal_stop_price_tk = None
                events.extend(self.pm.close_all_increments(current_price))
                ev = self.pm.close_core(current_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": reason, "new_direction": "FLAT", "price": current_price})
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                return events

            # 2. Stop Conferma Candela Segnale Core (Massimo + 5 pip)
            if self.signal_candle_active and self.signal_stop_price is not None:
                if current_price >= (self.signal_stop_price - 1e-7):
                    self.trailing_sl_core = None
                    self.trailing_sl_incr = None
                    self.signal_candle_active = False
                    self.signal_stop_price = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    events.extend(self.pm.close_all_increments(current_price))
                    ev = self.pm.close_core(current_price)
                    if ev: events.append(ev)
                    events.append({"type": "reversal", "reason": "live_stop_kj_break_max", "new_direction": "FLAT", "price": current_price})
                    self.current_direction = "FLAT"
                    self.retracement_start_price = None
                    return events

            # 3. Stop Loss Incrementi Intracandela: Paracadute TK a TK + 15 pip solo se forbice ampia > soglia
            if len(self.pm.increments) > 0 and proteggi_su_tk:
                sl_incr_base = tk + (15 * pip_val)
                if current_price >= (sl_incr_base - 1e-7):
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_tk", "price": current_price})
                    self.retracement_start_price = None

            # 4. Stop Conferma Candela Segnale TK (Massimo + 5 pip) - attivo solo se forbice ampia
            if len(self.pm.increments) > 0 and proteggi_su_tk and self.signal_candle_tk_active and self.signal_stop_price_tk is not None:
                if current_price >= (self.signal_stop_price_tk - 1e-7):
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_tk_break_max", "price": current_price})
                    self.retracement_start_price = None

            # 5. Gestione a 3 Stadi Singolo Incremento (Break-Even, Trailing Stop e Take Profit Bancomat)
            for inc in list(self.pm.increments):
                gain = inc.entry_price - current_price
                if not hasattr(inc, 'lowest_price') or inc.lowest_price is None:
                    inc.lowest_price = inc.entry_price
                inc.lowest_price = min(inc.lowest_price, current_price)

                # A. Take Profit Bancomat Immediato al Target (+25p Forex / +50p Comm)
                if gain >= (tp_threshold - 1e-7):
                    inc.close(current_price)
                    if inc in self.pm.increments:
                        self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    diff_p = gain / pip_val
                    gained_pips = int(round(diff_p)) if round(diff_p, 1).is_integer() else round(diff_p, 1)
                    events.append({
                        "type": "tp_increment",
                        "pnl": inc.pnl,
                        "price": current_price,
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "direction": "SHORT",
                        "tp_pips": gained_pips
                    })
                    self.retracement_start_price = None
                    continue

                # B. Attivazione Break-Even (+15p Forex / +30p Comm)
                if gain >= (be_threshold - 1e-7):
                    be_level = inc.entry_price - be_offset
                    if not getattr(inc, 'be_active', False):
                        inc.be_active = True
                        inc.sl_price = be_level
                        events.append({
                            "type": "increment_be_activated",
                            "ticket": inc.ticket,
                            "size": inc.size,
                            "direction": "SHORT",
                            "price": current_price,
                            "sl_price": be_level,
                            "be_pips": be_pips
                        })
                    # Trailing Stop progressivo sopra Break-Even
                    trail_level = inc.lowest_price + trail_dist
                    if getattr(inc, 'sl_price', None) is not None:
                        inc.sl_price = min(inc.sl_price, trail_level)
                    else:
                        inc.sl_price = min(be_level, trail_level)

                # C. Esecuzione Stop / Break-Even dell'incremento
                if getattr(inc, 'sl_price', None) is not None and current_price >= (inc.sl_price - 1e-7):
                    inc.close(current_price)
                    if inc in self.pm.increments:
                        self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    is_pure_be = (inc.sl_price >= (inc.entry_price - be_offset - 1e-7))
                    reason_close = "be_increment" if is_pure_be else "trailing_increment"
                    events.append({
                        "type": "increment_closed",
                        "reason": reason_close,
                        "pnl": inc.pnl,
                        "price": current_price,
                        "direction": "SHORT",
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "sl_price": inc.sl_price
                    })
                    self.retracement_start_price = None

        return events
