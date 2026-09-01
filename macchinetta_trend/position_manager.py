class Position:
    def __init__(self, entry_price, size, position_type="increment", direction="LONG"):
        """
        position_type può essere "core" o "increment"
        direction può essere "LONG" o "SHORT"
        """
        self.entry_price = entry_price
        self.size = size
        self.position_type = position_type
        self.direction = direction
        
        self.is_closed = False
        self.pnl = 0.0
        self.close_price = None
        self.ticket = None
        
    def to_dict(self):
        return {
            "entry": self.entry_price,
            "size": self.size,
            "type": self.position_type,
            "direction": self.direction,
            "ticket": self.ticket
        }

    def close(self, current_price):
        """Chiude forzatamente la posizione al prezzo corrente."""
        if not self.is_closed:
            self.is_closed = True
            self.close_price = current_price
            
            # Calcolo PNL bi-direzionale
            if self.direction == "LONG":
                self.pnl = (self.close_price - self.entry_price) * self.size
            else:
                self.pnl = (self.entry_price - self.close_price) * self.size
                
        return self.pnl

class PositionManager:
    def __init__(self):
        self.core_position = None
        self.increments = [] # Lista di istanze Position
        self.closed_positions = []

    def open_core(self, price, size, direction="LONG"):
        self.core_position = Position(price, size, "core", direction)
        return self.core_position

    def open_increment(self, price, size=1, direction="LONG"):
        pos = Position(price, size, "increment", direction)
        self.increments.append(pos)
        return pos

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
            oldest.close(current_price)
            self.closed_positions.append(oldest)
            return oldest
        return None
        
    def close_all_increments(self, current_price):
        """Chiude tutti gli incrementi aperti."""
        events = []
        for inc in self.increments:
            inc.close(current_price)
            self.closed_positions.append(inc)
            events.append({"type": "increment_closed", "pnl": inc.pnl, "price": current_price, "direction": inc.direction, "ticket": inc.ticket, "size": inc.size})
        self.increments = []
        return events
        
    def close_core(self, current_price):
        """Chiude la posizione Core principale."""
        event = None
        if self.core_position:
            self.core_position.close(current_price)
            self.closed_positions.append(self.core_position)
            event = {"type": "core_closed", "pnl": self.core_position.pnl, "price": current_price, "direction": self.core_position.direction, "ticket": self.core_position.ticket, "size": self.core_position.size}
            self.core_position = None
        return event
