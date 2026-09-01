from position_manager import PositionManager

class Candle:
    def __init__(self, open_p, high_p, low_p, close_p):
        self.open = open_p
        self.high = high_p
        self.low = low_p
        self.close = close_p
        
    def is_red(self):
        return self.close < self.open
        
    def is_green(self):
        return self.close > self.open
        
    def body_size(self):
        return abs(self.open - self.close)


class CoreEngine:
    def __init__(self, config):
        self.config = config
        self.pm = PositionManager()
        
        # Stato del motore
        self.is_running = False
        self.current_direction = None # "LONG" o "SHORT"
        self.candles = []  # Storico delle candele
        
        # Stato Indicatori calcolati all'ultima candela chiusa
        self.current_tk = None
        self.current_kj = None
        
    def reset(self):
        """Resetta lo stato della macchinetta."""
        self.is_running = False
        self.pm = PositionManager() # Reset completo della memoria trade
        # NOTA: le candele (lo storico) NON vengono resettate perché servono agli indicatori!

    def seed_history(self, candles_list):
        """Popola lo storico iniziale prima dell'avvio."""
        self.candles = candles_list

    def start(self, current_price, direction="LONG"):
        """Inizializza la macchinetta entrando a mercato con la Core nella direzione specificata."""
        self.is_running = True
        self.current_direction = direction
        self.pm.open_core(current_price, self.config.get("size_i"), direction)
        print(f"START: Eseguita Core a Mercato {direction} a Prezzo={current_price}")

    def _calculate_donchian(self, periods):
        """Calcola la mediana (Max+Min)/2 degli ultimi N periodi (candele)."""
        if len(self.candles) < periods:
            return None
        recent_candles = self.candles[-periods:]
        highest = max(c.high for c in recent_candles)
        lowest = min(c.low for c in recent_candles)
        return (highest + lowest) / 2.0

    def on_candle_close(self, closed_candle):
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
        tk = self.current_tk
        kj = self.current_kj
        pip_val = self.config.get("pip_value")
        min_body_price = self.config.get("min_body") * pip_val
        
        # ==========================================
        # LOGICA BI-DIREZIONALE (STOP & REVERSE)
        # ==========================================
        
        if self.current_direction == "LONG":
            # --- USCITE E REVERSAL LONG ---
            if c_close < kj:
                # Sotto la Kijun: Chiude tutto e REVERSA in SHORT
                events.extend(self.pm.close_all_increments(c_close))
                ev = self.pm.close_core(c_close)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_below_kj", "new_direction": "SHORT"})
                
                # Apre SHORT
                self.start(c_close, "SHORT")
                return events
                
            elif c_close < tk:
                # Sotto Tenkan: Chiude solo gli incrementi
                chiusure_inc = self.pm.close_all_increments(c_close)
                if chiusure_inc:
                    events.extend(chiusure_inc)
                    events.append({"type": "increments_cleared", "reason": "close_below_tk"})

            # --- INGRESSI LONG ---
            # Paletto: TK > KJ e la candela deve aver APERTO SOPRA la TK (close precedente > TK)
            if tk > kj and closed_candle.open > tk and c_close >= tk:
                if closed_candle.is_red() and closed_candle.body_size() >= min_body_price:
                    entry_price = c_close 
                    if self.pm.total_active_size() >= self.config.get("size_f"):
                        oldest = self.pm.force_close_oldest_increment(entry_price)
                        if oldest:
                            events.append({"type": "fifo_close", "pnl": oldest.pnl, "price": entry_price})
                    self.pm.open_increment(entry_price, size=1, direction="LONG")
                    events.append({"type": "increment_opened", "price": entry_price, "direction": "LONG"})

        elif self.current_direction == "SHORT":
            # --- USCITE E REVERSAL SHORT ---
            if c_close > kj:
                # Sopra la Kijun: Chiude tutto e REVERSA in LONG
                events.extend(self.pm.close_all_increments(c_close))
                ev = self.pm.close_core(c_close)
                if ev: events.append(ev)
                events.append({"type": "reversal", "reason": "close_above_kj", "new_direction": "LONG"})
                
                # Apre LONG
                self.start(c_close, "LONG")
                return events
                
            elif c_close > tk:
                # Sopra Tenkan: Chiude solo gli incrementi
                chiusure_inc = self.pm.close_all_increments(c_close)
                if chiusure_inc:
                    events.extend(chiusure_inc)
                    events.append({"type": "increments_cleared", "reason": "close_above_tk"})

            # --- INGRESSI SHORT ---
            # Paletto: TK < KJ e la candela deve aver APERTO SOTTO la TK (close precedente < TK)
            if tk < kj and closed_candle.open < tk and c_close <= tk:
                if closed_candle.is_green() and closed_candle.body_size() >= min_body_price:
                    entry_price = c_close 
                    if self.pm.total_active_size() >= self.config.get("size_f"):
                        oldest = self.pm.force_close_oldest_increment(entry_price)
                        if oldest:
                            events.append({"type": "fifo_close", "pnl": oldest.pnl, "price": entry_price})
                    self.pm.open_increment(entry_price, size=1, direction="SHORT")
                    events.append({"type": "increment_opened", "price": entry_price, "direction": "SHORT"})

        return events
