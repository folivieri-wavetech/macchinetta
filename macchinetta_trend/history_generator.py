import random
import csv
import os

def generate_history(filename="storico_5m.csv", num_candles=300, start_price=4500.0, pip_value=1.0):
    """
    Genera un set di candele realistiche basate su un Random Walk (con un tocco di rumore)
    e lo salva su CSV.
    Per il Gold (1 pip = 1.0), un'escursione a 5 minuti potrebbe essere mediamente di 2-8 pips.
    """
    candles = []
    current_open = start_price
    
    # Parametri per simulare mercato
    # Un trend casuale che dura qualche decina di candele per rendere il grafico più realistico
    trend_bias = 0.0
    
    for i in range(num_candles):
        # Ogni 20 candele cambiamo violentemente il trend
        if i % 20 == 0:
            trend_bias = random.uniform(-3.0, 3.0) * pip_value
            
        # Determiniamo la direzione e la forza della candela
        # Aumentiamo la deviazione standard per far piovere candele da 5-15 punti
        move = random.normalvariate(trend_bias, 8.0 * pip_value)
        
        # Generiamo il Close
        current_close = current_open + move
        
        # Generiamo High e Low (shadows) molto ampie per il Gold
        high_limit = max(current_open, current_close)
        low_limit = min(current_open, current_close)
        
        # Aggiungiamo un'ombra casuale (es. da 2 a 12 pips)
        shadow_up = random.uniform(2.0, 12.0 * pip_value)
        shadow_dw = random.uniform(2.0, 12.0 * pip_value)
        
        current_high = high_limit + shadow_up
        current_low = low_limit - shadow_dw
        
        # Occasionalmente (10% dei casi) creiamo uno "spike" (candela molto volatile)
        if random.random() < 0.10:
            spike = random.uniform(15.0, 40.0) * pip_value
            if random.choice([True, False]):
                current_high += spike
                if random.choice([True, False]): current_close += spike/2
            else:
                current_low -= spike
                if random.choice([True, False]): current_close -= spike/2

        # Aggiungiamo la candela (Numeri Interi per il Gold)
        candles.append({
            "id": i + 1,
            "open": int(round(current_open, 0)),
            "high": int(round(current_high, 0)),
            "low": int(round(current_low, 0)),
            "close": int(round(current_close, 0))
        })
        
        # L'apertura successiva è vicina alla chiusura attuale (magari con mini-gap)
        gap = random.uniform(-1.0, 1.0) * pip_value
        current_open = current_close + gap

    # Salviamo su CSV
    filepath = os.path.join(os.path.dirname(__file__), filename)
    with open(filepath, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["id", "open", "high", "low", "close"])
        writer.writeheader()
        writer.writerows(candles)
        
    return filepath, candles

def load_history(filename="storico_5m.csv"):
    filepath = os.path.join(os.path.dirname(__file__), filename)
    candles = []
    if not os.path.exists(filepath):
        return candles
        
    with open(filepath, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            candles.append({
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"])
            })
    return candles
