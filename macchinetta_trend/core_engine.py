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
        """Restituisce il target Take Profit in pip per gli incrementi in base al Timeframe."""
        tf_val = str(self.config.get("timeframe", "HOUR")).upper()
        if "HOUR_4" in tf_val or "H4" in tf_val:
            return 40
        elif "DAY" in tf_val or "D1" in tf_val:
            return 50
        else:
            return 30 # Default H1 (HOUR)

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
            # 1. Chiusura Trailing SL Core a fine candela se attivo
            if self.trailing_sl_core is not None and c_close < self.trailing_sl_core:
                self.trailing_sl_core = None
                self.trailing_sl_incr = None
                self.signal_candle_active = False
                self.signal_stop_price = None
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_below_trailing_sl_core", "new_direction": "FLAT"})
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

                # Gestione Stop Loss Incrementi: Trailing SL o Candela Segnale TK (se forbice TK-KJ > soglia)
                max_forbice_pips = self._get_max_kj_tk_threshold_pips()
                dist_kj_tk_pips = abs(tk - kj) / pip_val
                proteggi_su_tk = dist_kj_tk_pips > (max_forbice_pips - 1e-7)

                if len(self.pm.increments) > 0:
                    if self.trailing_sl_incr is not None and c_close < self.trailing_sl_incr:
                        # 1. Chiusura Trailing SL a fine candela se attivo
                        self.trailing_sl_incr = None
                        self.signal_candle_tk_active = False
                        self.signal_stop_price_tk = None
                        chiusure_inc = self.pm.close_all_increments(exec_price)
                        if chiusure_inc:
                            events.extend(chiusure_inc)
                            events.append({"type": "increments_cleared", "reason": "close_below_trailing_sl"})
                        self.retracement_start_price = None
                    elif proteggi_su_tk and c_close < tk:
                        # 2. Chiusura sotto Tenkan con forbice ampia (> soglia): Candela Segnale TK! Imposta stop a Minimo - 5 pip
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
                        # 3. c_close >= tk oppure forbice stretta (<= soglia, respiro verso KJ): eventuale Candela Segnale TK azzerata
                        self.signal_candle_tk_active = False
                        self.signal_stop_price_tk = None
                        # Aggiornamento Trailing SL dinamico a 20 pip da Close se distanza da TK >= 20 pip (cricchetto che può solo salire)
                        dist_tk = c_close - tk
                        if dist_tk >= (20 * pip_val):
                            nuovo_sl = c_close - (20 * pip_val)
                            if self.trailing_sl_incr is None:
                                self.trailing_sl_incr = nuovo_sl
                            else:
                                self.trailing_sl_incr = max(self.trailing_sl_incr, nuovo_sl)
                else:
                    self.trailing_sl_incr = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None

            has_cleared_increments_long = any(e.get("type") == "increments_cleared" for e in events)
            if self.current_direction == "LONG" and not has_cleared_increments_long:
                # Take Profit Incrementi a fine candela: H1=+30 pip, H4=+40 pip, D1=+50 pip
                incr_tp_pips = self._get_increment_tp_pips()
                if incr_tp_pips and len(self.pm.increments) > 0:
                    tp_target_delta = incr_tp_pips * pip_val
                    inc_to_close = [p for p in self.pm.increments if (c_close - p.entry_price) >= (tp_target_delta - 1e-7)]
                    for inc in inc_to_close:
                        inc.close(exec_price)
                        self.pm.increments.remove(inc)
                        self.pm.closed_positions.append(inc)
                        events.append({
                            "type": "tp_increment",
                            "pnl": inc.pnl,
                            "price": exec_price,
                            "ticket": inc.ticket,
                            "size": inc.size,
                            "direction": "LONG",
                            "tp_pips": incr_tp_pips
                        })
                    if inc_to_close:
                        self.retracement_start_price = None

                # --- INGRESSI INCREMENTO LONG ---
                # Candela ha aperto sopra TK, close >= TK e distanza da TK <= 20 pip
                if closed_candle.open > tk and c_close >= tk and (c_close - tk) <= (20 * pip_val + 1e-7):
                    # Candela rossa di almeno 1 pip su tutti i TF
                    if (closed_candle.open - closed_candle.close) >= (1 * pip_val - 1e-7):
                        entry_price = exec_price
                        # REGOLA OPZIONE B: Distanza minima di almeno 10 pip da qualsiasi incremento attivo a mercato
                        min_dist_incr = 10 * pip_val
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
            # 1. Chiusura Trailing SL Core a fine candela se attivo
            if self.trailing_sl_core is not None and c_close > self.trailing_sl_core:
                self.trailing_sl_core = None
                self.trailing_sl_incr = None
                self.signal_candle_active = False
                self.signal_stop_price = None
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_above_trailing_sl_core", "new_direction": "FLAT"})
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

                # Gestione Stop Loss Incrementi: Trailing SL o Candela Segnale TK (se forbice TK-KJ > soglia)
                max_forbice_pips = self._get_max_kj_tk_threshold_pips()
                dist_kj_tk_pips = abs(tk - kj) / pip_val
                proteggi_su_tk = dist_kj_tk_pips > (max_forbice_pips - 1e-7)

                if len(self.pm.increments) > 0:
                    if self.trailing_sl_incr is not None and c_close > self.trailing_sl_incr:
                        # 1. Chiusura Trailing SL a fine candela se attivo
                        self.trailing_sl_incr = None
                        self.signal_candle_tk_active = False
                        self.signal_stop_price_tk = None
                        chiusure_inc = self.pm.close_all_increments(exec_price)
                        if chiusure_inc:
                            events.extend(chiusure_inc)
                            events.append({"type": "increments_cleared", "reason": "close_above_trailing_sl"})
                        self.retracement_start_price = None
                    elif proteggi_su_tk and c_close > tk:
                        # 2. Chiusura sopra Tenkan con forbice ampia (> soglia): Candela Segnale TK! Imposta stop a Massimo + 5 pip
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
                        # 3. c_close <= tk oppure forbice stretta (<= soglia, respiro verso KJ): eventuale Candela Segnale TK azzerata
                        self.signal_candle_tk_active = False
                        self.signal_stop_price_tk = None
                        # Aggiornamento Trailing SL dinamico a 20 pip da Close se distanza da TK >= 20 pip (cricchetto che può solo scendere)
                        dist_tk = tk - c_close
                        if dist_tk >= (20 * pip_val):
                            nuovo_sl = c_close + (20 * pip_val)
                            if self.trailing_sl_incr is None:
                                self.trailing_sl_incr = nuovo_sl
                            else:
                                self.trailing_sl_incr = min(self.trailing_sl_incr, nuovo_sl)
                else:
                    self.trailing_sl_incr = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None

            has_cleared_increments_short = any(e.get("type") == "increments_cleared" for e in events)
            if self.current_direction == "SHORT" and not has_cleared_increments_short:
                # Take Profit Incrementi a fine candela: H1=+30 pip, H4=+40 pip, D1=+50 pip
                incr_tp_pips = self._get_increment_tp_pips()
                if incr_tp_pips and len(self.pm.increments) > 0:
                    tp_target_delta = incr_tp_pips * pip_val
                    inc_to_close = [p for p in self.pm.increments if (p.entry_price - c_close) >= (tp_target_delta - 1e-7)]
                    for inc in inc_to_close:
                        inc.close(exec_price)
                        self.pm.increments.remove(inc)
                        self.pm.closed_positions.append(inc)
                        events.append({
                            "type": "tp_increment",
                            "pnl": inc.pnl,
                            "price": exec_price,
                            "ticket": inc.ticket,
                            "size": inc.size,
                            "direction": "SHORT",
                            "tp_pips": incr_tp_pips
                        })
                    if inc_to_close:
                        self.retracement_start_price = None

                # --- INGRESSI INCREMENTO SHORT ---
                # Candela ha aperto sotto TK, close <= TK e distanza da TK <= 20 pip
                if closed_candle.open < tk and c_close <= tk and (tk - c_close) <= (20 * pip_val + 1e-7):
                    # Candela verde di almeno 1 pip su tutti i TF
                    if (closed_candle.close - closed_candle.open) >= (1 * pip_val - 1e-7):
                        entry_price = exec_price
                        # REGOLA OPZIONE B: Distanza minima di almeno 10 pip da qualsiasi incremento attivo a mercato
                        min_dist_incr = 10 * pip_val
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
        Valuta Stop Loss e Take Profit in tempo reale (intracandela):
        - Core: KJ +- 5 pip o Trailing SL Core
        - Incrementi Stop: TK +- 10 pip o Trailing SL Incr
        - Incrementi Take Profit: +30 pip (H1), +40 pip (H4), +50 pip (D1)
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
        
        if self.current_direction == "LONG":
            # 1. Stop Loss Core Intracandela (Paracadute): KJ - 15 pip o Trailing SL Core
            sl_core_base = kj - (15 * pip_val)
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

            # 3. Stop Loss Incrementi Intracandela: Trailing SL a 20 pip oppure (se forbice ampia > soglia) Paracadute TK a TK - 15 pip
            if len(self.pm.increments) > 0:
                if self.trailing_sl_incr is not None and current_price <= (self.trailing_sl_incr + 1e-7):
                    self.trailing_sl_incr = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_trailing", "price": current_price})
                    self.retracement_start_price = None
                elif proteggi_su_tk:
                    sl_incr_base = tk - (15 * pip_val)
                    if current_price <= (sl_incr_base + 1e-7):
                        self.trailing_sl_incr = None
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
                    self.trailing_sl_incr = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_tk_break_min", "price": current_price})
                    self.retracement_start_price = None

            # 5. Take Profit Incrementi (Live): H1=+30 pip, H4=+40 pip, D1=+50 pip dall'entry price
            incr_tp_pips = self._get_increment_tp_pips()
            if incr_tp_pips and len(self.pm.increments) > 0:
                tp_target_delta = incr_tp_pips * pip_val
                inc_to_close = [p for p in self.pm.increments if (current_price - p.entry_price) >= (tp_target_delta - 1e-7)]
                for inc in inc_to_close:
                    inc.close(current_price)
                    self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    events.append({
                        "type": "tp_increment",
                        "pnl": inc.pnl,
                        "price": current_price,
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "direction": "LONG",
                        "tp_pips": incr_tp_pips
                    })
                if inc_to_close:
                    self.retracement_start_price = None

        elif self.current_direction == "SHORT":
            # 1. Stop Loss Core Intracandela (Paracadute): KJ + 15 pip o Trailing SL Core
            sl_core_base = kj + (15 * pip_val)
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

            # 3. Stop Loss Incrementi Intracandela: Trailing SL a 20 pip oppure (se forbice ampia > soglia) Paracadute TK a TK + 15 pip
            if len(self.pm.increments) > 0:
                if self.trailing_sl_incr is not None and current_price >= (self.trailing_sl_incr - 1e-7):
                    self.trailing_sl_incr = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_trailing", "price": current_price})
                    self.retracement_start_price = None
                elif proteggi_su_tk:
                    sl_incr_base = tk + (15 * pip_val)
                    if current_price >= (sl_incr_base - 1e-7):
                        self.trailing_sl_incr = None
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
                    self.trailing_sl_incr = None
                    self.signal_candle_tk_active = False
                    self.signal_stop_price_tk = None
                    chiusure_inc = self.pm.close_all_increments(current_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": "live_stop_tk_break_max", "price": current_price})
                    self.retracement_start_price = None

            # 5. Take Profit Incrementi (Live): H1=+30 pip, H4=+40 pip, D1=+50 pip dall'entry price

            incr_tp_pips = self._get_increment_tp_pips()
            if incr_tp_pips and len(self.pm.increments) > 0:
                tp_target_delta = incr_tp_pips * pip_val
                inc_to_close = [p for p in self.pm.increments if (p.entry_price - current_price) >= (tp_target_delta - 1e-7)]
                for inc in inc_to_close:
                    inc.close(current_price)
                    self.pm.increments.remove(inc)
                    self.pm.closed_positions.append(inc)
                    events.append({
                        "type": "tp_increment",
                        "pnl": inc.pnl,
                        "price": current_price,
                        "ticket": inc.ticket,
                        "size": inc.size,
                        "direction": "SHORT",
                        "tp_pips": incr_tp_pips
                    })
                if inc_to_close:
                    self.retracement_start_price = None

        return events
