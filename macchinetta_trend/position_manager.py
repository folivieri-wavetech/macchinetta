class Position:
    def __init__(self, entry_price, size, position_type="increment"):
        """
        position_type può essere "core" o "increment"
        """
        self.entry_price = entry_price
        self.size = size
        self.position_type = position_type
        
        self.trailing_stop_level = None
        self.take_profit_level = None
        self.is_closed = False
        self.pnl = 0.0
        self.close_price = None
        
        # Registra il massimo raggiunto dal mercato mentre questa posizione era viva (utile per il TS)
        self.highest_price_seen = entry_price

    def update_highest(self, current_price):
        if current_price > self.highest_price_seen:
            self.highest_price_seen = current_price

    def evaluate_closure(self, current_price, ts_distance, ts_step, tp_distance=None):
        """
        Ritorna la reason ("ts_hit" o "tp_hit") se la posizione deve essere chiusa.
        """
        # 1. Inizializzazione TS iniziale (Stop Loss Hard) se non esiste
        if self.trailing_stop_level is None:
            self.trailing_stop_level = self.entry_price - ts_distance
            
        self.update_highest(current_price)
        
        # 2. Calcolo potenziale nuovo livello di Trailing Stop
        potential_ts = self.highest_price_seen - ts_distance
        
        # 3. Avanzamento a Gradini (Passo): Il TS avanza solo se la differenza è >= al passo
        if potential_ts >= self.trailing_stop_level + ts_step:
            steps_to_move = int((potential_ts - self.trailing_stop_level) / ts_step)
            self.trailing_stop_level += steps_to_move * ts_step
        
        # Check Trailing Stop (Se il prezzo scende sotto il livello del TS)
        if current_price <= self.trailing_stop_level:
            self.is_closed = True
            self.close_price = current_price
            self.pnl = (self.close_price - self.entry_price) * self.size
            return "ts_hit"
            
        # Check Take Profit
        if tp_distance is not None and tp_distance > 0:
            self.take_profit_level = self.entry_price + tp_distance
            if current_price >= self.take_profit_level:
                self.is_closed = True
                self.close_price = current_price
                self.pnl = (self.close_price - self.entry_price) * self.size
                return "tp_hit"
                
        return None

class PositionManager:
    def __init__(self):
        self.core_position = None
        self.increments = [] # Lista di istanze Position
        self.closed_positions = []

    def open_core(self, price, size):
        self.core_position = Position(price, size, "core")

    def open_increment(self, price, size=1):
        pos = Position(price, size, "increment")
        self.increments.append(pos)

    def total_active_size(self):
        core_size = self.core_position.size if self.core_position else 0
        inc_size = sum(p.size for p in self.increments)
        return core_size + inc_size

    def force_close_oldest_increment(self, current_price):
        """
        Logica FIFO: chiude l'incremento più vecchio se raggiungiamo Size_F.
        Essendo il più vecchio in un trend a salire, è quello al prezzo più basso.
        """
        if self.increments:
            oldest = self.increments.pop(0)
            oldest.is_closed = True
            oldest.close_price = current_price
            oldest.pnl = (oldest.close_price - oldest.entry_price) * oldest.size
            self.closed_positions.append(oldest)
            return oldest
        return None

    def update_all_positions(self, current_price, config):
        """
        Controlla TS e TP per tutte le posizioni attive.
        """
        events = []
        
        # 1. Update Core
        if self.core_position:
            # Il TS è agganciato alla Griglia: distanza = griglia, passo = griglia / 4
            ts_dist = config.get("griglia")
            ts_step = max(1, ts_dist / 4.0) 
            reason = self.core_position.evaluate_closure(current_price, ts_dist, ts_step, None) # Core non ha TP
            if reason:
                self.closed_positions.append(self.core_position)
                events.append({"type": "core_closed", "reason": reason, "pnl": self.core_position.pnl})
                self.core_position = None
                
        # 2. Update Incrementi
        active_increments = []
        for inc in self.increments:
            # Anche gli incrementi usano la logica Griglia per il TS
            ts_dist = config.get("griglia")
            ts_step = max(1, ts_dist / 4.0)
            reason = inc.evaluate_closure(current_price, ts_dist, ts_step, config.get("inc_tp"))
            if reason:
                self.closed_positions.append(inc)
                events.append({"type": "increment_closed", "reason": reason, "pnl": inc.pnl})
            else:
                active_increments.append(inc)
                
        self.increments = active_increments
        return events
