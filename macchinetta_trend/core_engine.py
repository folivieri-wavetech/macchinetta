from position_manager import PositionManager

class CoreEngine:
    def __init__(self, config):
        self.config = config
        self.pm = PositionManager()
        
        # Stato del motore
        self.is_running = False
        self.start_price = None
        
        # Livelli OCO iniziali
        self.buy_stop_level = None
        self.sell_stop_level = None
        
        # Tracking per logica Uncino
        self.absolute_high = None
        self.current_drawdown = 0.0 # Quanti punti è sceso dal massimo
        self.is_in_correction = False # True se è sceso di 'step_correzione'
        self.correction_low = None # Il minimo toccato durante la correzione

    def start(self, current_price):
        """Inizializza la macchinetta piazzando gli ordini pendenti virtuali."""
        self.is_running = True
        self.start_price = current_price
        griglia = self.config.get("griglia")
        
        self.buy_stop_level = current_price + griglia
        self.sell_stop_level = current_price - griglia
        
        print(f"START: Prezzo={current_price} | BuyStop={self.buy_stop_level} | SellStop={self.sell_stop_level}")
        
    def reset(self):
        """Resetta lo stato della macchinetta al termine della sessione."""
        self.is_running = False
        self.start_price = None
        self.buy_stop_level = None
        self.sell_stop_level = None
        self.absolute_high = None
        self.is_in_correction = False
        self.correction_low = None
        self.pm = PositionManager() # Reset completo della memoria trade
        
    def on_tick(self, current_price):
        """Metodo principale da chiamare ad ogni aggiornamento di prezzo."""
        if not self.is_running:
            return [] # Ritorna lista eventi
            
        events = []
        
        # 1. Fase Innesco (Se non abbiamo ancora la Core)
        if self.pm.core_position is None and self.absolute_high is None:
            # Check Buy Stop
            if current_price >= self.buy_stop_level:
                # Eseguito Long OCO
                self.pm.open_core(self.buy_stop_level, self.config.get("size_i"))
                self.absolute_high = self.buy_stop_level
                self.sell_stop_level = None # Cancella ordine opposto
                events.append({"type": "core_opened", "price": self.buy_stop_level})
                
            # Logica speculare per lo Short non è implementata in questo snippet 
            # (assumiamo che il bot sia long-only come da esempio, ma si può specchiare)


        # 2. Aggiornamento Posizioni Esistenti (TS e TP)
        chiusure = self.pm.update_all_positions(current_price, self.config)
        events.extend(chiusure)
        
        # Check se la Core è stata chiusa (Fine Trend)
        if self.pm.core_position is None and self.absolute_high is not None:
            # La Core è caduta! Breakout al ribasso confermato dal TS
            # Chiudiamo tutto e resettiamo
            if self.pm.increments:
                for inc in self.pm.increments:
                    inc.is_closed = True
                    inc.close_price = current_price
                    inc.pnl = (inc.close_price - inc.entry_price) * inc.size
                    self.pm.closed_positions.append(inc)
                    events.append({"type": "increment_force_closed_on_end", "pnl": inc.pnl})
                self.pm.increments = []
            
            events.append({"type": "session_ended", "reason": "core_stopped"})
            self.reset()
            return events

        # 3. Aggiornamento Massimo e Logica Uncino (Se siamo a mercato)
        if self.absolute_high is not None:
            if current_price > self.absolute_high:
                self.absolute_high = current_price
                self.is_in_correction = False # Nuovo massimo resetta le correzioni
                self.correction_low = None
                
            else:
                # Siamo sotto il massimo assoluto, misuriamo il drawdown
                self.current_drawdown = self.absolute_high - current_price
                step = self.config.get("step_correzione")
                
                if self.current_drawdown >= step:
                    # Si è formata la "Candela Rossa" virtuale (il drop è confermato)
                    self.is_in_correction = True
                    
                    # Tracciamo il minimo di questa correzione
                    if self.correction_low is None or current_price < self.correction_low:
                        self.correction_low = current_price
                
                # Se siamo in correzione, cerchiamo l'Uncino
                if self.is_in_correction and self.correction_low is not None:
                    rimbalzo = self.config.get("rimbalzo_uncino")
                    if current_price >= self.correction_low + rimbalzo:
                        # UNCINO CONFERMATO! Il prezzo è sceso di >20pt e ha rimbalzato di >5pt
                        # Proviamo ad aprire un incremento
                        
                        # Controllo Size_F (FIFO)
                        if self.pm.total_active_size() >= self.config.get("size_f"):
                            oldest = self.pm.force_close_oldest_increment(current_price)
                            if oldest:
                                events.append({"type": "fifo_close", "pnl": oldest.pnl})
                                
                        # Apriamo il nuovo incremento
                        self.pm.open_increment(current_price, size=1)
                        events.append({"type": "increment_opened", "price": current_price})
                        
                        # Resettiamo lo stato della correzione in attesa del prossimo setup
                        self.is_in_correction = False
                        self.correction_low = None

        return events
