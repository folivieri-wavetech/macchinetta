try:
    from position_manager import PositionManager
except ImportError:
    try:
        from macchinetta_trend.position_manager import PositionManager
    except ImportError:
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
        
    def reset(self):
        """Resetta lo stato della macchinetta."""
        self.is_running = False
        self.pm = PositionManager() # Reset completo della memoria trade
        self.retracement_start_price = None
        self.active_signal = None
        self.signal_candles_elapsed = 0
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
        highest = max(c.high for c in recent_candles)
        lowest = min(c.low for c in recent_candles)
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
            if c_close < kj:
                # Sotto la Kijun: Chiude tutto e passa in FLAT
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_below_kj", "new_direction": "FLAT"})
                
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                # Non esegue return, così può eventualmente valutare subito se ci sono le condizioni per entrare SHORT
                
            elif c_close < tk:
                # Sotto Tenkan: Chiude solo gli incrementi
                chiusure_inc = self.pm.close_all_increments(exec_price)
                if chiusure_inc:
                    events.extend(chiusure_inc)
                    events.append({"type": "increments_cleared", "reason": "close_below_tk"})
                self.retracement_start_price = None

            if self.current_direction == "LONG":
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
                                oldest = self.pm.force_close_oldest_increment(entry_price)
                                if oldest:
                                    events.append({"type": "fifo_close", "pnl": oldest.pnl, "price": entry_price, "ticket": oldest.ticket, "size": oldest.size})
                            pos = self.pm.open_increment(entry_price, size=1, direction="LONG")
                            events.append({"type": "increment_opened", "price": entry_price, "direction": "LONG", "position": pos})
                            
                            self.retracement_start_price = None # Resetta il conteggio dopo l'incremento
                    else:
                        self.retracement_start_price = None # Ritracciamento interrotto da candela verde
                else:
                    self.retracement_start_price = None # Fuori dai paletti

        elif self.current_direction == "SHORT":
            # --- USCITE E REVERSAL SHORT ---
            if c_close > kj:
                # Sopra la Kijun: Chiude tutto e passa in FLAT
                events.extend(self.pm.close_all_increments(exec_price))
                ev = self.pm.close_core(exec_price)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_above_kj", "new_direction": "FLAT"})
                
                self.current_direction = "FLAT"
                self.retracement_start_price = None
                # Non esegue return, così può eventualmente valutare subito se ci sono le condizioni per entrare LONG
                
            elif c_close > tk:
                # Sopra Tenkan: Chiude solo gli incrementi
                chiusure_inc = self.pm.close_all_increments(exec_price)
                if chiusure_inc:
                    events.extend(chiusure_inc)
                    events.append({"type": "increments_cleared", "reason": "close_above_tk"})
                self.retracement_start_price = None

            if self.current_direction == "SHORT":
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
                                oldest = self.pm.force_close_oldest_increment(entry_price)
                                if oldest:
                                    events.append({"type": "fifo_close", "pnl": oldest.pnl, "price": entry_price, "ticket": oldest.ticket, "size": oldest.size})
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

            is_long_cond = c_close > tk and (tk > kj or abs(tk - kj) <= min_body_price)
            is_short_cond = c_close < tk and (tk < kj or abs(tk - kj) <= min_body_price)
            
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
                        reason = "condizioni_long_allineate" if tk > kj else "condizioni_long_tollerate"
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
                        reason = "condizioni_short_allineate" if tk < kj else "condizioni_short_tollerate"
                        events.append({"type": "auto_start", "direction": "SHORT", "price": exec_price, "reason": reason})
                        self.active_signal = None
                        self.signal_candles_elapsed = 0
            
            else:
                # Se nessuna delle due condizioni base è vera, il segnale decade e si resetta tutto
                self.active_signal = None
                self.signal_candles_elapsed = 0

        return events
                

