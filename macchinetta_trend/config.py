import json
import os

class Config:
    def __init__(self, filename="trend_config.json"):
        self.filename = filename
        # Valori di default definiti nel piano
        self.params = {
            "size_i": 3,
            "size_f": 10,
            "griglia": 20,
            
            # Motore di Chiusura
            "core_ts": 100,
            "inc_ts": 40,
            "inc_tp": 20,
            
            # Logica ad uncino per gli incrementi (Opzione B)
            "step_correzione": 20, # Il drop per formare il corpo rosso virtuale
            "rimbalzo_uncino": 5   # L'uncino per confermare l'inversione
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
