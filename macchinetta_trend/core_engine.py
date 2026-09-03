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
        self.trailing_sl_incr = None # Trailing SL a 20 pip da Close per tutti gli incrementi
        
    def reset(self):
        """Resetta lo stato della macchinetta."""
        self.is_running = False
        self.pm = PositionManager() # Reset completo della memoria trade
        self.retracement_start_price = None
        self.active_signal = None
        self.signal_candles_elapsed = 0
        self.trailing_sl_incr = None
        # NOTA: le candele (lo storico) NON vengono resettate perché servono agli indicatori!

    def seed_history(self, candles_list):
        """Popola lo storico iniziale prima dell'avvio."""
        self.candles = candles_list

    def start(self, current_price, direction="LONG"):
        """Inizializza la macchinetta entrando a mercato con la Core nella direzione specificata."""
        self.is_running = True
        self.current_direction = direction
        self.retracement_start_price = None
        pos = self.pm.open_core(current_price, self.config.get("size_i"), direction)
        print(f"START: Eseguita Core a Mercato {direction} a Prezzo={current_price}")
        return pos

    def _calculate_donchian(self, periods):
        """Calcola la mediana (Max+Min)/2 degli ultimi N periodi (candele)."""
        if len(self.candles) < periods:
            return None
        recent_candles = self.candles[-periods:]
        valid_candles = [c for c in recent_candles if 0 < c.high < 1e8 and 0 < c.low < 1e8]
        if not valid_candles:
            return None
        highest = max(c.high for c in valid_candles)
        lowest = min(c.low for c in valid_candles)
        return (highest + lowest) / 2.0

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
        
        # ==========================================
        # LOGICA BI-DIREZIONALE (STOP & REVERSE)
        # ==========================================
        
        if self.current_direction == "LONG":
            # --- USCITE E REVERSAL LONG ---
            sl_core_long = kj - (5 * pip_val)
            if c_close < sl_core_long:
                # Sotto la Kijun - 5 pip: Chiude tutto e passa in FLAT
                self.trailing_sl_incr = None
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_below_kj_buffer", "new_direction": "FLAT"})
                
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                # Non esegue return, così può eventualmente valutare subito se ci sono le condizioni per entrare SHORT
                
            else:
                # Gestione Stop Loss Incrementi: TK - 5 pip o Trailing SL (il più alto / restrittivo)
                sl_incr_base = tk - (5 * pip_val)
                effective_sl_incr = max(sl_incr_base, self.trailing_sl_incr) if self.trailing_sl_incr is not None else sl_incr_base
                
                if len(self.pm.increments) > 0 and c_close < effective_sl_incr:
                    reason = "close_below_trailing_sl" if (self.trailing_sl_incr is not None and effective_sl_incr == self.trailing_sl_incr) else "close_below_tk_buffer"
                    self.trailing_sl_incr = None
                    chiusure_inc = self.pm.close_all_increments(exec_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": reason})
                    self.retracement_start_price = None
                else:
                    # Aggiornamento Trailing SL dinamico a 20 pip da Close (cricchetto che può solo salire)
                    if len(self.pm.increments) > 0:
                        dist_tk = c_close - tk
                        if dist_tk >= (20 * pip_val):
                            nuovo_sl = c_close - (20 * pip_val)
                            if self.trailing_sl_incr is None:
                                self.trailing_sl_incr = nuovo_sl
                            else:
                                self.trailing_sl_incr = max(self.trailing_sl_incr, nuovo_sl)
                    else:
                        self.trailing_sl_incr = None

            has_cleared_increments_long = any(e.get("type") == "increments_cleared" for e in events)
            if self.current_direction == "LONG" and not has_cleared_increments_long:
                # --- INGRESSI INCREMENTO LONG ---
                # Paletto: TK > KJ (o tollerato) e la candela deve aver APERTO SOPRA la TK (close precedente > TK)
                if (tk > kj or abs(tk - kj) <= min_body_price) and closed_candle.open > tk and c_close >= tk:
                    if closed_candle.is_red():
                        if self.retracement_start_price is None:
                            self.retracement_start_price = closed_candle.open
                            
                        distanza_percorsa = self.retracement_start_price - closed_candle.low
                        
                        if distanza_percorsa >= min_body_price:
                            entry_price = exec_price 
                            if self.pm.total_active_size() >= size_max:
                                best = self.pm.force_close_best_increment(entry_price)
                                if best:
                                    events.append({"type": "fifo_close", "pnl": best.pnl, "price": entry_price, "ticket": best.ticket, "size": best.size})
                            pos = self.pm.open_increment(entry_price, size=1, direction="LONG")
                            events.append({"type": "increment_opened", "price": entry_price, "direction": "LONG", "position": pos})
                            
                            self.retracement_start_price = None # Resetta il conteggio dopo l'incremento
                    else:
                        self.retracement_start_price = None # Ritracciamento interrotto da candela verde
                else:
                    self.retracement_start_price = None # Fuori dai paletti

        elif self.current_direction == "SHORT":
            # --- USCITE E REVERSAL SHORT ---
            sl_core_short = kj + (5 * pip_val)
            if c_close > sl_core_short:
                # Sopra la Kijun + 5 pip: Chiude tutto e passa in FLAT
                self.trailing_sl_incr = None
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_above_kj_buffer", "new_direction": "FLAT"})
                
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                # Non esegue return, così può eventualmente valutare subito se ci sono le condizioni per entrare LONG
                
            else:
                # Gestione Stop Loss Incrementi: TK + 5 pip o Trailing SL (il più basso / restrittivo)
                sl_incr_base = tk + (5 * pip_val)
                effective_sl_incr = min(sl_incr_base, self.trailing_sl_incr) if self.trailing_sl_incr is not None else sl_incr_base
                
                if len(self.pm.increments) > 0 and c_close > effective_sl_incr:
                    reason = "close_above_trailing_sl" if (self.trailing_sl_incr is not None and effective_sl_incr == self.trailing_sl_incr) else "close_above_tk_buffer"
                    self.trailing_sl_incr = None
                    chiusure_inc = self.pm.close_all_increments(exec_price)
                    if chiusure_inc:
                        events.extend(chiusure_inc)
                        events.append({"type": "increments_cleared", "reason": reason})
                    self.retracement_start_price = None
                else:
                    # Aggiornamento Trailing SL dinamico a 20 pip da Close (cricchetto che può solo scendere)
                    if len(self.pm.increments) > 0:
                        dist_tk = tk - c_close
                        if dist_tk >= (20 * pip_val):
                            nuovo_sl = c_close + (20 * pip_val)
                            if self.trailing_sl_incr is None:
                                self.trailing_sl_incr = nuovo_sl
                            else:
                                self.trailing_sl_incr = min(self.trailing_sl_incr, nuovo_sl)
                    else:
                        self.trailing_sl_incr = None

            has_cleared_increments_short = any(e.get("type") == "increments_cleared" for e in events)
            if self.current_direction == "SHORT" and not has_cleared_increments_short:
                # --- INGRESSI INCREMENTO SHORT ---
                # Paletto: TK < KJ (o tollerato) e la candela deve aver APERTO SOTTO la TK (close precedente < TK)
                if (tk < kj or abs(tk - kj) <= min_body_price) and closed_candle.open < tk and c_close <= tk:
                    if closed_candle.is_green():
                        if self.retracement_start_price is None:
                            self.retracement_start_price = closed_candle.open
                            
                        distanza_percorsa = closed_candle.high - self.retracement_start_price
                        
                        if distanza_percorsa >= min_body_price:
                            entry_price = exec_price 
                            if self.pm.total_active_size() >= size_max:
                                best = self.pm.force_close_best_increment(entry_price)
                                if best:
                                    events.append({"type": "fifo_close", "pnl": best.pnl, "price": entry_price, "ticket": best.ticket, "size": best.size})
                            pos = self.pm.open_increment(entry_price, size=1, direction="SHORT")
                            events.append({"type": "increment_opened", "price": entry_price, "direction": "SHORT", "position": pos})
                            
                            self.retracement_start_price = None # Resetta il conteggio dopo l'incremento
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
            max_dist = (self.config.get("max_kj_distance") or 50.0) * pip_val
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
        - Core: KJ +- 5 pip
        - Bancomat: per l'incremento più anziano (se attivo)
        - Incrementi base: TK +- 5 pip
        """
        events = []
        if not self.is_running or self.current_direction == "FLAT":
            return events
        if self.current_tk is None or self.current_kj is None or current_price is None:
            return events
            
        tk = self.current_tk
        kj = self.current_kj
        pip_val = self.config.get("pip_value") or 0.0001
        
        if self.current_direction == "LONG":
            # 1. Stop Loss Core: KJ - 5 pip
            sl_core = kj - (5 * pip_val)
            if current_price <= sl_core:
                self.trailing_sl_incr = None
                events.extend(self.pm.close_all_increments(current_price))
                ev = self.pm.close_core(current_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "live_stop_kj", "new_direction": "FLAT", "price": current_price})
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                return events

            # 2. Stop Loss Incrementi: TK - 5 pip o Trailing SL (il più alto / restrittivo)
            sl_incr_base = tk - (5 * pip_val)
            effective_sl_incr = max(sl_incr_base, self.trailing_sl_incr) if self.trailing_sl_incr is not None else sl_incr_base
            if len(self.pm.increments) > 0 and current_price <= effective_sl_incr:
                reason = "live_stop_trailing" if (self.trailing_sl_incr is not None and effective_sl_incr == self.trailing_sl_incr) else "live_stop_tk"
                self.trailing_sl_incr = None
                chiusure_inc = self.pm.close_all_increments(current_price)
                if chiusure_inc:
                    events.extend(chiusure_inc)
                    events.append({"type": "increments_cleared", "reason": reason, "price": current_price})
                self.retracement_start_price = None

        elif self.current_direction == "SHORT":
            # 1. Stop Loss Core: KJ + 5 pip
            sl_core = kj + (5 * pip_val)
            if current_price >= sl_core:
                self.trailing_sl_incr = None
                events.extend(self.pm.close_all_increments(current_price))
                ev = self.pm.close_core(current_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "live_stop_kj", "new_direction": "FLAT", "price": current_price})
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                return events

            # 2. Stop Loss Incrementi: TK + 5 pip o Trailing SL (il più basso / restrittivo)
            sl_incr_base = tk + (5 * pip_val)
            effective_sl_incr = min(sl_incr_base, self.trailing_sl_incr) if self.trailing_sl_incr is not None else sl_incr_base
            if len(self.pm.increments) > 0 and current_price >= effective_sl_incr:
                reason = "live_stop_trailing" if (self.trailing_sl_incr is not None and effective_sl_incr == self.trailing_sl_incr) else "live_stop_tk"
                self.trailing_sl_incr = None
                chiusure_inc = self.pm.close_all_increments(current_price)
                if chiusure_inc:
                    events.extend(chiusure_inc)
                    events.append({"type": "increments_cleared", "reason": reason, "price": current_price})
                self.retracement_start_price = None

        return events
