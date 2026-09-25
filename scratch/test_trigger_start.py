"""
Test di verifica logica Trigger Virtuale a Chiusura Candela (Trend)
"""
import sys
import unittest

def valuta_condizione_trigger(trig_dir, closed_close, trig_px, kj_val):
    if closed_close <= 0 or trig_px <= 0:
        return False
    if trig_dir == "SHORT":
        kj_ok = (kj_val is None or closed_close <= kj_val)
        return (closed_close <= trig_px and kj_ok)
    elif trig_dir == "LONG":
        kj_ok = (kj_val is None or closed_close >= kj_val)
        return (closed_close >= trig_px and kj_ok)
    return False

class TestTriggerTrend(unittest.TestCase):
    def test_short_trigger_attesa(self):
        # CADJPY SHORT: Kijun 108.20, Trigger 108.00
        kj = 108.20
        trig = 108.00
        
        # 1. Candela chiude a 108.05 (non ha rotto il trigger 108.00)
        self.assertFalse(valuta_condizione_trigger("SHORT", 108.05, trig, kj))
        
        # 2. Candela chiude a 108.00 esatto (<= trigger e <= kj)
        self.assertTrue(valuta_condizione_trigger("SHORT", 108.00, trig, kj))
        
        # 3. Candela chiude a 107.90 (sotto trigger e sotto kj)
        self.assertTrue(valuta_condizione_trigger("SHORT", 107.90, trig, kj))

    def test_short_trigger_blocco_kijun(self):
        # Se utente mette trigger sopra Kijun (es. trigger 108.50, KJ 108.20)
        # Se candela chiude a 108.30 (sotto trigger ma sopra Kijun) -> NON deve passare
        kj = 108.20
        trig = 108.50
        self.assertFalse(valuta_condizione_trigger("SHORT", 108.30, trig, kj))
        # Se poi chiude a 108.10 (sotto trigger E sotto Kijun) -> DEVE passare
        self.assertTrue(valuta_condizione_trigger("SHORT", 108.10, trig, kj))

    def test_long_trigger_attesa(self):
        # GBPUSD LONG: Kijun 1.3200, Trigger 1.3250
        kj = 1.3200
        trig = 1.3250
        
        # 1. Candela chiude a 1.3240 (non ha rotto il trigger 1.3250)
        self.assertFalse(valuta_condizione_trigger("LONG", 1.3240, trig, kj))
        
        # 2. Candela chiude a 1.3250 esatto (>= trigger e >= kj)
        self.assertTrue(valuta_condizione_trigger("LONG", 1.3250, trig, kj))
        
        # 3. Candela chiude a 1.3260 (sopra trigger e sopra kj)
        self.assertTrue(valuta_condizione_trigger("LONG", 1.3260, trig, kj))

    def test_long_trigger_blocco_kijun(self):
        # Se Kijun è 1.3260 e Trigger è 1.3240
        # Candela a 1.3245 (sopra trigger ma sotto Kijun) -> NON deve passare
        kj = 1.3260
        trig = 1.3240
        self.assertFalse(valuta_condizione_trigger("LONG", 1.3245, trig, kj))
        # Candela a 1.3265 (sopra trigger e sopra Kijun) -> DEVE passare
        self.assertTrue(valuta_condizione_trigger("LONG", 1.3265, trig, kj))

    def test_gestione_memoria_attivazione_e_cancellazione(self):
        dati = {
            "attivo": False,
            "stato": "FLAT",
            "direzione": "",
            "trigger_start_attivo": False,
            "trigger_start_prezzo": None
        }
        
        # 1. Programmazione Trigger LONG a 1.3250
        dati_armati = {
            **dati,
            "attivo": False,
            "stato": "TRIGGER_ATTESA",
            "direzione": "LONG",
            "trigger_start_attivo": True,
            "trigger_start_prezzo": 1.3250,
            "trigger_start_direzione": "LONG",
            "trigger_start_tf": "HOUR"
        }
        self.assertTrue(dati_armati["trigger_start_attivo"])
        self.assertEqual(dati_armati["stato"], "TRIGGER_ATTESA")
        self.assertFalse(dati_armati["attivo"])
        
        # 2. Annullamento manuale
        dati_annullati = {
            **dati_armati,
            "trigger_start_attivo": False,
            "trigger_start_prezzo": None,
            "trigger_start_direzione": None,
            "trigger_start_tf": None,
            "stato": "FLAT",
            "direzione": ""
        }
        self.assertFalse(dati_annullati["trigger_start_attivo"])
        self.assertEqual(dati_annullati["stato"], "FLAT")

if __name__ == "__main__":
    unittest.main()
