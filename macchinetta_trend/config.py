import json
import os

class Config:
    def __init__(self, filename="trend_config.json"):
        self.filename = filename
        
        # Valori di default per la logica V2 a Candele e Donchian
        self.params = {
            "size_i": 3,
            "size_f": 10,
            
            # Parametri Strumento (Simulazione Gold: 1 punto = 1 pip = 1€)
            "pip_value": 1.0,
            
            # Parametri Candele e Indicatori
            "min_body": 5.0,        # Pips minimi per considerare valida una candela (rossa o verde)
            "tk_periods": 21,       # Periodi Tenkan-sen (Donchian Veloce)
            "kj_periods": 55,       # Periodi Kijun-sen (Donchian Lento)
            
            # Risk Management
            "max_kj_distance": 10.0, # Distanza massima consentita tra prezzo e KJ per l'ingresso Core
            "max_entry_delay": 3,    # Candele massime di ritardo per aspettare un ritracciamento valido
            
            
            # Costanti di backtest
            "start_price": 158.00   # Prezzo di partenza generico per il simulatore
        }
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    loaded = json.load(f)
                    self.params.update(loaded)
            except Exception as e:
                print(f"Errore caricamento config: {e}")

    def save(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.params, f, indent=4)
        except Exception as e:
            print(f"Errore salvataggio config: {e}")

    def get(self, key):
        return self.params.get(key)

    def set(self, key, value):
        self.params[key] = value
        self.save()
